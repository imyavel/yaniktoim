"""Batch transform runner for yaniktoim — простая последовательная обёртка
над `src/3_transform.py`. По примеру ZoharTGBatch (только без чанкования и
без Telegram). Прогоняет всю очередь нетрансформированных статей пачками
по BATCH_SIZE; после успешного батча — render + 5_index + git push (опц).
При «hit your limit» от Claude — парсит время сброса и спит до него.

Usage (из корня yaniktoim/):
  python batch_runner/run_batch.py                       # все нетранформированные
  python batch_runner/run_batch.py --section best        # только из раздела
  python batch_runner/run_batch.py --limit 10            # сколько статей суммарно
  python batch_runner/run_batch.py --dry-run             # показать что будет
  python batch_runner/run_batch.py --no-push             # не пушить в gh
  python batch_runner/run_batch.py --batch-size 5        # размер пачки (def: 5)

Прерывание Ctrl+C — корректно сохраняет state. Можно запустить снова —
продолжит с того места: «уже трансформировано» определяется по наличию
файла `json/<NNN>.json` (то есть state.json — это лог, а не источник
истины).
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

# NOTE: stdout/stderr UTF-8 is set by the GUI launcher via PYTHONIOENCODING.
# When run from a plain console, Windows cp1251 may mangle Cyrillic — that's
# acceptable trade-off; the alternative (reassigning sys.stdout here) breaks
# the GUI subprocess pipe by detaching the binary buffer the parent reads.

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
JSON_DIR = ROOT / "json"
SITE = ROOT / "docs"
MANIFEST = ROOT / "manifest.json"

HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
LOG = HERE / "batch.log"
LOCK = HERE / "run.lock"

DEFAULT_BATCH_SIZE = 5
GIT_USER_NAME = "imyavel"
GIT_USER_EMAIL = "imyavel@gmail.com"

# Patterns. HIT_LIMIT_RESET_RX — anchored to "hit your limit" so a stray
# "resets" elsewhere in the log can't trigger sleep. re.DOTALL because the
# reset clause may be on a separate stderr line. Mirrors ZoharTGBatch/
# orchestrator.py.
HIT_LIMIT_RX = re.compile(r"hit your limit", re.IGNORECASE)
HIT_LIMIT_RESET_RX = re.compile(
    r"hit your limit.*?resets?\s*(?:at\s*)?"
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?"
    r"\s*(?:\(([^)]+)\))?",
    re.IGNORECASE | re.DOTALL,
)
HIT_LIMIT_IN_RX = re.compile(
    r"hit your limit.*?in\s+(\d+)\s+hour", re.IGNORECASE | re.DOTALL,
)
# Hard authentication / quota failures — abort, don't retry.
FATAL_RX = re.compile(
    r"\b(401|403|unauthorized|forbidden|invalid\s+api\s+key|"
    r"authentication\s+failed|api\s+key\s+(?:not\s+found|missing|invalid)|"
    r"insufficient\s+credit|quota\s+exhausted|account\s+(?:suspended|disabled))\b",
    re.IGNORECASE,
)

# Graceful shutdown flag — set by SIGBREAK/SIGINT handler, checked between
# batches and during the hit-limit sleep loop.
_shutdown_requested = False


# ---------- io helpers ----------

_logger: logging.Logger | None = None


def _init_logger() -> logging.Logger:
    """Rotating per-process logger. Each run appends to batch.log; size-based
    rotation keeps the disk footprint bounded (10MB × 5 backups)."""
    lg = logging.getLogger("yaniktoim.batch_runner")
    lg.setLevel(logging.INFO)
    lg.propagate = False
    if lg.handlers:
        return lg
    fmt = logging.Formatter("%(asctime)s %(message)s",
                            datefmt="%Y-%m-%dT%H:%M:%S")
    fh = RotatingFileHandler(
        LOG, maxBytes=10_000_000, backupCount=5, encoding="utf-8",
    )
    fh.setFormatter(fmt)
    lg.addHandler(fh)
    return lg


def log(msg: str) -> None:
    global _logger
    if _logger is None:
        _logger = _init_logger()
    ts = dt.datetime.now().isoformat(timespec="seconds")
    print(f"{ts} {msg}", flush=True)
    _logger.info(msg)


# ---------- single-instance lock ----------

def _pid_alive(pid: int) -> bool:
    """Cross-platform live-PID probe. On Windows uses tasklist (cheap and
    avoids ctypes); on POSIX uses os.kill(0)."""
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, check=False,
            ).stdout
            return str(pid) in out
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def acquire_lock() -> bool:
    """Atomic single-instance lock. Returns True on success.
    Stale lock (PID dead) is auto-cleaned. Live lock prints owner PID
    and returns False."""
    try:
        # O_EXCL — atomic on Windows and POSIX. No race with other launchers.
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        return True
    except FileExistsError:
        pass
    # Lock exists — check if owner is alive.
    try:
        prev = LOCK.read_text(encoding="ascii").strip()
        pid = int(prev) if prev.isdigit() else 0
    except Exception:
        pid = 0
    if pid and _pid_alive(pid):
        print(f"ERROR: batch_runner already running (PID {pid}). "
              f"Lock: {LOCK}", file=sys.stderr, flush=True)
        return False
    # Stale — replace.
    try:
        LOCK.unlink()
    except FileNotFoundError:
        pass
    try:
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        return True
    except FileExistsError:
        print("ERROR: lock race — another batch_runner won the start.",
              file=sys.stderr, flush=True)
        return False


def release_lock() -> None:
    try:
        if LOCK.exists():
            prev = LOCK.read_text(encoding="ascii").strip()
            if prev == str(os.getpid()):
                LOCK.unlink()
    except Exception:
        pass


# ---------- signal handling ----------

def _signal_handler(signum, _frame) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    try:
        name = signal.Signals(signum).name
    except Exception:
        name = str(signum)
    # Direct print — log() may double-write under signal context.
    print(f"\n[run_batch] got {name} — will stop after current batch",
          flush=True)


def _install_signal_handlers() -> None:
    sigs = [signal.SIGINT]
    if hasattr(signal, "SIGBREAK"):  # Windows
        sigs.append(signal.SIGBREAK)
    if hasattr(signal, "SIGTERM") and os.name != "nt":
        sigs.append(signal.SIGTERM)
    for s in sigs:
        try:
            signal.signal(s, _signal_handler)
        except (ValueError, OSError):
            pass


def _interruptible_sleep(seconds: float) -> None:
    """Sleep that wakes on shutdown request. 1-second granularity."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if _shutdown_requested:
            return
        time.sleep(min(1.0, end - time.monotonic()))


# ---------- json validation ----------

def is_valid_article_json(path: Path) -> bool:
    """A transformed article must be parseable JSON with at minimum a
    non-empty `title` and a `sections` list. Catches partially-written
    or empty files left by an aborted 3_transform.py run."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    title = data.get("title")
    sections = data.get("sections")
    if not (isinstance(title, str) and title.strip()):
        return False
    if not isinstance(sections, list):
        return False
    return True


def load_state() -> dict:
    """Load state.json. If the file is missing OR was truncated mid-write
    (Ctrl-Break during save_state), back it up and start fresh — losing
    the bookkeeping is far better than crashing on next launch."""
    fresh = {"done": [], "failed": [],
             "started_at": dt.datetime.now().isoformat(timespec="seconds")}
    if not STATE.exists():
        return fresh
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        bak = STATE.with_suffix(
            f".broken-{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}.json")
        try:
            shutil.move(str(STATE), str(bak))
            log(f"WARN: state.json corrupt ({e!r}) — backed up to {bak.name}")
        except Exception:
            pass
        return fresh


def save_state(s: dict) -> None:
    """Atomic write — tmp file in same dir + os.replace. Ctrl-Break during
    write leaves either the old state.json or the new one, never a mix."""
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(STATE))


# ---------- queue ----------

SECTION_ORDER = ["best", "dreamon", "cyberson", "dabudet",
                 "confront", "shoshana", "other"]


def pending_articles(manifest: list[dict], section: str | None,
                     limit: int | None) -> list[str]:
    """Очередь = author-defined order внутри каждого раздела,
    разделы в SECTION_ORDER. Если --section задан, обходим только его."""
    sections = [section] if section else SECTION_ORDER
    out: list[str] = []
    for sec in sections:
        rows = [r for r in manifest if r["section"] == sec]
        rows.sort(key=lambda x: x.get("section_order", 9999))
        for r in rows:
            n = r["number"]
            if (JSON_DIR / f"{n}.json").exists():
                continue
            out.append(n)
            if limit and len(out) >= limit:
                return out
    return out


def pick_by_numbers(manifest: list[dict], raw: str) -> list[str]:
    """Resolve a user-supplied --numbers string (e.g. '283' or '283,310,367')
    into a queue of canonical 3-digit IDs. Already-transformed numbers
    drop out with a log line (3_transform.py refuses to overwrite without
    --force). Unknown numbers go straight to a failed-list — we log and
    skip them, the caller can decide to abort or continue."""
    known = {r["number"] for r in manifest}
    queue: list[str] = []
    for token in raw.split(","):
        t = token.strip()
        if not t:
            continue
        if not t.isdigit():
            log(f"WARN: --numbers got non-digit token '{t}', skipping")
            continue
        n = t.zfill(3)
        if n not in known:
            log(f"WARN: --numbers {n} — not in manifest.json, skipping")
            continue
        if (JSON_DIR / f"{n}.json").exists():
            log(f"NOTE: --numbers {n} — json/{n}.json уже есть, пропускаю "
                f"(удалите файл, чтобы пересобрать)")
            continue
        queue.append(n)
    return queue


def _tz_offset(tz_str: str | None) -> dt.timedelta | None:
    """Recognize the few timezone tags claude actually prints. Anything else
    (Europe/Moscow, America/Los_Angeles via tzdata) — let the caller fall
    back to local-time interpretation."""
    if not tz_str:
        return None
    t = tz_str.strip().upper()
    table = {
        "UTC": dt.timedelta(0),
        "GMT": dt.timedelta(0),
        "PST": dt.timedelta(hours=-8),
        "PDT": dt.timedelta(hours=-7),
        "EST": dt.timedelta(hours=-5),
        "EDT": dt.timedelta(hours=-4),
    }
    return table.get(t)


def parse_reset(text: str) -> dt.datetime | None:
    """Return the wall-clock local datetime when claude's quota resets.
    Returns None if no reset clause is found. Two formats handled:
    'resets at 5pm (UTC)' (with optional TZ tag) and 'resets in 3 hours'."""
    m_in = HIT_LIMIT_IN_RX.search(text)
    if m_in:
        hours = int(m_in.group(1))
        return dt.datetime.now() + dt.timedelta(hours=hours)

    m = HIT_LIMIT_RESET_RX.search(text)
    if not m:
        return None
    h = int(m.group(1))
    mn = int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower()
    tz_str = m.group(4)
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0

    tz_off = _tz_offset(tz_str)
    if tz_off is not None:
        # Build the reset moment in the message's TZ, then convert to local.
        now_utc = dt.datetime.now(dt.timezone.utc)
        reset_in_tz = dt.datetime.now(dt.timezone(tz_off)).replace(
            hour=h, minute=mn, second=0, microsecond=0,
        )
        if reset_in_tz <= dt.datetime.now(dt.timezone(tz_off)):
            reset_in_tz += dt.timedelta(days=1)
        return reset_in_tz.astimezone().replace(tzinfo=None)

    # No TZ tag (or unrecognized) — assume local time.
    now = dt.datetime.now()
    reset = now.replace(hour=h, minute=mn, second=0, microsecond=0)
    if reset <= now:
        reset += dt.timedelta(days=1)
    return reset


# ---------- subprocess steps ----------

def run_batch(numbers: list[str]) -> tuple[bool, str]:
    """Transform a batch. Returns (success, combined_output).

    Hard timeout — claude.exe pulse is ~3-7 min/article + room for retries;
    600s per article should comfortably cover one hung call without freezing
    the runner forever. On failure, the captured stdout/stderr is dumped to
    `_logs/transform_<NNN>.subproc.txt` so the operator can diagnose."""
    cmd = [sys.executable, str(SRC / "3_transform.py")] + numbers
    log(f"TRANSFORM start: {' '.join(numbers)}")
    timeout_s = 600 * max(1, len(numbers))
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + "\n" + (e.stderr or "") if hasattr(e, "stdout") else ""
        log(f"TRANSFORM TIMEOUT after {timeout_s}s — assume claude.exe hung")
        _dump_subproc(numbers, out, f"timeout after {timeout_s}s")
        return False, out + f"\n[run_batch] timeout after {timeout_s}s\n"
    out = (proc.stdout or "") + "\n--- STDERR ---\n" + (proc.stderr or "")
    log(f"TRANSFORM exit={proc.returncode}")
    if proc.returncode != 0:
        _dump_subproc(numbers, out, f"exit={proc.returncode}")
    return proc.returncode == 0, out


def _dump_subproc(numbers: list[str], output: str, header: str) -> None:
    """Persist captured subprocess output so it can be inspected after a
    failed batch. Writes to _logs/transform_<first>_<last>.subproc.txt
    (single number → just _<N>.subproc.txt). Logs the path."""
    logs_dir = ROOT / "_logs"
    logs_dir.mkdir(exist_ok=True)
    tag = numbers[0] if len(numbers) == 1 else f"{numbers[0]}_{numbers[-1]}"
    path = logs_dir / f"transform_{tag}.subproc.txt"
    try:
        path.write_text(
            f"=== {header} === {dt.datetime.now().isoformat(timespec='seconds')}\n"
            f"=== numbers: {' '.join(numbers)} ===\n\n{output}",
            encoding="utf-8")
        log(f"  → subproc output: {path}")
    except Exception as e:
        log(f"  → failed to write subproc dump: {e!r}")


def run_render(numbers: list[str]) -> bool:
    """Returns True iff the renderer exited 0. Caller must skip push on False."""
    if not numbers:
        return True
    # Render via the single canonical renderer (docs/editor/render.js) through
    # the Node build. (Python src/4_render.py is deprecated — see its header.)
    cmd = ["node", str(SRC.parent / "tools" / "build.mjs")] + numbers
    log(f"RENDER {' '.join(numbers)}")
    rc = subprocess.run(cmd, check=False).returncode
    if rc != 0:
        log(f"RENDER FAILED rc={rc}")
        return False
    return True


def rebuild_indices() -> bool:
    log("INDEX rebuild")
    rc = subprocess.run(
        [sys.executable, str(SRC / "5_index.py")], check=False,
    ).returncode
    if rc != 0:
        log(f"INDEX FAILED rc={rc}")
        return False
    return True


def git_pull() -> None:
    """Rebase on origin/main before building so we see edits made via the
    in-page editor (which commits zml+html through the GitHub API). The batch
    only adds NEW articles, so conflicts are rare; if rebase fails we abort it
    and let the operator resolve manually rather than push a divergent state."""
    log("GIT pull --rebase")
    rc = subprocess.run(
        ["git", "-C", str(ROOT), "pull", "--rebase", "origin", "main"],
        check=False,
    ).returncode
    if rc != 0:
        log(f"GIT pull --rebase rc={rc} (likely no upstream yet or conflict)")
        subprocess.run(["git", "-C", str(ROOT), "rebase", "--abort"], check=False)


def git_push(message: str) -> None:
    # Single-repo model (§0): commit the WHOLE repo (zml/ + docs/) from ROOT so
    # source and generated html land in one logical commit. .gitignore keeps
    # raw/_backups/sqlite out of the public repo.
    log(f"GIT push: {message}")
    subprocess.run(["git", "-C", str(ROOT), "add", "-A"], check=False)
    rc = subprocess.run(
        ["git", "-C", str(ROOT),
         "-c", f"user.name={GIT_USER_NAME}",
         "-c", f"user.email={GIT_USER_EMAIL}",
         "commit", "-m", message],
        check=False,
    ).returncode
    if rc == 0:
        subprocess.run(["git", "-C", str(ROOT), "push", "origin", "main"], check=False)
    else:
        log("GIT nothing to commit (or commit failed)")


# ---------- main loop ----------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--section", help="ограничить разделом (best/dreamon/cyberson/...)")
    ap.add_argument("--limit", type=int, help="макс число статей в этом запуске")
    ap.add_argument("--numbers", help="ровно эти номера через запятую (напр. 283 "
                                      "или 283,310,367) — игнорирует --section/--limit")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                    help=f"размер пачки (default: {DEFAULT_BATCH_SIZE})")
    ap.add_argument("--dry-run", action="store_true", help="только показать очередь")
    ap.add_argument("--no-push", action="store_true", help="не делать git push")
    args = ap.parse_args()

    if not acquire_lock():
        return 3
    _install_signal_handlers()
    try:
        return _run(args)
    finally:
        release_lock()


def _run(args: argparse.Namespace) -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.numbers:
        if args.section or args.limit:
            log("NOTE: --numbers overrides --section/--limit")
        pending = pick_by_numbers(manifest, args.numbers)
        mode_desc = f"numbers={args.numbers}"
    else:
        pending = pending_articles(manifest, args.section, args.limit)
        mode_desc = f"section={args.section or 'any'}"
    log(f"START · pid={os.getpid()} · pending={len(pending)} · "
        f"batch_size={args.batch_size} · {mode_desc}")

    if not pending:
        log("Nothing to do.")
        return 0

    if args.dry_run:
        log(f"DRY RUN: {pending}")
        return 0

    # Sync with origin before building so we incorporate edits made via the
    # in-page editor (which commits straight to GitHub). Skipped with --no-push
    # (offline/local-only run). No-op pre-flip when there is no upstream yet.
    if not args.no_push:
        git_pull()

    state = load_state()
    i = 0
    while i < len(pending):
        if _shutdown_requested:
            log("SHUTDOWN requested — stopping before next batch")
            break

        batch = pending[i:i + args.batch_size]
        ok, out = run_batch(batch)

        # 1. Hard auth/quota failure — abort.
        m = FATAL_RX.search(out)
        if m:
            log(f"FATAL: {m.group(0)} — abort")
            return 2

        # 2. Hit limit — sleep until reset, retry SAME batch.
        if HIT_LIMIT_RX.search(out):
            reset = parse_reset(out)
            if reset:
                wait = (reset - dt.datetime.now()).total_seconds() + 60
                log(f"HIT LIMIT · sleep {int(wait)}s until "
                    f"{reset.isoformat(timespec='minutes')}")
                _interruptible_sleep(max(60.0, wait))
            else:
                log("HIT LIMIT · no reset time parsed, sleep 5h")
                _interruptible_sleep(5 * 3600)
            if _shutdown_requested:
                log("SHUTDOWN during hit-limit sleep — stopping")
                break
            continue  # retry the same i

        # 3. Determine which articles actually landed (file on disk
        #    AND content passes minimum schema check).
        done_now = []
        invalid_now = []
        for n in batch:
            p = JSON_DIR / f"{n}.json"
            if not p.exists():
                continue
            if not is_valid_article_json(p):
                invalid_now.append(n)
                continue
            if n not in state["done"]:
                done_now.append(n)
        failed_now = [n for n in batch if n not in done_now]
        state["done"].extend(done_now)
        for n in failed_now:
            if n not in state["failed"]:
                state["failed"].append(n)
        save_state(state)

        if invalid_now:
            log(f"INVALID JSON (file exists but schema fails): {invalid_now}")

        if done_now:
            render_ok = run_render(done_now)
            index_ok = rebuild_indices() if render_ok else False
            if render_ok and index_ok:
                if not args.no_push:
                    git_push(f"batch: +{len(done_now)} ({done_now[0]}..{done_now[-1]})")
            else:
                log("SKIP push — render or index failed")

        if failed_now:
            log(f"FAILED in batch (no/invalid JSON): {failed_now}")
            for n in failed_now:
                diff = ROOT / "_logs" / f"transform_{n}.diff.txt"
                if diff.exists():
                    log(f"  → {n}: see {diff}")

        i += args.batch_size

    log(f"DONE · transformed={len(state['done'])} · failed={len(state['failed'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

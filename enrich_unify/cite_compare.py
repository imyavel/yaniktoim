"""Сверка цитат (корзина C, §4) — READ-ONLY. По каждой §-несущей Зоар-ссылке достаёт
авторскую цитату из .zml (блок [epi]/[quote] или строка-сноска) и НАШ абзац из
zohar-sulam (#p§), нормализует и сравнивает (difflib). Расхождения → cite_report.md/html
на согласование. Ничего не меняет; «целостность»: берём только реально прочитанный
полный текст абзаца — если файл/§ не нашёлся, помечаем NO_SOURCE (не угадываем).

  python cite_compare.py
"""
from __future__ import annotations
import json, re, glob, html as htmlmod
from pathlib import Path
from difflib import SequenceMatcher

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ART = ROOT / "docs" / "art"
ZOHAR = ROOT.parent / "zohar-sulam"
OUT = HERE / "out"

STAG = re.compile(r"\{([a-z][a-z0-9-]*)\|(\d*)\|(\d+)\}")   # тег С явным §
QUOTE = re.compile(r"[«„“\"]([^»“”\"]{30,})[»“”\"]")          # «…»/„…"/"…"
EXCL = ({ln.strip() for ln in (HERE / "exclude.txt").read_text(encoding="utf-8").splitlines()
         if ln.strip() and not ln.startswith("#")} if (HERE / "exclude.txt").exists() else set())
OPEN = re.compile(r"\[(epi|quote)\b")
CLOSE = re.compile(r"\[/(epi|quote)\]")

def norm(s: str) -> str:
    s = htmlmod.unescape(s)
    s = re.sub(r"^\s*\d+\)\s*", "", s)                       # «NN) » в начале
    s = re.sub(r"^.{0,80}?и\s*т\.?\s*д\.?\s*:\s*", "", s)    # лемма-зачин «… и т. д.:»
    s = re.sub(r"[«»„“”\"'`]", "", s)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.U)               # пунктуация прочь
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def our_para(ch: str, n: int, para: str):
    p = ZOHAR / ch / f"{n:03d}.html"
    if not p.exists():
        return None
    h = p.read_text(encoding="utf-8")
    m = re.search(rf'id="p{para}"[^>]*>(.*?)</p>', h, re.S)
    if not m:
        return None
    t = re.sub(r"<[^>]+>", "", m.group(1))
    return htmlmod.unescape(re.sub(r"\s+", " ", t)).strip()

def author_quote(lines, idx0: int) -> str:
    """Цитата из блока [epi]/[quote] вокруг строки idx0 (0-based), иначе из самой строки."""
    start = end = idx0
    i = idx0
    while i >= 0 and idx0 - i < 60:
        if OPEN.search(lines[i]): start = i; break
        if CLOSE.search(lines[i]) and i < idx0: break
        i -= 1
    j = idx0
    while j < len(lines) and j - idx0 < 60:
        if CLOSE.search(lines[j]): end = j; break
        if OPEN.search(lines[j]) and j > idx0: break
        j += 1
    block = "\n".join(lines[start:end + 1]) if (start < idx0 or end > idx0) else lines[idx0]
    # Жадный захват: от первой откр. кавычки до последней закр. в блоке (учитывает вложенные «…»).
    opens = [block.find(c) for c in "«„“" if block.find(c) >= 0]
    closes = [block.rfind(c) for c in "»“”" if block.rfind(c) >= 0]
    if opens and closes and max(closes) > min(opens) + 30:
        return block[min(opens):max(closes) + 1], block
    qs = QUOTE.findall(block)
    return (max(qs, key=len) if qs else ""), block

def final_lines(fid: str):
    """zml с применёнными структурными правками (для финальной формы строк/тегов)."""
    lines = (ART / f"{fid}.zml").read_text(encoding="utf-8").splitlines()
    jf = OUT / f"{fid}.json"
    if jf.exists():
        d = json.loads(jf.read_text(encoding="utf-8"))
        for e in d.get("edits", []):
            if e.get("kind") == "TEXT":
                continue
            ln = e.get("line")
            if ln and 1 <= ln <= len(lines) and lines[ln - 1] == e.get("before"):
                lines[ln - 1] = e.get("after", "")
    return lines

def main():
    rows = []
    for jf in sorted(OUT.glob("*.json")):
        fid = jf.stem
        if fid in EXCL:
            continue
        lines = final_lines(fid)
        for idx, ln in enumerate(lines):
            for m in STAG.finditer(ln):
                ch, n, para = m.group(1), m.group(2), m.group(3)
                if not n:
                    continue
                q, block = author_quote(lines, idx)
                if len(q) < 30:
                    continue          # нет существенной авторской цитаты рядом — не сверяем
                ours = our_para(ch, int(n), para)
                if ours is None:
                    rows.append({"id": fid, "line": idx + 1, "ref": m.group(0),
                                 "status": "NO_SOURCE", "ratio": 0, "author": q, "ours": "", "block": block[:2000]})
                    continue
                ratio = SequenceMatcher(None, norm(q), norm(ours)).ratio()
                rows.append({"id": fid, "line": idx + 1, "ref": m.group(0),
                             "status": "diff" if ratio < 0.92 else "match",
                             "ratio": round(ratio, 3), "author": q, "ours": ours, "block": block[:2000]})
    rows.sort(key=lambda r: (r["status"] != "NO_SOURCE", r["status"] != "diff", r["ratio"]))
    json.dump(rows, open(HERE / "cite_rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    diff = [r for r in rows if r["status"] == "diff"]
    match = [r for r in rows if r["status"] == "match"]
    nosrc = [r for r in rows if r["status"] == "NO_SOURCE"]
    print(f"§-цитат проверено: {len(rows)} | расхождения: {len(diff)} | совпадают: {len(match)} | нет источника: {len(nosrc)}")
    for r in diff:
        print(f"  DIFF {r['id']}:{r['line']} {r['ref']} ratio={r['ratio']}")
    for r in nosrc:
        print(f"  NO_SOURCE {r['id']}:{r['line']} {r['ref']}")

if __name__ == "__main__":
    main()

"""Извлечь дату из текста статьи (regex по нескольким форматам), упасть в URL-дату
если в тексте не нашлось. Отсортировать 350 статей и присвоить #001..#350.

Ключ сортировки: (date_text_or_url, NNN_url).
Поле даты текста — первое попавшееся совпадение по списку шаблонов.
"""
from __future__ import annotations
import io, sys, json, re
from pathlib import Path
from datetime import date

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
CORPUS_JSON = RAW / "_corpus.json"
MANIFEST = ROOT / "manifest.json"

MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}
# (Mind: "май"/"мая" prefix "ма" — covers both. "марта" → "март". Tested below.)

# 19.06.2021 / 19/06/21 / 19-06-2021
RE_NUM = re.compile(r"\b([0-3]?\d)[.\-/]([01]?\d)[.\-/](\d{2,4})\b")
# 19 июня 2021 г.  / 19 июнЯ 2021
RE_MONTH = re.compile(r"\b([0-3]?\d)\s+([а-яА-ЯёЁ]+)\s+(\d{4})\b")
# Июнь 2021 (без числа — день по умолчанию = 1)
RE_MONTH_ONLY = re.compile(r"\b([А-ЯЁ][а-яё]+)\s+(\d{4})\b")
# URL: /YYYY/MM/DD/NNN
RE_URL = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/(\d+)")


def parse_month_word(word: str) -> int | None:
    w = word.lower()
    for prefix, n in MONTHS.items():
        if w.startswith(prefix):
            return n
    return None


def strip_html(html: str) -> str:
    # Cheap strip — replace <br> with newlines, drop tags.
    s = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"&quot;", '"', s)
    s = re.sub(r"&[a-zA-Z]+;", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def text_of_article(html: str) -> str:
    m = re.search(r'<div\s+class="text">(.*?)</div>\s*<br>', html, re.S)
    body = m.group(1) if m else html
    return strip_html(body)


def normalize_year(y: int) -> int:
    return 2000 + y if y < 100 else y


def extract_date(text: str) -> date | None:
    """Try several patterns; return the first date found in the text or None."""
    # Numeric DD.MM.YYYY
    for m in RE_NUM.finditer(text):
        d, mo, y = int(m.group(1)), int(m.group(2)), normalize_year(int(m.group(3)))
        if 1 <= d <= 31 and 1 <= mo <= 12 and 1990 <= y <= 2100:
            try:
                return date(y, mo, d)
            except ValueError:
                continue
    # DD <month-word> YYYY
    for m in RE_MONTH.finditer(text):
        d, mw, y = int(m.group(1)), m.group(2), int(m.group(3))
        mo = parse_month_word(mw)
        if mo and 1 <= d <= 31 and 1990 <= y <= 2100:
            try:
                return date(y, mo, d)
            except ValueError:
                continue
    # <Month-word> YYYY (default day 1)
    for m in RE_MONTH_ONLY.finditer(text):
        mw, y = m.group(1), int(m.group(2))
        mo = parse_month_word(mw)
        if mo and 1990 <= y <= 2100:
            return date(y, mo, 1)
    return None


def url_date(url: str) -> tuple[date, int] | None:
    m = RE_URL.search(url)
    if not m:
        return None
    y, mo, d, nnn = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    try:
        return date(y, mo, d), nnn
    except ValueError:
        return None


def main():
    corpus = json.loads(CORPUS_JSON.read_text(encoding="utf-8"))
    rows = []
    used_text_date = 0
    used_url_date = 0
    for stem, meta in corpus.items():
        html = (RAW / meta["html"]).read_text(encoding="utf-8")
        text = text_of_article(html)
        url_dt = url_date(meta["url"])
        if url_dt is None:
            continue
        url_d, nnn = url_dt
        text_d = extract_date(text)
        # Use text date only if it's not crazy-far from url date (sanity).
        chosen = url_d
        chosen_source = "url"
        if text_d and abs((text_d - url_d).days) < 365 * 6:
            chosen = text_d
            chosen_source = "text"
            used_text_date += 1
        else:
            used_url_date += 1
        rows.append({
            "stem": stem,
            "url": meta["url"],
            "section": meta["section"],
            "title": meta["title"],
            "html": meta["html"],
            "img": meta["img"],
            "url_date": url_d.isoformat(),
            "url_nnn": nnn,
            "text_date": text_d.isoformat() if text_d else None,
            "date_chosen": chosen.isoformat(),
            "date_source": chosen_source,
        })
    rows.sort(key=lambda r: (r["date_chosen"], r["url_nnn"]))
    for i, r in enumerate(rows, 1):
        r["number"] = f"{i:03d}"
    print(f"Articles: {len(rows)}")
    print(f"  date from text: {used_text_date}")
    print(f"  date from URL : {used_url_date}")
    # group by section
    by_sec: dict[str, int] = {}
    for r in rows: by_sec[r["section"]] = by_sec.get(r["section"], 0) + 1
    for s, n in sorted(by_sec.items()):
        print(f"  section {s}: {n}")
    MANIFEST.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved → {MANIFEST}")


if __name__ == "__main__":
    main()

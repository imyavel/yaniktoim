"""Собрать вход для LLM-классификации дат: по каждой статье — шапка + окна
контекста вокруг КАЖДОГО датового токена и маркера авторства во ВСЁМ тексте.

Так модель видит все даты (включая середину/конец длинных поэм), но без
пересылки мегабайт мистической прозы.

Выход: _logs/redate_input.json — список {number, stem, url, url_date, snippet}.
"""
from __future__ import annotations
import io, sys, json, re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
MANIFEST = ROOT / "manifest.json"
OUT = ROOT / "_logs" / "redate_input.json"

HEADER = 500   # всегда показываем начало (дата-заголовок)
WIN = 90       # ±символов вокруг каждого кандидата

MONTHS = ("январ|феврал|март|апрел|ма[йяе]|июн|июл|август|сентябр|октябр|"
          "ноябр|декабр")
MARKERS = ("написано|записано|создано|сложено|сочинено|сочинён|дано|рождено|"
           "дополнено|обновлено|добавлено")

# числовые даты (с годом или без), месяц-словом, и маркеры авторства
RE_CAND = re.compile(
    r"(\d{1,2}[.\-/]\d{1,2}(?:[.\-/]\d{2,4})?)"          # 17.03.20 / 18-04 / 21/11/15
    r"|(\d{0,2}\s*(?:" + MONTHS + r")[а-яё]*\s*\d{2,4})"  # 6 ноября 2020 / Май 2021
    r"|((?:" + MARKERS + r"))",                            # маркер авторства
    re.I,
)


def strip_html(html: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"&quot;", '"', s)
    s = re.sub(r"&[a-zA-Z]+;", "", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def text_of_article(html: str) -> str:
    m = re.search(r'<div\s+class="text">(.*?)</div>\s*<br>', html, re.S)
    body = m.group(1) if m else html
    return strip_html(body)


def evidence(text: str) -> str:
    """Шапка + слитые окна вокруг всех кандидатов."""
    spans: list[tuple[int, int]] = [(0, min(HEADER, len(text)))]
    for m in RE_CAND.finditer(text):
        spans.append((max(0, m.start() - WIN), min(len(text), m.end() + WIN)))
    # слить пересекающиеся
    spans.sort()
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 5:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    chunks = []
    for a, b in merged:
        seg = text[a:b].strip()
        chunks.append(seg if a == 0 else "… " + seg)
    return "\n---\n".join(chunks)


def main() -> int:
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = []
    sizes = []
    for r in man:
        text = text_of_article((RAW / r["html"]).read_text(encoding="utf-8"))
        ev = evidence(text)
        sizes.append(len(ev))
        rows.append({
            "number": r["number"],
            "stem": r["stem"],
            "url": r["url"],
            "url_date": r["url_date"],
            "snippet": ev,
        })
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    sizes.sort()
    print(f"Wrote {len(rows)} evidence blocks -> {OUT}")
    print(f"size: p50={sizes[len(sizes)//2]} p90={sizes[int(len(sizes)*0.9)]} "
          f"max={sizes[-1]} total={sum(sizes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Re-fetch каталоговых страниц proza.ru чтобы зафиксировать порядок,
в котором автор разместил статьи в каждом разделе. Записываем поле
`section_order` (целое, 0-based внутри раздела) в manifest.json.

Дальше 5_index.py использует это поле для оглавлений (а не глобальный
номер по дате).
"""
from __future__ import annotations
import io, os, re, sys, time, json
from pathlib import Path
from http.cookiejar import MozillaCookieJar
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
COOKIES = RAW / "proza_cookies.txt"
MANIFEST = ROOT / "manifest.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# slug -> book number
SECTIONS = {
    "dreamon":  17,
    "cyberson": 24,
    "dabudet":  13,
    "confront": 16,
    "shoshana": 25,
    "other":    20,
}
# best — отдельная страница автора без &book=
ART_RE = re.compile(r'<a href="(/\d{4}/\d{2}/\d{2}/\d+)" class="poemlink">')


def session():
    jar = MozillaCookieJar(str(COOKIES)); jar.load(ignore_discard=True, ignore_expires=True)
    s = requests.Session(); s.cookies = jar
    s.headers.update({"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9",
                      "Referer": "https://proza.ru/avtor/agent017"})
    return s


def get_html(s, url):
    for attempt in range(3):
        try:
            r = s.get(url, timeout=30)
            if r.ok: return r.content.decode("cp1251", errors="replace")
        except requests.RequestException:
            pass
        time.sleep(2 ** attempt)
    return ""


def url_stem(path): return re.sub(r"[^0-9A-Za-z]+", "_", path).strip("_")


def order_for_book(s, book):
    """Return list of paths in the order proza.ru shows them in book=<n>."""
    out: list[str] = []
    for offset in (0, 50, 100, 150):
        url = (f"https://proza.ru/avtor/agent017&s={offset}&book={book}"
               if offset else f"https://proza.ru/avtor/agent017&book={book}")
        html = get_html(s, url)
        paths = ART_RE.findall(html)
        for p in paths:
            if p not in out:
                out.append(p)
        if len(paths) < 50:
            break
        time.sleep(0.3)
    return out


def order_for_best(s):
    """Page /avtor/agent017 — the landing page shows the author's favorites."""
    url = "https://proza.ru/avtor/agent017"
    html = get_html(s, url)
    paths = ART_RE.findall(html)
    seen = []; [seen.append(p) for p in paths if p not in seen]
    return seen


def main():
    s = session()
    print(f"Loaded {sum(1 for _ in s.cookies)} cookies.")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_path = {r["url"].replace("https://proza.ru", ""): r for r in manifest}

    section_orders: dict[str, list[str]] = {}
    for slug, book in SECTIONS.items():
        paths = order_for_book(s, book)
        section_orders[slug] = paths
        print(f"  {slug} (book={book}): {len(paths)} ordered paths")
    section_orders["best"] = order_for_best(s)
    print(f"  best (landing): {len(section_orders['best'])} paths")

    # Apply order to manifest. Each article has exactly one section (already
    # set by 1_fetch). Inside that section we look up its index in the
    # section_orders[section] list — that's the canonical author-defined order.
    missing = 0
    for r in manifest:
        sec = r["section"]
        path = r["url"].replace("https://proza.ru", "")
        order_list = section_orders.get(sec, [])
        try:
            r["section_order"] = order_list.index(path)
        except ValueError:
            r["section_order"] = 9999  # not found on the catalog page — push to end
            missing += 1
            print(f"  ! not found in catalog: {sec} {path}")
    print(f"missing in catalog pages: {missing}")
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved → {MANIFEST}")


if __name__ == "__main__":
    main()

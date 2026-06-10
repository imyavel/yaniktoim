"""Сгенерировать sitemap.xml и robots.txt для сайта yaniktoim (docs/).

Сайт публикуется на GitHub Pages: https://imyavel.github.io/yaniktoim/
Каталог docs/ — корень публикации (живые самодостаточные страницы).

Идемпотентно: оба файла перезаписываются целиком из текущего состояния
docs/, поэтому sitemap всегда соответствует тому, что реально лежит на
сайте, без расхождений.

  python tools/build_sitemap.py            # записать sitemap.xml + robots.txt
  python tools/build_sitemap.py --dry-run  # только показать сводку
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
BASE = "https://imyavel.github.io/yaniktoim/"

# Файлы в корне docs/, которые НЕ должны попадать в sitemap.
#  search.html — JS-страница поиска, краулить нечего.
#  sitemap/robots — служебные.
#  404.html — страница ошибки.
EXCLUDE_FILES = frozenset({
    "search.html", "sitemap.xml", "robots.txt", "404.html",
})
# Каталоги, которые целиком исключаются (индекс поиска и git).
EXCLUDE_DIRS = frozenset({"pagefind", ".git", "img"})


def path_to_url(rel: str) -> str:
    """docs-относительный путь HTML -> публичный URL (без BASE).

    index.html -> ""              (корень с завершающим слэшем)
    foo/index.html -> "foo/"      (форма с завершающим слэшем — каноничная)
    art/654.html -> "art/654.html"
    """
    p = rel.replace("\\", "/")
    if p == "index.html":
        return ""
    if p.endswith("/index.html"):
        return p[: -len("index.html")]
    return p


def collect(docs: Path) -> list[tuple[str, str]]:
    """Вернуть [(rel_path, lastmod_iso), ...] для индексируемых *.html.

    Корневой index.html ставится первым (приятно глазу, на SEO не влияет).
    lastmod — дата последней модификации файла.
    """
    items: list[tuple[str, str]] = []
    for p in sorted(docs.rglob("*.html")):
        parts = p.relative_to(docs).parts
        if any(seg in EXCLUDE_DIRS for seg in parts):
            continue
        if parts[-1] in EXCLUDE_FILES:
            continue
        if parts[-1].endswith(".view.html"):
            continue  # ZML-предпросмотр (noindex, интерим) — не в sitemap
        rel = "/".join(parts)
        lastmod = dt.date.fromtimestamp(p.stat().st_mtime).isoformat()
        items.append((rel, lastmod))
    items.sort(key=lambda t: (t[0] != "index.html", t[0]))
    return items


def build_sitemap(items: list[tuple[str, str]]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for rel, lastmod in items:
        loc = (BASE + path_to_url(rel)).replace("&", "&amp;")
        lines.append(f"  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod></url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def build_robots() -> str:
    return (
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {BASE}sitemap.xml\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="только показать сводку, ничего не писать")
    args = ap.parse_args()

    if not DOCS.is_dir():
        print(f"docs/ не найден: {DOCS}", file=sys.stderr)
        return 1

    items = collect(DOCS)
    sitemap = build_sitemap(items)
    robots = build_robots()

    print(f"Страниц в sitemap: {len(items)}")
    print(f"  первая: {BASE}{path_to_url(items[0][0]) if items else ''}")
    print(f"  последняя: {BASE}{path_to_url(items[-1][0]) if items else ''}")

    if args.dry_run:
        print("(--dry-run: файлы не записаны)")
        return 0

    (DOCS / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (DOCS / "robots.txt").write_text(robots, encoding="utf-8")
    print(f"Записано: {DOCS / 'sitemap.xml'}")
    print(f"Записано: {DOCS / 'robots.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

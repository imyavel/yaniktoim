"""Идемпотентно вставить SEO-теги в <head> страниц docs/.

Добавляет ТОЛЬКО недостающее (повторный прогон безопасен):
  • <link rel="canonical">            — собственный URL страницы
  • <meta name="description">         — для статей берётся из descriptions.json;
                                        иначе сохраняется существующее описание
  • og:title / og:type / og:url / og:description / og:site_name / og:locale
  • twitter:card / twitter:title / twitter:description

Источник описания (по приоритету): descriptions.json (для art/*) →
существующий <meta name="description"> → существующий og:description.

  python tools/apply_seo.py             # применить ко всем страницам
  python tools/apply_seo.py --dry-run   # показать, что добавилось бы
  python tools/apply_seo.py --limit 5   # только первые N (для проверки)
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DESCRIPTIONS = ROOT / "descriptions.json"
BASE = "https://imyavel.github.io/yaniktoim/"
SITE_NAME = "Путь Восходящей Звезды"

EXCLUDE_DIRS = frozenset({"pagefind", ".git", "img"})

HEAD_RX = re.compile(r"</head>", re.I)
TITLE_RX = re.compile(r"<title>(.*?)</title>", re.S | re.I)
TAG_RX = re.compile(r"<[^>]+>")
WS_RX = re.compile(r"\s+")


def path_to_url(rel: str) -> str:
    p = rel.replace("\\", "/")
    if p == "index.html":
        return ""
    if p.endswith("/index.html"):
        return p[: -len("index.html")]
    return p


def esc(s: str) -> str:
    return htmllib.escape(s, quote=True)


def existing_meta_desc(head: str) -> str | None:
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]*content=["\'](.*?)["\']',
                  head, re.I | re.S)
    return m.group(1) if m else None


def existing_og_desc(head: str) -> str | None:
    m = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]*content=["\'](.*?)["\']',
                  head, re.I | re.S)
    return m.group(1) if m else None


def has(head: str, attr: str, val: str) -> bool:
    return re.search(rf'{attr}=["\']{re.escape(val)}["\']', head, re.I) is not None


def build_tags(rel: str, head: str, descriptions: dict[str, str]) -> list[str]:
    url = BASE + path_to_url(rel)
    mt = TITLE_RX.search(head)
    title = WS_RX.sub(" ", TAG_RX.sub("", mt.group(1)) if mt else "").strip()
    is_article = rel.startswith("art/")
    og_type = "article" if is_article else "website"

    # описание: json (статьи) -> существующее description -> существующее og:description
    desc = None
    if is_article:
        desc = descriptions.get(rel)
    if not desc:
        desc = existing_meta_desc(head) or existing_og_desc(head)

    tags: list[str] = []
    if not has(head, "rel", "canonical"):
        tags.append(f'<link rel="canonical" href="{esc(url)}">')
    if desc and existing_meta_desc(head) is None:
        tags.append(f'<meta name="description" content="{esc(desc)}">')
    if not has(head, "property", "og:title") and title:
        tags.append(f'<meta property="og:title" content="{esc(title)}">')
    if not has(head, "property", "og:type"):
        tags.append(f'<meta property="og:type" content="{og_type}">')
    if not has(head, "property", "og:url"):
        tags.append(f'<meta property="og:url" content="{esc(url)}">')
    if desc and not has(head, "property", "og:description"):
        tags.append(f'<meta property="og:description" content="{esc(desc)}">')
    if not has(head, "property", "og:site_name"):
        tags.append(f'<meta property="og:site_name" content="{esc(SITE_NAME)}">')
    if not has(head, "property", "og:locale"):
        tags.append('<meta property="og:locale" content="ru_RU">')
    if not has(head, "name", "twitter:card"):
        tags.append('<meta name="twitter:card" content="summary">')
    if not has(head, "name", "twitter:title") and title:
        tags.append(f'<meta name="twitter:title" content="{esc(title)}">')
    if desc and not has(head, "name", "twitter:description"):
        tags.append(f'<meta name="twitter:description" content="{esc(desc)}">')
    return tags


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    descriptions: dict[str, str] = {}
    if DESCRIPTIONS.exists():
        descriptions = json.loads(DESCRIPTIONS.read_text(encoding="utf-8"))
    print(f"descriptions.json: {len(descriptions)} описаний")

    files = []
    for p in sorted(DOCS.rglob("*.html")):
        parts = p.relative_to(DOCS).parts
        if any(seg in EXCLUDE_DIRS for seg in parts):
            continue
        files.append(p)
    if args.limit:
        files = files[: args.limit]

    changed = skipped = 0
    for p in files:
        rel = "/".join(p.relative_to(DOCS).parts)
        text = p.read_text(encoding="utf-8")
        mh = HEAD_RX.search(text)
        if not mh:
            print(f"[!] нет </head>: {rel}", file=sys.stderr)
            continue
        head = text[: mh.start()]
        tags = build_tags(rel, head, descriptions)
        if not tags:
            skipped += 1
            continue
        block = "".join("\n" + t for t in tags) + "\n"
        new = text[: mh.start()] + block + text[mh.start():]
        changed += 1
        if args.dry_run:
            print(f"[+ {len(tags)}] {rel}")
            for t in tags:
                print("    " + t)
        else:
            p.write_text(new, encoding="utf-8")

    verb = "добавилось бы" if args.dry_run else "обновлено"
    print(f"Страниц {verb}: {changed}; без изменений: {skipped}; всего: {len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

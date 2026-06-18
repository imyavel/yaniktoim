# -*- coding: utf-8 -*-
"""
add_artid_search.py — make each article findable in site search by its art-id.

Problem: the art-id (e.g. #654, #03H, #22SA) lives only in section-index lists
(`<span class="num">#654</span>`), never in the article page's own indexable
body. So Pagefind never returns the *article* when you search its number — only
the section listing (or noise). See roadmap_cms.md "Открытые задачи".

Fix: inject one visually-hidden, Pagefind-indexable token per article carrying
its id, with a high search weight so the exact article ranks first. The token is
SR-readable ("Артикль №654") but invisible on screen — no visual change to the
352 article designs.

Also: exclude the orphan /proza-design/ design-experiment pages (not linked
anywhere public) from the search index so they stop polluting results.

Idempotent: re-running replaces the existing token instead of duplicating it.
Touches only docs/art/<ID>.html (NOT *.view.html — views are pagefind-ignored)
and docs/proza-design/**/*.html.
"""
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"

# Visually-hidden + high-weight + meta. Inline style => guaranteed hidden
# regardless of each page's own CSS. Pagefind indexes the text (it parses HTML,
# not rendered CSS) and honours data-pagefind-weight / data-pagefind-meta.
MARKER_CLASS = "pf-artid"
HIDE_STYLE = ("position:absolute;width:1px;height:1px;padding:0;margin:-1px;"
              "overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0")

# Remove any previously-injected token (idempotency).
EXISTING_RE = re.compile(
    r'\s*<span[^>]*class="' + MARKER_CLASS + r'"[^>]*>.*?</span>',
    re.DOTALL)
BODY_OPEN_RE = re.compile(r'(<body\b[^>]*>)', re.IGNORECASE)


def token_for(art_id: str) -> str:
    # No data-pagefind-meta: it would render an English "Artid: …" label in the
    # PagefindUI results. The high weight makes the article outrank the section
    # listing; the indexed text "Артикль №654" supplies a clean RU excerpt.
    return (f'<span class="{MARKER_CLASS}" data-pagefind-weight="10" '
            f'style="{HIDE_STYLE}">Артикль №{art_id}</span>')


def inject_artid() -> int:
    art_dir = DOCS / "art"
    changed = 0
    files = sorted(p for p in art_dir.glob("*.html")
                   if not p.name.endswith(".view.html"))
    for p in files:
        art_id = p.name[:-len(".html")]
        html = p.read_text(encoding="utf-8")
        html = EXISTING_RE.sub("", html)  # strip stale token if present
        new_html, n = BODY_OPEN_RE.subn(
            lambda m: m.group(1) + "\n" + token_for(art_id), html, count=1)
        if n != 1:
            print(f"  !! no <body> in {p.name} — skipped", file=sys.stderr)
            continue
        if new_html != p.read_text(encoding="utf-8"):
            p.write_text(new_html, encoding="utf-8")
            changed += 1
    print(f"art-id token: {changed}/{len(files)} article pages updated")
    return changed


def ignore_proza_design() -> int:
    pd = DOCS / "proza-design"
    if not pd.exists():
        print("proza-design/: absent — nothing to exclude")
        return 0
    changed = 0
    files = sorted(pd.rglob("*.html"))
    for p in files:
        html = p.read_text(encoding="utf-8")

        def add_attr(m):
            tag = m.group(1)
            if "data-pagefind-ignore" in tag:
                return tag
            return tag[:-1] + ' data-pagefind-ignore="all">'

        new_html, n = BODY_OPEN_RE.subn(add_attr, html, count=1)
        if n == 1 and new_html != html:
            p.write_text(new_html, encoding="utf-8")
            changed += 1
    print(f"proza-design: {changed}/{len(files)} pages excluded from index")
    return changed


if __name__ == "__main__":
    inject_artid()
    ignore_proza_design()

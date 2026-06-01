"""Вставить кликабельный значок «наушники» 🎧 в <h1> статей корпуса.

Источник аудио-ссылок: index017.xml (поле `link` = URL telegram-трека).
Сопоставление записи индекса ↔ статья корпуса — по `url` (proza.ru), а НЕ по
названиям (URL уникален и совпадает с manifest.json — надёжнее fuzzy-title).

Страницы docs/art/<art>.html самодостаточны (CSS инлайн, разная вёрстка от
LLM), поэтому значок стилизуется инлайн прямо на <a>, без зависимости от
per-page классов. Значок ставится сразу после текста заголовка — ПЕРЕД первым
вложенным <span> (heb/rule обычно display:block и уходят на свою строку), либо
перед </h1>, если span-ов нет.

Идемпотентно: повторный запуск пропускает уже размеченные H1.

  python tools/add_audio_links.py            # применить
  python tools/add_audio_links.py --dry-run  # только показать, что будет
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.json"
ART_DIR = ROOT / "docs" / "art"
INDEX_XML = Path(r"C:\Users\admin\agent017bot\index017.xml")  # самая свежая копия

H1_RX = re.compile(r"(<h1\b[^>]*>)(.*?)(</h1>)", re.S)
INNER_SPAN_RX = re.compile(r"<span\b", re.I)

MARKER = "audio-link"


def norm_url(u: str | None) -> str | None:
    if not u:
        return None
    return u.strip().lower().rstrip("/").replace("http://", "https://")


def anchor_html(link: str) -> str:
    return (
        f'<a class="{MARKER}" href="{link}" target="_blank" '
        f'rel="noopener noreferrer" title="Слушать аудио-озвучку" '
        f'aria-label="Аудио-озвучка" '
        f'style="text-decoration:none;font-size:.62em;vertical-align:middle;'
        f'margin-left:.4em;white-space:nowrap;">\U0001F3A7</a>'
    )


def build_link_map() -> dict[str, str]:
    """norm proza-url -> telegram link (только записи с непустым link)."""
    tree = ET.parse(INDEX_XML)
    out: dict[str, str] = {}
    for w in tree.iter("work"):
        u = norm_url(w.get("url"))
        link = w.get("link")
        if u and link:
            out[u] = link
    return out


def inject(html: str, link: str) -> str | None:
    """Вставить значок в единственный <h1>. None — если уже размечен / нет h1."""
    m = H1_RX.search(html)
    if not m:
        return None
    open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)
    if MARKER in inner or "\U0001F3A7" in inner:
        return None  # идемпотентность
    icon = anchor_html(link)
    span = INNER_SPAN_RX.search(inner)
    if span:
        new_inner = inner[: span.start()] + icon + inner[span.start():]
    else:
        new_inner = inner + icon
    new_h1 = open_tag + new_inner + close_tag
    return html[: m.start()] + new_h1 + html[m.end():]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    link_map = build_link_map()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    applied, skipped, no_link, no_file, no_h1 = [], [], [], [], []
    for rec in manifest:
        art = rec.get("art")
        u = norm_url(rec.get("url"))
        if not art:
            continue
        link = link_map.get(u or "")
        if not link:
            no_link.append(art)
            continue
        f = ART_DIR / f"{art}.html"
        if not f.exists():
            no_file.append(art)
            continue
        html = f.read_text(encoding="utf-8")
        new = inject(html, link)
        if new is None:
            if H1_RX.search(html) is None:
                no_h1.append(art)
            else:
                skipped.append(art)  # уже размечен
            continue
        if not args.dry_run:
            f.write_text(new, encoding="utf-8", newline="\n")
        applied.append(art)

    tag = "DRY-RUN" if args.dry_run else "DONE"
    print(f"[{tag}] applied={len(applied)} already-marked={len(skipped)} "
          f"no-audio-link={len(no_link)} missing-file={len(no_file)} "
          f"no-h1={len(no_h1)}")
    if no_h1:
        print("  ! NO <h1> (проверить вручную):", ", ".join(no_h1))
    if no_file:
        print("  ! NO FILE:", ", ".join(no_file))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

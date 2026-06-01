"""Вставить кликабельный значок «наушники» 🎧 в <h1> статей корпуса.

Источник аудио-ссылок: index017.xml (поле `link` = URL telegram-трека).
Сопоставление записи индекса ↔ статья корпуса — по `url` (proza.ru), а НЕ по
названиям (URL уникален и совпадает с manifest.json — надёжнее fuzzy-title).

РАЗМЕЩЕНИЕ. Страницы docs/art/<art>.html самодостаточны (CSS инлайн, разная
вёрстка от LLM). H1 бывает с инлайновыми сносками (<sup>/<span class="pop">…)
ПОСРЕДИ заголовка и с хвостовым подзаголовком (heb/rule/sub…, обычно
display:block). Поэтому:
  • значок ставится в КОНЕЦ H1 (после всего текста и сносок), НО
  • если H1 заканчивается блочным (display:block/flex/grid/table) подзаголовком —
    перед ним (иначе значок упал бы на отдельную строку под подзаголовком).
Блочность класса определяется из <style> самой страницы.

Идемпотентно: старый <a class="audio-link"> в H1 вырезается и ставится заново,
поэтому повторный/исправляющий прогон безопасен.

  python tools/add_audio_links.py            # применить
  python tools/add_audio_links.py --dry-run  # только показать сводку
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
AUDIO_RX = re.compile(r'<a class="audio-link".*?</a>', re.S)
STYLE_RX = re.compile(r"<style[^>]*>(.*?)</style>", re.S | re.I)
TAG_RX = re.compile(r"<(/?)([a-zA-Z][\w-]*)([^>]*?)(/?)>")
CLASS_ATTR_RX = re.compile(r'class\s*=\s*"([^"]*)"')

MARKER = "audio-link"
BLOCK_DISPLAYS = ("block", "flex", "grid", "table", "inline-block")
VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr"}


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
    tree = ET.parse(INDEX_XML)
    out: dict[str, str] = {}
    for w in tree.iter("work"):
        u = norm_url(w.get("url"))
        link = w.get("link")
        if u and link:
            out[u] = link
    return out


def block_classes(page_html: str) -> set[str]:
    """Классы, у которых в CSS страницы display: block|flex|grid|… ."""
    css = "\n".join(STYLE_RX.findall(page_html))
    blocks: set[str] = set()
    for rule in css.split("}"):
        if "{" not in rule:
            continue
        sel, body = rule.split("{", 1)
        dm = re.search(r"display\s*:\s*([a-z-]+)", body, re.I)
        if not dm or dm.group(1).strip().lower() not in BLOCK_DISPLAYS:
            continue
        # display применяется к ПОСЛЕДНЕМУ токену селектора (subject). Берём
        # классы только из него, иначе `.fnref:hover .pop{display:block}`
        # ошибочно пометил бы .fnref (предка) блочным.
        for one in sel.split(","):
            subject = re.split(r"[\s>+~]+", one.strip())[-1]
            for cls in re.findall(r"\.([\w-]+)", subject):
                blocks.add(cls)
    return blocks


def last_toplevel_element(inner: str):
    """Если inner (без хвостовых пробелов) заканчивается элементом верхнего
    уровня — вернуть (start_index, set_of_classes). Иначе None (хвост — текст)."""
    rinner = inner.rstrip()
    if not rinner.endswith(">"):
        return None
    stack: list[tuple[int, str]] = []  # (start_pos, classattr) для открытых тегов
    last_pop: tuple[int, str] | None = None
    for m in TAG_RX.finditer(rinner):
        closing, name, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if name in VOID or selfclose:
            continue
        if not closing:
            stack.append((m.start(), attrs))
        else:
            if stack:
                start, attrs_open = stack.pop()
                if m.end() == len(rinner) and not stack:
                    last_pop = (start, attrs_open)
    if last_pop is None:
        return None
    start, attrs_open = last_pop
    cm = CLASS_ATTR_RX.search(attrs_open)
    classes = set(cm.group(1).split()) if cm else set()
    return start, classes


def inject(page_html: str, link: str) -> tuple[str | None, str]:
    """Вернуть (новый html | None, статус). None — нет <h1>."""
    m = H1_RX.search(page_html)
    if not m:
        return None, "no-h1"
    open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)
    had = MARKER in inner
    inner = AUDIO_RX.sub("", inner)  # снять прежнюю вставку (идемпотентность/фикс)

    blk = block_classes(page_html)
    tail = last_toplevel_element(inner)
    icon = anchor_html(link)
    if tail and (tail[1] & blk):
        pos = tail[0]                     # перед хвостовым блочным подзаголовком
        new_inner = inner[:pos] + icon + inner[pos:]
    else:
        rstripped = inner.rstrip()
        pad = inner[len(rstripped):]
        new_inner = rstripped + icon + pad  # в самый конец, до хвостовых пробелов

    new_html = page_html[: m.start()] + open_tag + new_inner + close_tag + page_html[m.end():]
    return new_html, ("refixed" if had else "added")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    link_map = build_link_map()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    added, refixed, unchanged, no_link, no_file, no_h1 = [], [], [], [], [], []
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
        new, status = inject(html, link)
        if status == "no-h1":
            no_h1.append(art)
            continue
        if new == html:
            unchanged.append(art)
            continue
        if not args.dry_run:
            f.write_text(new, encoding="utf-8", newline="\n")
        (added if status == "added" else refixed).append(art)

    tag = "DRY-RUN" if args.dry_run else "DONE"
    print(f"[{tag}] added={len(added)} refixed={len(refixed)} "
          f"unchanged={len(unchanged)} no-audio-link={len(no_link)} "
          f"missing-file={len(no_file)} no-h1={len(no_h1)}")
    if refixed:
        print("  refixed:", ", ".join(sorted(refixed)))
    if no_h1:
        print("  ! NO <h1>:", ", ".join(no_h1))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

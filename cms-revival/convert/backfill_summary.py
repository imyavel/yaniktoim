# -*- coding: utf-8 -*-
"""Одноразовый бэкфилл `summary:` во фронтматтер .zml (P1 url-unification).

Источник описания — <meta name="description" content="..."> из СТАРОГО
docs/art/<id>.html. Кураторские описания живут только там; ZML-вью берёт OG из
fm.summary (render.js:1614), которого у корпуса нет → описание пустое.

Алгоритм для каждого docs/art/<id>.html (исключая *.view.html):
  • вынуть content из <meta name="description"> (любой порядок атрибутов/кавычек);
  • декодировать HTML-сущности (html.unescape) — текст должен быть «чистым»,
    т.к. render.js сам htmlEscape'нет его при выводе meta (иначе двойной экранёж);
  • если в соответствующем <id>.zml во фронтматтере уже есть `summary:` — НЕ трогать;
  • иначе вставить строкой `summary: <текст>` перед закрывающим `---`.

Значение пишем БЕЗ кавычек (как title:/notes_title:): парсер render.js
(parseFrontmatter) построчный и НЕ разэкранирует \" — кавычки-обёртки он бы
просто срезал. Сохраняем EOL и тело файла байт-в-байт, меняем только фронтматтер.

Запуск:  python -X utf8 backfill_summary.py [--apply]   (без --apply = dry-run)
"""
import sys, re, html
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]      # …/yaniktoim
ART = ROOT / "docs" / "art"

APPLY = "--apply" in sys.argv[1:]

# <meta ... name="description" ... content="..."> — атрибуты в любом порядке.
META_RX = re.compile(
    r'<meta\b[^>]*\bname\s*=\s*["\']description["\'][^>]*>',
    re.IGNORECASE,
)
CONTENT_RX = re.compile(r'\bcontent\s*=\s*"([^"]*)"|\bcontent\s*=\s*\'([^\']*)\'',
                        re.IGNORECASE)
# граница фронтматтера: первый блок ---\n…\n---
FM_RX = re.compile(r'^---\r?\n([\s\S]*?\r?\n)---\r?\n', re.MULTILINE)


def extract_description(html_text):
    m = META_RX.search(html_text)
    if not m:
        return None
    cm = CONTENT_RX.search(m.group(0))
    if not cm:
        return None
    raw = cm.group(1) if cm.group(1) is not None else cm.group(2)
    return html.unescape(raw).strip()


def has_summary(fm_block):
    return re.search(r'^summary\s*:', fm_block, re.MULTILINE) is not None


def main():
    htmls = sorted(p for p in ART.glob("*.html") if not p.name.endswith(".view.html"))
    n_total = len(htmls)
    inserted, has_already, empty_desc, no_zml, no_fm, edge = [], [], [], [], [], []

    for hp in htmls:
        art = hp.name[:-5]                       # strip .html
        zp = ART / f"{art}.zml"
        desc = extract_description(hp.read_text(encoding="utf-8"))
        if not desc:
            empty_desc.append(art); continue
        if not zp.exists():
            no_zml.append(art); continue
        ztext = zp.read_text(encoding="utf-8")
        m = re.match(r'^---\r?\n([\s\S]*?\r?\n)---\r?\n', ztext)
        if not m:
            no_fm.append(art); continue
        if has_summary(m.group(1)):
            has_already.append(art); continue
        # описание, начинающееся/кончающееся ASCII-кавычкой, парсер срезал бы → флажок
        if desc[:1] in ('"', "'") or desc[-1:] in ('"', "'"):
            edge.append((art, desc)); continue

        eol = "\r\n" if "\r\n" in ztext[:m.end()] else "\n"
        # вставляем перед закрывающим '---' (последней строкой фронтматтера)
        insert_at = m.start() + len("---" + eol) + len(m.group(1))
        new = ztext[:insert_at] + f"summary: {desc}{eol}" + ztext[insert_at:]
        inserted.append((art, desc))
        if APPLY:
            zp.write_text(new, encoding="utf-8", newline="")

    print(f"Всего старых html: {n_total}")
    print(f"  summary уже есть: {len(has_already)}")
    print(f"  пустое описание (пропуск): {len(empty_desc)}", empty_desc[:20])
    print(f"  нет .zml: {len(no_zml)}", no_zml)
    print(f"  нет фронтматтера: {len(no_fm)}", no_fm)
    print(f"  edge (кавычка по краям, ПРОПУЩЕНЫ): {len(edge)}")
    for art, d in edge:
        print(f"     {art}: {d!r}")
    print(f"  ВСТАВЛЕНО summary: {len(inserted)}  ({'APPLIED' if APPLY else 'dry-run'})")
    for art, d in inserted[:5]:
        print(f"     {art}: {d[:90]}")


if __name__ == "__main__":
    main()

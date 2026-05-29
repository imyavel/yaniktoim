"""Render main index + section indexes from manifest."""
from __future__ import annotations
import io, sys, json, html as html_mod
from pathlib import Path
from datetime import date

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "templates"
SITE = ROOT / "docs"
MANIFEST = ROOT / "manifest.json"

CSS_VERSION = "20260528-04"
SECTION_NAMES = {
    "best":     "Избранное",
    "dreamon":  "Мечтай!!",
    "cyberson": "Киберсон",
    "dabudet":  "Да будет Свет!",
    "confront": "Столкновение с реальностью",
    "shoshana": "Шошана среди шипов",
    "other":    "Без категории",
}
ORDER = ["best", "dreamon", "cyberson", "dabudet", "confront", "shoshana", "other"]


def fmt_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d.%m.%Y")


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_sec: dict[str, list[dict]] = {s: [] for s in ORDER}
    for r in manifest:
        sec = r.get("section")
        if sec in by_sec:
            by_sec[sec].append(r)
    # Sort each section by author-defined order (captured in 2b_section_order),
    # NOT by chronological #number.
    for s in ORDER:
        by_sec[s].sort(key=lambda x: x.get("section_order", 9999))

    today = date.today().isoformat()

    # ----- main index -----
    items = []
    for s in ORDER:
        if not by_sec[s]: continue
        items.append(
            f'<li><a href="{s}/index.html">{html_mod.escape(SECTION_NAMES[s])}</a>'
            f'<span class="meta">{len(by_sec[s])} статей</span></li>'
        )
    tpl = (TPL / "main_index.html").read_text(encoding="utf-8")
    out = (tpl
        .replace("{{TOTAL}}", str(len(manifest)))
        .replace("{{SECTIONS_COUNT}}", str(sum(1 for s in ORDER if by_sec[s])))
        .replace("{{SECTIONS_LIST}}", "\n".join(items))
        .replace("{{BUILD_DATE}}", today)
        .replace("{{CSS_VERSION}}", CSS_VERSION))
    (SITE / "index.html").write_text(out, encoding="utf-8")
    print(f"main → site/index.html ({len(manifest)} articles, {sum(1 for s in ORDER if by_sec[s])} sections)")

    # ----- section indexes -----
    tpl_s = (TPL / "section_index.html").read_text(encoding="utf-8")
    for s in ORDER:
        rows = by_sec[s]
        if not rows: continue
        sec_dir = SITE / s
        sec_dir.mkdir(parents=True, exist_ok=True)
        lis = []
        for r in rows:
            art = r.get("art") or r.get("number", "???")
            published = (sec_dir / f"{art}.html").exists()
            title_safe = html_mod.escape(r["title"])
            if published:
                title_html = f'<a href="{art}.html">{title_safe}</a>'
                li_cls = ""
            else:
                # Not transformed/rendered yet — grayed-out, not clickable.
                title_html = f'<span class="title">{title_safe}</span>'
                li_cls = ' class="pending"'
            lis.append(
                f'<li{li_cls}><span class="num">#{art}</span>'
                f'{title_html}'
                f'<span class="meta">{fmt_date(r["date_chosen"])}</span></li>'
            )
        out = (tpl_s
            .replace("{{SECTION_NAME}}", html_mod.escape(SECTION_NAMES[s]))
            .replace("{{COUNT}}", str(len(rows)))
            .replace("{{ARTICLES_LIST}}", "\n".join(lis))
            .replace("{{BUILD_DATE}}", today)
            .replace("{{CSS_VERSION}}", CSS_VERSION))
        (sec_dir / "index.html").write_text(out, encoding="utf-8")
        print(f"  {s} → {len(rows)} articles")


if __name__ == "__main__":
    main()

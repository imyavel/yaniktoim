"""Починить prev/next ссылки в опубликованных страницах после смены артиклей.

Соседство по разделу не менялось (section_order тот же), сменились лишь art-id
соседей. Патчим ТОЛЬКО href внутри <a class="prev|next" …> по карте old→new.
Содержимое статей и self-бейдж не трогаем (поправятся при ре-рендере из zml).
"""
from __future__ import annotations
import io, sys, json, re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "docs" / "art"
OLD = ROOT / "manifest_pre_redate.json"
NEW = ROOT / "manifest.json"


def main() -> int:
    old = {r["number"]: r["art"] for r in json.loads(OLD.read_text(encoding="utf-8"))}
    new = {r["number"]: r["art"] for r in json.loads(NEW.read_text(encoding="utf-8"))}
    o2n = {old[n]: new[n] for n in old if old[n] != new[n]}
    art_files = {p.name for p in ART.glob("*.html")}

    nav_re = re.compile(r'(<a class="(?:prev|next)" href=")([0-9A-Za-z]+)\.html(")')

    n_files = 0
    n_links = 0
    skipped = []

    def repl(m: re.Match) -> str:
        nonlocal n_links
        tgt = m.group(2)
        if tgt + ".html" in art_files:
            return m.group(0)                      # уже валидна
        if tgt in o2n and (o2n[tgt] + ".html") in art_files:
            n_links += 1
            return f"{m.group(1)}{o2n[tgt]}.html{m.group(3)}"
        skipped.append(tgt)                        # не моя правка (pending-сосед)
        return m.group(0)

    for p in sorted(ART.glob("*.html")):
        txt = p.read_text(encoding="utf-8")
        new_txt = nav_re.sub(repl, txt)
        if new_txt != txt:
            p.write_text(new_txt, encoding="utf-8")
            n_files += 1

    print(f"patched {n_links} prev/next links in {n_files} files")
    if skipped:
        uniq = sorted(set(skipped))
        print(f"left untouched (pre-existing broken, unpublished neighbor): {uniq}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

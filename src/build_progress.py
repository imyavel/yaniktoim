"""Сводный progress.json: для каждой статьи — статус fetched/transformed/rendered.
Перезаписывается каждый раз из реальной файловой системы — никаких stale-флагов."""
from __future__ import annotations
import io, sys, json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
JSON_DIR = ROOT / "json"
SITE = ROOT / "docs"
MANIFEST = ROOT / "manifest.json"
OUT = ROOT / "progress.json"

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
rows = []
for r in manifest:
    n = r["number"]; sec = r["section"]; stem = r["stem"]
    rows.append({
        "number": n,
        "section": sec,
        "stem": stem,
        "title": r["title"],
        "fetched_html": (RAW / r["html"]).exists(),
        "fetched_img":  bool(r.get("img")) and (RAW / r["img"]).exists() if r.get("img") else False,
        "transformed":  (JSON_DIR / f"{n}.json").exists(),
        "rendered":     (SITE / sec / f"{n}.html").exists(),
    })

stats = {
    "total": len(rows),
    "fetched_html": sum(1 for r in rows if r["fetched_html"]),
    "fetched_img":  sum(1 for r in rows if r["fetched_img"]),
    "transformed":  sum(1 for r in rows if r["transformed"]),
    "rendered":     sum(1 for r in rows if r["rendered"]),
    "by_section":   {},
}
for r in rows:
    s = stats["by_section"].setdefault(r["section"], {"n": 0, "transformed": 0, "rendered": 0})
    s["n"] += 1
    if r["transformed"]: s["transformed"] += 1
    if r["rendered"]:    s["rendered"] += 1

OUT.write_text(json.dumps({"stats": stats, "articles": rows}, ensure_ascii=False, indent=2),
               encoding="utf-8")
print(f"Saved → {OUT}")
for k, v in stats.items():
    if k != "by_section":
        print(f"  {k}: {v}")
print("  by_section:")
for s, v in stats["by_section"].items():
    print(f"    {s}: {v}")

"""§2.2 enrich_zohar — пересобрать zohar_index.json из РЕПО zohar-sulam.

Источник истины — готовый HTML соседнего репозитория `imyavel/zohar-sulam`
(исходный пайплайн НЕ воскрешаем). На каждую главу:
  • human / kniga_slug / kniga_human  — из JSON-LD BreadcrumbList первой статьи;
  • article_count, para_min, para_max;
  • articles{N: title}                — из <title> каждой NNN.html;
  • paras{"§": "N"}                   — карта параграф→статья (для {глава||§}).

Выход → cms-revival/editor/data/zohar_index.json (+ копия в docs/editor/data/).
build_views.mjs синкает тот же файл в docs при пересборке вью.

Запуск:  python cms-revival/editor/build_zohar_index.py
"""
from __future__ import annotations
import io
import json
import re
import sys
import glob
import datetime as dt
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

HERE = Path(__file__).resolve().parent              # cms-revival/editor
DATA = HERE / "data"
DOCS_DATA = HERE.parents[1] / "docs" / "editor" / "data"

# zohar-sulam рядом с yaniktoim (imyavel/zohar-sulam)
ZOHAR = HERE.parents[2] / "zohar-sulam"
if not ZOHAR.exists():
    ZOHAR = Path(r"C:\Users\admin\imyavel\zohar-sulam")

URL_BASE = "https://imyavel.github.io/zohar-sulam"

TITLE_RX = re.compile(r"<title>\s*Статья\s+(\d+)\.\s*(.+?)\s*</title>", re.S)
PARA_RX = re.compile(r'<p class="para-start"(?:\s+id="p\d+")?>\s*(\d+)\)')
JSONLD_RX = re.compile(
    r'<script\s+type="application/ld\+json"[^>]*>\s*(\{.*?"BreadcrumbList".*?\})\s*</script>',
    re.S)
NUM_RX = re.compile(r"^\d{3}$")


def slug_from_url(url: str) -> str:
    m = re.search(r"/([^/]+)/(?:index\.html|\d+\.html)?/?$", url)
    return m.group(1) if m else ""


def breadcrumbs(html: str) -> list[dict]:
    m = JSONLD_RX.search(html)
    if not m:
        return []
    try:
        items = json.loads(m.group(1)).get("itemListElement") or []
    except json.JSONDecodeError:
        return []
    return [{"name": it.get("name", ""), "item": it.get("item", "")} for it in items]


def chapter_dirs() -> list[Path]:
    excluded = {"pagefind", "__pycache__", "tools", ".git"}
    return sorted(
        p for p in ZOHAR.iterdir()
        if p.is_dir() and not p.name.startswith("kniga-")
        and not p.name.startswith(".") and p.name not in excluded
        and glob.glob(str(p / "[0-9][0-9][0-9].html")))


def main() -> int:
    if not ZOHAR.exists():
        print(f"ERROR: zohar-sulam не найден: {ZOHAR}", file=sys.stderr)
        return 1

    chapters: dict[str, dict] = {}
    articles: dict[str, dict] = {}
    paras: dict[str, dict] = {}

    for cdir in chapter_dirs():
        slug = cdir.name
        files = sorted(p for p in cdir.glob("*.html") if NUM_RX.match(p.stem))
        if not files:
            continue

        first = files[0].read_text(encoding="utf-8", errors="replace")
        bc = breadcrumbs(first)
        meta = {"human": "", "kniga_slug": "", "kniga_human": ""}
        if len(bc) >= 3:
            meta["kniga_human"] = bc[1]["name"]
            meta["kniga_slug"] = slug_from_url(bc[1]["item"])
            meta["human"] = bc[2]["name"]

        arts: dict[str, str] = {}
        pmap: dict[str, str] = {}
        pmin, pmax = 10**9, 0
        dup = []
        for fp in files:
            html = fp.read_text(encoding="utf-8", errors="replace")
            n = str(int(fp.stem))
            mt = TITLE_RX.search(html)
            if mt:
                arts[n] = mt.group(2).strip()
            for pg in PARA_RX.findall(html):
                if pg in pmap and pmap[pg] != n:
                    dup.append(pg)
                pmap[pg] = n
                pi = int(pg)
                pmin, pmax = min(pmin, pi), max(pmax, pi)
        if dup:
            print(f"  WARN {slug}: дубль § {sorted(set(dup))[:5]}… "
                  f"({len(dup)}) — {{глава||§}} будет неоднозначен!")

        meta["article_count"] = len(arts)
        meta["para_min"] = pmin if arts else 0
        meta["para_max"] = pmax
        chapters[slug] = meta
        articles[slug] = arts
        paras[slug] = pmap
        print(f"  · {slug:14s} {len(arts):3d} статей, §{pmin}–{pmax}, "
              f"{len(pmap)} параграфов")

    index = {
        "_source": str(ZOHAR),
        "_url_base": URL_BASE,
        "_compiled_at": dt.datetime.now().isoformat(timespec="seconds"),
        "chapters": chapters,
        "articles": articles,
        "paras": paras,
    }
    blob = json.dumps(index, ensure_ascii=False, indent=2)
    (DATA / "zohar_index.json").write_text(blob, encoding="utf-8")
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    (DOCS_DATA / "zohar_index.json").write_text(blob, encoding="utf-8")

    total_arts = sum(len(v) for v in articles.values())
    total_paras = sum(len(v) for v in paras.values())
    print(f"\nГлав: {len(chapters)} · статей: {total_arts} · параграфов: {total_paras}")
    print(f"Записано: {DATA/'zohar_index.json'}")
    print(f"          {DOCS_DATA/'zohar_index.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

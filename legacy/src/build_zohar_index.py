"""Собрать `_logs/zohar_index.json` из локального корпуса
`C:\\Users\\admin\\Heb\\Translated\\Site\\`.

Новая структура zohar-sulam (2026-05-28): URL = `<chapter_slug>/<NNN>.html`
(NNN padded к 3 цифрам). У каждой главы есть человеческое имя из breadcrumbs
JSON-LD внутри страницы. Помимо chapter-уровня есть kniga-уровень
(например `kniga-akdama` → «Введение (Акдама)»), нужный для красивого
резолвинга в нашем рендере.

Результирующий JSON:
{
  "_source": ".../Heb/Translated/Site/",
  "_url_base": "https://imyavel.github.io/zohar-sulam",
  "_compiled_at": "YYYY-MM-DDTHH:MM:SS",
  "chapters": {
    "akdama": {
      "human": "Акдама (Предисловие)",
      "kniga_slug": "kniga-akdama",
      "kniga_human": "Введение (Акдама)",
      "article_count": 34
    },
    ...
  },
  "articles": {
    "akdama": { "1": "Заголовок", "4": "«МИ бара ЭЛЕ» Элияhу", ... },
    ...
  }
}

Резолвинг `{akdama|4}` в нашем `4_render.py`:
  human = "Книга Зоар. " + chapters[akdama].kniga_human + ". " + articles[akdama]["4"]
        → "Книга Зоар. Введение (Акдама). «МИ бара ЭЛЕ» Элияhу"
  href  = url_base + "/akdama/004.html"
"""
from __future__ import annotations
import io
import json
import re
import sys
import datetime as dt
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]
SITE = Path(r"C:\Users\admin\Heb\Translated\Site")
OUT = ROOT / "_logs" / "zohar_index.json"
URL_BASE = "https://imyavel.github.io/zohar-sulam"

# Внутри статьи: <title>Статья N. <human></title>.
ARTICLE_TITLE_RX = re.compile(
    r"<title>\s*Статья\s+(\d+)\.\s*(.+?)\s*</title>",
    re.IGNORECASE | re.DOTALL,
)

# JSON-LD блок BreadcrumbList.
JSONLD_RX = re.compile(
    r'<script\s+type="application/ld\+json"[^>]*>\s*(\{.*?"BreadcrumbList".*?\})\s*</script>',
    re.IGNORECASE | re.DOTALL,
)

NUM_RX = re.compile(r"^\d{3}$")


def parse_breadcrumbs(html: str) -> list[dict]:
    """Извлечь [{name, item}, ...] из JSON-LD BreadcrumbList на странице."""
    m = JSONLD_RX.search(html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    items = data.get("itemListElement") or []
    return [
        {"name": it.get("name", ""), "item": it.get("item", "")}
        for it in items
    ]


def slug_from_url(url: str) -> str:
    """URL `…/akdama/index.html` или `…/kniga-akdama/index.html` → `akdama` / `kniga-akdama`."""
    # Берём последний значимый сегмент пути перед `/index.html` или `/NNN.html`.
    m = re.search(r"/([^/]+)/(?:index\.html|\d+\.html)/?$", url)
    if m:
        return m.group(1)
    # Fallback: последний сегмент перед `/`.
    parts = [p for p in url.rstrip("/").split("/") if p]
    return parts[-1] if parts else ""


def collect_chapter(chapter_dir: Path) -> tuple[dict, dict]:
    """Пройти все NNN.html в одной chapter-папке.
    Returns (meta, articles_map) где
      meta = {"human": ..., "kniga_slug": ..., "kniga_human": ...}
      articles_map = {"4": "«МИ бара ЭЛЕ» Элияhу", ...}
    """
    files = sorted(p for p in chapter_dir.glob("*.html")
                   if NUM_RX.match(p.stem))
    if not files:
        return {}, {}

    articles: dict[str, str] = {}
    meta = {"human": "", "kniga_slug": "", "kniga_human": ""}

    # Берём breadcrumbs из первого NNN.html — они одинаковые в пределах главы.
    first_html = files[0].read_text(encoding="utf-8", errors="replace")
    bc = parse_breadcrumbs(first_html)
    # bc обычно: [Главная, <Книга>, <Глава>, <Статья N>]
    # Используем элементы 2 и 3 (после "Главная") если они есть.
    if len(bc) >= 3:
        kniga = bc[1]
        chapter = bc[2]
        meta["kniga_human"] = kniga["name"]
        meta["kniga_slug"] = slug_from_url(kniga["item"])
        meta["human"] = chapter["name"]

    for fp in files:
        html = fp.read_text(encoding="utf-8", errors="replace")
        m = ARTICLE_TITLE_RX.search(html)
        if not m:
            print(f"  WARN: {fp.relative_to(SITE)} — title не распознан")
            continue
        n = str(int(m.group(1)))  # без leading zeros в key
        articles[n] = m.group(2).strip()

    return meta, articles


def main() -> int:
    if not SITE.exists():
        print(f"ERROR: corpus directory not found: {SITE}", file=sys.stderr)
        return 1

    # Главы = подпапки в Site/, чьё имя не начинается на 'kniga-' и не служебное.
    excluded = {"pagefind", "__pycache__"}
    chapter_dirs = sorted(
        p for p in SITE.iterdir()
        if p.is_dir() and not p.name.startswith("kniga-")
        and p.name not in excluded
    )
    print(f"Found {len(chapter_dirs)} chapter directories", flush=True)

    chapters: dict[str, dict] = {}
    articles: dict[str, dict[str, str]] = {}

    for cdir in chapter_dirs:
        slug = cdir.name
        print(f"  · {slug:25s}", end="")
        meta, articles_map = collect_chapter(cdir)
        if not articles_map:
            print("  (no articles)")
            continue
        meta["article_count"] = len(articles_map)
        chapters[slug] = meta
        articles[slug] = articles_map
        print(f"  → {len(articles_map):3d} articles, "
              f"kniga={meta['kniga_slug'] or '?'}")

    index = {
        "_source": str(SITE),
        "_url_base": URL_BASE,
        "_compiled_at": dt.datetime.now().isoformat(timespec="seconds"),
        "chapters": chapters,
        "articles": articles,
    }

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    total_articles = sum(len(v) for v in articles.values())
    print(f"\nWrote {OUT}")
    print(f"  chapters: {len(chapters)}")
    print(f"  articles: {total_articles}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

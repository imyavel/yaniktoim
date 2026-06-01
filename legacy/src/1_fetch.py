"""Скачать корпус agent017 с proza.ru через залогиненную сессию (cookies.txt).

Идём по 6 книгам + странице автора (избранное). Собираем уникальные URL,
скачиваем HTML каждой статьи (cp1251 → utf-8) и первую <img> в .maintext.

Структура вывода:
  raw/<URL_STEM>.html     — например 2024_01_06_1439.html
  raw/<URL_STEM>.jpg      — иллюстрация, если есть и доступна
  raw/_corpus.json        — { url_stem: {url, section_slug, html_path, img_path, title?} }

Идентификация раздела:
  Книги 17/24/13/16/25/20 → dreamon/cyberson/dabudet/confront/shoshana/other
  Статьи с авторской "Избранное" → best (только те что НЕ встретились ни в одной книге)
"""
from __future__ import annotations
import io, os, re, sys, time, json
from pathlib import Path
from http.cookiejar import MozillaCookieJar
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
COOKIES = RAW / "proza_cookies.txt"
CORPUS_JSON = RAW / "_corpus.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

SECTIONS = [
    ("dreamon",  17, "Мечтай!!"),
    ("cyberson", 24, "Киберсон"),
    ("dabudet",  13, "Да будет Свет!"),
    ("confront", 16, "Конфронтология Духа"),
    ("shoshana", 25, "Роза Среди Шипов"),
    ("other",    20, "Без категории"),
]

ART_RE = re.compile(r'<a href="(/\d{4}/\d{2}/\d{2}/\d+)" class="poemlink">([^<]+)</a>')
IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)


def session() -> requests.Session:
    jar = MozillaCookieJar(str(COOKIES)); jar.load(ignore_discard=True, ignore_expires=True)
    s = requests.Session(); s.cookies = jar
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": "https://proza.ru/avtor/agent017",
    })
    return s


def get_html(s: requests.Session, url: str) -> str:
    for attempt in range(3):
        try:
            r = s.get(url, timeout=30)
            if r.ok:
                return r.content.decode("cp1251", errors="replace")
            print(f"  status {r.status_code} on {url}, retry")
        except requests.RequestException as e:
            print(f"  request error: {e}, retry")
        time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}")


def list_book(s: requests.Session, book: int) -> list[tuple[str, str]]:
    """Return list of (path, title) for all articles in a given book."""
    url = f"https://proza.ru/avtor/agent017&book={book}"
    html = get_html(s, url)
    pairs = ART_RE.findall(html)
    # dedupe while keeping order
    seen = set(); out = []
    for p, t in pairs:
        if p not in seen:
            seen.add(p); out.append((p, t))
    return out


def list_favorites(s: requests.Session) -> list[tuple[str, str]]:
    """Return list of (path, title) on the author landing page (favorites)."""
    url = "https://proza.ru/avtor/agent017"
    html = get_html(s, url)
    pairs = ART_RE.findall(html)
    seen = set(); out = []
    for p, t in pairs:
        if p not in seen:
            seen.add(p); out.append((p, t))
    return out


def find_first_img(html: str) -> str | None:
    """Return absolute URL of the first content image inside .maintext."""
    m = re.search(r'<div\s+class="maintext">(.*?)<div\s+id="footer"', html, re.S)
    body = m.group(1) if m else html
    for m in IMG_RE.finditer(body):
        src = m.group(1)
        if src.startswith(("data:", "/images/")) or src.endswith(".svg"):
            continue
        if src.startswith("//"):
            return "https:" + src
        if src.startswith("/"):
            return "https://proza.ru" + src
        if src.startswith("http"):
            return src
        return "https://proza.ru/" + src
    return None


def url_stem(path: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", path).strip("_")


def main():
    s = session()
    print(f"Loaded {sum(1 for _ in s.cookies)} cookies.")

    # 1) Collect URL → section_slug map from 6 books.
    url_to_section: dict[str, str] = {}
    titles: dict[str, str] = {}
    for slug, book, name in SECTIONS:
        articles = list_book(s, book)
        print(f"  {slug} ({name}, book={book}): {len(articles)} articles")
        for path, title in articles:
            url_to_section[path] = slug
            titles[path] = title.strip()

    # 2) Author landing page → favorites (best). Only those NOT yet assigned go to 'best'.
    favs = list_favorites(s)
    new_in_best = 0
    for path, title in favs:
        if path not in url_to_section:
            url_to_section[path] = "best"
            titles[path] = title.strip()
            new_in_best += 1
    print(f"  best (unique on landing page): {new_in_best}")

    print(f"Total unique articles: {len(url_to_section)}")
    if len(url_to_section) != 350:
        print(f"  WARNING: expected 350, got {len(url_to_section)}")

    # 3) Download HTML + first image for each.
    corpus: dict = {}
    sorted_paths = sorted(url_to_section.keys())
    for i, path in enumerate(sorted_paths, 1):
        stem = url_stem(path)
        section = url_to_section[path]
        title = titles[path]
        html_path = RAW / f"{stem}.html"
        img_path = None
        if html_path.exists():
            html = html_path.read_text(encoding="utf-8")
            # keep image discovery idempotent: skip image refetch if file already there
            existing_imgs = list(RAW.glob(f"{stem}.*"))
            existing_imgs = [p for p in existing_imgs if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp")]
            if existing_imgs:
                img_path = existing_imgs[0].name
        else:
            url = "https://proza.ru" + path
            html = get_html(s, url)
            html_path.write_text(html, encoding="utf-8")
            # First image
            img_url = find_first_img(html)
            if img_url:
                try:
                    rb = s.get(img_url, timeout=30)
                    if rb.ok and rb.content:
                        ext = os.path.splitext(img_url.split("?", 1)[0])[1].lower()
                        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                            ct = rb.headers.get("Content-Type", "").lower()
                            ext = ".jpg" if "jpeg" in ct else ".png" if "png" in ct else ""
                        if ext:
                            (RAW / f"{stem}{ext}").write_bytes(rb.content)
                            img_path = f"{stem}{ext}"
                except requests.RequestException as e:
                    print(f"    img err: {e}")
            time.sleep(0.6)  # be gentle to proza.ru
        corpus[stem] = {
            "url": "https://proza.ru" + path,
            "path": path,
            "section": section,
            "title": title,
            "html": html_path.name,
            "img": img_path,
        }
        if i % 25 == 0 or i == len(sorted_paths):
            print(f"  {i}/{len(sorted_paths)}: {stem} ({section}) img={img_path}")

    CORPUS_JSON.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved manifest of {len(corpus)} entries → {CORPUS_JSON}")


if __name__ == "__main__":
    main()

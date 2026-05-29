"""Add-on: paginate large sections (&s=50, &s=100, …), also probe unseen books.

Idempotent: skips HTML/img that already exist in raw/.
Updates raw/_corpus.json by merging.
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

# Sections + an extra probe for book=26 (saw a stray link on book=16 listing).
SECTIONS = [
    ("dreamon",  17, "Мечтай!!"),
    ("cyberson", 24, "Киберсон"),
    ("dabudet",  13, "Да будет Свет!"),
    ("confront", 16, "Конфронтология Духа"),
    ("shoshana", 25, "Роза Среди Шипов"),
    ("other",    20, "Без категории"),
    ("probe26",  26, "(unknown book=26)"),
]
ART_RE = re.compile(r'<a href="(/\d{4}/\d{2}/\d{2}/\d+)" class="poemlink">([^<]+)</a>')
IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)


def session():
    jar = MozillaCookieJar(str(COOKIES)); jar.load(ignore_discard=True, ignore_expires=True)
    s = requests.Session(); s.cookies = jar
    s.headers.update({"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9",
                      "Referer": "https://proza.ru/avtor/agent017"})
    return s


def get_html(s, url):
    for attempt in range(3):
        try:
            r = s.get(url, timeout=30)
            if r.ok:
                return r.content.decode("cp1251", errors="replace")
            print(f"  {r.status_code} on {url}, retry")
        except requests.RequestException as e:
            print(f"  err: {e}")
        time.sleep(2 ** attempt)
    return None


def find_first_img(html):
    m = re.search(r'<div\s+class="maintext">(.*?)<div\s+id="footer"', html, re.S)
    body = m.group(1) if m else html
    for m in IMG_RE.finditer(body):
        src = m.group(1)
        if src.startswith(("data:", "/images/")) or src.endswith(".svg"):
            continue
        if src.startswith("//"): return "https:" + src
        if src.startswith("/"):  return "https://proza.ru" + src
        if src.startswith("http"): return src
        return "https://proza.ru/" + src
    return None


def url_stem(path): return re.sub(r"[^0-9A-Za-z]+", "_", path).strip("_")


def main():
    s = session()
    corpus = json.loads(CORPUS_JSON.read_text(encoding="utf-8")) if CORPUS_JSON.exists() else {}
    existing_paths = {meta["path"] for meta in corpus.values()}
    print(f"existing: {len(existing_paths)}")
    new_pairs: list[tuple[str, str, str]] = []  # (slug, path, title)
    for slug, book, name in SECTIONS:
        for offset in (0, 50, 100, 150):
            url = f"https://proza.ru/avtor/agent017&s={offset}&book={book}" if offset else f"https://proza.ru/avtor/agent017&book={book}"
            html = get_html(s, url)
            if not html:
                break
            pairs = ART_RE.findall(html)
            new_here = [(p, t) for p, t in pairs if p not in existing_paths]
            print(f"  {slug} book={book} s={offset}: {len(pairs)} total, {len(new_here)} new")
            if not pairs:
                break
            for p, t in new_here:
                new_pairs.append((slug if slug != "probe26" else "other", p, t.strip()))
                existing_paths.add(p)
            if len(pairs) < 50:  # last page reached
                break
            time.sleep(0.4)

    print(f"new to fetch: {len(new_pairs)}")
    for i, (slug, path, title) in enumerate(new_pairs, 1):
        stem = url_stem(path)
        html_path = RAW / f"{stem}.html"
        img_name = None
        if html_path.exists():
            html = html_path.read_text(encoding="utf-8")
            for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                if (RAW / f"{stem}{ext}").exists():
                    img_name = f"{stem}{ext}"; break
        else:
            html = get_html(s, "https://proza.ru" + path)
            if html is None:
                continue
            html_path.write_text(html, encoding="utf-8")
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
                            img_name = f"{stem}{ext}"
                except requests.RequestException as e:
                    print(f"    img err: {e}")
            time.sleep(0.4)
        corpus[stem] = {
            "url": "https://proza.ru" + path,
            "path": path,
            "section": slug,
            "title": title,
            "html": html_path.name,
            "img": img_name,
        }
        if i % 20 == 0 or i == len(new_pairs):
            print(f"  {i}/{len(new_pairs)}: {stem} ({slug})")
    CORPUS_JSON.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Total in corpus now: {len(corpus)}")


if __name__ == "__main__":
    main()

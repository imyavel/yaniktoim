# -*- coding: utf-8 -*-
"""Music-canon recon: сверяет [mus]-треки корпуса с базой-истиной songs/index.html.

База-истина = docs/songs/index.html: 220 карточек, каждая `<p class="t">Название — Автор</p>`
+ `data-id="<ytid>"` (канон-ориентация «Название — Автор», подтверждён оператором).

Для каждого трека из out/*.zml извлекаем YT-id и текущие слоты (title=поле2, author=поле3),
сматчиваем по id с базой и классифицируем ориентацию:
  MATCH    — текущие (title,author) совпадают с каноном базы → флип render даст «Назв — Авт» ✓
  REVERSED — текущие слоты перевёрнуты (combo-hack) → нужно поменять местами в ZML
  DIFF     — оба поля есть, но не совпадают ни прямо ни наоборот (нормализация/опечатка) → глянуть
  NODB     — id не в базе (или нет YT-id) → дизамбигуация эвристикой/веб-поиском/пометкой
"""
import re, glob, os, sys, io, json, html as _html
from difflib import SequenceMatcher
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))
SONGS = os.path.join(ROOT, "..", "..", "yaniktoim", "docs", "songs", "index.html")
OUT = os.path.join(ROOT, "out")

def yt_id(u):
    if not u:
        return None
    m = re.search(r"(?:v=|youtu\.be/|youtube\.com/embed/|/vi/)([A-Za-z0-9_-]{11})", u)
    return m.group(1) if m else None

JUNK_RX = re.compile(r"^\s*(youtube|слушать(\s+на\s+youtube)?|трек под настроени[ея]|"
                     r"видео( к части)?|музыка( в тему| под настроени[ея])?|"
                     r"www\.youtube|youtu\.be|https?:|►\s*youtube)", re.I)

def is_junk(s):
    """Слот несёт UI-мусор/ссылку вместо названия/автора."""
    t = (s or "").strip()
    return (not t) or bool(JUNK_RX.match(t)) or t in ("▶ YouTube", "^")

def norm(s):
    """Нормализация для сравнения: html-unescape, ё→е, убрать сноски/скобки/пунктуацию."""
    s = _html.unescape(s or "").lower().replace("ё", "е")
    s = re.sub(r"\[\^[^\]]+\]", " ", s)          # маркеры сносок
    s = re.sub(r"\([^)]*\)", " ", s)             # скобочные аннотации
    s = re.sub(r"[«»\"'`.,!?·…—–-]+", " ", s)    # пунктуация/тире/разделители
    s = re.sub(r"\s+", " ", s).strip()
    return s

def sim(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()

# ── база-истина из songs/index.html ──
html = open(SONGS, encoding="utf-8").read()
DB = {}   # ytid → (title, author) — html-unescaped
for fig in re.findall(r'<figure class="song">.*?</figure>', html, re.S):
    mid = re.search(r'data-id="([A-Za-z0-9_-]{11})"', fig)
    mt = re.search(r'<p class="t">(.*?)</p>', fig, re.S)
    if not mid or not mt:
        continue
    t = _html.unescape(re.sub(r"<[^>]+>", "", mt.group(1)).strip())
    if " — " in t:
        title, author = t.split(" — ", 1)
    else:
        title, author = t, ""
    DB[mid.group(1)] = (title.strip(), author.strip())

print("=== база-истина songs: %d карточек с id ===" % len(DB))

def resolve(ct, ca, dt, da):
    """Возвращает (action, final_title, final_author). Чиним ОРИЕНТАЦИЮ (slot2=название),
    текст статьи сохраняем; мусорные/пустые слоты заполняем из базы."""
    jt, ja = is_junk(ct), is_junk(ca)
    if not jt and not ja:                       # оба слота содержательны
        keep = sim(ct, dt) + sim(ca, da)
        swap = sim(ct, da) + sim(ca, dt)
        if swap > keep + 0.20:
            return ("SWAP", ca, ct)             # перевёрнуто → меняем местами (текст статьи)
        return ("KEEP", ct, ca)
    if jt and ja:                               # оба мусор/пусто → берём базу целиком
        return ("FILLBOTH", dt, da)
    good = ca if jt else ct                     # единственный содержательный слот
    # он — название или автор? сравниваем с базой
    if sim(good, da) > sim(good, dt) + 0.10:
        return ("FILL", dt, good)               # содержательное было автором
    return ("FILL", good, da)                   # норма: содержательное = название, автор из базы

# ── треки корпуса ──
ACTIONS = {"KEEP": [], "SWAP": [], "FILL": [], "FILLBOTH": [], "NODB": []}
total = 0
art_changes = {}   # art → [(action, vid, cur, target)]

for path in sorted(glob.glob(os.path.join(OUT, "*.zml"))):
    art = os.path.basename(path)[:-4]
    txt = open(path, encoding="utf-8").read()
    in_mus = False
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("[mus"):
            in_mus = True; continue
        if s == "[/mus]":
            in_mus = False; continue
        if not in_mus:
            continue
        if not (s.startswith("[") and s.endswith("]") and "|" in s):
            continue
        parts = s[1:-1].split("|")
        url = parts[0]
        title = parts[1] if len(parts) > 1 else ""
        if len(parts) >= 4 and parts[-1].isdigit():
            author = "|".join(parts[2:-1])
        else:
            author = "|".join(parts[2:]) if len(parts) > 2 else ""
        total += 1
        vid = yt_id(url)
        if vid and vid in DB:
            dt, da = DB[vid]
            action, ft, fa = resolve(title, author, dt, da)
            ACTIONS[action].append((art, vid, title, author, ft, fa))
            if action != "KEEP":
                art_changes.setdefault(art, []).append((action, vid, "%s | %s" % (title, author), "%s | %s" % (ft, fa)))
        else:
            ACTIONS["NODB"].append((art, vid, title, author))
            art_changes.setdefault(art, []).append(("NODB", vid, "%s | %s" % (title, author), ""))

print("=== треков всего: %d ===" % total)
for k in ("KEEP", "SWAP", "FILL", "FILLBOTH", "NODB"):
    print("  %-9s %d" % (k, len(ACTIONS[k])))

def dump(cat, hdr):
    print("\n=== %s — %d ===" % (hdr, len(ACTIONS[cat])))
    for row in ACTIONS[cat]:
        if cat == "NODB":
            art, vid, t, a = row
            print("  %-7s [%s] '%s | %s'" % (art, vid or "—", t, a))
        else:
            art, vid, t, a, ft, fa = row
            print("  %-7s [%s] '%s | %s'  →  '%s | %s'" % (art, vid, t, a, ft, fa))

dump("SWAP", "SWAP (ориентация перевёрнута → меняем слоты)")
dump("FILLBOTH", "FILLBOTH (оба слота мусор/пусто → берём базу)")
dump("FILL", "FILL (один слот мусор/пусто → дозаполняем из базы)")
dump("NODB", "NODB (нет в базе — дизамбигуация/пометка)")

print("\n=== статей с изменениями: %d ===" % len(art_changes))
json.dump({"actions": {k: len(v) for k, v in ACTIONS.items()}, "total": total,
           "art_changes": {a: art_changes[a] for a in sorted(art_changes)}},
          open(os.path.join(ROOT, "music_canon_recon.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

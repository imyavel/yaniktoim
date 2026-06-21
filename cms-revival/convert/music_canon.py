# -*- coding: utf-8 -*-
"""Музыка-канон «Название — Автор»: оркестрация слотов трек-карточек.

Оракул-ориентации = `yaniktoim/docs/songs/index.html` (220 карточек «Название — Автор»,
канон подтверждён оператором) + `music_canon_overrides.json` (ручные/LLM-вердикты для
треков вне базы и точечные правки глитчей базы).

Принцип (прецедент roadmap «158 Обман|Ария· = уже-канон»): СОХРАНЯЕМ текст статьи, чиним
только ОРИЕНТАЦИЮ (slot2=название), дозаполняем пустые/мусорные слоты, расщепляем склейки.
Терсе-версией базы текст НЕ затираем; 1CM-стиль «Артист. Название. Перевод…» — faithful-лейбл.

API: canonicalize(url, title, author) -> (title, author, action).
Импортируется конвертером (html_to_zml.py, emit_music) и применяется к каждому треку.
"""
import re, os, json, html as _html, unicodedata
from difflib import SequenceMatcher


def _fold(s):
    """Снять латинские диакритики: Oxygène→Oxygene, Noubliez→Noubliez (база vs статья)."""
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn")

_HERE = os.path.dirname(os.path.abspath(__file__))
_SONGS = os.path.join(_HERE, "..", "..", "yaniktoim", "docs", "songs", "index.html")
_OVERRIDES = os.path.join(_HERE, "music_canon_overrides.json")

_MARK_RX = re.compile(r"\[\^[^\]]+\]")
_URL_RX = re.compile(r"(?:https?://|www\.youtube|youtu\.be/|youtube\.com/)\S*", re.I)
# плейсхолдер-подпись целиком (после снятия url/«youtube»): «трек под настроение» и т.п.
_PLACE_RX = re.compile(
    r"(трек под настроени[ея]|музыка( в тему| под настроени[ея]| в теме)?|"
    r"видео([- ]?пандан| к части| в тему)?|под настроение|"
    r"слушать(\s+(на|онлайн))?|смотреть(\s+(на|онлайн))?|в тему)"
    r"(\s*\([^)]*\))?", re.I)


def _strip_urls(s):
    return _URL_RX.sub("", s or "").strip()


def is_junk(s):
    """Слот несёт UI-мусор/ссылку/плейсхолдер вместо названия/автора."""
    t = _html.unescape(s or "").strip()
    if not t or t in ("▶ YouTube", "^", "—", "-", "|"):
        return True
    t = _strip_urls(t)
    t = re.sub(r"\byoutube\b", "", t, flags=re.I).strip(" :|–—-")
    if not t:                                   # был только url / «YouTube»
        return True
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", t):   # голый YT-id как «название» (165A)
        return True
    if re.match(r"(музыка|трек)?\s*под настроени[ея]", t, re.I):  # «…под настроение …» = подпись
        return True
    return bool(_PLACE_RX.fullmatch(t))


def _markers(s):
    """('текст без маркеров', ['[^N]', …]) — маркеры сносок снимаются для сравнения."""
    marks = _MARK_RX.findall(s or "")
    return _MARK_RX.sub("", s or "").strip(), marks


def norm(s):
    s = _fold(_html.unescape(s or "")).lower().replace("ё", "е")
    s = _MARK_RX.sub(" ", s)
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[«»\"'`.,!?:·…—–\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def sim(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def yt_id(u):
    if not u:
        return None
    m = re.search(r"(?:v=|youtu\.be/|youtube\.com/embed/|/vi/)([A-Za-z0-9_-]{11})", u)
    return m.group(1) if m else None


# ── загрузка оракула (ленивая, один раз) ──
_DB = None


def _load_db():
    global _DB
    if _DB is not None:
        return _DB
    db = {}
    try:
        htm = open(_SONGS, encoding="utf-8").read()
        for fig in re.findall(r'<figure class="song">.*?</figure>', htm, re.S):
            mid = re.search(r'data-id="([A-Za-z0-9_-]{11})"', fig)
            mt = re.search(r'<p class="t">(.*?)</p>', fig, re.S)
            if not mid or not mt:
                continue
            t = _html.unescape(re.sub(r"<[^>]+>", "", mt.group(1)).strip())
            title, author = (t.split(" — ", 1) + [""])[:2] if " — " in t else (t, "")
            db[mid.group(1)] = (title.strip(), author.strip())
    except FileNotFoundError:
        pass
    # overrides: {ytid: {"title":..,"author":..}} — побеждают базу
    try:
        ov = json.load(open(_OVERRIDES, encoding="utf-8"))
        for vid, rec in ov.get("tracks", {}).items():
            db[vid] = (rec.get("title", "").strip(), rec.get("author", "").strip())
    except FileNotFoundError:
        pass
    _DB = db
    return db


def _split_combo(text, dt, da):
    """Склейка «Название<sep>Автор» в одном слоте → (title, author) с текстом статьи.
    Расщепляем ТОЛЬКО когда обе части уверенно ложатся на базу (floor на каждую) —
    иначе None (русские названия с запятой типа «Город, которого нет» не режем)."""
    FLOOR = 0.5
    best = None
    for sep in (" — ", " – ", " - ", "—", "–", ": ", ", ", ". "):
        if sep not in text:
            continue
        p, q = text.split(sep, 1)
        p, q = p.strip(), q.strip()
        if not p or not q or sep in q:        # >2 частей → не трогаем (1CM-лейблы)
            continue
        if re.search(r"перевод|youtu|http|\bвидео\b", q, re.I):
            continue
        keep = (sim(p, dt), sim(q, da))       # p=название, q=автор
        swap = (sim(p, da), sim(q, dt))       # p=автор, q=название
        if min(keep) >= FLOOR and sum(keep) >= sum(swap):
            cand = ((p, q), sum(keep))
        elif min(swap) >= FLOOR:
            cand = ((q, p), sum(swap))
        else:
            continue
        if not best or cand[1] > best[1]:
            best = cand
    return best[0] if best else None


# статьи с авторской курацией муз-секции (транслитерации/переводы) — держим faithful
_FAITHFUL_ARTS = {"1CM"}


_REV = None


def fill_url(title, author):
    """url-less трек → YouTube-url по совпадению (название[,автор]) с базой songs/overrides.
    '' если совпадения нет. Доборы (б): 237 «Дорогая передача», 31I «I Will Always Love You»."""
    global _REV
    if _REV is None:
        _REV = {}
        for vid, (t, a) in _load_db().items():
            _REV.setdefault((norm(t), norm(a)), vid)
            _REV.setdefault((norm(t), ""), vid)        # фолбэк по одному названию
    vid = _REV.get((norm(title), norm(author))) or _REV.get((norm(title), ""))
    return "https://youtu.be/%s" % vid if vid else ""


def canonicalize(url, title, author, art=None):
    """(title, author, action). action ∈ KEEP/SWAP/FILL/SPLIT/FILLBOTH/NODB."""
    db = _load_db()
    vid = yt_id(url)
    rec = db.get(vid) if vid else None

    t_txt, t_marks = _markers(title)
    a_txt, a_marks = _markers(author)
    t_txt, a_txt = _strip_urls(t_txt), _strip_urls(a_txt)    # вшитый url-мусор в полях (14U)
    jt, ja = is_junk(t_txt), is_junk(a_txt)

    def with_marks(s, marks):
        return s + "".join(marks) if marks else s

    if art in _FAITHFUL_ARTS:                                # курация автора → как есть
        return (title, author, "KEEP")

    if rec is None:
        return (title, author, "NODB")                       # вне базы → резолв в overrides

    dt, da = rec

    if not jt and not ja:                                    # оба слота содержательны
        keep = sim(t_txt, dt) + sim(a_txt, da)
        swap = sim(t_txt, da) + sim(a_txt, dt)
        if swap > keep + 0.20:
            return (with_marks(a_txt, a_marks), with_marks(t_txt, t_marks), "SWAP")
        return (title, author, "KEEP")

    if jt and ja:                                            # оба мусор/пусто → база
        return (with_marks(dt, t_marks + a_marks), da, "FILLBOTH")

    # ── один слот содержателен, другой пуст/мусор ──
    good_txt, good_marks = (t_txt, t_marks) if not jt else (a_txt, a_marks)

    # faithful-лейбл: авторская подпись с переводом / длинная фраза — НЕ трогаем (1CM)
    if re.search(r"перевод", good_txt, re.I) or len(good_txt.split()) > 7:
        return (with_marks(good_txt, good_marks), "", "KEEP")

    sp = _split_combo(good_txt, dt, da)                      # склейка «Назв<sep>Авт»?
    if sp:
        return (with_marks(sp[0], good_marks), sp[1], "SPLIT")

    # склейка без разделителя «Oxygene 7Jean-Michel Jarre» → база целиком
    nspace = norm(good_txt).replace(" ", "")
    if dt and da and norm(dt).replace(" ", "") in nspace and norm(da).replace(" ", "") in nspace:
        return (with_marks(dt, good_marks), da, "FILLBOTH")

    if sim(good_txt, da) > 0.8 and sim(good_txt, dt) < 0.4:
        return (dt, with_marks(good_txt, good_marks), "FILL")    # содержательное ≈ автор (редко)
    # автор уже в содержательном слоте (в т.ч. в скобках/транслите) → не дублируем
    if da and _fold(da).lower() not in _fold(good_txt).lower() and norm(da) not in norm(good_txt):
        return (with_marks(good_txt, good_marks), da, "FILL")    # норма: контент=назв, автор из базы
    return (with_marks(good_txt, good_marks), "", "KEEP")        # автор базы пуст/уже внутри


# ── self-test: прогон по корпусу out/*.zml, печать всех не-KEEP ──
if __name__ == "__main__":
    import glob, sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    OUT = os.path.join(_HERE, "out")
    counts = {}
    rows = []
    for path in sorted(glob.glob(os.path.join(OUT, "*.zml"))):
        art = os.path.basename(path)[:-4]
        in_mus = False
        for line in open(path, encoding="utf-8").read().splitlines():
            s = line.strip()
            if s.startswith("[mus"):
                in_mus = True; continue
            if s == "[/mus]":
                in_mus = False; continue
            if not in_mus or not (s.startswith("[") and s.endswith("]") and "|" in s):
                continue
            parts = s[1:-1].split("|")
            url = parts[0]
            title = parts[1] if len(parts) > 1 else ""
            if len(parts) >= 4 and parts[-1].isdigit():
                author = "|".join(parts[2:-1])
            else:
                author = "|".join(parts[2:]) if len(parts) > 2 else ""
            ft, fa, act = canonicalize(url, title, author, art)
            counts[act] = counts.get(act, 0) + 1
            if act != "KEEP":
                rows.append((act, art, "%s | %s" % (title, author), "%s | %s" % (ft, fa)))
    print("counts:", counts)
    for act in ("SWAP", "SPLIT", "FILL", "FILLBOTH", "NODB"):
        print("\n=== %s ===" % act)
        for a, art, cur, new in rows:
            if a == act:
                print("  %-7s '%s'  →  '%s'" % (art, cur, new))

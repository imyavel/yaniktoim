# -*- coding: utf-8 -*-
"""Строит черновик proper-nouns.txt ПО ДАННЫМ (вердикт оператора 2026-06-17):
для каждого слова — регистр в НЕ-капс АВТОРСКОМ тексте, середина предложения;
majority-cap → в список. Исключаем: статью roza_mira (др. автор), блоки [dlg]
(читатели/оппоненты) и [quote] (внешние источники), капс-строки, позиции начала
предложения / после . ! ? … : « — (форсированная заглавная).

Группировка по лемме (pymorphy3) ТОЛЬКО для счёта; БАЗА для списка = наблюдаемая
НОМИНАТИВНАЯ поверхностная форма (надёжнее garbled normal_form для ивр./арам.
терминов). Вывод: draft-список + review-таблица (ratio, counts, POS, формы)."""
import re, glob, os
from collections import defaultdict
import pymorphy3

morph = pymorphy3.MorphAnalyzer()
ART = "C:/Users/admin/imyavel/yaniktoim/docs/art"
SKIP_BLOCKS = {"dlg", "quote", "shir"}
CYR = re.compile(r"[А-Яа-яёЁ]")
WORD = re.compile(r"[А-ЯЁа-яё][А-ЯЁа-яё-]*")
TOKEN = re.compile(r"[А-ЯЁа-яё][А-ЯЁа-яё-]*|[.!?…:«»—–()\"]+")
BLOCK_OPEN = re.compile(r"^\[(\w+)")
INLINE = [(re.compile(r"\{(?:term|leit|[a-z]+)\|([^}]*)\}"), r"\1"),
          (re.compile(r"\[\[([^\]]*)\]\]"), " "), (re.compile(r"\[\^[^\]]*\]"), " "),
          (re.compile(r"\[[^\]|]*\|([^\]]*)\]"), r"\1"),
          (re.compile(r"\[/?spl[^\]]*\]"), " "), (re.compile(r"[_*]"), "")]
SENT_BREAK = set(".!?…:«—–")


def is_caps_line(s):
    L = CYR.findall(s)
    return len(L) >= 3 and sum(c.isupper() for c in L) / len(L) >= 0.70


def clean(s):
    for rx, rep in INLINE:
        s = rx.sub(rep, s)
    return s


cap = defaultdict(int)
low = defaultdict(int)
forms = defaultdict(lambda: defaultdict(int))   # lemma → surface → count (cap only)
nomn = defaultdict(lambda: defaultdict(int))     # lemma → nomn surface → count
pos_of = {}

for p in sorted(glob.glob(ART + "/*.zml")):
    art = os.path.basename(p)[:-4]
    if art == "roza_mira":
        continue
    body = open(p, encoding="utf-8").read().split("---", 2)[-1]
    skip = None
    for ln in body.split("\n"):
        st = ln.strip()
        if skip:
            if re.match(r"^\[/%s\]" % skip, st):
                skip = None
            continue
        mo = BLOCK_OPEN.match(st)
        if mo and mo.group(1) in SKIP_BLOCKS:
            skip = mo.group(1)
            continue
        if not st or st.startswith("#") or re.match(r"^\[\^[^\]]*\]:", st):
            continue
        if re.match(r"^\[/?\w+[^\]]*\]$", st) or (st.startswith("[") and "|" in st):
            continue
        text = clean(st)
        if is_caps_line(text):
            continue
        cap_next = True
        for tk in TOKEN.findall(text):
            if not WORD.match(tk):
                cap_next = bool(SENT_BREAK & set(tk))
                continue
            if not cap_next and len(re.sub(r"[^А-Яа-яёЁ]", "", tk)) >= 3:
                pr = morph.parse(tk)[0]
                lem = pr.normal_form
                pos_of[lem] = str(pr.tag.POS)
                if tk[0].isupper():
                    cap[lem] += 1
                    forms[lem][tk] += 1
                    if pr.tag.case == "nomn":
                        nomn[lem][tk] += 1
                else:
                    low[lem] += 1
            cap_next = False


FLEETING = {"ТВОРЕЦ", "ОРЁЛ", "ОТЕЦ", "КОНЕЦ", "ВЕНЕЦ"}  # беглая гласная — нужен номинатив


def best_base(lem):
    """→ (base, exact). База = LCP titlecase-форм (Свет/Света → СВЕТ; матчер
    pnStem+CASE_ENDINGS покрывает склонения). Если titlecase-форм НЕТ (слово всегда
    ALLCAPS — акроним/имя-в-капсе типа АВАЯ/ЧСВ/ГАР) → exact-only !ФОРМА. Беглая
    гласная (Творец/Орёл) — наблюдаемый номинатив."""
    tc = {f: n for f, n in forms[lem].items() if f != f.upper() and f[:1].isupper()}
    if not tc:  # всегда ALLCAPS → акроним/имя-в-капсе
        b = max(forms[lem], key=forms[lem].get) if forms[lem] else lem.upper()
        return b.upper(), True
    fs = [f.upper() for f in tc]
    nom = (max((f for f in nomn[lem] if f in tc), key=lambda f: nomn[lem][f], default=None)
           or max(tc, key=tc.get)).upper()
    if nom in FLEETING:
        return nom, False
    lcp = os.path.commonprefix(fs)
    return (lcp if len(re.sub(r"[^А-ЯЁ]", "", lcp)) >= 3 else nom), False


# служебные слова / OCR-мусор / нарицательные-ложноположительные (контекст-утечка)
STOP = {"итак", "коли", "домой", "даром", "кругом", "нафига", "вас", "тебя",
        "твой", "ваш", "ты", "вы", "он", "она", "они", "свыше", "пал-на", "эле",
        "бней", "сдпл", "мжоси", "абеа", "беа", "мад", "ввз", "вов", "кдс", "ксп",
        "пчф", "имя", "наука", "морг", "пруд", "программист", "стенограмма",
        "предисловие", "училка", "серебро", "реал", "рая", "корень", "земной",
        "снежный", "мировой", "дама", "кава", "гром", "атом", "джокер", "мастер",
        "ворона", "глагол", "бар", "коля", "хая", "хия", "аве", "абба", "введение",
        "самоуправление", "конгресс", "википедия", "космос"}
# прилагательные-основы: матчер заточен под падежи СУЩ., прил. покрывает лишь
# ЧАСТИЧНО (Высшей матчится, Высший нет → рассинхрон) → исключаем по основе.
# Гонорифик «Свят/Благословен» рисует applyHonorific отдельно — здесь не нужен.
DROP_BASE = {"ВЕТХИЙ", "ВЫСШ", "ВСЕСИЛЬН", "ВСЕМОГУЩ", "БОЖ", "ЖИВОТВОРЯЩ",
             "ЗНАЮЩ", "ВОСХОДЯЩ", "СВЯТ", "БЛАГОСЛОВЕН",
             "ВОВ", "РАЯ", "КОРНЕ", "ДУХОВНО-ПОЛОВОЙ", "БНЕЙ", "АВЕ", "ЭЛЕ",
             "НАФИГА", "МЖОСИ", "АВИ", "ПВИ", "ПВР", "АБ-САГ", "ЗАМЫС"}
# исправление основ (наблюдалась лишь косвенная форма → корректный номинатив-стем)
FIX = {"АЛЬФОЙ": "АЛЬФА", "ОМЕГОЙ": "ОМЕГА", "ЗМЕЕМ": "ЗМЕЙ", "АНИБЕ": "АНИБ",
       "МАШИАХА": "МАШИАХ", "ПУШКИНА": "ПУШКИН", "ЛЮБ": "ЛЮБОВЬ"}
CASE_ENDINGS = {"", "А", "Я", "У", "Ю", "Е", "Ы", "И", "О", "ОМ", "ЕМ", "ЁМ",
                "ОВ", "ЕВ", "АМ", "ЯМ", "АМИ", "ЯМИ", "АХ", "ЯХ", "ОЙ", "ЕЙ",
                "ОЮ", "ЕЮ", "Ь", "Й", "ИЕ", "ИЯ", "ИИ", "ИЕМ"}
rows = []
for lem in set(cap) | set(low):
    c, l = cap[lem], low[lem]
    if lem in STOP:
        continue
    if (c + l) >= 4 and c / (c + l) > 0.50:    # строгое большинство (вердикт оператора)
        rows.append((c / (c + l), c + l, c, l, lem))
rows.sort(reverse=True)

draft, review = {}, []
review.append("ratio  cap/low  exact BASE            (top forms)")
for ratio, tot, c, l, lem in rows:
    base, exact = best_base(lem)
    entry = ("!" + base) if exact else base
    tops = ", ".join(f"{w}:{n}" for w, n in sorted(forms[lem].items(), key=lambda x: -x[1])[:3])
    review.append("%.2f  %4d/%-4d %-3s   %-16s (%s)"
                  % (ratio, c, l, "EX" if exact else "", entry, tops))
    draft.setdefault(entry, (ratio, tot))

# ручное добивание канон-наборов (вердикт оператора 2026-06-17 «логично писать все
# с заглавной, если часть уже с заглавной»): сфирот и миры всегда с заглавной в
# авторском тексте, но недобрали порог частоты total≥4 (Хесед/Гвура 4/0, Нецах 2/0,
# Брия/Ецира 3/0). Ход НЕ добавлен: омоним с нарицательным «ход» (15 строчн./4 загл.),
# матчер их не различает (оба → ХОД) → ложно капитализировал бы «ход».
MANUAL_ADD = ["ХЕСЕД", "ГВУРА", "НЕЦАХ", "БРИЯ", "ЕЦИРА"]
for m in MANUAL_ADD:
    draft.setdefault(m, (1.0, 0))

# --- чистка ---
draft = {("!" + FIX[e[1:]] if e.startswith("!") and e[1:] in FIX else FIX.get(e, e)): v
         for e, v in draft.items()}
ents = [e for e in draft if e.strip("!") not in DROP_BASE]
plain = {e for e in ents if not e.startswith("!")}
# !X лишний, если есть обычный X
ents = [e for e in ents if not (e.startswith("!") and e[1:] in plain)]
# дедуп склонений: B = склонение A (B startswith A и хвост — падежное окончание) → drop B.
# Безопасно для Кол/Колесо/Кольцо (ЕС/ЬЦ — не окончания).
bases = sorted(plain, key=len)
redundant = set()
for i, a in enumerate(bases):
    for b in bases[i + 1:]:
        if b not in redundant and b.startswith(a) and b[len(a):] in CASE_ENDINGS:
            redundant.add(b)
final = sorted(e for e in ents if e not in redundant)
open("caps_review.txt", "w", encoding="utf-8").write("\n".join(review))
open("caps_draft.txt", "w", encoding="utf-8").write("\n".join(final))
print("итог: %d (!exact: %d), убрано склонений-дублей: %d"
      % (len(final), sum(1 for e in final if e.startswith("!")), len(redundant)))

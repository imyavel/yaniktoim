# -*- coding: utf-8 -*-
"""Разведка пополнения proper-nouns.txt: в НЕ-капс прозе слово, написанное с
Заглавной НЕ в начале предложения, — кандидат в имена собственные. Ранжируем по
числу СТАТЕЙ, где встретилось; флаг — покрыто ли текущим списком (по основе)."""
import re, glob, os
ROOT = "C:/Users/admin/imyavel"
LIST = open(ROOT + "/cms-revival/config/proper-nouns.txt", encoding="utf-8").read()
BASES = [re.sub(r"^!", "", l.strip()) for l in LIST.splitlines()
         if l.strip() and not l.startswith("#")]


def covered(word):
    u = word.upper()
    for b in BASES:
        # основа списка — префикс слова (склонение), мин. 4 буквы общих
        n = min(len(b), len(u))
        if n >= 4 and u[:n - 1] == b[:n - 1] and abs(len(u) - len(b)) <= 3:
            return True
    return False


def is_caps_line(s):
    letters = re.findall(r"[А-Яа-яёЁ]", s)
    if len(letters) < 3:
        return False
    return sum(c.isupper() for c in letters) / len(letters) >= 0.70


CAP = re.compile(r"(?<![.!?]\s)(?<![.!?]\s\s)\b([А-ЯЁ][а-яё]{2,})\b")
SENT_START = re.compile(r"(?:^|[.!?»]\s+|[:—-]\s+)$")

from collections import defaultdict
artcount = defaultdict(set)
for p in glob.glob(ROOT + "/yaniktoim/docs/art/*.zml"):
    art = os.path.basename(p)[:-4]
    body = open(p, encoding="utf-8").read().split("---", 2)[-1]
    for ln in body.split("\n"):
        s = ln.strip()
        if not s or s.startswith(("[", "#")) or re.match(r"^\[\^", s) or is_caps_line(s):
            continue
        s = re.sub(r"\{(?:term|leit|[a-z]+)\|([^}]*)\}", r"\1", s)
        s = re.sub(r"\[\[([^\]]*)\]\]|\[\^[^\]]*\]|\[[^\]|]*\|([^\]]*)\]|[_*]", " ", s)
        # пройтись по словам, отслеживая начало предложения
        toks = re.findall(r"[А-ЯЁа-яё][А-ЯЁа-яё-]*|[.!?:»—]", s)
        sent_start = True
        for tk in toks:
            if tk in ".!?:»—":
                sent_start = tk in ".!?"
                continue
            if not sent_start and re.match(r"^[А-ЯЁ][а-яё]{2,}$", tk):
                artcount[tk.upper()].add(art)
            sent_start = False

rows = sorted(((len(a), w) for w, a in artcount.items()), reverse=True)
print("=== mid-sentence Capitalized words by #articles (uncovered first) ===")
miss = [(n, w) for n, w in rows if not covered(w) and n >= 4]
for n, w in miss[:60]:
    print("  %3d  %s" % (n, w))
print("--- top COVERED (sanity) ---")
for n, w in [(n, w) for n, w in rows if covered(w)][:8]:
    print("  %3d  %s [covered]" % (n, w))

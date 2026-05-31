# -*- coding: utf-8 -*-
"""
Фикс prev/next ссылок в docs/art по глобальному порядку из index.html.
Логика порядка/извлечения идентична check_order.py. Меняется ТОЛЬКО значение
href в нужном якоре (prev и/или next); текст-метка не трогается.
"""
import re, os

DOCS = os.path.dirname(os.path.abspath(__file__))
ART  = os.path.join(DOCS, "art")

main = open(os.path.join(DOCS, "index.html"), encoding="utf-8").read()
main_toc = main[main.find('<ul class="toc">'):]
sections = re.findall(r'href="([a-z]+)/index\.html"', main_toc)

order, art_section = [], {}
for sec in sections:
    idx = open(os.path.join(DOCS, sec, "index.html"), encoding="utf-8").read()
    a = idx.find('<ul class="toc">')
    toc = idx[a:idx.find('</ul>', a)]
    for num in re.findall(r'<span class="num">#([0-9A-Za-z]+)</span>', toc):
        order.append(num + ".html"); art_section[num + ".html"] = sec

pos = {f: i for i, f in enumerate(order)}
n = len(order)
exp_prev = lambda i: order[i-1] if i > 0 else None
exp_next = lambda i: order[i+1] if i < n-1 else None

def role_of(cls):
    c = (cls or "").lower()
    if re.search(r'prev|pv|prv', c): return "prev"
    if re.search(r'next|nx|nxt', c): return "next"
    return None

def extract(s, fn):
    links = []
    for attrs, tgt in re.findall(r'<a\b([^>]*)href="([0-9A-Za-z]+\.html)"', s):
        m = re.search(r'class="([^"]*)"', attrs)
        links.append((role_of(m.group(1) if m else None), tgt))
    prev = next_ = None
    unknown = [t for r, t in links if r is None]
    for r, t in links:
        if r == "prev": prev = t
        elif r == "next": next_ = t
    if unknown:
        if prev is None and next_ is None:
            if len(unknown) == 2: prev, next_ = unknown
            elif len(unknown) == 1:
                i = pos[fn]
                if i == 0: next_ = unknown[0]
                elif i == n-1: prev = unknown[0]
                elif unknown[0] == exp_prev(i): prev = unknown[0]
                else: next_ = unknown[0]
        else:
            for t in unknown:
                if prev is None and next_ is not None: prev = t
                elif next_ is None and prev is not None: next_ = t
    return prev, next_

changed, skipped = [], []
for i, fn in enumerate(order):
    p = os.path.join(ART, fn)
    if not os.path.exists(p):
        continue
    s = open(p, encoding="utf-8").read()
    ap, an = extract(s, fn)
    ep, en = exp_prev(i), exp_next(i)
    if (ap, an) == (ep, en):
        continue
    new = s
    fixes = []
    for old, new_t, kind in ((ap, ep, "prev"), (an, en, "next")):
        if old == new_t:
            continue
        if new_t is None:
            skipped.append((fn, kind, f"ожидается пусто, в файле {old}")); continue
        if not os.path.exists(os.path.join(ART, new_t)):
            skipped.append((fn, kind, f"целевой файл {new_t} не существует")); continue
        if old is None:
            skipped.append((fn, kind, f"в файле нет {kind}-ссылки, надо {new_t}")); continue
        token = f'href="{old}"'
        cnt = new.count(token)
        if cnt != 1:
            skipped.append((fn, kind, f'href="{old}" встречается {cnt} раз — пропуск')); continue
        new = new.replace(token, f'href="{new_t}"')
        fixes.append(f"{kind} {old}→{new_t}")
    if new != s:
        open(p, "w", encoding="utf-8").write(new)
        changed.append((fn, fixes))

print(f"Изменено файлов: {len(changed)}")
for fn, fixes in changed:
    print(f"  {fn}: {', '.join(fixes)}")
if skipped:
    print(f"Пропущено (требует ручного разбора): {len(skipped)}")
    for fn, kind, why in skipped:
        print(f"  {fn} [{kind}]: {why}")

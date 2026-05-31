# -*- coding: utf-8 -*-
"""
Проверка prev/next ссылок в статьях docs/art против глобального порядка,
заданного index.html (порядок разделов) + <раздел>/index.html (порядок статей).
Несоответствия пишутся в order_change.md.
"""
import re, os

DOCS = os.path.dirname(os.path.abspath(__file__))
ART  = os.path.join(DOCS, "art")

# 1) Порядок разделов из главного index.html
main = open(os.path.join(DOCS, "index.html"), encoding="utf-8").read()
main_toc = main[main.find('<ul class="toc">'):]
sections = re.findall(r'href="([a-z]+)/index\.html"', main_toc)

# 2) Глобальный порядок статей: разделы по очереди, внутри — порядок toc.
#    Берём ВСЕ <li> по #num (и опубликованные, и pending без ссылки),
#    т.к. фактическая цепочка prev/next проходит и через pending-статьи.
order = []        # ['654.html', '22SA.html', ...]
art_section = {}  # файл -> раздел (для отчёта)
for sec in sections:
    idx = open(os.path.join(DOCS, sec, "index.html"), encoding="utf-8").read()
    toc = idx[idx.find('<ul class="toc">'):idx.find('</ul>', idx.find('<ul class="toc">'))]
    for num in re.findall(r'<span class="num">#([0-9A-Za-z]+)</span>', toc):
        f = num + ".html"
        order.append(f)
        art_section[f] = sec

pos = {f: i for i, f in enumerate(order)}
n = len(order)

# 3) Ожидаемые prev/next (сквозная цепочка через все разделы)
def exp_prev(i): return order[i-1] if i > 0 else None
def exp_next(i): return order[i+1] if i < n-1 else None

# 4) Извлечение фактических prev/next из хвоста каждого html
def role_of(cls):
    c = (cls or "").lower()
    if re.search(r'prev|pv|prv', c): return "prev"
    if re.search(r'next|nx|nxt', c): return "next"
    return None

def extract(fn):
    s = open(os.path.join(ART, fn), encoding="utf-8").read()
    links = []  # (role_or_None, target) в порядке появления
    for attrs, tgt in re.findall(r'<a\b([^>]*)href="([0-9A-Za-z]+\.html)"', s):
        m = re.search(r'class="([^"]*)"', attrs)
        links.append((role_of(m.group(1) if m else None), tgt))
    prev = next_ = None
    unknown = [t for r, t in links if r is None]
    for r, t in links:
        if r == "prev": prev = t
        elif r == "next": next_ = t
    # ссылки без класса — раскидываем по порядку/позиции
    if unknown:
        if prev is None and next_ is None:
            if len(unknown) == 2:
                prev, next_ = unknown[0], unknown[1]
            elif len(unknown) == 1:
                # одиночная ссылка без класса: по глобальной позиции
                i = pos[fn]
                if i == 0: next_ = unknown[0]
                elif i == n-1: prev = unknown[0]
                else:
                    # неоднозначно — по соседям
                    if unknown[0] == exp_prev(i): prev = unknown[0]
                    else: next_ = unknown[0]
        else:
            for t in unknown:
                if prev is None and next_ is not None: prev = t
                elif next_ is None and prev is not None: next_ = t
    return prev, next_

# 5) Сравнение
rows = []  # (статья, есть_prev, есть_next, надо_prev, надо_next)
missing_files = []
for i, fn in enumerate(order):
    if not os.path.exists(os.path.join(ART, fn)):
        missing_files.append(fn); continue
    ap, an = extract(fn)
    ep, en = exp_prev(i), exp_next(i)
    if (ap, an) != (ep, en):
        rows.append((fn, ap, an, ep, en))

# 6) Запись order_change.md
def cell(p, nx):
    p = p or "—"; nx = nx or "—"
    return f"prev: `{p}` · next: `{nx}`"

out = []
out.append("# Несоответствия порядка prev / next\n")
out.append(f"Разделы (порядок): {', '.join(sections)}.  ")
out.append(f"Всего статей в порядке: {n}. Несоответствий: {len(rows)}.\n")
if missing_files:
    out.append(f"**Нет html-файла для:** {', '.join(missing_files)}\n")
out.append("| Статья | Есть в файле | Должно быть |")
out.append("|---|---|---|")
for fn, ap, an, ep, en in rows:
    out.append(f"| `{fn}` ({art_section.get(fn,'?')}) | {cell(ap,an)} | {cell(ep,en)} |")
out.append("")

open(os.path.join(DOCS, "order_change.md"), "w", encoding="utf-8").write("\n".join(out))
print(f"Разделы: {sections}")
print(f"Статей в порядке: {n}, html в art/: {len(os.listdir(ART))}")
print(f"Несоответствий: {len(rows)}; отсутствующих файлов: {len(missing_files)}")
print("order_change.md записан.")

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Детерминированный фиксер вложенных <a> в <a> в статьях yaniktoim (docs/art/*.html).

Корень дефекта: браузерный adoption-agency закрывает внешний <a> на месте
внутреннего и выбрасывает popup/ссылку инлайном ("текст сноски виден в зоне").

Три структурных случая:
  P/A1 — <sup|span class~fn><a>MARK<span class~pop>...<a ext></a>...</span></a></...>
         -> popup-span выносится из <a> наружу (остаётся внутри fn-обёртки).
  P/A2 — <a class~fnref href id>MARK<span class~pop>...<a ext></a>...</span></a>  (без fn-обёртки)
         -> внешний <a> демотируется в <span class=...> (hover-host), MARK кладётся
            во внутренний <a class=... href id>, popup-span — соседний потомок span.
  W    — <a OUT>PRE <FNODE сноска с внутренним <a>> POST</a>  (контент/заголовок-самоссылка)
         -> <a OUT>PRE</a> <FNODE> POST   (внешняя ссылка закрывается перед сноской)

Использование:
  python -X utf8 tools/fix_nested_anchors.py            # dry-run, печатает план
  python -X utf8 tools/fix_nested_anchors.py --apply     # бэкап + правка на месте
"""
import re, sys, glob, os, shutil, datetime

ART = os.path.join(os.path.dirname(__file__), "..", "docs", "art")
POP_RE = re.compile(r'class="[^"]*\bpop|class="[^"]*pop\b|class="[^"]*fnpop|class="[^"]*fn-pop', re.I)

def mask(s):
    """Заменить тела <style>/<script> равной длиной 'X', чтобы сохранить офсеты."""
    def repl(m): return m.group(0)[:m.start(1)-m.start(0)] + 'X'*(m.end(1)-m.start(1)) + m.group(0)[m.end(1)-m.start(0):]
    return re.sub(r'<(style|script)[^>]*>(.*?)</\1>', repl, s, flags=re.S|re.I)

def strip_tags(h): return re.sub(r'<[^>]+>', '', h)

def match_tag(text, name, open_start):
    """Найти позицию конца закрывающего тега для элемента name, открытого в open_start."""
    op = re.compile(r'<'+name+r'\b[^>]*>', re.I)
    cl = re.compile(r'</'+name+r'\s*>', re.I)
    toks = sorted(list(op.finditer(text, open_start)) + list(cl.finditer(text, open_start)),
                  key=lambda m: m.start())
    depth = 0
    for m in toks:
        if m.start() < open_start: continue
        if m.group(0).lower().startswith('</'):
            depth -= 1
            if depth == 0: return m.end()
        else:
            depth += 1
    return None

def get_attr(tag, attr):
    m = re.search(attr+r'="([^"]*)"', tag, re.I)
    return m.group(1) if m else None

def class_of(tag):
    return get_attr(tag, 'class') or ''

def find_outer_anchor_regions(masked):
    """Список (outer_open_match, region_end) для якорей, содержащих вложенный <a>."""
    toks = list(re.finditer(r'<a\b[^>]*>|</a\s*>', masked, re.I))
    regions = []
    stack = []
    for t in toks:
        if t.group(0).lower().startswith('</a'):
            if stack:
                opened, has_nested = stack.pop()
                if not stack and has_nested:
                    regions.append((opened, t.end()))
                elif stack and has_nested:
                    # пометить родителя как имеющего вложенность (для верхнего уровня)
                    pass
        else:
            if stack:
                stack[-1] = (stack[-1][0], True)  # родитель содержит вложенный <a>
            stack.append((t, False))
    return regions

def classify_and_fix(s, masked, outer_open, region_end):
    """Вернуть (case, old_substr, new_substr) для одного региона внешнего якоря."""
    o_start = outer_open.start()
    o_open_end = outer_open.end()
    outer_open_tag = s[o_start:o_open_end]
    # outer close: последний </a> региона
    outer_close_start = region_end
    m = re.search(r'</a\s*>\s*$', s[o_start:region_end])
    # region_end уже = end внешнего </a>; найдём его start
    close_m = list(re.finditer(r'</a\s*>', masked[o_start:region_end], re.I))[-1]
    close_start = o_start + close_m.start()
    inner = s[o_open_end:close_start]
    inner_masked = masked[o_open_end:close_start]

    first_a = re.search(r'<a\b', inner_masked, re.I)
    # popup-span: первый span, чей класс содержит pop
    pop_open = None
    for sm in re.finditer(r'<span\b[^>]*>', inner_masked, re.I):
        if POP_RE.search(sm.group(0)):
            pop_open = sm; break
    has_pop = pop_open is not None
    href = get_attr(outer_open_tag, 'href') or ''
    is_fn_href = re.match(r'#(fn|note|cmt|ref|prim)', href, re.I) is not None
    # маркер = текст до popup-span (если popup есть), иначе до первого внутреннего <a>
    marker_end = pop_open.start() if has_pop else first_a.start()
    marker_text = strip_tags(inner[:marker_end]).strip()

    # P: внешний якорь — сам маркер-сноска (href на #fn…), внутри его popup со ссылкой
    is_P = has_pop and is_fn_href

    if is_P:
        pop_open_abs = o_open_end + pop_open.start()
        pop_end_abs = match_tag(masked, 'span', pop_open_abs)
        popup = s[pop_open_abs:pop_end_abs]
        pre_part = s[o_open_end:pop_open_abs]            # MARK (до popup)
        post_part = s[pop_end_abs:close_start]           # обычно пусто

        # A1 если обёрнут в <sup|span class~fn ...>
        wrap_open = re.search(r'<(sup|span)\b[^>]*class="[^"]*fn[^"]*"[^>]*>\s*$', s[:o_start], re.I)
        wrap_ok = False
        if wrap_open:
            wname = wrap_open.group(1)
            after = re.match(r'\s*</'+wname+r'\s*>', s[region_end:], re.I)
            wrap_ok = after is not None
        if wrap_ok:
            new = outer_open_tag + pre_part + post_part + "</a>" + popup
            return ("P/A1", s[o_start:region_end], new)
        else:
            cls = class_of(outer_open_tag) or "fnref"
            href = get_attr(outer_open_tag, 'href')
            idv = get_attr(outer_open_tag, 'id')
            hid = (f' href="{href}"' if href else '') + (f' id="{idv}"' if idv else '')
            inner_a = f'<a class="{cls}"{hid}>' + pre_part + post_part + '</a>'
            new = f'<span class="{cls}">' + inner_a + popup + '</span>'
            return ("P/A2", s[o_start:region_end], new)
    else:
        # W: закрыть внешнюю ссылку перед узлом сноски
        first_a_abs = o_open_end + first_a.start()
        # FNODE = ближайшая sup/span-обёртка перед first_a, иначе сам внутренний <a>
        before = s[o_open_end:first_a_abs]
        wrap = None
        for wm in re.finditer(r'<(sup|span|a)\b[^>]*>', before, re.I):
            wrap = wm
        fnode_start = None; fnode_end = None
        # проверим, оборачивает ли последний открытый sup/span внутренний <a>
        if wrap and wrap.group(1).lower() in ('sup','span'):
            wstart = o_open_end + wrap.start()
            wend = match_tag(masked, wrap.group(1), wstart)
            if wend and wend > first_a_abs:
                fnode_start, fnode_end = wstart, wend
        if fnode_start is None:
            # FNODE = внутренний <a> целиком
            fnode_start = first_a_abs
            fnode_end = match_tag(masked, 'a', first_a_abs)
        PRE = s[o_open_end:fnode_start]
        FNODE = s[fnode_start:fnode_end]
        POST = s[fnode_end:close_start]
        new = outer_open_tag + PRE + "</a>" + FNODE + POST
        return ("W", s[o_start:region_end], new)

def process(path, apply=False):
    s = open(path, encoding="utf-8").read()
    masked = mask(s)
    regions = find_outer_anchor_regions(masked)
    if not regions: return None
    # обрабатываем справа налево
    edits = []
    for outer_open, region_end in sorted(regions, key=lambda r: -r[0].start()):
        case, old, new = classify_and_fix(s, masked, outer_open, region_end)
        edits.append((outer_open.start(), region_end, case, old, new))
    result = s
    for start, end, case, old, new in edits:
        if new is None: continue
        result = result[:start] + new + result[end:]
    # A2 демотирует <a class=fn…> в <span> — деквалифицируем селекторы a.fnref/a.fnmark/a.fn-ref
    if any(c == 'P/A2' for _,_,c,_,_ in edits):
        result = re.sub(r'\ba\.(fnref|fnmark|fn-ref)\b', r'.\1', result)
    return s, result, [(c, o, n) for _,_,c,o,n in reversed(edits)]

def main():
    apply = '--apply' in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith('--')]
    files = [os.path.join(ART, f+'.html') for f in only] if only else sorted(glob.glob(os.path.join(ART,'*.html')))
    bdir = os.path.join(ART, '..', '..', '_backups', 'nested_a_'+datetime.datetime.now().strftime('%y%m%d_%H%M%S')) if apply else None
    if bdir: os.makedirs(bdir, exist_ok=True)
    total=0; changed=0; cases={}
    for path in files:
        r = process(path, apply)
        if not r: continue
        s, result, edits = r
        if result == s: continue
        total+=1
        name=os.path.basename(path)
        for case,old,new in edits:
            cases[case]=cases.get(case,0)+1
        print(f"\n##### {name}  ({len(edits)} sites)")
        for case,old,new in edits:
            print(f"  [{case}]")
            print(f"    OLD: {old[:200].strip()}")
            print(f"    NEW: {(new or '∅')[:200].strip()}")
        if apply:
            shutil.copy2(path, os.path.join(bdir, name))
            open(path,'w',encoding='utf-8').write(result)
            changed+=1
    print(f"\n=== files needing change: {total}; cases: {cases}")
    if apply: print(f"=== applied to {changed} files; backups in {bdir}")

if __name__=='__main__':
    main()

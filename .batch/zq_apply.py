# -*- coding: utf-8 -*-
import json, os
ROOT = r"C:\Users\admin\yaniktoim\docs\art"
B = os.path.dirname(os.path.abspath(__file__))
def T(n): return json.load(open(os.path.join(B, "zq_out", "%02d.json" % n), encoding="utf-8"))["translation"].strip()
def load(f): return open(os.path.join(ROOT, f), encoding="utf-8").read()
def save(f, h): open(os.path.join(ROOT, f), "w", encoding="utf-8").write(h)

def region(h, a, bend, new, label):
    """replace h[index(a) : index(bend)+len(bend)] with `new`. Assert uniqueness."""
    assert h.count(a) == 1, "A x%d %s" % (h.count(a), label)
    i0 = h.index(a)
    j = h.index(bend, i0);
    assert h.count(bend) == 1, "B x%d %s" % (h.count(bend), label)
    i1 = j + len(bend)
    return h[:i0] + new + h[i1:]

def repl(h, old, new, label):
    assert h.count(old) == 1, "repl x%d %s" % (h.count(old), label)
    return h.replace(old, new)

log = []

# 18T п.66
f="18T.html"; h=load(f)
h=region(h, '<p>Причина этой зависти', 'наравне с ангелами.</p>', '<p>'+T(6)+'</p>', "18T-66")
save(f,h); log.append("18T")

# 591 п.89
f="591.html"; h=load(f)
h=region(h, '<p>«89) „Но место проживания', 'скрылся в этом море“».</p>', '<p>«89) „'+T(20)+'“».</p>', "591-89")
save(f,h); log.append("591")

# 34O п.82  (keep '82)' num span and <cite>)
f="34O.html"; h=load(f)
h=region(h, 'Осталась другая суббота', 'они соединены вместе.', T(14), "34O-82")
save(f,h); log.append("34O")

# 28MA x3
f="28MA.html"; h=load(f)
h=region(h, 'Цитата: «И дело в том, что до создания', '», Заповедь девятая, п. 236',
         'Цитата: «'+T(10)+'», Заповедь девятая, п. 236', "28MA-236")
h=region(h, 'Цитата: «Сказал он в ответ: «И Бнайяу', '», Погонщик ослов, п. 91',
         'Цитата: «'+T(11)+'», Погонщик ослов, п. 91', "28MA-91")
h=region(h, 'Цитата: ««И птица будет летать', '» - Заповедь седьмая, п. 255',
         'Цитата: «'+T(12)+'» - Заповедь седьмая, п. 255', "28MA-225")
save(f,h); log.append("28MA x3")

# 239 x2 + link fix
f="239.html"; h=load(f)
t7 = T(7).replace('тикуны', 'тикуны<a class="fnref" id="ref-14" data-fn="fn-14" href="#fn-14">14</a>', 1)
assert 'fnref' in t7
h=region(h, 'Цитата: «Рабби Шимон и все товарищи', '»<span class="src">— Ночь Невесты, п. 126',
         'Цитата: «'+t7+'»<span class="src">— Ночь Невесты, п. 126', "239-126")
h=region(h, 'Цитата: «Сказал он в ответ: „И Бнайяу', '»<span class="src">— п. 91, Том 1. Погонщик',
         'Цитата: «'+T(88)+'»<span class="src">— п. 91, Том 1. Погонщик', "239-91")
h=repl(h,
  'п. 91, Том 1. Погонщик ослов. Книга Зоар. РАШБИ-Бааль Сулам. <a href="https://imyavel.github.io/zohar-sulam/akdama/014.html" target="_blank" rel="noopener">akdama/014</a>',
  'п. 91, Том 1. Погонщик ослов. Книга Зоар. РАШБИ-Бааль Сулам. <a href="https://imyavel.github.io/zohar-sulam/akdama/012.html" target="_blank" rel="noopener">akdama/012</a>',
  "239-link")
save(f,h); log.append("239 x2+link")

print(" | ".join(log)); print("DONE")

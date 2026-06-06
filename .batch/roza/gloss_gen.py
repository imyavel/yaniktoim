# -*- coding: utf-8 -*-
"""Сгенерировать раздел-глоссарий glossary.html из vols/glossary.txt (Opus 4.8)."""
from pathlib import Path
import roza_run as R

gloss_src = (R.VOLS/"glossary.txt").read_text(encoding="utf-8")
out = R.OUT/"glossary.html"
SYS = ("You are an analytical writer. You produce a compact Russian-language glossary "
       "as a strict HTML fragment and WRITE it to the destination file with the Write "
       "tool. Final reply: ONE short confirmation line.")
up = (f"Перед тобой «Краткий словарь» терминов Даниила Андреева из «Розы Мира». "
      f"Собери КОМПАКТНЫЙ глоссарий для статьи: отбери ~32–40 самых важных и часто "
      f"употребляемых терминов и имён (например: метаистория, трансфизика, Шаданакар, "
      f"брамфатура, Энроф, затомис, Синклит, сакуала, уицраор, эгрегор, стихиали, "
      f"демиург, Соборная Душа, Звента-Свентана, Жругр, игвы, раругги, шрастры, "
      f"каросса, Олирна, Гагтунгр, Планетарный Логос и т.п. — выбирай по словарю). "
      f"Для каждого дай КРАТКОЕ определение (1–2 фразы) своими словами на основе словаря, "
      f"единообразно по написанию. Расположи по алфавиту. Выведи СТРОГО как HTML-фрагмент:\n"
      f'<section id="glossary">\n  <h2>Глоссарий терминов</h2>\n  <dl>\n'
      f"    <dt>Термин</dt>\n    <dd>определение</dd>\n    ...\n  </dl>\n</section>\n"
      f"Без инлайн-стилей, без <script>, без <html>/<head>/<body>. Запиши фрагмент в файл: "
      f"{out}. В ответ — только короткое подтверждение.\n\n=== КРАТКИЙ СЛОВАРЬ ===\n{gloss_src}")
ok = R.run_claude(SYS, up, "glossary", max_out="32000")
if ok and out.exists():
    h = out.read_text(encoding="utf-8")
    n = h.count("<dt>")
    bad = ("<html" in h.lower()) or ("<script" in h.lower()) or ('id="glossary"' not in h)
    print(f"glossary: {n} terms, bad={bad}, {len(h)} bytes")
else:
    print("GLOSSARY FAILED")

# -*- coding: utf-8 -*-
import json, os, subprocess, concurrent.futures as cf, sys

BASE = os.path.dirname(os.path.abspath(__file__))
items = json.load(open(os.path.join(BASE, "zohar_quotes_input.json"), encoding="utf-8"))
outdir = os.path.join(BASE, "zq_out"); os.makedirs(outdir, exist_ok=True)

PROMPT = """Ты — текстолог-каббалист. В авторской статье (проект yaniktoim) встречается ЦИТАТА из «Книги Зоар» (Перуш Сулам, РАШБИ — Бааль Сулам) с атрибуцией. Автор ссылается на ДРУГОЙ перевод того же места (сайт zohar-sulam). Тексты — разные переводы одного источника.

АТРИБУЦИЯ (хвост текста перед ссылкой): {attrib}
Ссылка ведёт на: akdama/{target} (п. {para}).

ЗАДАЧА:
1. Найди в ТЕКСТЕ СТАТЬИ прямую цитату из Зоара, к которой относится эта атрибуция (обычно в кавычках «...» или "..."/“...”). Извлеки её ДОСЛОВНО.
2. В ОКНЕ ПЕРЕВОДА найди соответствующий по смыслу фрагмент (тот же текст Зоара, но в переводе zohar-sulam). Ориентируйся на номер абзаца п.{para} (в переводе абзацы помечены «N)»). Извлеки сопоставимый фрагмент дословно (только релевантные предложения).
3. Если в статье НЕТ прямой цитаты (только ссылка-указатель) — has_quote=false.
4. Если цитата есть, но в окне перевода соответствие НЕ находится — found_in_link=false и поясни (возможно, ссылка ведёт не туда).

Верни СТРОГО один JSON-объект, без markdown, без пояснений вокруг:
{{"has_quote": true/false, "quote": "<дословная цитата из статьи или пусто>", "translation": "<сопоставимый фрагмент из перевода или пусто>", "para": <число или null>, "found_in_link": true/false, "note": "<кратко: совпадение/расхождение/мислинк>"}}

=== ТЕКСТ СТАТЬИ ===
{article}

=== ОКНО ПЕРЕВОДА (akdama/{target}) ===
{window}
"""

def run(it):
    n = it["n"]
    prompt = PROMPT.format(attrib=it["attrib_tail"], target=it["target"],
                           para=it["para"], article=it["article_text"],
                           window=it["translation_window"])
    try:
        p = subprocess.run(
            r'"C:\Users\admin\AppData\Roaming\npm\claude.cmd" -p --model opus --output-format json',
            input=prompt, capture_output=True, text=True, encoding="utf-8",
            timeout=300, cwd=BASE, shell=True)
        env = json.loads(p.stdout)
        result = env.get("result", "")
        # extract inner json
        s = result.find("{"); e = result.rfind("}")
        inner = json.loads(result[s:e+1]) if s >= 0 else {"parse_error": result[:200]}
    except Exception as ex:
        inner = {"error": "%s: %s" % (type(ex).__name__, ex), "stderr": (locals().get('p').stderr[:300] if locals().get('p') else "")}
    inner["_n"] = n; inner["_art"] = it["art"]; inner["_target"] = it["target"]; inner["_href"] = it["href"]; inner["_attrib"] = it["attrib_tail"]
    json.dump(inner, open(os.path.join(outdir, "%02d.json" % n), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("done #%d %s -> akdama/%s  has_quote=%s found=%s" % (n, it["art"], it["target"], inner.get("has_quote"), inner.get("found_in_link")), flush=True)
    return inner

with cf.ThreadPoolExecutor(max_workers=4) as ex:
    list(ex.map(run, items))
print("ALL DONE")

# -*- coding: utf-8 -*-
import json, os, glob

BASE = os.path.dirname(os.path.abspath(__file__))
ART = "https://imyavel.github.io/yaniktoim/art/%s.html"
rows = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(BASE, "zq_out", "*.json")))]

quotes = [r for r in rows if r.get("has_quote")]
noq = [r for r in rows if r.get("has_quote") is False]
err = [r for r in rows if "error" in r or "parse_error" in r]

L = []
L.append("# Зоар: сверка цитат в статьях с переводом zohar-sulam\n")
L.append("Сформировано 2026-06-01 (headless Opus). Для каждой прямой цитаты из «Книги Зоар» в статье — ")
L.append("сопоставимый фрагмент в переводе zohar-sulam по новой ссылке. Перевод другой, потому сверка смысловая.\n")

ok = [r for r in quotes if r.get("found_in_link")]
miss = [r for r in quotes if not r.get("found_in_link")]

L.append("## Сверенные цитаты (соответствие найдено: %d)\n" % len(ok))
for r in ok:
    art = r["_art"]; tgt = r["_target"]
    L.append("### [%s](%s) → [akdama/%s](%s)" % (art, ART % art, tgt, r["_href"]))
    if r.get("para"): L.append("*п. %s*  \n" % r["para"])
    L.append("**Цитата в статье:**\n")
    L.append("> %s\n" % r.get("quote", "").strip())
    L.append("**В переводе по ссылке:**\n")
    L.append("> %s\n" % r.get("translation", "").strip())
    if r.get("note"): L.append("_%s_\n" % r["note"])

if miss:
    L.append("\n## Цитата есть, но в переводе по ссылке не найдена — возможный мислинк (%d)\n" % len(miss))
    for r in miss:
        art = r["_art"]; tgt = r["_target"]
        L.append("### [%s](%s) → [akdama/%s](%s)" % (art, ART % art, tgt, r["_href"]))
        L.append("**Цитата в статье:**\n")
        L.append("> %s\n" % r.get("quote", "").strip())
        L.append("_%s_\n" % r.get("note", ""))

if noq:
    L.append("\n## Без прямой цитаты (ссылка-указатель, %d)\n" % len(noq))
    for r in noq:
        L.append("- [%s](%s) → akdama/%s — %s" % (r["_art"], ART % r["_art"], r["_target"], r.get("note", "")))

if err:
    L.append("\n## Ошибки обработки (%d)\n" % len(err))
    for r in err:
        L.append("- #%s %s → akdama/%s: %s" % (r.get("_n"), r.get("_art"), r.get("_target"), r.get("error") or r.get("parse_error")))

open(os.path.join(os.path.dirname(BASE), "zohar_quotes_check.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("quotes=%d ok=%d miss=%d noq=%d err=%d -> zohar_quotes_check.md" % (len(quotes), len(ok), len(miss), len(noq), len(err)))

# -*- coding: utf-8 -*-
import re, glob, os, json
ROOT = r"C:\Users\admin\yaniktoim"
B = os.path.join(ROOT, ".batch")
res = json.load(open(os.path.join(B, "short_resolved.json"), encoding="utf-8"))
titles = json.load(open(os.path.join(B, "kab_titles.json"), encoding="utf-8"))
ART = "https://imyavel.github.io/yaniktoim/art/%s"

# kabbalahmedia source -> akdama page
AK = {"yUcfylRm":"001","pJEgVWrp":"003","BRG7YgUs":"004","M07beI2F":"006","0PRkRr2w":"007",
      "KnH2EYPh":"011","KJWljPMB":"012","jvJkHG2l":"017","F2LYqFgK":"022","lgUtBujx":"023",
      "aZn9EUGB":"029","SMsTmV9E":"030"}
# Zohar but outside Akdama -> proposed section (flag)
SECT = {"NslF3LJh":("bereshit","Зоар Том2 «Берешит-1», п.1 — уточнить страницу bereshit/NNN"),
        "ZEPIzcHJ":("bereshit","Зоар Том2 «Берешит-2», п.366 — уточнить страницу bereshit/NNN"),
        "ejxH6XIB":("tetzaveh/003","Зоар Том5 «Тецаве» = Статья 3 «И ты приблизь к себе» (цитата 2AT)"),
        "L8daQ2n7":("akdama?","«Общее выяснение 14 заповедей» — отдельной статьи на сайте НЕТ, уточнить")}
ZOHAR = set(AK) | set(SECT)

def kid(u):
    f = res.get(u, u)
    m = re.search(r'kabbalahmedia\.info/ru/sources/([A-Za-z0-9]+)', f) or re.search(r'kabbalahmedia\.info/ru/sources/([A-Za-z0-9]+)', u)
    return m.group(1) if m else None
def dest(u):
    f = res.get(u, u)
    if 'youtu' in f: return "youtube"
    if 'wikisource' in f: return "wikisource"
    if 'docs.google' in f: return "gdoc"
    if f.startswith("HTTP") or f.startswith("ERR"): return "DEAD"
    return f

pat = re.compile(r'href="(https?://(?:kabbalahmedia\.info|www\.kabbalah\.info|goo\.su|clck\.ru)[^"]+)"')
# special dead-but-Zohar (by context): file,url -> akdama target
DEAD_ZOHAR = {("64P.html","https://clck.ru/3TPssD"):"001",   # Ростки/Роза, Акдама пп.4-6
              ("0BH.html","https://goo.su/33lt"):"001"}       # Роза п.1

from collections import defaultdict
repl_ak = defaultdict(list)   # akdama target -> [(file,url)]
repl_sect = defaultdict(list) # sect key -> [(file,url)]
remove = defaultdict(list)    # kid/'kabbalah.info' -> [(file,url)]
leave = defaultdict(list)     # dest -> [(file,url)]
dead_z = []

for f in glob.glob(os.path.join(ROOT, "docs", "**", "*.html"), recursive=True):
    h = open(f, encoding="utf-8").read(); b = os.path.basename(f)
    for m in pat.finditer(h):
        u = m.group(1); k = kid(u); d = dest(u)
        if (b, u) in DEAD_ZOHAR:
            dead_z.append((b, u, DEAD_ZOHAR[(b, u)])); continue
        if k in AK:
            repl_ak["akdama/"+AK[k]].append((b, u, k))
        elif k in SECT:
            repl_sect[k].append((b, u))
        elif k:  # kabbalahmedia non-Zohar
            remove[k].append((b, u))
        elif 'kabbalah.info' in u:
            remove["kabbalah.info/341 (Обобщающее введение, Бааль Сулам)"].append((b, u))
        else:
            leave[d].append((b, u))

L = ["# Зоар/каббала: вторая волна — короткие и *kabbalah* ссылки\n",
     "Сформировано 2026-06-01. **Файл для ревью ДО правок.** Источники резолвлены (goo.su/clck.ru → kabbalahmedia),",
     "названия взяты с kabbalahmedia (Googlebot-prerender). Зоар-ссылки → наш корпус zohar-sulam; не-Зоар *kabbalah* → удалить.\n"]

L.append("## §1. Заменить на zohar-sulam — Акдама (1:1, надёжно)\n")
L.append("| Источник (kabbalahmedia) | → | встречается в статьях |")
L.append("|---|---|---|")
for tgt in sorted(repl_ak):
    occ = repl_ak[tgt]; k = occ[0][2]
    files = ", ".join(sorted(set(b[:-5] for b, u, _ in occ)))
    nm = titles.get(k, k).split(" - ")[0]
    L.append(f"| {nm} (`{k}`) | {tgt} | {files} |")
if dead_z:
    L.append("\n**Мёртвый шортлинк, но это Зоар-Акдама → заменить:**")
    for b, u, t in dead_z:
        L.append(f"- [{b[:-5]}]({ART%b}) `{u}` (мёртв) → akdama/{t}  (Роза / Ростки, пп.4-6)")

L.append("\n## §2. Заменить — Зоар ВНЕ Акдамы (нужно подтверждение страницы)\n")
for k, (tgt, note) in SECT.items():
    occ = repl_sect.get(k, [])
    files = ", ".join(sorted(set(b[:-5] for b, u in occ))) or "—"
    L.append(f"- **{titles.get(k,k).split(' - ')[0]}** (`{k}`) → `{tgt}` — {note}.  Статьи: {files}")

L.append("\n## §3. Перепроверка цитаты (единственная verbatim-цитата при этих ссылках)\n")
r = json.load(open(os.path.join(B, "zq_out", "201.json"), encoding="utf-8")) if os.path.exists(os.path.join(B,"zq_out","201.json")) else None
L.append(f"### [2AT]({ART%'2AT.html'}) → [tetzaveh/003](https://imyavel.github.io/zohar-sulam/tetzaveh/003.html)  *п.41*")
if r:
    L.append("\n**Цитата в статье:**\n")
    L.append("> "+(r.get("quote","") or "").strip())
    L.append("\n**В переводе по ссылке:**\n")
    L.append("> "+(r.get("translation","") or "").strip())
    L.append("\n_"+(r.get("note","") or "")+"_")

L.append("\n## §4. Удалить из HTML — *kabbalah*, НЕ ведёт на Зоар\n")
L.append("| Источник | вид | встречается в |")
L.append("|---|---|---|")
for k in sorted(remove, key=lambda x: titles.get(x, x)):
    occ = remove[k]
    files = ", ".join(sorted(set(b[:-5] for b, u in occ)))
    nm = titles.get(k, k)
    L.append(f"| {nm} | {'kabbalahmedia/'+k if k in titles else k} | {files} |")

L.append("\n## §5. Оставить как есть (короткие, но не Зоар и не kabbalah)\n")
for d in sorted(leave):
    occ = leave[d]
    rows = ", ".join(sorted(set(b[:-5] for b, u in occ)))
    L.append(f"- **{d}**: {rows}  ({len(occ)} ссыл.)")

open(os.path.join(ROOT, "wave2_links.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("repl_ak targets:", len(repl_ak), "| sect:", sum(len(v) for v in repl_sect.values()),
      "| remove src:", len(remove), "| leave:", sum(len(v) for v in leave.values()), "| dead_z:", len(dead_z))
print("-> wave2_links.md")

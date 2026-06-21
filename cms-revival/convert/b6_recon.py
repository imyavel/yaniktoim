# -*- coding: utf-8 -*-
"""B6 «См. также» recon: классифицирует сноски-определения по префиксу,
парсит поля `::`, резолвит название→art-id по manifest, считает «авторов».
Отчёт → b6_recon.json (utf-8). В stdout — только числа (Windows-safe)."""
import json
import re
from collections import Counter
from pathlib import Path

OUT = Path(__file__).parent / "out"
MANIFEST = Path("C:/Users/admin/imyavel/yaniktoim/manifest.json")
REPORT = Path(__file__).parent / "b6_recon.json"

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))


def norm(s):
    s = s.lower().replace("ё", "е")
    return re.sub(r"[^0-9a-zа-я]+", "", s)


TITLE2ART = {}
for r in manifest:
    t = norm(r.get("title", ""))
    if t and t not in TITLE2ART:
        TITLE2ART[t] = r["art"]
ART_SET = {r["art"] for r in manifest}

FN_RX = re.compile(r"^\[\^([^\]]+)\]:\s*(.*)$")
IDLINK_RX = re.compile(r"\[\[([0-9A-Za-z_]+)\]\]")
PREFIXES = [
    ("seealso", re.compile(r"^(?:См\.?\s*также|А\s+также)\b\s*::?\s*", re.I)),
    ("music",   re.compile(r"^Музыка\b\s*::?\s*", re.I)),
    ("citata",  re.compile(r"^Цитата\b", re.I)),
]


def classify(body):
    for kind, rx in PREFIXES:
        m = rx.match(body)
        if m:
            return kind, body[m.end():]
    return "other", body


stats = Counter()
seealso_resolution = Counter()
authors = Counter()
unresolved_names = []
nonstd = []           # seealso с числом полей != 2 (name::author)
music_examples = []
all_seealso = []

for f in sorted(OUT.glob("*.zml")):
    art = f.stem
    for line in f.read_text(encoding="utf-8").splitlines():
        m = FN_RX.match(line)
        if not m:
            continue
        body = m.group(2).strip()
        kind, rest = classify(body)
        stats[kind] += 1
        if kind == "music":
            if len(music_examples) < 25:
                music_examples.append({"art": art, "fn": m.group(1), "body": body})
            continue
        if kind != "seealso":
            continue
        # поля по `::`
        parts = [p.strip(" ,") for p in re.split(r"::+", rest) if p.strip(" ,")]
        name = parts[0] if parts else ""
        author = parts[-1] if len(parts) >= 2 else ""
        # резолв названия
        idm = IDLINK_RX.search(name)
        if idm:
            res = "via_link" if idm.group(1) in ART_SET else "link_badid"
        else:
            a = TITLE2ART.get(norm(name))
            if a:
                res = "via_title"
            else:
                res = "unresolved"
                if len(unresolved_names) < 80:
                    unresolved_names.append({"art": art, "fn": m.group(1),
                                             "name": name, "author": author})
        seealso_resolution[res] += 1
        if author:
            authors[author] += 1
        if len(parts) != 2:
            if len(nonstd) < 60:
                nonstd.append({"art": art, "fn": m.group(1), "nparts": len(parts),
                               "body": body})
        all_seealso.append({"art": art, "fn": m.group(1), "name": name,
                            "author": author, "res": res, "nparts": len(parts)})

report = {
    "totals": dict(stats),
    "seealso_resolution": dict(seealso_resolution),
    "authors_top": authors.most_common(40),
    "n_unique_authors": len(authors),
    "unresolved_names_sample": unresolved_names,
    "nonstd_sample": nonstd,
    "music_sample": music_examples,
}
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
print("totals:", dict(stats))
print("seealso_resolution:", dict(seealso_resolution))
print("unique_authors:", len(authors))
print("nonstd(seealso != 2 fields):", stats["seealso"] and len(nonstd), "(sample cap 60)")
print("report ->", REPORT.name)

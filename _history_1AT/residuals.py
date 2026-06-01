# -*- coding: utf-8 -*-
import re, os, glob, json

ROOT = r"C:\Users\admin\yaniktoim\docs"
SONGS = os.path.join(ROOT, "songs", "index.html")
ART = os.path.join(ROOT, "art")
s = open(SONGS, encoding="utf-8").read()

id2song = {}
tiles = []
for fig in re.findall(r'<figure class="song">.*?</figure>', s, re.S):
    mid = re.search(r'data-id="([\w-]+)"', fig)
    mt = re.search(r'<p class="t">(.*?)</p>', fig, re.S)
    label = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', mt.group(1))).strip()
    id2song[mid.group(1)] = label
    hrefs = re.findall(r'href="\.\./art/([\w.-]+\.html)"', fig)
    tiles.append((mid.group(1), label, hrefs))

def art_ids(f):
    txt = open(os.path.join(ART, f), encoding="utf-8").read()
    return list(dict.fromkeys(re.findall(r'(?:watch\?v=|youtu\.be/|embed/|/vi/|data-yt=")([\w-]{11})', txt)))

orphans = set()
rows = []
for tid, label, hrefs in tiles:
    for h in hrefs:
        if not os.path.exists(os.path.join(ART, h)):
            rows.append((label, tid, h, "FILE MISSING", [])); continue
        ids = art_ids(h)
        if tid in ids:
            continue
        resolved = [(i, id2song.get(i, "??ORPHAN??")) for i in ids]
        for i in ids:
            if i not in id2song:
                orphans.add(i)
        rows.append((label, tid, h, "id absent", resolved))

print(f"РЕЗИДУАЛЬНЫХ пар (tile->article без exact-id): {len(rows)}")
for label, tid, h, why, resolved in rows:
    print(f"\n● [{tid}] {label}  ->  art/{h}")
    for i, nm in resolved:
        print(f"     {i}  =  {nm}")

print("\n\n=== ORPHAN ids (нет на странице Песни Ступеней) — нужно резолвить ===")
print(" ".join(sorted(orphans)))
json.dump(sorted(orphans), open(r"C:\Users\admin\yaniktoim\_history_1AT\orphans.json", "w"))
print("count:", len(orphans))

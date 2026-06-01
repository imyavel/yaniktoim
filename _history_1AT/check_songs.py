# -*- coding: utf-8 -*-
import re, os, glob, collections

ROOT = r"C:\Users\admin\yaniktoim\docs"
SONGS = os.path.join(ROOT, "songs", "index.html")
ART = os.path.join(ROOT, "art")

s = open(SONGS, encoding="utf-8").read()

# Parse each <figure class="song"> block
tiles = []  # (ytid, label, [hrefs])
for fig in re.findall(r'<figure class="song">.*?</figure>', s, re.S):
    mid = re.search(r'data-id="([\w-]+)"', fig)
    mt = re.search(r'<p class="t">(.*?)</p>', fig, re.S)
    if not (mid and mt):
        continue
    ytid = mid.group(1)
    label = re.sub(r'\s+', ' ', mt.group(1)).strip()
    hrefs = re.findall(r'href="\.\./art/([\w.-]+\.html)"', fig)
    tiles.append((ytid, label, hrefs))

print(f"Плиток в Песни Ступеней: {len(tiles)}")

# Build article -> set of ALL yt ids (any markup form) + optional player names
art_ids = {}      # filename -> {ytid: trackname}
YT = re.compile(r'(?:watch\?v=|youtu\.be/|embed/|/vi/|data-yt=")([\w-]{11})')
for f in glob.glob(os.path.join(ART, "*.html")):
    txt = open(f, encoding="utf-8").read()
    d = {}
    for ytid in YT.findall(txt):
        d.setdefault(ytid, "")
    # attach player track-name where present
    for ytid, name in re.findall(r'data-yt="([\w-]+)".*?<span class="track-name">(.*?)</span>', txt, re.S):
        name = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', name)).strip()
        d[ytid] = name
    art_ids[os.path.basename(f)] = d

# 1. Duplicate ytid across tiles / inconsistent labels
byid = collections.defaultdict(list)
for ytid, label, hrefs in tiles:
    byid[ytid].append(label)
print("\n=== 1. Один и тот же YouTube ID в нескольких плитках ===")
dupe = {k: v for k, v in byid.items() if len(v) > 1}
if not dupe:
    print("  нет — каждый ID уникален")
for k, v in dupe.items():
    print(f"  {k}: {v}")

# 2. Tile links to an article that does NOT contain that ytid
print("\n=== 2. Плитка ссылается на статью, где НЕТ её трека (по YouTube ID) ===")
problems = []
for ytid, label, hrefs in tiles:
    for h in hrefs:
        if h not in art_ids:
            problems.append((label, ytid, h, "ФАЙЛ НЕ НАЙДЕН"))
        elif ytid not in art_ids[h]:
            present = ", ".join(sorted(art_ids[h].keys())) or "(нет музыки)"
            problems.append((label, ytid, h, f"ID отсутствует; в статье есть: {present}"))
if not problems:
    print("  нет — все ссылки указывают на статьи, реально содержащие этот трек")
for label, ytid, h, why in problems:
    print(f"  [{ytid}] {label}\n     -> art/{h}: {why}")

# 3. Article contains a track ID that is NOT listed/back-linked on the song page tile
print("\n=== 3. В статье есть трек, который Песнь Ступеней НЕ связывает с этой статьёй ===")
tile_articles = collections.defaultdict(set)  # ytid -> set(articles linked)
allids = set()
for ytid, label, hrefs in tiles:
    allids.add(ytid)
    for h in hrefs:
        tile_articles[ytid].add(h)
missing = []
for art_file, d in art_ids.items():
    for ytid in d:
        if ytid not in allids:
            missing.append((art_file, ytid, "ID вообще отсутствует на странице Песни Ступеней"))
        elif art_file not in tile_articles[ytid]:
            missing.append((art_file, ytid, "ID есть на странице, но статья не указана в его плитке"))
if not missing:
    print("  нет — каждый трек статьи отражён на странице Песни Ступеней")
for art_file, ytid, why in missing:
    print(f"  art/{art_file} [{ytid}]: {why}")

print("\n=== ИТОГ ===")
print(f"  плиток: {len(tiles)}, уникальных ID: {len(allids)}")
print(f"  проблем тип2 (битые ссылки): {len(problems)}")
print(f"  проблем тип3 (несвязанные треки): {len(missing)}")
print(f"  дубль-ID: {len(dupe)}")

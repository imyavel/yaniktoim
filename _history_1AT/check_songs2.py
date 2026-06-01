# -*- coding: utf-8 -*-
import re, os, glob, collections, html

ROOT = r"C:\Users\admin\yaniktoim\docs"
SONGS = os.path.join(ROOT, "songs", "index.html")
ART = os.path.join(ROOT, "art")

def norm(t):
    t = html.unescape(t).lower().replace("ё", "е")
    t = re.sub(r"[^0-9a-zа-я ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()

# ---- parse song tiles ----
s = open(SONGS, encoding="utf-8").read()
tiles = []  # dict id,label,title,perf,hrefs
for fig in re.findall(r'<figure class="song">.*?</figure>', s, re.S):
    mid = re.search(r'data-id="([\w-]+)"', fig)
    mt = re.search(r'<p class="t">(.*?)</p>', fig, re.S)
    if not (mid and mt):
        continue
    label = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', mt.group(1))).strip()
    parts = re.split(r'\s+—\s+', label, 1)
    title = parts[0].strip()
    perf = parts[1].strip() if len(parts) > 1 else ""
    hrefs = re.findall(r'href="\.\./art/([\w.-]+\.html)"', fig)
    tiles.append(dict(id=mid.group(1), label=label, title=title, perf=perf, hrefs=hrefs))

# ---- parse article tracks: generic head-text extractor (covers all variants) ----
def clean_label(raw):
    raw = raw.split('<a', 1)[0]          # drop the ext-link anchor
    raw = re.sub(r'<[^>]+>', ' ', raw)
    raw = html.unescape(raw)
    raw = raw.replace('▶', ' ').replace('▾', ' ').replace('▸', ' ').replace('↗', ' ').replace('↑', ' ')
    raw = re.sub(r'—?\s*к сноск[еи][^·]*·?\s*youtube\.com', ' ', raw, flags=re.I)
    raw = re.sub(r'youtube\.com|youtu\.be', ' ', raw)
    raw = raw.replace('«', '').replace('»', '')
    return re.sub(r'\s+', ' ', raw).strip(' —·')

def parse_article(txt):
    tracks = {}  # id -> dict(title=label, artist="", raw=label)
    # every track container: data-yt / data-vid = ID, capture head up to the ext-link title
    for m in re.finditer(r'data-(?:yt|vid)="([\w-]+)".*?title="Открыть на YouTube"', txt, re.S):
        i = m.group(1)
        if i in tracks:
            continue
        label = clean_label(m.group(0)[m.group(0).find('>') + 1:])
        tracks[i] = dict(artist="", title=label, raw=label)
    # any other ytid (thumbnail/embed/bare link) with no metadata
    for i in re.findall(r'(?:watch\?v=|youtu\.be/|embed/|/vi/|data-yt=")([\w-]{11})', txt):
        tracks.setdefault(i, dict(artist="", title="", raw=""))
    return tracks

arts = {}
for f in glob.glob(os.path.join(ART, "*.html")):
    arts[os.path.basename(f)] = parse_article(open(f, encoding="utf-8").read())

# ---- soft match: does article contain the tile's song? ----
def soft_match(tile, tracks):
    if tile["id"] in tracks:
        return ("id", tile["id"])
    nt = norm(tile["title"]); npf = norm(tile["perf"])
    for i, tr in tracks.items():
        na, nti, nraw = norm(tr["artist"]), norm(tr["title"]), norm(tr["raw"])
        # title equality / substring either way
        if nt and nti and (nt == nti or nt in nti or nti in nt):
            # if both have performer, require it to be compatible
            if npf and na and not (npf in na or na in npf or npf.split()[-1] in na):
                continue
            return ("title", f"{tr['artist']} — {tr['title']} [{i}]")
        if nt and nraw and nt in nraw:
            return ("raw", f"{tr['raw'][:50]} [{i}]")
    return None

print("=== РЕЗИДУАЛЬНЫЕ дефекты тип-2 (после мягкого сопоставления по песне) ===")
residual = []
softfixed = []
for tile in tiles:
    for h in tile["hrefs"]:
        if h not in arts:
            residual.append((tile, h, "ФАЙЛ НЕ НАЙДЕН", None)); continue
        if tile["id"] in arts[h]:
            continue  # exact upload, fine
        m = soft_match(tile, arts[h])
        if m:
            softfixed.append((tile, h, m))
        else:
            labels = "; ".join(f"{t.get('artist','')}—{t.get('title','')}[{i}]".strip("—")
                               for i, t in arts[h].items()) or "(нет музыки)"
            residual.append((tile, h, labels, None))

for tile, h, info, _ in residual:
    print(f"  ✗ [{tile['id']}] {tile['label']}")
    print(f"       -> art/{h}: {info}")

print(f"\n  Мягко подтверждено (та же песня, другой аплоад/название): {len(softfixed)}")
for tile, h, m in softfixed:
    print(f"     ~ {tile['label']}  ->  art/{h}  via {m[0]}: {m[1]}")

print(f"\n=== ИТОГ ===")
print(f"  было битых тип-2: 21")
print(f"  осталось РЕАЛЬНЫХ дефектов: {len(residual)}")
print(f"  объяснено мягким правилом: {len(softfixed)}")

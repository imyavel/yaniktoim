# -*- coding: utf-8 -*-
import re, json, os
ROOT = r"C:\Users\admin\yaniktoim\docs\art"
M = json.load(open(r"C:\Users\admin\yaniktoim\.batch\music_maps.json", encoding="utf-8"))
LL = {tuple(k.split("|", 1)): v for k, v in M["ll"].items()}
def norm(t): return re.sub(r'\s+', ' ', re.sub(r'[«»“”"]', '', t)).strip().lower()

# ---------- 368 : flat (head/arrow/title) -> playable ----------
f = os.path.join(ROOT, "368.html"); h = open(f, encoding="utf-8").read()
m = re.search(r'<div class="track flat">\s*<div class="head">(.*?)</div>\s*</div>', h, re.S)
if m:
    head_inner = m.group(1)  # arrow + title span
    tt = re.search(r'<span class="title">(.*?)</span>', head_inner, re.S)
    title_txt = re.sub(r'<[^>]+>', ' ', tt.group(1)); title_txt = re.sub(r'\s+', ' ', title_txt).strip()
    vid = LL.get(("368", norm(title_txt)))
    if vid:
        new = ('<div class="track" data-yt="%s">\n        <div class="head">%s'
               '<a class="ext" href="https://www.youtube.com/watch?v=%s" target="_blank" rel="noopener" title="Открыть на YouTube">↗</a>\n        </div>\n        <div class="player"><div class="ratio"></div></div>\n      </div>'
               % (vid, head_inner.rstrip(), vid))
        h = h[:m.start()] + new + h[m.end():]
        open(f, "w", encoding="utf-8").write(h); print("368: converted «%s» -> %s" % (title_txt, vid))
    else:
        print("368: no map for", title_txt)

# ---------- 217A : flat (track-head/track-title) -> playable ----------
f = os.path.join(ROOT, "217A.html"); h = open(f, encoding="utf-8").read()
flat = re.compile(r'<div class="track flat">\s*<div class="track-head">\s*<span class="track-title">(.*?)</span>\s*(?:<span class="track-icons">.*?</span>\s*)?</div>\s*</div>', re.S)
done = {};
def repl(mm):
    raw_title = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', mm.group(1))).strip()
    vid = LL.get(("217A", norm(raw_title)))
    if not vid:
        return mm.group(0)  # leave non-mapped flat tracks
    disp = re.sub(r'^\s*YOUTUBE\.COM\s*[—-]\s*', '', mm.group(1)).strip()  # clean junk prefix
    done[raw_title] = vid
    return ('<div class="track" data-yt="%s">\n        <div class="track-head">\n          <span class="track-title">%s</span>\n'
            '          <span class="track-icons"><span class="chev">▾</span>'
            '<a class="ext" href="https://youtu.be/%s" target="_blank" rel="noopener" title="Открыть на YouTube">↗</a></span>\n'
            '        </div>\n        <div class="track-player"></div>\n      </div>' % (vid, disp, vid))
h2 = flat.sub(repl, h)
open(f, "w", encoding="utf-8").write(h2)
n = len(re.findall(r'<div class="track flat">', h)) - len(re.findall(r'<div class="track flat">', h2))
print("217A: converted %d flat-track occurrences; titles->id:" % n)
for t, v in done.items(): print("   «%s» -> %s" % (t[:45], v))
print("217A: flat tracks left:", len(re.findall(r'<div class="track flat">', h2)))

# -*- coding: utf-8 -*-
import re, glob, os, json
ROOT = r"C:\Users\admin\yaniktoim"
B = os.path.join(ROOT, ".batch")
res = json.load(open(os.path.join(B, "short_resolved.json"), encoding="utf-8"))
def T(n): return json.load(open(os.path.join(B, "zq_out", "%02d.json" % n), encoding="utf-8"))["translation"].strip()

AK = {"yUcfylRm":"001","pJEgVWrp":"003","BRG7YgUs":"004","M07beI2F":"006","0PRkRr2w":"007",
      "KnH2EYPh":"011","KJWljPMB":"012","jvJkHG2l":"017","F2LYqFgK":"022","lgUtBujx":"023",
      "aZn9EUGB":"029","SMsTmV9E":"030"}
SECT = {"NslF3LJh":"bereshit/001","ZEPIzcHJ":"bereshit/095","ejxH6XIB":"tetzaveh/003"}
DEAD_ZOHAR = {("0BH.html","https://goo.su/33lt"):"akdama/001",
              ("64P.html","https://clck.ru/3TPssD"):"akdama/001"}
ZBASE = "https://imyavel.github.io/zohar-sulam/%s.html"

def kid(u):
    m = re.search(r'kabbalahmedia\.info/ru/sources/([A-Za-z0-9]+)', res.get(u, u)) or \
        re.search(r'kabbalahmedia\.info/ru/sources/([A-Za-z0-9]+)', u)
    return m.group(1) if m else None
def is_bare(txt):
    t = re.sub(r'<[^>]+>', '', txt).strip()
    return t == '' or bool(re.match(r'(https?://|goo\.su/|clck\.ru/|www\.kabbalah\.info|kabbalahmedia\.info)', t))

atag = re.compile(r'<a\b[^>]*?href="([^"]*)"[^>]*?>(.*?)</a>', re.S)
stats = {"replace":0, "remove":0}

def process(fname, h):
    def f(m):
        whole, href, inner = m.group(0), m.group(1), m.group(2)
        if not re.search(r'(kabbalahmedia\.info|www\.kabbalah\.info|goo\.su|clck\.ru)', href):
            return whole
        target = None
        if (fname, href) in DEAD_ZOHAR: target = DEAD_ZOHAR[(fname, href)]
        else:
            k = kid(href)
            if k in AK: target = "akdama/" + AK[k]
            elif k in SECT: target = SECT[k]
            elif k or 'kabbalah.info' in href:   # kabbalahmedia non-Zohar / kabbalah.info -> REMOVE
                stats["remove"] += 1
                return ""    # drop the <a> entirely, keep surrounding attribution
            else:
                return whole  # goo.su/clck.ru -> youtube/wikisource/gdoc/dead-nonzohar -> LEAVE
        # REPLACE: swap href + (if bare url) visible text
        label = target  # e.g. akdama/029, bereshit/001, tetzaveh/003
        new_tag = re.sub(r'href="[^"]*"', 'href="%s"' % (ZBASE % target), whole, count=1)
        if is_bare(inner):
            new_tag = re.sub(r'(>)(.*?)(</a>)', lambda mm: mm.group(1) + label + mm.group(3), new_tag, count=1, flags=re.S)
        stats["replace"] += 1
        return new_tag
    return atag.sub(f, h)

changed = []
for fp in glob.glob(os.path.join(ROOT, "docs", "**", "*.html"), recursive=True):
    h0 = open(fp, encoding="utf-8").read()
    h = process(os.path.basename(fp), h0)
    if h != h0:
        open(fp, "w", encoding="utf-8").write(h)
        changed.append(os.path.basename(fp))

print("REPLACE:", stats["replace"], "REMOVE:", stats["remove"])
print("files changed:", len(set(changed)), sorted(set(changed)))

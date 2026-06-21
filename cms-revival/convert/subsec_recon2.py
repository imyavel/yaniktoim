# -*- coding: utf-8 -*-
"""Сколько описательных подзаголовков (deck/standfirst/subtitle) ЗАПЕРТО внутри
<header>/.lead и потому выбрасывается как хром (и невидимо оракулу)."""
import re, glob, os, importlib.util
os.chdir(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("conv", "html_to_zml.py")
conv = importlib.util.module_from_spec(spec); spec.loader.exec_module(conv)
ART = conv.ROOT / "yaniktoim" / "docs" / "art"
CAND = re.compile(r"\b(deck|standfirst|subtitle)\b")
HDR_CLS = {"lead", "lead-main", "masthead", "article-header", "post-header"}

hits = []
for p in sorted(glob.glob(str(ART / "*.html"))):
    art = os.path.basename(p)[:-5]
    if "." in art:
        continue
    html = open(p, encoding="utf-8").read()
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    if not m:
        continue
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", m.group(1), flags=re.S)
    t = conv.Tree(); t.feed(body); root = t.root

    def walk(node, in_header):
        for k in node.get("kids", []):
            if not isinstance(k, dict):
                continue
            c = conv.cls(k)
            ih = in_header or k["tag"] in ("header", "footer", "nav") or bool(c & HDR_CLS)
            ctext = " ".join(sorted(c))
            if CAND.search(ctext) and ih:
                txt = re.sub(r"\s+", " ", conv.raw_text(k)).strip()
                if txt:
                    hits.append((art, k["tag"], ctext, len(txt), txt[:70]))
            walk(k, ih)
    walk(root, False)

print("=== %d описательных подзаголовков заперто в header/.lead ===" % len(hits))
for h in hits:
    print("  %-6s %-4s %-22s len=%-4d %r" % h)

# -*- coding: utf-8 -*-
"""Точная диагностика: какие описат. подзаголовки РЕАЛЬНО выброшены (предок =
<header>-тег, скипается конвертером) vs живут в <div class=lead> (walk их видит).
Колонка in_zml: есть ли текст в текущем out/<id>.zml."""
import re, glob, os, importlib.util
os.chdir(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("conv", "html_to_zml.py")
conv = importlib.util.module_from_spec(spec); spec.loader.exec_module(conv)
ART = conv.ROOT / "yaniktoim" / "docs" / "art"
CAND = re.compile(r"\b(deck|standfirst|subtitle|article-subtitle)\b")

rows = []
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
    zml = ""
    op = "out/%s.zml" % art
    if os.path.exists(op):
        zml = open(op, encoding="utf-8").read()

    def walk(node, in_hdr_tag):
        for k in node.get("kids", []):
            if not isinstance(k, dict):
                continue
            ih = in_hdr_tag or k["tag"] == "header"
            c = conv.cls(k)
            if CAND.search(" ".join(sorted(c))):
                txt = re.sub(r"\s+", " ", conv.raw_text(k)).strip()
                if txt:
                    probe = re.sub(r"\s+", "", txt[:25])
                    in_zml = probe in re.sub(r"\s+", "", zml)
                    rows.append((art, "/".join(sorted(c)), "HDR" if ih else "div",
                                 "in_zml" if in_zml else "DROPPED", txt[:55]))
            walk(k, ih)
    walk(root, False)

drop = [r for r in rows if r[3] == "DROPPED"]
print("=== %d кандидатов; DROPPED=%d ===" % (len(rows), len(drop)))
for r in rows:
    print("  %-6s %-18s %-4s %-8s %r" % r)

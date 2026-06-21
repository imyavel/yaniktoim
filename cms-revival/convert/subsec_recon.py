# -*- coding: utf-8 -*-
"""Разведка краевых схем [subsec]: где живут subtitle-ish узлы относительно
##-заголовков и шапки. Для каждого узла-кандидата: art, tag, class, текст,
предыдущий блок-сиблинг (tag.class), внутри-секции-ли (после первого h2)."""
import re, glob, os, json, importlib.util
os.chdir(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("conv", "html_to_zml.py")
conv = importlib.util.module_from_spec(spec); spec.loader.exec_module(conv)

CAND = re.compile(r"(subtitle|subhead|sub-h|vsub|deck|standfirst|lede|subkicker"
                  r"|article-subtitle|work-sub|undertitle|sub-meta|sub-paren|sub-label|sub-title)")
HANDLED = {"sec-sub", "poemsub", "poem-sub", "poemtitle", "poem-title"}
ART = conv.ROOT / "yaniktoim" / "docs" / "art"

rows = []
for p in sorted(glob.glob(str(ART / "*.html"))):
    art = os.path.basename(p)[:-5]
    if "." in art or art.endswith("view"):
        continue
    html = open(p, encoding="utf-8").read()
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    if not m:
        continue
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", m.group(1), flags=re.S)
    t = conv.Tree(); t.feed(body); root = t.root

    # обойти все узлы, отслеживая «видели ли уже h2/h1» в порядке документа
    def walk(node, seen):
        kids = node.get("kids", [])
        prev = None  # предыдущий блок-сиблинг
        for k in kids:
            if not isinstance(k, dict):
                continue
            tag = k["tag"]
            c = conv.cls(k)
            ctext = " ".join(sorted(c))
            if tag in ("h1",):
                seen["h1"] = True
            if tag in ("h2", "h3", "h4"):
                seen["h2"] = True
                seen["last_h"] = re.sub(r"\s+", " ", conv.raw_text(k)).strip()[:40]
            if CAND.search(ctext) and not (c & HANDLED):
                txt = re.sub(r"\s+", " ", conv.raw_text(k)).strip()
                pv = None
                if prev is not None:
                    pv = "%s.%s" % (prev["tag"], "/".join(sorted(conv.cls(prev))) or "-")
                rows.append({
                    "art": art, "tag": tag, "class": ctext,
                    "after_h2": seen.get("h2", False), "after_h1": seen.get("h1", False),
                    "prev": pv, "last_h": seen.get("last_h", ""),
                    "len": len(txt), "text": txt[:90],
                })
            prev = k
            walk(k, seen)

    walk(root, {})

# группировка по классу
by_cls = {}
for r in rows:
    by_cls.setdefault(r["class"], []).append(r)

print("=== %d узлов-кандидатов, %d классов ===" % (len(rows), len(by_cls)))
for cl in sorted(by_cls, key=lambda x: -len(by_cls[x])):
    rs = by_cls[cl]
    in_sec = sum(1 for r in rs if r["after_h2"])
    print("\n## class=%r  (%d; в секции после h2: %d)" % (cl, len(rs), in_sec))
    for r in rs[:8]:
        loc = "СЕК" if r["after_h2"] else ("ШАПКА" if not r["after_h1"] else "тело-доH2")
        print("   %-6s %-4s %-5s prev=%-18s <%s> %r"
              % (r["art"], r["tag"], loc, r["prev"], r["last_h"], r["text"]))
    if len(rs) > 8:
        print("   … +%d" % (len(rs) - 8))
open("subsec_recon.json", "w", encoding="utf-8").write(json.dumps(rows, ensure_ascii=False, indent=1))

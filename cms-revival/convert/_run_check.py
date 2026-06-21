# -*- coding: utf-8 -*-
"""Прогон корпуса + инварианты + список изменившихся (out vs docs/art)."""
import json, glob, os, re, importlib.util, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("conv", "html_to_zml.py")
conv = importlib.util.module_from_spec(spec); spec.loader.exec_module(conv)
DOCS = conv.ROOT / "docs" / "art"

ids = sorted(os.path.basename(p)[:-4] for p in glob.glob("out/*.zml"))
res, errs = {}, []
for art in ids:
    conv.FLAGS.clear()
    try:
        zml, cov = conv.convert(art)
    except Exception as e:
        import traceback
        errs.append((art, repr(e), traceback.format_exc()))
        continue
    res[art] = {"cov": round(cov, 3) if cov is not None else None,
                "flags": [f for f in conv.FLAGS if f.startswith("[%s]" % art)]}

covs = [v["cov"] for v in res.values() if v["cov"] is not None]
corridor = sum(1 for c in covs if 0.97 <= c <= 1.05)
below = sorted((a, res[a]["cov"]) for a in res if res[a]["cov"] is not None and res[a]["cov"] < 0.97)
above = sorted((a, res[a]["cov"]) for a in res if res[a]["cov"] is not None and res[a]["cov"] > 1.20)

# сноски-определения по всему корпусу (out/*.zml после прогона)
fn_def = 0
for p in glob.glob("out/*.zml"):
    for ln in open(p, encoding="utf-8"):
        if re.match(r"^\[\^[^\]]*\]:", ln):
            fn_def += 1

# изменившиеся: out/<id>.zml != docs/art/<id>.zml
changed = []
for art in ids:
    op = "out/%s.zml" % art
    dp = DOCS / ("%s.zml" % art)
    if not dp.exists():
        changed.append((art, "NEW"))
        continue
    if open(op, encoding="utf-8").read() != dp.read_text("utf-8"):
        changed.append((art, "diff"))

out = []
out.append("TOTAL=%d ERRORS=%d" % (len(ids), len(errs)))
out.append("CORRIDOR(0.97-1.05)=%d  below0.97=%d  above1.20=%d" % (corridor, len(below), len(above)))
out.append("FN_DEFS=%d" % fn_def)
out.append("CHANGED=%d: %s" % (len(changed), ", ".join("%s(%s)" % c for c in changed)))
out.append("BELOW: %s" % ", ".join("%s=%.3f" % b for b in below))
out.append("ABOVE: %s" % ", ".join("%s=%.3f" % a for a in above))
for art, e, tb in errs:
    out.append("ERR %s: %s" % (art, e))
open("_run_check.txt", "w", encoding="utf-8").write("\n".join(out))
# touched-articles flags
touched = ["1CM", "roza_mira", "071", "17BA", "1BI", "46L", "462", "272", "2BS", "32K", "1AM"]
tf = []
for a in touched:
    if a in res:
        tf.append("=== %s cov=%s ===" % (a, res[a]["cov"]))
        tf += res[a]["flags"]
open("_run_check_flags.txt", "w", encoding="utf-8").write("\n".join(tf))
print("\n".join(out[:4]))
print("errors:", len(errs))

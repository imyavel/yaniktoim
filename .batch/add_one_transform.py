# -*- coding: utf-8 -*-
"""Сверстать ОДНУ статью тем же промптом/механизмом, что и legacy batch-раннер,
но с путями, указывающими на ЖИВОЙ корень yaniktoim/ (а не legacy/).

Импортирует legacy/src/3b_transform_html.py как модуль, переопределяет его
path-глобалы на живой корень и зовёт transform_one().

  python -X utf8 .batch/add_one_transform.py 666
  python -X utf8 .batch/add_one_transform.py 666 --force
"""
from __future__ import annotations
import io, sys, json, importlib.util
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

LIVE = Path(r"C:\Users\admin\yaniktoim")
SRC = LIVE / "legacy" / "src" / "3b_transform_html.py"
PROMPT = LIVE / "legacy" / "batch_runner" / "convert_prompt_005.md"

spec = importlib.util.spec_from_file_location("th_live", SRC)
th = importlib.util.module_from_spec(spec)
spec.loader.exec_module(th)

# Переопределяем все path-глобалы модуля на ЖИВОЙ корень.
th.ROOT = LIVE
th.RAW = LIVE / "raw"
th.SITE = LIVE / "docs"
th.ART_DIR = LIVE / "docs" / "art"
th.LOGS = LIVE / "_logs"
th.MANIFEST = LIVE / "manifest.json"
th.PROMPT_MD = PROMPT

force = "--force" in sys.argv
args = [a for a in sys.argv[1:] if a != "--force"]
art = args[0]

manifest = json.loads(th.MANIFEST.read_text(encoding="utf-8"))
rec = next((r for r in manifest if r.get("art") == art), None)
if rec is None:
    print(f"art {art} not found in manifest"); sys.exit(2)
base_prompt = PROMPT.read_text(encoding="utf-8")

print(f"transform art={art} stem={rec['stem']} section={rec['section']} "
      f"force={force}")
res = th.transform_one(rec, base_prompt, manifest, force=force)
print(f"RESULT kind={res.kind} detail={res.detail!r}")
sys.exit(0 if res.ok else 3)

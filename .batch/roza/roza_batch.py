# -*- coding: utf-8 -*-
"""Последовательный батч по томам: pass1→pass2, идемпотентно/возобновляемо.
Usage: python roza_batch.py 02 03 04 ...   (по умолчанию 02..12)"""
import sys, re, time
from pathlib import Path
import roza_run as R

OUT = R.OUT
def frag_valid(nn):
    f = OUT/f"vol_{nn}.html"
    if not f.exists(): return False
    h = f.read_text(encoding="utf-8")
    need = ["Главные идеи","Модели и концепции","Ключевые термины","Выводы и акценты"]
    if any(x not in h for x in need): return False
    if "<html" in h.lower() or "<script" in h.lower(): return False
    if f'id="vol-{nn}"' not in h: return False
    w = len(re.sub(r"<[^>]+>"," ",h).split())
    return 1200 <= w <= 3200

vols = sys.argv[1:] or [f"{i:02d}" for i in range(2,13)]
log = OUT/"batch.log"
def say(m):
    print(m, flush=True)
    with open(log,"a",encoding="utf-8") as f: f.write(m+"\n")

say(f"=== BATCH START vols={vols} ===")
res={}
for nn in vols:
    if frag_valid(nn):
        say(f"[{nn}] SKIP (fragment already valid)"); res[nn]="skip"; continue
    notes = OUT/f"vol_{nn}_notes.md"
    if not (notes.exists() and len(notes.read_text(encoding='utf-8'))>800):
        say(f"[{nn}] pass1 ...")
        if not R.pass1(nn):
            say(f"[{nn}] PASS1 FAIL — abort vol"); res[nn]="p1fail"; continue
    else:
        say(f"[{nn}] pass1 cached")
    say(f"[{nn}] pass2 ...")
    ok = R.pass2(nn)
    # one auto-retry of pass2 if thin/invalid
    if not ok and (OUT/f"vol_{nn}.html").exists():
        say(f"[{nn}] pass2 retry once")
        ok = R.pass2(nn)
    res[nn] = "ok" if (ok and frag_valid(nn)) else "p2fail"
    say(f"[{nn}] -> {res[nn]}")
say(f"=== BATCH DONE {res} ===")

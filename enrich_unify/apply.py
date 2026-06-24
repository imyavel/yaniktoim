"""Применить структурные правки унификации к docs/art/*.zml. Только kind!=TEXT,
исключённые (exclude.txt) пропускаются. Безопасно: правка применяется ТОЛЬКО если
строка с номером e['line'] точно равна e['before'] (иначе — лог mismatch, пропуск).
Идемпотентно: если строка уже == e['after'] — пропуск.

  python apply.py --dry     # показать, ничего не писать
  python apply.py           # применить
"""
from __future__ import annotations
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ART = ROOT / "docs" / "art"
OUT = HERE / "out"
EXCL = ({ln.strip() for ln in (HERE / "exclude.txt").read_text(encoding="utf-8").splitlines()
         if ln.strip() and not ln.startswith("#")} if (HERE / "exclude.txt").exists() else set())

def main():
    dry = "--dry" in sys.argv
    applied = skipped_done = mismatch = 0
    touched = 0
    for jf in sorted(OUT.glob("*.json")):
        fid = jf.stem
        if fid in EXCL:
            continue
        edits = [e for e in json.loads(jf.read_text(encoding="utf-8")).get("edits", [])
                 if e.get("kind") != "TEXT"]
        if not edits:
            continue
        zml = ART / f"{fid}.zml"
        lines = zml.read_text(encoding="utf-8").split("\n")
        changed = False
        for e in edits:
            i = e.get("line", 0) - 1
            if not (0 <= i < len(lines)):
                mismatch += 1; print(f"  MISMATCH {fid}:{e.get('line')} line out of range"); continue
            if lines[i] == e.get("after"):
                skipped_done += 1; continue
            if lines[i] != e.get("before"):
                mismatch += 1
                print(f"  MISMATCH {fid}:{e.get('line')}\n    have: {lines[i][:90]!r}\n    want: {e.get('before','')[:90]!r}")
                continue
            lines[i] = e.get("after"); applied += 1; changed = True
        if changed and not dry:
            zml.write_text("\n".join(lines), encoding="utf-8")
            touched += 1
    print(f"\n{'DRY ' if dry else ''}applied={applied} already-done={skipped_done} mismatch={mismatch} files-touched={touched}")

if __name__ == "__main__":
    main()

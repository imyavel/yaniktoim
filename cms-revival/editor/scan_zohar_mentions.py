"""enrich_zohar Фаза 2 — сканер ВСЕХ Зоар-упоминаний корпуса → worklist.json.

Классифицирует каждое упоминание в docs/art/*.zml:
  TAG_NUM   — {ch|N}            (есть глава+номер; нужен дубль-снос, § авто-первый)
  TAG_PARA  — {ch||§}           (Phase A; нужно +N статьи, дубль-снос)
  TAG_FULL  — {ch|N|§}          (уже целевая форма; проверить дубль рядом)
  CITE_URL  — cite="[zohar-url|путь]"  (3 эпиграфа; путь→тег)
  CITE_BARE — cite="…Зоар…" без ссылки (определить главу+§ или в отчёт)
  TEXT      — Зоар/Сулам/Ашлаг/РАШБИ в прозе без тега/cite (worklist B; триаж)

Вывод: enrich_unify/worklist.json  — {file: {path, mentions:[{line,col?,kind,text}]}}.
Только чтение; ничего не правит.
"""
from __future__ import annotations
import re, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ART = ROOT / "docs" / "art"
OUT = ROOT / "enrich_unify"
OUT.mkdir(exist_ok=True)

TAG = re.compile(r"\{([a-z][a-z0-9-]*)?\|(\d*)(?:\|(\d*))?\}")
CITE = re.compile(r'cite="([^"]*)"')
ZURL = re.compile(r'\[https?://[^\]|]*zohar[^\]|]*\|[^\]]+\]', re.I)
# маркеры зоар-упоминания в прозе
ZWORD = re.compile(r"Зоар|ЗОАР|Зогар|Зоѓар|Сулам|Ашлаг|РАШБИ|Рашби|Бааль\s+Сулам|перуш", re.I)

def classify_tag(ch, num, para):
    if not ch:
        return "TAG_ROOT"        # {|} весь Зоар / битые — почти нет
    if num and para:
        return "TAG_FULL"
    if num and not para:
        return "TAG_NUM"
    if not num and para:
        return "TAG_PARA"
    return "TAG_CHAP"            # {ch|} вся глава

def main():
    result = {}
    for zml in sorted(ART.glob("*.zml")):
        fid = zml.stem
        lines = zml.read_text(encoding="utf-8").splitlines()
        mentions = []
        for i, ln in enumerate(lines, 1):
            seen_tag = False
            for m in TAG.finditer(ln):
                seen_tag = True
                kind = classify_tag(m.group(1), m.group(2), m.group(3))
                mentions.append({"line": i, "kind": kind, "tag": m.group(0), "text": ln.strip()})
            # cite= с Зоаром
            for cm in CITE.finditer(ln):
                cval = cm.group(1)
                if ZURL.search(ln):
                    mentions.append({"line": i, "kind": "CITE_URL", "text": ln.strip()})
                elif ZWORD.search(cval):
                    mentions.append({"line": i, "kind": "CITE_BARE", "text": ln.strip()})
            # текстовое упоминание без тега и без cite-обработки выше
            if not seen_tag and "cite=" not in ln and ZWORD.search(ln):
                mentions.append({"line": i, "kind": "TEXT", "text": ln.strip()})
        if mentions:
            result[fid] = {"path": str(zml.relative_to(ROOT)).replace("\\", "/"), "mentions": mentions}
    (OUT / "worklist.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    # сводка
    from collections import Counter
    c = Counter()
    for f in result.values():
        for mn in f["mentions"]:
            c[mn["kind"]] += 1
    print(f"files with mentions: {len(result)}")
    for k, v in sorted(c.items(), key=lambda x: -x[1]):
        print(f"  {k:10} {v}")
    print(f"total mentions: {sum(c.values())}")

if __name__ == "__main__":
    main()

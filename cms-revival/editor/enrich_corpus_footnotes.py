"""§4-5 (корзина A, детерминированная часть) — обогатить Зоар-ссылки по сноскам.

Сноски корпуса цитируют по формату «<заголовок>, п. <§>, … {глава|статья}». Где
у строки с существующей ссылкой {глава|N} есть явный «п. <§>» (или «параграф»/«§»),
И этот § по индексу принадлежит ИМЕННО статье N — апгрейдим до {глава||§}
(каноничная форма цитаты по плану §0: глава+параграф, номер статьи выводится из §).

Жёсткий инвариант: меняем ТОЛЬКО если paras[ch][§] == N (§ реально внутри статьи) →
ссылка не может «уехать» на другую статью. Прочее (без явного «п.», мисматч §↔статья)
не трогаем — это LLM-триаж. Идемпотентно (ссылка уже с § → пропуск).

  python cms-revival/editor/enrich_corpus_footnotes.py            # dry-run (показать)
  python cms-revival/editor/enrich_corpus_footnotes.py --apply    # записать
"""
from __future__ import annotations
import re
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                       # yaniktoim
ART = ROOT / "docs" / "art"
INDEX = json.loads((HERE / "data" / "zohar_index.json").read_text(encoding="utf-8"))
PARAS = INDEX["paras"]

CORZINA_A = ("05D 09G 0B6 0BC 0BCA 0BH 0CA 11U 11UA 12F 12L 12P 163 163A 165 16D "
             "17U 18A 18AA 18T 19UA 1AA 1B5 1BF 1BH 1CF 217A 239 24I 255 28MA 2C7 "
             "341A 34O 462 46L 47H 47O 591 64P 666").split()

LINK = re.compile(r"\{([a-z][a-z0-9-]*)\|(\d+)\}")          # только {ch|N} (есть глава+номер)
HINT = re.compile(r"(?:п\.?\s*|параграф\s*|§\s*)(\d+)", re.I)


def enrich_line(line: str) -> tuple[str, list]:
    changes = []
    hints = [h for h in HINT.findall(line)]

    def repl(m: re.Match) -> str:
        ch, num = m.group(1), m.group(2)
        owner_map = PARAS.get(ch, {})
        for h in hints:
            if owner_map.get(h) == str(int(num)):     # § принадлежит статье N
                changes.append((m.group(0), f"{{{ch}||{h}}}", f"§{h}→ст.{num}"))
                return f"{{{ch}||{h}}}"
        return m.group(0)

    return LINK.sub(repl, line), changes


def main() -> int:
    apply = "--apply" in sys.argv
    total = 0
    for aid in CORZINA_A:
        fp = ART / f"{aid}.zml"
        if not fp.exists():
            print(f"  MISSING {aid}", file=sys.stderr)
            continue
        lines = fp.read_text(encoding="utf-8").split("\n")
        out = []
        file_changes = []
        for ln in lines:
            new, ch = enrich_line(ln)
            out.append(new)
            file_changes.extend(ch)
        if file_changes:
            total += len(file_changes)
            print(f"{aid}: " + "; ".join(f"{a}→{b} ({n})" for a, b, n in file_changes))
            if apply:
                fp.write_text("\n".join(out), encoding="utf-8")
    print(f"\n{'ПРИМЕНЕНО' if apply else 'DRY-RUN'}: обогащено ссылок {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

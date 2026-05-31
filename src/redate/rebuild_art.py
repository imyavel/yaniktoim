"""Пересобрать art-id по обновлённым датам (manifest_redated.json) и сравнить
со старыми артиклями из manifest.json.

Кодеки и алгоритм группировки — те же, что в src/build_art_ids.py (SPEC §2.3):
группа по date_chosen, сортировка по url_nnn, суффикс по позиции в группе.

Выход:
  • manifest_redated.json — с пересчитанным полем art;
  • _logs/art_diff.md — таблица старый→новый art (только изменения) + сводка.
Канонический manifest.json НЕ трогаем — свап делает оператор отдельно.
"""
from __future__ import annotations
import io, sys, json, datetime as dt
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[2]
REDATED = ROOT / "manifest_redated.json"
ORIG = ROOT / "manifest.json"
DIFF = ROOT / "_logs" / "art_diff.md"


def enc_year(y: int) -> str:
    if 2020 <= y <= 2029:
        return str(y - 2020)
    if 1994 <= y <= 2019:
        return chr(ord("Z") - (2019 - y))
    raise ValueError(f"year {y} out of range")


def enc_month(mo: int) -> str:
    return str(mo) if 1 <= mo <= 9 else chr(ord("A") + mo - 10)


def enc_day(d: int) -> str:
    return str(d) if 1 <= d <= 9 else chr(ord("A") + d - 10)


def enc_suffix(n: int) -> str:
    if n == 0:
        return ""
    if 1 <= n <= 26:
        return chr(ord("A") + n - 1)
    if 27 <= n <= 52:
        return chr(ord("a") + n - 27)
    raise ValueError(f"too many per day: position {n + 1}")


def make_art(d: dt.date, pos: int) -> str:
    return enc_year(d.year) + enc_month(d.month) + enc_day(d.day) + enc_suffix(pos)


def main() -> int:
    man = json.loads(REDATED.read_text(encoding="utf-8"))
    orig = {r["number"]: r for r in json.loads(ORIG.read_text(encoding="utf-8"))}

    by_date: dict[str, list[dict]] = defaultdict(list)
    for r in man:
        by_date[r["date_chosen"]].append(r)

    art_to_stem: dict[str, str] = {}
    errors: list[str] = []
    for date_str, group in by_date.items():
        group.sort(key=lambda x: int(x["url_nnn"]))
        try:
            d = dt.date.fromisoformat(date_str)
        except ValueError as e:
            errors.append(f"{group[0]['stem']}: bad date {date_str!r} ({e})")
            continue
        for pos, rec in enumerate(group):
            try:
                art = make_art(d, pos)
            except ValueError as e:
                errors.append(f"{rec['stem']}: {e}")
                continue
            if art in art_to_stem:
                errors.append(f"COLLISION {art!r}: {art_to_stem[art]} vs {rec['stem']}")
                continue
            art_to_stem[art] = rec["stem"]
            rec["art"] = art

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors[:20]:
            print("  -", e)
        return 3

    # diff старый→новый art
    changed = []
    for r in man:
        old = orig.get(r["number"], {}).get("art")
        if old != r["art"]:
            changed.append((r["number"], old, r["art"], r["date_chosen"],
                            orig.get(r["number"], {}).get("date_chosen"),
                            r["date_source"], r["title"][:34]))

    REDATED.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# Art diff (manifest.json → manifest_redated.json)\n",
             f"Статей: {len(man)} · артиклей всего: {len(art_to_stem)} · "
             f"изменился art: **{len(changed)}** · коллизий: 0\n",
             f"\n| # | old_art | NEW_art | new_date | old_date | src | title |",
             f"|---|---|---|---|---|---|---|"]
    for n, oa, na, nd, od, src, t in sorted(changed):
        lines.append(f"| {n} | `{oa}` | **`{na}`** | {nd} | {od} | {src} | {t} |")
    DIFF.write_text("\n".join(lines), encoding="utf-8")

    print(f"Total arts: {len(art_to_stem)} (unique, 0 collisions)")
    print(f"art changed: {len(changed)} / {len(man)}")
    dates_sorted = sorted(by_date)
    print(f"date range: {dates_sorted[0]} (art={by_date[dates_sorted[0]][0]['art']}) "
          f".. {dates_sorted[-1]}")
    print(f"max per day: {max(len(g) for g in by_date.values())}")
    print(f"Art diff -> {DIFF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

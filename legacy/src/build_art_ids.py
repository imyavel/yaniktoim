"""Сгенерировать `art`-id для всех статей в `manifest.json`.

Формат `art` — см. SPEC.md §2.3:
  XYZ        — для одной статьи в день (X=год, Y=месяц, Z=день; всё base-32)
  XYZA..XYZZ — для 2-й..27-й статьи того же дня (suffix A..Z)
  XYZa..XYZz — для 28-й..53-й статьи того же дня (suffix a..z)

Шкала года (один символ):
  0..9 = 2020..2029
  Z=2019, Y=2018, ..., A=1994 (обратная шкала для редких ранних)

Алгоритм:
  1. Прочитать `manifest.json`.
  2. Сгруппировать записи по `date_chosen`.
  3. В каждой группе отсортировать по `url_nnn` ascending.
  4. Присвоить каждой записи `art` по позиции в группе.
  5. Проверить уникальность.
  6. Записать обновлённый `manifest.json` (старая копия в `manifest_pre_art.json`).

Идемпотентен — повторный запуск с тем же набором даёт тот же результат.
"""
from __future__ import annotations
import datetime as dt
import io
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.json"
BACKUP = ROOT / "manifest_pre_art.json"


# ────── кодеки ──────

def encode_year(year: int) -> str:
    """`0`..`9` = 2020..2029; `Z`..`A` = 2019..1994."""
    if 2020 <= year <= 2029:
        return str(year - 2020)
    if 1994 <= year <= 2019:
        # 2019 → 0 steps back → 'Z'; 1994 → 25 steps back → 'A'.
        return chr(ord("Z") - (2019 - year))
    raise ValueError(f"Year {year} out of supported range (1994–2029)")


def encode_month(month: int) -> str:
    """`1`..`9`, `A`=10, `B`=11, `C`=12."""
    if 1 <= month <= 9:
        return str(month)
    if 10 <= month <= 12:
        return chr(ord("A") + month - 10)
    raise ValueError(f"Invalid month {month}")


def encode_day(day: int) -> str:
    """`1`..`9`, `A`=10, ..., `V`=31."""
    if 1 <= day <= 9:
        return str(day)
    if 10 <= day <= 31:
        return chr(ord("A") + day - 10)
    raise ValueError(f"Invalid day {day}")


def encode_suffix(n: int) -> str:
    """n=0 → "", n=1..26 → A..Z, n=27..52 → a..z, n>52 → ValueError."""
    if n == 0:
        return ""
    if 1 <= n <= 26:
        return chr(ord("A") + n - 1)
    if 27 <= n <= 52:
        return chr(ord("a") + n - 27)
    raise ValueError(
        f"Too many articles per day (position {n + 1}); max is 53"
    )


def make_art(date: dt.date, position: int) -> str:
    """Полный art из даты и порядка в группе."""
    return (
        encode_year(date.year)
        + encode_month(date.month)
        + encode_day(date.day)
        + encode_suffix(position)
    )


# ────── main ──────

def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print(f"Loaded manifest: {len(manifest)} entries", flush=True)

    # 1. Проверить наличие date_chosen у каждой записи.
    missing = [r["stem"] for r in manifest if not r.get("date_chosen")]
    if missing:
        print(f"ERROR: {len(missing)} entries без date_chosen:")
        for s in missing[:10]:
            print(f"  - {s}")
        return 2

    # 2. Сгруппировать по date_chosen.
    by_date: dict[str, list[dict]] = defaultdict(list)
    for r in manifest:
        by_date[r["date_chosen"]].append(r)

    # 3. В каждой группе — сортировка по url_nnn ascending.
    multi_day_groups: list[tuple[str, list[dict]]] = []
    for date_str, group in by_date.items():
        group.sort(key=lambda x: int(x["url_nnn"]))
        if len(group) > 1:
            multi_day_groups.append((date_str, group))

    # 4. Присвоить art каждой записи.
    art_to_stem: dict[str, str] = {}
    errors: list[str] = []
    for date_str, group in by_date.items():
        try:
            d = dt.date.fromisoformat(date_str)
        except ValueError as e:
            errors.append(f"{group[0]['stem']}: bad date_chosen={date_str!r} ({e})")
            continue
        for pos, rec in enumerate(group):
            try:
                art = make_art(d, pos)
            except ValueError as e:
                errors.append(f"{rec['stem']}: {e}")
                continue
            if art in art_to_stem:
                errors.append(
                    f"COLLISION: art={art!r} already taken by "
                    f"{art_to_stem[art]!r}, can't assign to {rec['stem']!r}"
                )
                continue
            art_to_stem[art] = rec["stem"]
            rec["art"] = art

    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors[:20]:
            print(f"  - {e}")
        if len(errors) > 20:
            print(f"  ... +{len(errors) - 20} more")
        return 3

    # 5. Backup + write.
    if not BACKUP.exists():
        shutil.copy2(MANIFEST, BACKUP)
        print(f"Backup → {BACKUP.name}")
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Updated → {MANIFEST.name}")

    # 6. Stats.
    print()
    print(f"Total arts assigned:        {len(art_to_stem)}")
    print(f"Dates with single article:  {sum(1 for g in by_date.values() if len(g) == 1)}")
    print(f"Dates with multiple:        {len(multi_day_groups)}")
    print(f"Max articles in one date:   {max(len(g) for g in by_date.values())}")
    print()
    print(f"Date range:")
    dates_sorted = sorted(by_date.keys())
    print(f"  earliest: {dates_sorted[0]}  → art={by_date[dates_sorted[0]][0]['art']}")
    print(f"  latest:   {dates_sorted[-1]} → art={by_date[dates_sorted[-1]][-1]['art']}")
    print()
    print("Multi-per-day groups (top 10 by size):")
    multi_day_groups.sort(key=lambda x: -len(x[1]))
    for date_str, group in multi_day_groups[:10]:
        arts = [r["art"] for r in group]
        print(f"  {date_str}: {len(group)} arts = {arts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

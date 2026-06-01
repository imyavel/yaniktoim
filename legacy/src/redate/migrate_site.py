"""Миграция на исправленные даты/артикли.

Шаги:
  1. Бэкап текущего manifest.json → manifest_pre_redate.json (если ещё нет).
  2. Свап: manifest_redated.json → manifest.json (служебные поля date_marks/
     date_win_raw убираем, схему возвращаем к исходной).
  3. Переименование опубликованных страниц docs/art/<old>.html → <new>.html
     для всех изменившихся art. Двухфазно (old→.tmp→new), т.к. среди правок
     есть цепочечные перестановки (A→B, где B занят переезжающей статьёй).

Перечни (docs/<section>/index.html) пересобираются отдельно: src/5_index.py.
"""
from __future__ import annotations
import io, sys, json, shutil
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "manifest.json"
REDATED = ROOT / "manifest_redated.json"
BACKUP = ROOT / "manifest_pre_redate.json"
ART = ROOT / "docs" / "art"

DROP_FIELDS = ("date_marks", "date_win_raw")
TMP = ".migrate.tmp"


def main() -> int:
    orig = json.loads(MANIFEST.read_text(encoding="utf-8"))
    new = json.loads(REDATED.read_text(encoding="utf-8"))
    orig_by = {r["number"]: r for r in orig}

    # 1. backup
    if not BACKUP.exists():
        shutil.copy2(MANIFEST, BACKUP)
        print(f"backup → {BACKUP.name}")
    else:
        print(f"backup exists: {BACKUP.name} (keep)")

    # план переименований (только изменившиеся art, файл которых опубликован)
    renames = []
    for r in new:
        old_art = orig_by[r["number"]]["art"]
        if old_art != r["art"] and (ART / f"{old_art}.html").exists():
            renames.append((old_art, r["art"]))

    news = {n for _, n in renames}
    olds = {o for o, _ in renames}
    if len(news) != len(renames):
        print("FATAL: дубли среди новых имён — прервано")
        return 2

    # 2. двухфазное переименование
    for old, _ in renames:
        (ART / f"{old}.html").rename(ART / f"{old}{TMP}")
    for old, nw in renames:
        (ART / f"{old}{TMP}").rename(ART / f"{nw}.html")
    print(f"renamed {len(renames)} published pages (two-phase)")

    # проверка: все новые есть, старые (не занятые новыми) исчезли
    missing = [n for n in news if not (ART / f"{n}.html").exists()]
    orphan = [o for o in olds if o not in news and (ART / f"{o}.html").exists()]
    leftover_tmp = list(ART.glob(f"*{TMP}"))
    if missing or orphan or leftover_tmp:
        print(f"WARN missing_new={missing} orphan_old={orphan} tmp={leftover_tmp}")

    # 3. свап манифеста (чистим служебные поля)
    for r in new:
        for f in DROP_FIELDS:
            r.pop(f, None)
    MANIFEST.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"swapped manifest.json ({len(new)} records, dropped {DROP_FIELDS})")

    n_pub = len(list(ART.glob("*.html")))
    print(f"docs/art now: {n_pub} html files")
    return 0


if __name__ == "__main__":
    sys.exit(main())

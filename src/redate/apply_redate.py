"""Применить политику к разметке дат от модели и собрать новый манифест.

Политика (детерминированно в коде):
  date_chosen = самая ранняя дата с role=authorship и value ≤ url_date;
                если таких нет → url_date (date_source='url').

Вход:  manifest.json  +  _logs/redate/batch_*.json (разметка модели).
Выход: manifest_redated.json  +  _logs/redate_diff.md (отчёт расхождений).
Артикли НЕ трогаем — это отдельный шаг (build_art_ids.py на новом манифесте).
"""
from __future__ import annotations
import io, sys, json, re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "manifest.json"
BATCHDIR = ROOT / "_logs" / "redate"
OUT = ROOT / "manifest_redated.json"
DIFF = ROOT / "_logs" / "redate_diff.md"

AUTH_ROLE = "authorship"

# Копирайт-диапазоны вида «(с) 2020-2022, …» — НЕ даты написания.
RE_COPYRIGHT = re.compile(r"\(с\)|\(c\)|©|copyright|bneiadam", re.I)

# Ручные решения оператора (приоритет над разметкой модели).
OVERRIDES: dict[str, str] = {
    "243": "2008-04-26",  # «Написано ~2008 г.» → оператор зафиксировал точную дату
}


def load_marks() -> dict[str, dict]:
    marks: dict[str, dict] = {}
    for f in sorted(BATCHDIR.glob("batch_*.json")):
        if f.name.endswith(".err.txt"):
            continue
        for x in json.loads(f.read_text(encoding="utf-8")):
            marks[str(x["number"]).zfill(3)] = x
    return marks


def choose(url_date: str, dates: list[dict]) -> tuple[str, str, dict | None]:
    """→ (date_chosen, date_source, winning_mark)."""
    cands = [d for d in dates
             if d.get("role") == AUTH_ROLE and d.get("value")
             and d["value"] <= url_date
             and not RE_COPYRIGHT.search(d.get("raw", ""))]
    if not cands:
        return url_date, "url", None
    win = min(cands, key=lambda d: d["value"])
    return win["value"], "text", win


def main() -> int:
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    marks = load_marks()
    missing = [r["number"] for r in man if r["number"] not in marks]
    if missing:
        print(f"WARN: {len(missing)} статей без разметки: {missing[:15]}")

    diff_rows = []
    n_changed = 0
    for r in man:
        m = marks.get(r["number"])
        dates = (m or {}).get("dates", [])
        chosen, source, win = choose(r["url_date"], dates)
        if r["number"] in OVERRIDES:
            chosen = OVERRIDES[r["number"]]
            source = "override"
            win = {"value": chosen, "raw": "[оператор] " + (win or {}).get("raw", "")}
        old_chosen = r["date_chosen"]
        r["date_marks"] = dates
        r["date_chosen"] = chosen
        r["date_source"] = source
        r["text_date"] = win["value"] if win else None
        r["date_win_raw"] = win["raw"] if win else None
        if chosen != old_chosen:
            n_changed += 1
            diff_rows.append((r["number"], old_chosen, chosen, r["url_date"],
                              source, (win or {}).get("raw", ""),
                              (m or {}).get("note", "")))

    # sanity: chosen ≤ url everywhere
    bad = [r["number"] for r in man if r["date_chosen"] > r["url_date"]]

    OUT.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# Redate diff\n",
             f"Статей: {len(man)} · изменилась date_chosen: **{n_changed}** · "
             f"chosen>url (ошибки): {len(bad)}\n",
             f"\n| # | old_chosen | NEW_chosen | url_date | src | строка-источник | note |",
             f"|---|---|---|---|---|---|---|"]
    for n, oc, nc, url, src, raw, note in sorted(diff_rows):
        lines.append(f"| {n} | {oc} | **{nc}** | {url} | {src} | "
                     f"`{raw[:40]}` | {note[:50]} |")
    DIFF.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {OUT.name}: {len(man)} entries")
    print(f"date_chosen changed: {n_changed}")
    print(f"chosen>url violations: {len(bad)} {bad[:10]}")
    print(f"Diff report -> {DIFF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

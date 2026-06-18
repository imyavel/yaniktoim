# -*- coding: utf-8 -*-
"""
build_structure.py — собрать docs/config/structure.json из manifest.json.

structure.json — ЕДИНЫЙ источник СТРУКТУРЫ сайта (Ф10): список/имена/порядок
разделов + размещение/порядок/статус каждой статьи. Заголовки и даты статей в
него НЕ кладём (берутся из manifest при генерации списков → нет дрейфа названий).

Сидируется один раз из manifest (порядок разделов — кураторский ORDER, порядок
статей — section_order). Дальше structure.json правит admin-редактор структуры.
Идемпотентно: пере-генерация из manifest перезатирает (до первой ручной правки).

  python tools/build_structure.py            # записать docs/config/structure.json
  python tools/build_structure.py --check     # показать сводку, не писать
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.json"
OUT = ROOT / "docs" / "config" / "structure.json"

# Кураторский порядок и АВТОРСКИЕ имена разделов (= SECTION_HUMAN в render.js,
# = SECTION_NAMES в legacy 5_index.py). НЕ переименовывать сиды — имена далее
# живут в structure.json и правятся через UI.
ORDER = ["best", "dreamon", "cyberson", "dabudet", "confront", "shoshana", "other"]
SECTION_NAMES = {
    "best": "Избранное",
    "dreamon": "Мечтай!!",
    "cyberson": "Киберсон",
    "dabudet": "Да будет Свет!",
    "confront": "Конфронтология Духа",
    "shoshana": "Роза Среди Шипов",
    "other": "Без категории",
}
# Спец-страница (не обычный раздел): своя плитка на главной, не редактируется как
# раздел. href фиксирован; meta («N композиций») СЧИТАЕТСЯ из реального числа плиток
# в ZML-версии (docs/songs/index.zml), а не хардкодится — синхронно с динамическим
# скриптом главной (template_index.html). NB: build_structure.py перезатирает весь
# structure.json, поэтому в live-режиме его НЕ запускают (структуру правит UI); meta
# здесь — корректный сид/фолбэк для no-JS.
SONGS_ZML = ROOT / "docs" / "songs" / "index.zml"


def ru_plural(n, one, few, many):
    a, b = n % 10, n % 100
    if a == 1 and b != 11:
        return one
    if 2 <= a <= 4 and not (12 <= b <= 14):
        return few
    return many


def count_shir_tiles(zml_path):
    """Число валидных плиток в блоке [shir] (как рендер: ≥2 поля — ytID+Композиция)."""
    import re
    try:
        zml = zml_path.read_text(encoding="utf-8")
    except OSError:
        return 0
    m = re.search(r"\[shir\b[^\]]*\]([\s\S]*?)\[/shir\]", zml)
    if not m:
        return 0
    n = 0
    for ln in m.group(1).split("\n"):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        f = ln.split("|")
        if len(f) >= 2 and f[0].strip() and f[1].strip():
            n += 1
    return n


def specials():
    n = count_shir_tiles(SONGS_ZML)
    meta = f"{n} {ru_plural(n, 'композиция', 'композиции', 'композиций')}" if n else "220 композиций"
    return [{"slug": "songs", "name": "Песнь Ступеней",
             "href": "songs/index.html", "meta": meta}]


def num_overrides():
    """Снять ручные ярлыки '#<num>' из текущих страниц разделов, где num != art
    (напр. roza_mira → 'РМ'). Сид однократный; дальше живёт в structure.json."""
    import re
    rx = re.compile(r'<span class="num">#([^<]+)</span><a href="\.\./art/([^"]+?)\.html"')
    ov = {}
    for p in (ROOT / "docs").glob("*/index.html"):
        for num, art in rx.findall(p.read_text(encoding="utf-8")):
            if num != art:
                ov[art] = num
    return ov


def build():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ov = num_overrides()
    sections = [
        {"slug": s, "name": SECTION_NAMES[s], "order": i, "archived": False}
        for i, s in enumerate(ORDER)
    ]
    articles = []
    for r in manifest:
        sec = r.get("section")
        if sec not in SECTION_NAMES:
            sec = "other"
        rec = {
            "art": r["art"],
            "section": sec,
            "order": r.get("section_order", 9999),
            "status": "published",
        }
        if r["art"] in ov:
            rec["num"] = ov[r["art"]]   # ручной ярлык в списке (напр. РМ), default = art
        articles.append(rec)
    # стабильный порядок в файле: раздел (по ORDER), затем order
    sec_rank = {s: i for i, s in enumerate(ORDER)}
    articles.sort(key=lambda a: (sec_rank.get(a["section"], 999), a["order"], a["art"]))
    return {"version": 1, "sections": sections, "specials": specials(), "articles": articles}


def main():
    st = build()
    if "--check" in sys.argv:
        from collections import Counter
        c = Counter(a["section"] for a in st["articles"])
        print("sections:", [s["slug"] for s in st["sections"]])
        print("articles:", len(st["articles"]), "by section:", dict(c))
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"structure.json: {len(st['sections'])} разделов, "
          f"{len(st['articles'])} статей → {OUT}")


if __name__ == "__main__":
    main()

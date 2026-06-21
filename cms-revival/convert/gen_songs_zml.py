# -*- coding: utf-8 -*-
"""Миграция спец-страницы «Песнь Ступеней» на ZML-носитель (ZML3 §6.8).

Источник истины = yaniktoim/.batch/songs_data.json (ytID → {title:"Композиция — Автор",
arts:[art-id,…]}). Сплитим title по ПОСЛЕДНЕМУ « — » (автор = хвост; кейс Цоя
«…— война — Виктор Цой» режется верно). Автор может отсутствовать (~17 карточек:
саундтреки/детские) → пустой слот, рендер даёт comp-only.

Подписи ссылок берём из manifest (авто-синк, уходит хардкод): сверено — все 216
art-id совпадают с art_titles страницы 1:1 → `id:override` не нужен ни одному.

Порядок плиток = как на текущей странице: (-len(arts), title.lower()).

Выход: yaniktoim/docs/songs/index.zml. Сборку вью делает editor/build_songs.mjs.
"""
import json, os, io, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
YANIK = os.path.join(HERE, "..", "..")
SONGS_DATA = os.path.join(YANIK, ".batch", "songs_data.json")
OVERRIDES = os.path.join(HERE, "songs_overrides.json")  # ytID → {comp, author}
OUT_ZML = os.path.join(YANIK, "docs", "songs", "index.zml")


def plural(n):
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return "композиция"
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return "композиции"
    return "композиций"


def esc_field(s):
    """Экранируем литеральный | внутри |-поля (§6.2). Кавычки/прочее — как есть."""
    return (s or "").replace("|", "\\|")


def main():
    data = json.load(open(SONGS_DATA, encoding="utf-8"))
    overrides = {}
    if os.path.exists(OVERRIDES):
        overrides = json.load(open(OVERRIDES, encoding="utf-8")).get("tracks", {})
    rows = sorted(data.items(), key=lambda kv: (-len(kv[1]["arts"]), kv[1]["title"].lower()))
    n = len(rows)
    nword = "%d %s" % (n, plural(n))

    no_author = 0
    overridden = 0
    lines = []
    for vid, info in rows:
        t = info["title"].strip()
        if " — " in t:
            comp, author = t.rsplit(" — ", 1)          # автор = последний сегмент
        else:
            comp, author = t, ""
        ov = overrides.get(vid)                         # ручной канон побеждает (после сортировки)
        if ov:
            comp, author = ov.get("comp", comp), ov.get("author", author)
            overridden += 1
        comp, author = esc_field(comp.strip()), esc_field(author.strip())
        if not author:
            no_author += 1
        arts = ", ".join(info["arts"])                 # art-id голые (без override)
        if arts:
            fields = [vid, comp, author, arts]
        elif author:
            fields = [vid, comp, author]
        else:
            fields = [vid, comp]
        lines.append(" | ".join(fields))

    body = "\n".join(lines)
    zml = (
        # theme/width НЕ эмитим: «Песнь Ступеней» — раздел "songs" в Ф8′-правилах
        # (admin задаёт дизайн/ширину в админке); пустой frontmatter → resolveDisplay
        # берёт правило раздела/global. Ручной theme:/width: тут перебил бы правило.
        "---\n"
        "title: Песнь Ступеней\n"
        "summary: Песнь Ступеней — вся музыка корпуса «Путь Восходящей Звезды»: "
        "%s со ссылками на статьи.\n"
        "---\n"
        "Вся музыка корпуса — %s. Под каждой плиткой — статьи, где она звучит. "
        "Нажмите на плитку, чтобы включить.\n\n"
        "[shir cols=3 min=300]\n"
        "%s\n"
        "[/shir]\n"
    ) % (nword, nword, body)

    os.makedirs(os.path.dirname(OUT_ZML), exist_ok=True)
    open(OUT_ZML, "w", encoding="utf-8").write(zml)
    print("OK: %s — %d плиток (%d без автора, %d overrides применено), %d ссылок на статьи" %
          (os.path.relpath(OUT_ZML, YANIK), n, no_author, overridden,
           sum(len(v["arts"]) for v in data.values())))


if __name__ == "__main__":
    main()

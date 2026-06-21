# -*- coding: utf-8 -*-
"""Отчёт «чего нет в [shir]»: ytID из [mus]-блоков корпуса, которых НЕТ на странице
«Песнь Ступеней» (220 ytID). Классифицирует альт-загрузка (название похоже на трек,
уже на странице, но другой ytID) vs новая (названия на странице нет).

Выход: imyavel/songs_missing.md — оператор проверяет и добавляет вручную.
Запуск: python convert/songs_missing_report.py
"""
import json, glob, os, re, io, sys, datetime
from difflib import SequenceMatcher

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
YANIK = os.path.join(HERE, "..", "..")
OUT_MD = os.path.join(HERE, "..", "..", "songs_missing.md")

ALT_THRESHOLD = 0.6


def norm(s):
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"\[\^[^\]]+\]", " ", s)
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[«»\"'`.,!?:·…—–-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    songs = json.load(open(os.path.join(YANIK, ".batch", "songs_data.json"), encoding="utf-8"))
    page_ids = set(songs.keys())
    page = [(vid, v["title"]) for vid, v in songs.items()]   # (ytID, "Comp — Author")

    YT = re.compile(r"(?:v=|youtu\.be/|youtube\.com/embed/|/vi/|watch\?v=)([A-Za-z0-9_-]{11})")
    nodb = {}   # vid -> {arts:set, title, author}
    for path in sorted(glob.glob(os.path.join(YANIK, "docs", "art", "*.zml"))):
        art = os.path.basename(path)[:-4]
        in_mus = False
        for raw in open(path, encoding="utf-8").read().splitlines():
            s = raw.strip()
            if s.startswith("[mus"): in_mus = True; continue
            if s == "[/mus]": in_mus = False; continue
            if not in_mus or not (s.startswith("[") and "|" in s): continue
            m = YT.search(s)
            if not m: continue
            vid = m.group(1)
            if vid in page_ids: continue
            parts = [p.strip() for p in s.strip("[]").split("|")]
            title = parts[1] if len(parts) > 1 else ""
            author = "|".join(parts[2:]) if len(parts) > 2 else ""
            d = nodb.setdefault(vid, {"arts": set(), "title": title, "author": author})
            d["arts"].add(art)

    def best_page(title):
        nt = norm(title)
        if not nt:
            return (0.0, "", "")
        best = (0.0, "", "")
        for pv, pt in page:
            r = SequenceMatcher(None, nt, norm(pt)).ratio()
            if r > best[0]:
                best = (r, pt, pv)
        return best

    alts, news = [], []
    for vid, d in sorted(nodb.items(), key=lambda kv: sorted(kv[1]["arts"])[0]):
        score, ptitle, pvid = best_page(d["title"])
        row = (vid, d["title"], d["author"], sorted(d["arts"]), score, ptitle, pvid)
        (alts if score >= ALT_THRESHOLD and norm(d["title"]) else news).append(row)

    def cell(s):
        return (s or "").replace("|", "\\|").strip() or "—"

    L = []
    L.append("# Песни, которых НЕТ в «Песнь Ступеней» (на проверку и добавление)")
    L.append("")
    L.append("_Сгенерировано %s скриптом `cms-revival/convert/songs_missing_report.py`._" %
             datetime.date.today().isoformat())
    L.append("")
    L.append("Треки, чей YouTube-ID встречается в `[mus]`-блоках статей корпуса, но **отсутствует** "
             "на странице «Песнь Ступеней» (сверка с 220 ytID страницы). Всего **%d**: "
             "%d вероятных альт-загрузок + %d новых." % (len(nodb), len(alts), len(news)))
    L.append("")
    L.append("**Как добавить нужное:** строкой в `[shir]` блоке `yaniktoim/docs/songs/index.zml` "
             "(`ytID | Композиция | Автор | арт-id, …`) ИЛИ, если хочешь авто-генерацию, дописать "
             "в `songs_data.json`/override; затем `python convert/gen_songs_zml.py && node editor/build_songs.mjs`. "
             "Название/автор ниже — КАК В СТАТЬЕ (часто требует сверки с самим видео).")
    L.append("")
    L.append("## Вероятные альт-загрузки (тот же трек, другой ytID — уже есть на странице)")
    L.append("")
    L.append("| ytID (видео) | в статье: Композиция \\| Автор | статья(и) | похоже на (на странице) |")
    L.append("|---|---|---|---|")
    for vid, t, a, arts, sc, pt, pv in alts:
        link = "[%s](https://youtu.be/%s)" % (vid, vid)
        L.append("| %s | %s \\| %s | %s | «%s» (`%s`, sim %.2f) |" %
                 (link, cell(t), cell(a), ", ".join(arts), cell(pt), pv, sc))
    L.append("")
    L.append("## Новые (названия на странице нет)")
    L.append("")
    L.append("| ytID (видео) | в статье: Композиция \\| Автор | статья(и) |")
    L.append("|---|---|---|")
    for vid, t, a, arts, sc, pt, pv in news:
        link = "[%s](https://youtu.be/%s)" % (vid, vid)
        L.append("| %s | %s \\| %s | %s |" % (link, cell(t), cell(a), ", ".join(arts)))
    L.append("")
    L.append("> Примечание: классификация альт/новая — эвристика по похожести названия "
             "(порог %.2f). Поля «в статье» взяты из `[mus]` и местами неточны "
             "(junk/перепутаны/без автора) — сверяй с самим видео." % ALT_THRESHOLD)
    L.append("")

    open(OUT_MD, "w", encoding="utf-8").write("\n".join(L))
    print("OK: %s — всего %d (%d альт + %d новых)" %
          (os.path.relpath(OUT_MD, os.path.join(HERE, "..", "..")), len(nodb), len(alts), len(news)))


if __name__ == "__main__":
    main()

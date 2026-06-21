# -*- coding: utf-8 -*-
"""Аудит обобщаемости правил конвертера (поручение 2026-06-11).
Read-only анализ: гоняет парсер/эвристики html_to_zml.py по всем 352 статьям,
инвентаризирует схемы ролей и dry-run'ит convert() во временный out.
Сам конвертер НЕ меняется. Выход: audit_scan.json + сводка в stdout.
"""
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import html_to_zml as C  # noqa: E402

ART = C.ART
AUDIT_OUT = HERE / "audit_out"
AUDIT_OUT.mkdir(exist_ok=True)
C.OUT = AUDIT_OUT  # dry-run: не трогаем боевой out/

KNOWN_TITLE = {"t-name", "tname", "tk-name", "name", "t-title", "ttitle",
               "track-title", "track-name", "m-title", "song-title"}
KNOWN_ARTIST = {"t-art", "tartist", "t-artist", "tk-art", "t-author", "artist"}
VERSE_LINE = {"line", "ln", "verse-line"}
STANZA = {"st", "stanza"}
BACKREF_KNOWN = "↑↩↪⮌"

def parse(art):
    html = (ART / f"{art}.html").read_text("utf-8")
    body_html = re.search(r"<body[^>]*>(.*)</body>", html, re.S).group(1)
    body_html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", body_html, flags=re.S)
    t = C.Tree()
    t.feed(body_html)
    meta = {}
    mm = re.search(r'id="yanik-meta"[^>]*>\s*(\{.*?\})\s*</script>', html, re.S)
    if mm:
        try:
            meta = json.loads(mm.group(1))
        except Exception:
            pass
    return t.root, meta, html

def norm_len(s):
    return len(re.sub(r"\s+", "", s))

def visible_text(root):
    """Грубая «контентная» масса оригинала: текст body без явного хрома."""
    CHROME = {"crumbs", "breadcrumbs", "toc", "byline", "artline", "colophon",
              "corpus-nav", "section-nav", "license", "build-date", "hashtag",
              "hero", "cover", "rule-orn", "title-orn", "ornament", "pop",
              "footer", "nav"}
    node = {"tag": "#root", "attrs": {}, "kids": list(root["kids"])}
    def deep(n):
        out = []
        for k in n["kids"]:
            if isinstance(k, str):
                out.append(k)
                continue
            if k["tag"] in ("header", "nav", "footer"):
                continue
            if C.cls(k) & CHROME:
                continue
            out.append(deep(k))
        return "".join(out)
    return deep(node)

def zml_text(zml):
    body = re.sub(r"^---.*?---\s*", "", zml, flags=re.S)
    body = re.sub(r"\[/?[a-z^][^\]\n]*\]", " ", body)   # блок-теги и [^N]:
    body = re.sub(r"^##.*$", " ", body, flags=re.M)
    body = re.sub(r"\{[^}]*\}", " ", body)
    body = re.sub(r"\[\[[^\]]*\]\]", " ", body)
    return body

recs = []
class_freq = Counter()          # class -> в скольких статьях встретился
class_sample = {}
arts = sorted(p.stem for p in ART.glob("*.html") if not p.name.endswith(".view.html"))
print("articles:", len(arts))

for art in arts:
    root, meta, html = parse(art)
    r = {"art": art, "scheme": meta.get("scheme", "")}

    allcls = set()
    for n in C.find(root, lambda x: True):
        allcls |= C.cls(n)
    for cl in allcls:
        class_freq[cl] += 1
        class_sample.setdefault(cl, art)

    # структура
    r["sec_blocks"] = len(C.find(root, lambda x: "sec-block" in C.cls(x)))
    r["has_container"] = bool(C.first(root, lambda x: "container" in C.cls(x) or x["tag"] == "article"))
    r["has_h1"] = bool(C.first(root, lambda x: x["tag"] == "h1"))

    # эпиграфы
    epis = C.find(root, C.is_epi)
    r["epi_n"] = len(epis)
    r["epi_brbr"] = 0  # prose-epi с <br><br> (замороженный баг а)
    for e in epis:
        body = C.first(e, lambda x: "epi-body" in C.cls(x)) or e
        raw = C.inline(C.prune(C._shallow(body), C._epi_is_cite), art, "nl")
        raw2 = re.sub(r"\n[ \t]+", " ", raw)
        lines = [l.strip() for l in raw2.split("\n")]
        nb = [l for l in lines if l]
        verse = len(nb) >= 2 and sum(len(l) for l in nb) / max(len(nb), 1) < 50
        if not verse and "" in [l.strip() for l in lines[1:-1]]:
            r["epi_brbr"] += 1
    # epi-подобные классы, которые is_epi НЕ ловит
    miss = set()
    for n in C.find(root, lambda x: True):
        for cl in C.cls(n):
            if ("epi" in cl and cl not in ("epi", "epis", "epi-body", "epi-cite",
                                           "epi-label", "epigraph", "epigraph-label")
                    and not C.is_epi(n)):
                miss.add(cl)
    r["epi_cls_miss"] = sorted(miss)
    r["bq_unclassed"] = len(C.find(root, lambda x: x["tag"] == "blockquote" and not C.cls(x)))
    r["bq_other"] = sorted({" ".join(sorted(C.cls(x))) for x in C.find(
        root, lambda x: x["tag"] == "blockquote" and C.cls(x) and not C.is_epi(x))})

    # сноски
    fns = C.collect_footnotes(root, art)
    r["fn_defs"] = len(fns)
    r["fn_branch"] = ("ol.notes" if C.first(root, lambda x: x["tag"] == "ol" and "notes" in C.cls(x))
                      else "div.fn" if C.find(root, lambda x: x["tag"] == "div" and "fn" in C.cls(x))
                      else "li.fn" if C.find(root, lambda x: x["tag"] == "li" and "fn" in C.cls(x))
                      else "p.note" if C.find(root, lambda x: x["tag"] == "p" and "note" in C.cls(x))
                      else "none")
    sups = C.find(root, lambda x: x["tag"] == "sup" and C.first(x, lambda y: y["tag"] == "a"))
    r["fn_refs"] = len(sups)
    r["fn_refs_lost"] = r["fn_refs"] > 0 and r["fn_defs"] == 0
    # стрелки backref за пределами известного набора
    arr = set()
    for num, txt in fns:
        m = re.search(r"([↑↩↪⮌⤴⬆▲↥↟⮍«»←]+)\s*$", txt)
        if m:
            arr.add(m.group(1))
    r["fn_tail_arrows_leaked"] = sorted(arr)

    # музыка
    tracks = C.find(root, lambda x: "track" in C.cls(x))
    yt = C.find(root, lambda x: isinstance(x, dict) and (
        x.get("attrs", {}).get("data-yt") or x.get("attrs", {}).get("data-embed")))
    ytlinks = C.find(root, lambda x: x["tag"] == "a" and "youtu" in (x["attrs"].get("href") or ""))
    r["music_tracks"] = len(tracks)
    r["music_data_yt"] = len(yt)
    r["music_yt_links"] = len(ytlinks)
    tcls = set()
    for n in tracks + yt:
        tcls |= {c for c in C.cls(n)}
        for k in C.find(n, lambda x: True):
            tcls |= C.cls(k)
    r["music_title_known"] = bool(tcls & KNOWN_TITLE)
    r["music_cls"] = sorted(tcls - {"track", "player", "play", "yt", "thumb"})[:12]

    # стих
    r["verse_cls"] = bool(C.find(root, lambda x: "verse" in C.cls(x)))
    r["stanza_cls"] = bool(C.find(root, lambda x: C.cls(x) & STANZA))
    r["line_cls"] = bool(C.find(root, lambda x: C.cls(x) & VERSE_LINE))
    # стих в <p>: p с >=2 <br>
    pbr = 0
    for p in C.find(root, lambda x: x["tag"] == "p" and not C.is_epi(x)):
        brs = len([k for k in p["kids"] if isinstance(k, dict) and k["tag"] == "br"])
        if brs >= 2:
            pbr += 1
    r["p_multibr"] = pbr

    # прочие роли
    r["subtitle"] = bool(C.first(root, lambda x: x["tag"] in ("div", "p") and "subtitle" in C.cls(x)))
    r["sec_sub"] = len(C.find(root, lambda x: "sec-sub" in C.cls(x)))
    r["lead_source"] = bool(C.first(root, lambda x: "lead-source" in C.cls(x)))
    r["audio_links"] = len(C.find(root, lambda x: x["tag"] == "a" and (
        "audio-link" in C.cls(x) or "t.me/" in (x["attrs"].get("href") or ""))))
    r["junk_semis"] = html.count(";;;;")
    r["see_also_dbl"] = len(re.findall(r"::", visible_text(root)))

    # dry-run convert
    C.FLAGS.clear()
    try:
        zml = C.convert(art)
        r["convert"] = "ok"
        r["flags"] = list(C.FLAGS)
        r["fallback"] = any("generic-walk fallback" in f for f in C.FLAGS)
        ov, zv = norm_len(visible_text(root)), norm_len(zml_text(zml))
        r["cover"] = round(zv / ov, 3) if ov else None
    except Exception as e:
        r["convert"] = "ERR: %s" % e
        r["fallback"] = None
        r["cover"] = None
    recs.append(r)

(HERE / "audit_scan.json").write_text(
    json.dumps(recs, ensure_ascii=False, indent=1), "utf-8")

# ── сводка ──────────────────────────────────────────────────────────────────
def n(pred):
    return sum(1 for r in recs if pred(r))

print("\n== СТРУКТУРА ==")
print("sec-block:", n(lambda r: r["sec_blocks"] > 0),
      "| flat(container/article):", n(lambda r: r["sec_blocks"] == 0 and r["has_container"]),
      "| ни то ни то:", n(lambda r: r["sec_blocks"] == 0 and not r["has_container"]))
print("convert ERR:", n(lambda r: r["convert"] != "ok"),
      [r["art"] for r in recs if r["convert"] != "ok"][:20])
print("generic fallback:", n(lambda r: r.get("fallback")))
cov = [r for r in recs if r.get("cover") is not None]
for lo, hi in [(0, .5), (.5, .8), (.8, .95), (.95, 1.05), (1.05, 9)]:
    print("  cover %4.2f–%4.2f: %d" % (lo, hi, sum(1 for r in cov if lo <= r["cover"] < hi)))
worst = sorted(cov, key=lambda r: r["cover"])[:15]
print("  худшие:", [(r["art"], r["cover"]) for r in worst])

print("\n== ЭПИГРАФЫ ==")
print("статей с [epi]:", n(lambda r: r["epi_n"] > 0), "| всего epi:", sum(r["epi_n"] for r in recs))
print("prose-epi c <br><br> (баг а):", n(lambda r: r["epi_brbr"] > 0),
      "статей /", sum(r["epi_brbr"] for r in recs), "шт.")
m = Counter()
for r in recs:
    for c in r["epi_cls_miss"]:
        m[c] += 1
print("epi-классы мимо is_epi:", m.most_common(15))
print("blockquote без класса:", n(lambda r: r["bq_unclassed"] > 0))
bq = Counter()
for r in recs:
    for c in r["bq_other"]:
        bq[c] += 1
print("blockquote с прочими классами:", bq.most_common(15))

print("\n== СНОСКИ ==")
br = Counter(r["fn_branch"] for r in recs)
print("ветки:", dict(br))
print("ссылки есть, определения НЕ собраны:", n(lambda r: r["fn_refs_lost"]),
      [r["art"] for r in recs if r["fn_refs_lost"]][:25])
ar = Counter()
for r in recs:
    for a in r["fn_tail_arrows_leaked"]:
        ar[a] += 1
print("утёкшие хвост-стрелки:", dict(ar))

print("\n== МУЗЫКА ==")
print("статей с треками:", n(lambda r: r["music_tracks"] + r["music_data_yt"] > 0))
print("yt-ссылки без track/data-yt:", n(lambda r: r["music_yt_links"] > 0
      and r["music_tracks"] == 0 and r["music_data_yt"] == 0))
print("трек-узлы без известного title-класса:", n(lambda r:
      (r["music_tracks"] + r["music_data_yt"]) > 0 and not r["music_title_known"]),
      [r["art"] for r in recs if (r["music_tracks"] + r["music_data_yt"]) > 0
       and not r["music_title_known"]][:25])

print("\n== СТИХ ==")
print("verse-класс:", n(lambda r: r["verse_cls"]), "| stanza:", n(lambda r: r["stanza_cls"]),
      "| line:", n(lambda r: r["line_cls"]),
      "| стих-в-<p> (>=2 br):", n(lambda r: r["p_multibr"] > 0))

print("\n== ПРОЧЕЕ ==")
print("subtitle:", n(lambda r: r["subtitle"]), "| sec-sub:", n(lambda r: r["sec_sub"] > 0),
      "| lead-source:", n(lambda r: r["lead_source"]),
      "| audio:", n(lambda r: r["audio_links"] > 0),
      "| ';;;;':", n(lambda r: r["junk_semis"] > 0),
      "| '::' в тексте:", n(lambda r: r["see_also_dbl"] > 0))

print("\n== ТОП КЛАССОВ КОРПУСА (док-частота) ==")
for cl, k in class_freq.most_common(80):
    print("%5d  %-24s (напр. %s)" % (k, cl, class_sample[cl]))

# -*- coding: utf-8 -*-
"""Ф4 — HTML→ZML экстрактор, v2 (единый role-based walk; решение оператора 2026-06-12,
вариант B аудита `audit_generalizability_001.md`).

Корпус свёрстан LLM с РАЗНЫМИ именами классов на статью, но единой СЕМАНТИКОЙ
(convert_prompt_005). Принципы v2:
  1. ОДИН проход в документ-порядке; спуск в ЛЮБУЮ незнакомую обёртку.
  2. Роли определяются структурой/позицией, а не перечнем классов, где возможно.
  3. НИЧЕГО не выбрасывается молча: неопознанное → проза + флаг.
  4. 📏-инвариант (SPEC §9): авторские <br> не плющатся — маршрутизируются
     ([poem] / абзацный разрыв / continuation сноски). Косметический whitespace
     разметки отделяется от авторских <br> сентинелом \\x00 (режим br='mark').
  5. Оракул-гейт: после конвертации сверка текст-массы оригинал↔ZML;
     покрытие <0.97 или >1.20 → флаг к разбору.

Usage: python html_to_zml.py <art-id> [<art-id> ...]
  читает ../../yaniktoim/docs/art/<id>.html, пишет out/<id>.zml и out/<id>.flags.txt
"""
import json
import os as _os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from music_canon import canonicalize, fill_url  # музыка-канон: оркестрация слотов + url-фолбэк

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "yaniktoim" / "docs" / "art"
MANIFEST = {r["art"]: r for r in json.loads((ROOT / "yaniktoim/manifest.json").read_text("utf-8"))}
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

VOID = {"br", "img", "hr", "meta", "link", "input", "source"}
BR = "\x00"  # сентинел авторского <br> (отличаем от косметических \n разметки)


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "#root", "attrs": {}, "kids": []}
        self.stack = [self.root]

    def handle_starttag(self, t, attrs):
        n = {"tag": t, "attrs": dict(attrs), "kids": []}
        self.stack[-1]["kids"].append(n)
        if t not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, t, attrs):
        self.stack[-1]["kids"].append({"tag": t, "attrs": dict(attrs), "kids": []})

    def handle_endtag(self, t):
        if t in VOID:
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i]["tag"] == t:
                del self.stack[i:]
                break

    def handle_data(self, d):
        self.stack[-1]["kids"].append(d)


def cls(n):
    return set((n.get("attrs", {}).get("class", "") or "").split())


def find(n, pred, acc=None):
    acc = acc if acc is not None else []
    for k in n["kids"]:
        if isinstance(k, dict):
            if pred(k):
                acc.append(k)
            find(k, pred, acc)
    return acc


def first(n, pred):
    r = find(n, pred)
    return r[0] if r else None


def prune(n, pred):
    """Remove matching descendants in place."""
    n["kids"] = [k for k in n["kids"] if not (isinstance(k, dict) and pred(k))]
    for k in n["kids"]:
        if isinstance(k, dict):
            prune(k, pred)
    return n


def raw_text(n):
    out = []
    for k in n["kids"]:
        if isinstance(k, str):
            out.append(k)
        elif k["tag"] == "br":
            out.append("\n")
        else:
            out.append(raw_text(k))
    return "".join(out)


FLAGS = []


def flag(art, msg):
    FLAGS.append(f"[{art}] {msg}")


# ── термин-политика (вопрос 6 / T-A·B·C) ─────────────────────────────────────
# Адресные наборы strong/b-текстов на статью → inline {term|…}. roza_mira-набор
# (T-B1 правило «strong-в-начале-li + —» + T-B3 LLM-классификация серой зоны)
# лежит в roza_mira_terms.json (генерит extract_roza_terms.py); точечные T-C по
# b/strong (46L аббревиатуры, 462 имена собственные) — статически здесь.
TERM_POLICY = {
    "46L": {"СА", "СС", "ТС", "КК", "АР"},
    "462": {"Путь Восходящей Звезды", "Элиягу Бар Малей", "Бина Анеле"},
}
_ROZA_TERMS = Path(__file__).resolve().parent / "roza_mira_terms.json"
if _ROZA_TERMS.exists():
    TERM_POLICY["roza_mira"] = set(json.loads(_ROZA_TERMS.read_text("utf-8")))
# span-классы термина, ГАТИРОВАННЫЕ статьёй (T-C: 17BA .sef сфирот, 1BI .he ивр-глоссы)
TERM_SPAN_BY_ART = {"17BA": {"sef"}, "1BI": {"he"}}
# strong/b → {term|…} безопасен только для плоского текста (без вложенной разметки)
_TERM_SAFE_RX = re.compile(r"^[^{}\[\]\n|]+$")


# ── inline reconstruction ──────────────────────────────────────────────────
FNREF_A_CLS = {"fnref", "fn-ref", "fnmark", "fn-mark", "noteref", "note-ref", "fn-anchor"}
POPUP_CLS = {"pop", "fn-pop", "fnpop", "fn-preview", "tooltip", "tip"}


def inline(n, art, br="space"):
    """Serialize children to ZML inline text.
    br: 'space' (схлопнуть) | 'nl' (\\n) | 'mark' (сентинел BR — авторский перенос,
    отличимый от косметических \\n pretty-print)."""
    brchar = {"space": " ", "nl": "\n", "mark": BR}[br]
    out = []
    for k in n["kids"]:
        if isinstance(k, str):
            out.append(k)
            continue
        t = k["tag"]
        c = cls(k)
        if t == "br":
            out.append(brchar)
        elif t == "sup":
            out.append(fn_ref(k, art))
        elif t == "a":
            if c & FNREF_A_CLS:  # сноска-маркер ссылкой без <sup>
                n2 = _ref_num(k["attrs"].get("href", ""), raw_text(k))
                out.append(f"[^{n2}]" if n2 is not None else "")
            else:
                out.append(link(k, art))
        elif t in ("em", "i"):
            inner = inline(k, art, br).strip()
            out.append(f"_{inner}_" if inner else "")
        elif t in ("b", "strong"):
            inner = inline(k, art, br)
            key = re.sub(r"\s+", " ", inner).strip()
            if key and key in TERM_POLICY.get(art, ()) and _TERM_SAFE_RX.match(key):
                out.append("{term|%s}" % key)  # T-B/T-C: адресный термин
            else:
                out.append(inner)  # ZML has no bold marker; keep text
        elif t == "p":
            # вложенный <p> = авторская граница абзаца (инвариант 14:25: не
            # склеивать); двойной разделитель → пустая строка → разрыв группы
            out.append(brchar * 2 + inline(k, art, br) + brchar * 2)
        elif t == "span":
            if (c & {"term", "leit"}) or (c & TERM_SPAN_BY_ART.get(art, set())):
                # C10: авторская разметка термина/лейтмотива (158: span.term ×20);
                # T-C: гатированные span-классы (17BA .sef, 1BI .he)
                kind = "leit" if "leit" in c else "term"
                inner = inline(k, art, br).strip()
                out.append("{%s|%s}" % (kind, inner) if inner else "")
                continue
            if c & POPUP_CLS:
                # preview-пузырь сноски — generated, drop; НО в части схем (185A)
                # попап-обёртка содержит и сам маркер-ссылку — извлечь его.
                mk = first(k, lambda x: bool(cls(x) & FNREF_A_CLS) or x["tag"] == "sup")
                if mk is not None:
                    n2 = _ref_num(mk["attrs"].get("href", ""), raw_text(mk))
                    out.append(f"[^{n2}]" if n2 is not None else "")
                continue
            if c & FNREF_A_CLS:
                href = k["attrs"].get("href", "")
                if href:
                    n2 = _ref_num(href, raw_text(k))
                    out.append(f"[^{n2}]" if n2 is not None else "")
                    continue
                # обёртка без своего href: берём вложенный `<a href="#fnN">`
                # (215B: `<span class="fnmark"><a href="#fn1"><sup>*</sup></a><span.fn-popup>`).
                # Эмитим ТОЛЬКО при реально существующей сноске (frag в FN_ID_MAP) —
                # пустые сноски (0BO: `<li id="fn1">` лишь с ↩) выпали из карты →
                # не плодим висячий маркер (раньше _ref_num тянул «1» из «#fn1»).
                mk = first(k, lambda x: x["tag"] == "a"
                           and x["attrs"].get("href", "").startswith("#"))
                frag = mk["attrs"].get("href", "").lstrip("#") if mk else ""
                if frag and FN_ID_MAP.get(frag) is not None:
                    out.append("[^%s]" % FN_ID_MAP[frag])
                continue
            if (c & {"anchor-hint", "anchorhint", "anchor-note", "anchor", "up"}
                    and re.fullmatch(r"[↑↟▴^\s]*(наверх)?",
                                     raw_text(k).strip(), re.I)):
                # хинт «↑ наверх» в заголовках (18T/189/55D…) — артефакт навигации
                continue
            if "kicker" in c:
                # киккер-спан ВНУТРИ H1 (59C/1B5A/416B) — рубрика/надзаголовок,
                # НЕ часть названия: тёк в title («Да будет Свет!И это только
                # начало») — снять (вердикт 21:12 2026-06-12)
                flag(art, "kicker-спан внутри строки снят («%s»)" % raw_text(k).strip()[:30])
                continue
            out.append(inline(k, art, br))
        else:
            out.append(inline(k, art, br))
    return "".join(out)


FN_ID_MAP = {}  # anchor-id определения → финальный номер (заполняет collect_footnotes)
MUS_FN = {}        # id(трек-узла) → (group, number): трек = ЦЕЛЬ сноски (1CM ¶, 12F)
MUS_FN_GLYPH = {}  # group → глиф маркера («¶») или "" (числовая метка)


def _ref_num(href, text):
    """Номер сноски для маркера: сперва по карте якорей (надёжно при
    пер-секционных схемах #s7-fnN — 217A), затем последняя цифра-группа."""
    frag = (href or "").lstrip("#")
    if frag and frag in FN_ID_MAP:
        return FN_ID_MAP[frag]
    m = re.search(r"fn[-_]?(\d+)", href or "")
    if m:
        return int(m.group(1))
    nums = re.findall(r"\d+", href or "") or re.findall(r"\d+", text or "")
    return int(nums[-1]) if nums else None


def fn_ref(sup, art):
    a = first(sup, lambda x: x["tag"] == "a")
    if not a:
        n = _ref_num("", raw_text(sup))
        return f"[^{n}]" if n is not None else ""
    n = _ref_num(a["attrs"].get("href", ""), raw_text(a))
    return f"[^{n}]" if n is not None else ""


AUDIO_HREFS = set()  # href'ы, признанные озвучкой (заполняет convert per-article)


def link(a, art):
    href = a["attrs"].get("href", "")
    c = cls(a)
    txt = inline(a, art, "space").strip()
    if "audio-link" in c or href in AUDIO_HREFS:
        return ""  # audio narration → frontmatter audio: (collected in convert)
    if "back" in c or "self" in c or href.startswith("#"):
        frag = href.lstrip("#")
        if frag in FN_ID_MAP and FN_ID_MAP[frag] is not None:
            # якорь-маркер сноски (`<a href="#fn2">**</a>` — 182) → [^N]/[^**]
            return "[^%s]" % FN_ID_MAP[frag]
        # anchor / back-to-top. If it WRAPS real text (corpus puts the section
        # title inside the #top link), keep the text; if it's just an arrow, drop.
        if txt and not re.fullmatch(r"[↑↟↩↪⮌▴▾^⌃→←»«›‹\s]+", txt):
            return txt
        return ""  # bare back-to-top / backref — render regenerates it
    mz = re.search(r"zohar-sulam/([a-z][a-z-]*)/0*(\d+)\.html", href)
    if mz:
        return "{%s|%s}" % (mz.group(1), mz.group(2))
    if re.fullmatch(r"[A-Za-z0-9_]+\.html", href):  # local corpus article
        return "[[%s]]" % href[:-5]
    if href.startswith("http"):
        return "[%s|%s]" % (href, txt) if txt and txt != href else "[%s]" % href
    return txt


# ── B6: канон сносок «См. также» (консервативно, вердикт оператора 2026-06-17) ──
# Чистим авторскую разметку `::` → пунктуация и сносим псевдоним-автора СВОИХ
# статей (Зеир Арихович Анпин / Зеир А"А / ЭБМ / Элиягу Бар Малей). Внешних
# авторов (Кастанеда, Высоцкий…), [[ID]], внешние ссылки и текст НЕ трогаем.
# Резолв названий→art-id НЕ расширяем (что резолвилось ссылкой — уже [[ID]]).
_B6_PREFIX = re.compile(r"^\s*(?:См\.?\s*также|А\s+также|Музыка|Цитата)\b", re.I)
_B6_HEAD = re.compile(r"^(\s*)(См\.?\s*также|А\s+также|Музыка|Цитата)\s*::?\s*", re.I)
_B6_SELF = re.compile(
    r"\s*[—,.;(]\s*(?:Зеир\s+Арихович\s+Анпин|Зеир\s+А[\"“”]?А|ЭБМ|"
    r"Элиягу\s+Бар\s+Малей)(?:\s*\))?",
    re.I)
_B6_EMPTY = re.compile(r"^(?:См\.?\s*также|А\s+также)\s*:?\s*$", re.I)


def b6_seealso(txt):
    """Косметика «См. также»-сносок: `::`→пунктуация, снос псевдонима-автора."""
    if not _B6_PREFIX.match(txt or ""):
        return txt
    # префикс «X::» → «X: » (одиночное двоеточие)
    t = _B6_HEAD.sub(lambda m: "%s%s: " % (m.group(1), m.group(2)), txt, count=1)
    t = re.sub(r"\s*::+\s*", " — ", t)        # остальные поля `::` → « — »
    t = _B6_SELF.sub("", t)                    # снос своего псевдонима-атрибуции
    t = re.sub(r"\s{2,}", " ", t).strip()
    t = re.sub(r"\s*[—,]\s*$", "", t)          # висячий разделитель после сноса
    return t


# ── 📏 авторские переносы → структура ────────────────────────────────────────
def _mark_lines(node, art):
    """inline в режиме 'mark' → строки по авторским <br>; косметический
    whitespace разметки (\\n+отступы pretty-print) схлопнут в пробел."""
    txt = inline(node, art, "mark")
    txt = re.sub(r"\s+", " ", txt)  # \x00 не входит в \s — авторские переносы живут
    return [ln.strip() for ln in txt.split(BR)]


def _line_groups(lines):
    """Строки → группы, разделённые пустыми строками (двойной <br>)."""
    groups, cur = [], []
    for ln in lines:
        if ln:
            cur.append(ln)
        elif cur:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def _versey(lines):
    nb = [l for l in lines if l]
    return len(nb) >= 2 and sum(len(l) for l in nb) / len(nb) < 50


def _groups_text(groups):
    """ГЛОБАЛЬНЫЙ ИНВАРИАНТ (оператор, 2026-06-12 14:25): авторские переносы
    НЕ плющатся НИГДЕ. Группы (между пустыми строками) → абзацы; строки внутри
    группы сохраняются \\n (render рисует <br>). Чистится только двойной пробел."""
    return "\n\n".join(
        "\n".join(re.sub(r"\s{2,}", " ", l).strip() for l in g if l.strip())
        for g in groups if g)


def para_blocks(node, art):
    """<p>/текст-ран → список ZML-блоков с 📏-маршрутизацией:
    стих-форма → [poem]; <br><br> → отдельные абзацы; одиночные <br> в длинной
    прозе → flow (канон: CAPS-периоды/wrapped prose не стих)."""
    lines = _mark_lines(node, art)
    groups = _line_groups(lines)
    if not groups:
        return []
    if _versey(lines):  # стих-ФОРМА → [poem]-обёртка (чисто стилевой выбор)
        body = "\n\n".join("\n".join(g) for g in groups)
        return ["[poem]\n%s\n[/poem]" % body]
    # инвариант 14:25: строки групп СОХРАНЯЮТСЯ (\n), плющится только двойной пробел
    out = ["\n".join(re.sub(r"\s{2,}", " ", l).strip() for l in g if l.strip())
           for g in groups if g]
    # декоративные разделители (✦ ✦ ✦ / *** / ⁂) и сирота-лейбл «Эпиграф» — не контент
    out = [p for p in out
           if re.search(r"\w", p) and p.lower().strip() not in ("эпиграф", "эпиграфы")]
    return out


# ── epigraph detection (role-based, scheme-agnostic) ──────────────────────────
def is_epi(x):
    if not isinstance(x, dict):
        return False
    c = cls(x)
    if "epis" in c:                       # the .epis WRAPPER, not an epigraph
        return False
    if "epi" in c and x["tag"] in ("div", "p", "blockquote"):
        return True
    if "epigraph" in c and x["tag"] in ("blockquote", "div", "p"):
        return True
    return False


def _epi_is_cite(x):
    return isinstance(x, dict) and (
        x["tag"] == "cite" or bool(cls(x) & {"cite", "epi-cite", "src", "epigraph-src",
                                             "epi-source", "epigraph-author", "author"}))


def _shallow(n):
    return {"tag": n["tag"], "attrs": n["attrs"], "kids": list(n["kids"])}


# ── block emitters ──────────────────────────────────────────────────────────
def _cite_of(n):
    cite_el = first(n, _epi_is_cite)
    if not cite_el:
        return ""
    tmp = _shallow(cite_el)
    prune(tmp, lambda x: x["tag"] == "sup")  # drop footnote ref from cite text
    return re.sub(r"\s+", " ", raw_text(tmp)).strip().strip("—").strip()


def emit_epi(n, art, kind=None):
    """kind: None (авто: verse-эвристика) | 'dedi' (посвящение, вердикт 8)."""
    cite = _cite_of(n)
    body = first(n, lambda x: "epi-body" in cls(x)) or n
    # serialize body WITHOUT the cite element so its text isn't duplicated.
    body = prune(_shallow(body), _epi_is_cite)
    prune(body, lambda x: bool(cls(x) & {"epi-label", "epigraph-label", "epi-h", "epi-tag"}))
    lines = _mark_lines(body, art)
    groups = _line_groups(lines)
    if not groups:
        return ""
    nonblank = [l for l in lines if l]
    verse = _versey(nonblank)
    # инвариант 14:25: строки сохраняются при ЛЮБОМ kind (verse — стилевой класс)
    txt = _groups_text(groups)
    if kind:
        attrs = ' kind="%s"' % kind  # явная роль (dedi) сильнее verse-эвристики
    else:
        attrs = ' kind="verse"' if verse else ""
    if cite:
        attrs += ' cite="%s"' % cite
    return "[epi%s]\n%s\n[/epi]" % (attrs, txt)


_QUOTE_LABEL_RX = re.compile(r'^[«"“]?\s*цитата\s*[:.]?\s*[»"”]?$', re.I)


def _drop_quote_label(stanzas, art):
    """Снять литерал-лейбл «Цитата» первой строкой стиха/цитаты (1CM, вердикт
    A6/В5): emit_verse-пути его не стрипали — теперь единый помощник."""
    if stanzas and _QUOTE_LABEL_RX.match(stanzas[0].split("\n", 1)[0].strip()):
        head = stanzas[0].split("\n", 1)
        stanzas[0] = head[1] if len(head) > 1 else ""
        stanzas = [s for s in stanzas if s]
        flag(art, "label-строка «Цитата» снята со стиха")
    return stanzas


def emit_quote(n, art):
    """blockquote/div.quote вне роли эпиграфа → [quote] (роль «цитата», C12).
    kind=scripture при одноимённом классе. Label-спан/строка «Цитата» снимается
    (вердикт A6 — дубль лейбла карточки, 1CM)."""
    cite = _cite_of(n)
    body = prune(_shallow(n), _epi_is_cite)
    prune(body, lambda x: bool(cls(x) & {"label", "q-label", "quote-label", "qlabel"}))
    lines = _mark_lines(body, art)
    groups = _line_groups(lines)
    if not groups:
        return ""
    # инвариант 14:25: строки внутри цитаты сохраняются (\n)
    paras = ["\n".join(re.sub(r"\s{2,}", " ", l).strip() for l in g if l.strip())
             for g in groups if g]
    if paras and _QUOTE_LABEL_RX.match(paras[0].split("\n", 1)[0]):
        head = paras[0].split("\n", 1)
        paras = ([head[1]] if len(head) > 1 else []) + paras[1:]
        flag(art, "label-строка «Цитата» снята с [quote]")
    if not paras:
        return ""
    txt = "\n\n".join(paras)
    attrs = ' kind="scripture"' if "scripture" in cls(n) else ""
    if cite:
        attrs += ' cite="%s"' % cite
    return "[quote%s]\n%s\n[/quote]" % (attrs, txt)


def emit_subsec(node, art):
    lines = [l for l in _mark_lines(node, art) if l]
    return "[subsec]\n" + "\n".join(lines) + "\n[/subsec]" if lines else ""


# ── спасение описат. подзаголовков из <header> (вердикт «спасай», 2026-06-17) ──
# Часть статей завернула описательный подзаголовок в <header class=lead> рядом с
# H1. <header> — в CHROME_TAGS → walk выбрасывал его весь как хром (и оракул
# header исключает → потеря БЕЗ сигнала). Достаём такие узлы и эмитим под H1:
# deck/standfirst → [subsec] (дескриптивный дек), subtitle/article-subtitle →
# [sub] (жанр/назв.); дата-строка → [line dateline]; дубль раздела — снять.
LEAD_SUBT_CLS = {"subtitle", "article-subtitle"}
LEAD_DECK_CLS = {"deck", "standfirst"}


def find_lead_subtitles(root):
    """subtitle/deck/standfirst-узлы внутри <header>-тега, в document-порядке, без
    дублей. Только <header> (его скипает walk) — div.lead/.subtitle walk видит сам."""
    out, seen = [], set()
    for h in find(root, lambda x: x["tag"] == "header"):
        for n in find(h, lambda x: bool(cls(x) & (LEAD_SUBT_CLS | LEAD_DECK_CLS))):
            if id(n) not in seen:
                seen.add(id(n))
                out.append(n)
    return out


def lead_subtitle_text(header_node):
    """Видимый текст спасаемых подзаголовков ОДНОГО <header> — для оракула, чтобы
    он считал их (иначе ov их исключает, а zv уже содержит → ложный сдвиг)."""
    return " ".join(re.sub(r"\s+", " ", raw_text(n)).strip() for n in find(
        header_node, lambda x: bool(cls(x) & (LEAD_SUBT_CLS | LEAD_DECK_CLS))))


def _verse_lines(node, art):
    """Строки стиха: в СТИХ-контексте значимы и <br>, и текстовые переносы
    исходника (LLM кладёт каждую строку стиха на свою строку разметки — 29M:
    div.stanza>p без <br>). В прозе текст-\\n косметичен — там _mark_lines."""
    return [ln.strip() for ln in inline(node, art, "nl").split("\n") if ln.strip()]


def emit_stanzas(stanzas, art):
    """Build a [poem] from stanza nodes. Lines come from .line/.ln children
    (34O/29M scheme), else from <br>/newline-split text (237/29M schemes)."""
    out = []
    for st in stanzas:
        line_els = [k for k in st["kids"]
                    if isinstance(k, dict) and (cls(k) & {"line", "ln", "verse-line"})]
        if line_els:
            lines = [re.sub(r"\s+", " ", inline(l, art, "space").strip()) for l in line_els]
            s = "\n".join(l for l in lines if l)
        else:
            s = "\n".join(_verse_lines(st, art))
        if s:
            out.append(s)
    out = _drop_quote_label(out, art)  # label «Цитата» первой строкой (1CM, A6)
    return "[poem]\n" + "\n\n".join(out) + "\n[/poem]" if out else ""


def emit_verse_blocks(n, art):
    """Поэма-обёртка со СМЕШАННЫМИ детьми (строфы + прозо-<p> между ними — 323):
    идём по детям в документ-порядке, строфы группируем в [poem], прозу эмитим
    абзацами между поэмами. → список блоков."""
    kids = [k for k in n["kids"] if isinstance(k, dict)]
    direct_st = [k for k in kids if cls(k) & {"st", "stanza"}]
    if not direct_st or len(direct_st) == len(kids):
        b = emit_verse(n, art)
        return [b] if b else []
    out, run = [], []

    def flush():
        if run:
            out.append(emit_stanzas(run, art))
            run.clear()
    for k in kids:
        if cls(k) & {"st", "stanza"}:
            run.append(k)
        elif k["tag"] == "p":
            flush()
            out.extend(para_blocks(k, art))
        else:
            run.append(k)  # безымянная обёртка внутри поэмы — как строфа
    flush()
    return [b for b in out if b]


def emit_verse(n, art):
    # a .verse/.poem wrapper, a single stanza, or a block of <br>/newline-lines.
    sts = find(n, lambda x: cls(x) & {"st", "stanza"})
    if sts:
        return emit_stanzas(sts, art)
    if cls(n) & {"st", "stanza"}:
        return emit_stanzas([n], art)
    # строфы = <p>-дети (29M-стиль) либо разрывы пустыми строками
    psts = [k for k in n["kids"] if isinstance(k, dict) and k["tag"] == "p"]
    if psts:
        out = ["\n".join(_verse_lines(p, art)) for p in psts]
        out = _drop_quote_label([s for s in out if s], art)
        return "[poem]\n" + "\n\n".join(out) + "\n[/poem]" if out else ""
    # В СТИХ-контексте значимы И <br>, И исходные переносы строк (LLM кладёт каждую
    # строку стиха на свою строку разметки — 1CM/335). НО <br> + косметический
    # отступ-\n исходника НЕ должны удваиваться в ЛОЖНЫЙ разрыв строфы (272:
    # blockquote.verse со сплошными <br>). Решение: схлопываем только ГОРИЗОНТАЛЬНУЮ
    # ws (не \n), затем <br>(+окруж. ws) → ОДИН \n; пустая строка (\n\s*\n = <br><br>
    # ИЛИ реально пустая строка исходника) = разрыв строфы.
    txt = re.sub(r"[ \t]+", " ", inline(n, art, "mark"))
    txt = re.sub(r"\s*%s\s*" % re.escape(BR), "\n", txt)
    stanzas = []
    for b in re.split(r"\n\s*\n", txt):
        lines = [ln.strip() for ln in b.split("\n") if ln.strip()]
        if lines:
            stanzas.append("\n".join(lines))
    stanzas = _drop_quote_label(stanzas, art)  # «Цитата» первой строкой (1CM, В5)
    return "[poem]\n" + "\n\n".join(stanzas) + "\n[/poem]" if stanzas else ""


# ── музыка ───────────────────────────────────────────────────────────────────
TITLE_CLS = {"t-name", "tname", "tk-name", "name", "t-title", "ttitle",
             "track-title", "track-name", "m-title", "song-title", "tk-title",
             "ttl", "tt", "t"}
ARTIST_CLS = {"t-art", "tartist", "t-artist", "tk-art", "t-author", "artist",
              "track-artist", "ta", "by", "author", "art"}
LABEL_CLS = {"music-label", "lbl", "label", "mus-label"}


def _clean_track_text(s):
    s = re.sub(r"[\s\x00]+", " ", s or "").strip()
    s = re.sub(r"^[▶▷►▸‣▹➤·•\s]+", "", s)
    # глифы-артефакты исходной разметки внутри строки («↗↑›» — 12F; «▾» — 16J)
    s = re.sub(r"\s*[↗↪➚⧉⇗➦↑›‹▾▴▿▵]+\s*", " ", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def is_track(n):
    """Трек-плитка. Признак ЛОКАЛЕН: класс/атрибут на самом узле, либо data-yt
    в потомках у МАЛЕНЬКОГО листа (короткий текст, без заголовков) — иначе любой
    верхний wrap, где глубоко лежит музыка, съедал бы статью целиком."""
    if n["tag"] not in ("div", "details", "figure", "li"):
        return False
    c = cls(n)
    if c & {"track", "player"}:
        return True
    a = n.get("attrs", {})
    if a.get("data-yt") or a.get("data-embed"):
        return True
    if first(n, lambda x: x["tag"] in ("h1", "h2", "h3", "p")):
        return False
    if len(re.sub(r"\s+", "", raw_text(n))) > 200:
        return False
    return bool(first(n, lambda x: isinstance(x, dict) and (
        x.get("attrs", {}).get("data-yt") or x.get("attrs", {}).get("data-embed"))))


def is_music_container(n):
    if n["tag"] not in ("div", "section", "details", "aside"):
        return False
    return any("music" in c for c in cls(n)) and "music-label" not in cls(n)


def _yt_id(url):
    m = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else None


def _is_fnmark(x):
    return x["tag"] == "sup" or (x["tag"] in ("a", "span") and bool(cls(x) & FNREF_A_CLS))


def _is_inter_note(x):
    """inter-track заметка в муз-контейнере (1AQA «Слушать вместе и одновременно!»):
    p/div.note — НЕ note-маркер/элемент сноски."""
    return (isinstance(x, dict) and x.get("tag") in ("p", "div")
            and "note" in cls(x) and not (cls(x) & {"note-item", "note-mark", "fn", "fnref"}))


def collect_music(container):
    """Упорядоченный список муз-узлов (треки/лейблы/inter-заметки) в порядке документа,
    НЕ спускаясь внутрь треков (Б2: заметка между плитками сохраняет позицию)."""
    items = []

    def walk(node):
        for kd in node.get("kids", []):
            if not isinstance(kd, dict):
                continue
            if is_track(kd) or (cls(kd) & LABEL_CLS) or _is_inter_note(kd):
                items.append(kd)
            else:
                walk(kd)

    walk(container)
    return items


def emit_music(blocks, art):
    """blocks: list of track-ish nodes (and labels). Build one [mus].
    Реф-маркеры сносок в полях трека/лейбла ОСТАЮТСЯ НА МЕСТЕ текстовым `[^N]`
    (оператор 15:14, кейс Gregorian[12] 16J) — render рисует рабочий sup+popup."""
    label = ""
    entries = []
    refs_group = None  # трек-как-цель-сноски: группа маркеров (1CM ¶, 12F)
    refs_glyph = ""

    def _inline_refs(node):
        """sup/fnref-узлы → текст-маркер `[^N]` на своём месте (in place)."""
        sh = _shallow(node)

        def walk_repl(n):
            for idx, kd in enumerate(n["kids"]):
                if not isinstance(kd, dict):
                    continue
                if _is_fnmark(kd):
                    if kd["tag"] == "sup":
                        r = fn_ref(kd, art)
                    else:
                        n2 = _ref_num(kd["attrs"].get("href", ""), raw_text(kd))
                        r = "[^%s]" % n2 if n2 is not None else ""
                    n["kids"][idx] = r or ""
                else:
                    walk_repl(kd)
        walk_repl(sh)
        return sh

    for b in blocks:
        c = cls(b)
        if c & LABEL_CLS:
            label = raw_text(_inline_refs(b)).strip().rstrip(":")
            if "[^" in label:
                # data-label темы — плоский текст, render маркер там не нарисует
                flag(art, "маркер сноски на label [mus] «%s» — render рисует строку-этикетку со сноской (.music-label)" % label[:40])
            continue
        if _is_inter_note(b):                     # Б2: inter-track заметка → строка-заметка
            nt = re.sub(r"\s+", " ", raw_text(_inline_refs(b)).strip())
            if nt:
                entries.append(("note", nt))
            continue
        bid = id(b)  # ДО _inline_refs (shallow-копия меняет id): трек-как-цель-сноски
        tracknum = ""                             # Б1: явный номер трека «N)» (1AQA/2BN)
        nn = first(b, lambda x: "num" in cls(x) and re.match(r"^\s*\d+[.)]", raw_text(x) or ""))
        if nn:
            tracknum = re.match(r"^\s*(\d+)", raw_text(nn)).group(1)
        b = _inline_refs(b)
        url = ""
        ae = first(b, lambda x: x["tag"] == "a" and ("ext" in " ".join(cls(x)) or "youtu" in x["attrs"].get("href", "")))
        if ae:
            url = ae["attrs"].get("href", "")
        if not url:
            de = first(b, lambda x: x.get("attrs", {}).get("data-embed") or x.get("attrs", {}).get("data-yt"))
            if de:
                d = de["attrs"].get("data-embed") or de["attrs"].get("data-yt")
                url = d if d.startswith("http") else "https://youtu.be/" + d
            elif b["attrs"].get("data-yt") or b["attrs"].get("data-embed"):
                d = b["attrs"].get("data-yt") or b["attrs"].get("data-embed")
                url = d if d.startswith("http") else "https://youtu.be/" + d
        # title/author: известные классы → структурный фолбэк (b/strong = title;
        # остаток после «—» = author) → raw split « — ». Имена классов per-article
        # случайны — перечень не закроется, структура надёжнее (аудит §3).
        name = (first(b, lambda x: cls(x) & {"t-name", "tname", "tk-name", "name"})
                or first(b, lambda x: cls(x) & (TITLE_CLS - {"t"}))
                or first(b, lambda x: "t" in cls(x) and x["tag"] == "span"))
        artn = first(b, lambda x: cls(x) & ARTIST_CLS)
        if name:
            # artist-спан может быть ВЛОЖЕН в title-спан (47H: `<span class="track-title">
            # <span class="artist">Joan Osborne</span> — One of us</span>`) → исключаем его
            # текст из названия, иначе render даёт двойного автора «A — A — Song».
            name_node = prune(_shallow(name), lambda x: bool(cls(x) & ARTIST_CLS)) if artn else name
            # тире-разделитель внутри title-спана после вырезания вложенного artist:
            # ведущий (47H «<artist>Joan Osborne</artist> — One of us» → « — One of us»)
            # ИЛИ хвостовой (44Q «Return of the Warlord — <by>ManOwaR</by>» → «… — »).
            # 1C8A: title-спан сам начинался с «— Poker Face». Срезаем разделитель с обоих
            # концов, иначе render даёт двойное тире / висячий дефис.
            name_txt = raw_text(name_node)
            # формат «N) Автор — Песня» (2BSA: `<ttl>1) <art>Burito</art> — Пока…`):
            # после вырезания вложенного artist остаётся «N) — Песня» → срезаем номер
            # ВМЕСТЕ с висячим разделителем (только при наличии тире — 53KA «1.Моя
            # Звезда» без тире не тронется, номер в названии сохраняется)
            name_txt = re.sub(r"^\s*\d+[.)]\s*[—–-]\s*", "", name_txt)
            name_txt = re.sub(r"^\s*[—–-]\s*", "", name_txt)
            name_txt = re.sub(r"\s*[—–-]\s*$", "", name_txt)
            title = _clean_track_text(name_txt)
            author = _clean_track_text(re.sub(r"^[—–-]\s*", "", raw_text(artn))) if artn else ""
        else:
            bo = first(b, lambda x: x["tag"] in ("b", "strong"))
            full = _clean_track_text(raw_text(b))
            if bo:
                # b-узел отображается в карточке ПЕРВЫМ; render склеивает
                # «author — title» → b-текст идёт в author (порядок = оригинал;
                # чинит «Moment of Peace — Gregorian» 16J, «Circle of Life —
                # Elton John» 12L — поля больше не переворачиваются)
                author = _clean_track_text(raw_text(bo))
                rem = full.replace(author, "", 1) if author and author in full else ""
                title = _clean_track_text(re.sub(r"^[—–-]\s*", "", rem.strip()))
            else:
                title, author = full, ""
        if not author and " — " in title:
            # комбо-строка «X — Y»: кто автор — не определить; render склеивает
            # «author — title» → первый кусок в author-слот = АВТОРСКИЙ порядок
            # отображения сохраняется (12L «Elton John — Circle of Life»)
            author, title = [_clean_track_text(s) for s in title.split(" — ", 1)]
        author = re.sub(r"^[—–-]\s*", "", author).strip()  # ведущее тире остатка (368)
        if not author:
            # «Композиция, АВТОР» (финальный трек-лист 12F, вердикт A5г) — автор
            # капсом после запятой → раздельные поля (render сам склеит «А — К»)
            mca = re.match(r"^(.{2,}?),\s+([А-ЯЁ][А-ЯЁ\s.&«»'-]{2,})$", title)
            if mca:
                title, author = mca.group(1).strip(), mca.group(2).strip()
                flag(art, "трек «Композиция, АВТОР» → раздельные поля")
        if not url and not title:
            continue  # ZML3: a [mus] track is valid with ≥1 field (title OR url)
        fnum = None
        if bid in MUS_FN:  # трек = цель сноски → 4-е поле = номер сноски (для cite_note-id)
            refs_group, fnum = MUS_FN[bid]
            refs_glyph = MUS_FN_GLYPH.get(refs_group, "")
        entries.append(("trk", url, title, author, fnum, tracknum))
    # музыка-канон «Название — Автор»: ориентация слотов по базе songs (оракул) —
    # slot2=название всегда; перевёрнутые/склеенные/мусорные слоты чинятся (music_canon.py)
    def _canon(e):
        if e[0] == "note":
            return e
        _, u, t, a, f, n = e
        if not u.strip():                     # добор (б): url-less трек → url из базы songs
            u = fill_url(t, a) or u
        ct, ca, _ = canonicalize(u, t, a, art)
        if n:  # Б1: явный номер «N)» в начало названия; снять задвоение из обоих слотов
            ct = re.sub(r"^\s*\d+[.)]\s*", "", ct)
            ca = re.sub(r"^\s*\d+[.)]\s*", "", ca)
            ct = "%s) %s" % (n, ct)
        return ("trk", u, ct, ca, f)
    entries = [_canon(e) for e in entries]
    # дедуп: безымянная url-строка (голый embed-плеер рядом с титулованной
    # строкой того же видео — 185A/34O) дропается, если ID уже представлен с title
    titled_ids = {_yt_id(e[1]) for e in entries
                  if e[0] == "trk" and (e[2] or e[3]) and _yt_id(e[1])}
    lines, seen = [], set()
    for e in entries:
        if e[0] == "note":                        # Б2: inter-track заметка
            lines.append("> " + e[1])
            continue
        _, url, title, author, fnum = e
        vid = _yt_id(url)
        if not title and not author and vid and vid in titled_ids and fnum is None:
            continue
        key = (vid or url, title, author)
        if key in seen and fnum is None:
            continue
        seen.add(key)
        if fnum is not None:  # трек-как-цель-сноски: 4-е поле = номер (render → cite_note-id)
            lines.append("[%s|%s|%s|%d]" % (url, title, author, fnum))
        else:
            lines.append("[%s|%s|%s]" % (url, title, author))
    # дефолт-лейбл («Музыка под настроение») опускается, НО не когда несёт маркер
    # сноски — иначе сноска с этикетки гибнет (1C8C «…[^4]», вердикт 20:27)
    head = ("[mus]"
            if not label or ("настроени" in label.lower() and "[^" not in label)
            else '[mus="%s"]' % label)
    if refs_group:  # трек = цель сноски (сноска-на-плеер): [mus refs=… glyph=…]
        head = "[mus refs=%s%s]" % (refs_group, " glyph=%s" % refs_glyph if refs_glyph else "")
    if not lines:
        return ""
    return head + "\n" + "\n".join(lines) + "\n[/mus]"


def register_music_footnotes(root, art):
    """Трек-плеер как ЦЕЛЬ сноски (вердикт оператора 14:13): маркер в тексте
    `<a href="#mus-1">¶1</a>` ссылается на трек `<div class="track" id="mus-1">`
    (1CM серия ¶, 12F «Рекомендуемая музыка»). Регистрируем id трека в FN_ID_MAP
    как `<префикс>.<номер>` → маркер станет [^префикс.номер] (рабочая ссылка-переход
    на плеер); [mus] получит refs=/glyph=, а у трека в render будет cite_note-id +
    обратная стрелка. Запускать ПОСЛЕ collect_footnotes, ДО walk."""
    MUS_FN.clear()
    MUS_FN_GLYPH.clear()
    tracks = [t for t in find(root, is_track) if t["attrs"].get("id")]
    if not tracks:
        return
    by_id = {t["attrs"]["id"]: t for t in tracks}
    inside_track = set()
    for t in tracks:
        for d in find(t, lambda x: True):
            inside_track.add(id(d))
    for a in find(root, lambda x: x["tag"] == "a"
                  and x["attrs"].get("href", "").lstrip("#") in by_id):
        if id(a) in inside_track:
            continue  # ссылка ВНУТРИ трека (его обратная стрелка) — не маркер
        tid = a["attrs"]["href"].lstrip("#")
        m = re.match(r"^(.*?)-?(\d+)$", tid)
        if not m:
            continue
        group = re.sub(r"[^A-Za-z0-9_-]", "", m.group(1)) or "trk"
        num = int(m.group(2))
        FN_ID_MAP[tid] = "%s.%d" % (group, num)
        MUS_FN[id(by_id[tid])] = (group, num)
        gl = re.sub(r"[\d\s.):]+", "", raw_text(a))  # «¶1»→«¶», «1»→«»
        if group not in MUS_FN_GLYPH:
            MUS_FN_GLYPH[group] = gl[:2] if gl else ""
    if MUS_FN:
        flag(art, "трек-плеер как цель сноски (%d) → [mus refs=…] (сноска-на-плеер)" % len(MUS_FN))


def slug_of(h2, block):
    for el in (block, h2):
        i = el["attrs"].get("id")
        if i:
            return i
    a = first(h2, lambda x: x["tag"] == "a" and x["attrs"].get("name"))
    return a["attrs"].get("name") if a else None


# ── footnotes v2 (контейнер-роль, не классы айтемов) ─────────────────────────
NOTES_CONT_CLS = {"notes", "footnotes", "fnlist", "fn-list", "notelist",
                  "notes-list", "endnotes", "fns", "fnotes", "fnitems"}
ITEM_CLS = {"fn", "note", "fnote", "footnote", "fn-item", "fnitem", "fnentry",
            "note-item", "fn-note"}
BACKREF_CLS = {"back", "backref", "fn-back", "ret", "return", "back-ref"}
# спан с номером/значком сноски В АЙТЕМЕ (имена per-article: num/fn-num/mark/mk…)
MARKER_CLS = {"num", "marker", "fn-num", "fnnum", "fn-mark", "fnmark", "mark", "mk", "note-mark"}
# анонимные сноски без in-text маркера (А1): note-anon (0BH/184 — голая, без ярлыка),
# fn-anon (0BCA — ::before «*», звёздная анон). Собираются как note-item.
ANON_NOTE_CLS = {"note-anon", "fn-anon", "anon-note", "noteanon"}
_ID_RX = re.compile(r"^(fn|note|n|fnote|footnote|ref-?def)[-_]?\d+$", re.I)


def _has_backref(n):
    return bool(first(n, lambda x: x["tag"] == "a" and (
        bool(cls(x) & BACKREF_CLS)
        or (x["attrs"].get("href", "").startswith("#")
            and re.fullmatch(r"[↑↟↩↪⮌⤴⬆\s]+", raw_text(x) or " ") is not None
            and raw_text(x).strip() != ""))))


def _is_note_item(n, in_notes_cont):
    if n["tag"] not in ("li", "p", "div"):
        return False
    c = cls(n)
    if c & ITEM_CLS:
        return True
    if c & ANON_NOTE_CLS:  # А1: голая/звёздная анон-сноска (note-anon/fn-anon)
        return True
    if _ID_RX.match(n["attrs"].get("id", "")):
        return True
    if _has_backref(n):
        return True
    if in_notes_cont and n["tag"] == "li":
        return True  # безклассовый li внутри notes-контейнера (09S: section>ol>li)
    return False


def _star_norm(s):
    """Юникод-звёзды (∗ U+2217, ✱, ⁎) → ASCII '*' для маркер-логики (239)."""
    return re.sub(r"[∗✱⁎]", "*", s or "")


def _fn_glyph(it):
    """Авторский значок серии из .num/.marker спана («¤1» → '¤'; 1CM ¤ ¶ ^ ‡,
    341A '*N'). None, если маркер чисто числовой."""
    sp = first(it, lambda x: bool(cls(x) & MARKER_CLS))
    if not sp:
        return None
    g = re.sub(r"[\d\s.): ]+", "", _star_norm(raw_text(sp)))
    return g if 0 < len(g) <= 2 else None


def collect_footnotes(root, art):
    """→ (fns: [(num, txt, prefix)], groups, consumed_ids, first_container_node).

    Один контейнер сносок (норма корпуса) → дефолт-группа `[^N]:` хвостом
    (поведение как раньше). НЕСКОЛЬКО контейнеров (пер-секционные схемы 12F/1CM/
    217A/341A) → ГРУППЫ ZML3 §4.1 (fn-ревью, вердикты 1+3+5): каждый контейнер —
    именованная группа s1, s2…; определения `[^sK.N]:` в хвосте, вывод `[refs=sK
    glyph=…]` на месте контейнера (walk эмитит по first-item-id); нумерация
    ПЕР-ГРУППОВАЯ авторская (серии не сливаются). groups: [{name, items, first_id,
    glyph}]. Инвариант корпуса — КОНТЕЙНЕР сносок + айтемы с backref/id."""
    # 1. контейнеры по классу
    containers = find(root, lambda x: x["tag"] in ("section", "div", "ol", "ul")
                      and bool(cls(x) & NOTES_CONT_CLS) and "toc" not in cls(x))
    # 2. + родители айтемов с независимыми уликами (класс/id И backref) вне их
    cont_ids = {id(c) for c in containers}
    extra_parents = {}
    def scan(node, anc_in_cont):
        for k in node["kids"]:
            if not isinstance(k, dict):
                continue
            inside = anc_in_cont or id(k) in cont_ids
            if not inside and k["tag"] in ("li", "p", "div") and (
                    (cls(k) & ITEM_CLS) or _ID_RX.match(k["attrs"].get("id", ""))) \
                    and _has_backref(k):
                extra_parents[id(node)] = node
            scan(k, inside)
    scan(root, False)
    containers += [p for pid, p in extra_parents.items() if pid not in cont_ids]
    # внешние контейнеры поглощают вложенные (section.notes > ol.fnlist)
    keep = []
    cids = [id(c) for c in containers]
    for c in containers:
        if not any(id(c) != id(o) and id(c) in {id(d) for d in find(o, lambda x: True)}
                   for o in containers):
            keep.append(c)
    containers = keep

    consumed = set()
    first_item = None
    cont_fns = []  # per-container: (cont, [(num, txt, anchor, starred, prefix, glyph)], first_item_id)
    # документ-порядок контейнеров
    order = {id(n): i for i, n in enumerate(find(root, lambda x: True))}
    containers.sort(key=lambda c: order.get(id(c), 0))
    for cont in containers:
        fns = []
        cont_first = None
        # ВАЖНО: потребляем ТОЛЬКО айтемы (+их поддеревья), а не контейнер целиком —
        # рядом с айтемами живут НЕ-сносочные абзацы («П.С.», звёздные определения
        # без разметки — 2CQ), их обязан подобрать обычный walk (ничего не терять).
        # айтемы: прямые дети-элементы контейнера (и спуск в один уровень обёрток)
        items = []
        def gather(node, depth=0):
            for k in node["kids"]:
                if not isinstance(k, dict):
                    continue
                # вложенная обёртка-контейнер (section.notes > div.notelist, 35Q):
                # сама проходит _is_note_item через _has_backref (upref у потомков) —
                # СПУСКАЕМСЯ в неё, а не глотаем 9 айтемов одним блобом
                if (depth < 2 and k["tag"] in ("div", "ol", "ul", "section")
                        and bool(cls(k) & NOTES_CONT_CLS)):
                    gather(k, depth + 1)
                elif _is_note_item(k, True):
                    items.append(k)
                elif depth < 2 and k["tag"] in ("div", "ol", "ul", "section"):
                    gather(k, depth + 1)
        gather(cont)
        in_ol = cont["tag"] == "ol" or bool(first(cont, lambda x: x["tag"] == "ol"))
        seq = 0
        for it in items:
            consumed.add(id(it))
            for d in find(it, lambda x: True):
                consumed.add(id(d))
            if first_item is None:
                first_item = it
            if cont_first is None:
                cont_first = id(it)
            seq += 1
            num = _fn_number(it)
            be = (first(it, lambda x: bool(cls(x) & {"fn-body", "fn-text", "note-body", "body", "txt"}))
                  or it)
            be = prune(_shallow(be), lambda x: bool(cls(x) & (MARKER_CLS | BACKREF_CLS)))
            txt = _fn_text(be, art)
            # литеральный звёздный маркер «*N.» в начале тела — АВТОРИТЕТНЫЙ номер
            # (надёжнее id: в пер-секционных схемах id-цифры врут — 217A)
            starred = False
            # авторский звёздный маркер анонимной сноски («*», «**») — хранить
            # как `[^|*]:` (render рисует его, а не дефолт «См. также») — 182
            prefix = ""
            ac = cls(it)
            _anon_bare = bool(ac & (ANON_NOTE_CLS - {"fn-anon"}))
            _anon_star = "fn-anon" in ac
            if _anon_bare or _anon_star:
                # А1: анон-сноска без in-text маркера — голая (note-anon → render
                # без ярлыка, prefix="bare"→[^|]:) либо звёздная (fn-anon, ::before
                # «*» в оригинале → [^*]); номер не присваиваем
                num = None
                prefix = "*" if _anon_star else "bare"
            mk = first(it, lambda x: bool(cls(x) & MARKER_CLS))
            if mk is not None and re.fullmatch(r"\*+", _star_norm(raw_text(mk).strip()) or "#"):
                prefix = _star_norm(raw_text(mk).strip())
                # ЯВНЫЙ звёздный маркер-спан («*»/«**») главенствует над id-числом
                # (1AQA: `<li id="fn1"><span class="note-mark">*</span>`) → это звёздная
                # сноска [^*], не [^1]; гард ниже (in_ol) удержит num=None при «*»-маркере
                num = None
            # юникод-звёзды (∗∗∗ — 239) нормализуются к '*' для маркер-логики
            mstar = re.match(r"^\*+\s*(\d+)\s*[.)]?\s*", _star_norm(txt or ""))
            if mstar:
                num = int(mstar.group(1))
                txt = txt[mstar.end():].strip()
                starred = True
            elif not prefix:
                mb = re.match(r"^(\*+)\s+", _star_norm(txt or ""))  # звёзды голым текстом в теле
                if mb:
                    prefix = mb.group(1)
                    txt = txt[mb.end():].strip()
            if num is None and in_ol and it["tag"] == "li" and not (_anon_bare or _anon_star):
                # последовательная нумерация <ol> (если нет анон-маркера « * »)
                mk = first(it, lambda x: bool(cls(x) & MARKER_CLS))
                if not (mk and "*" in _star_norm(raw_text(mk))):
                    num = seq
            if txt:
                # be храним: тела пере-сериализуются ПОСЛЕ заполнения FN_ID_MAP
                # (кросс-рефы сносок на ГРУППОВЫЕ определения — 341A [^s2.1])
                fns.append([num, txt, it["attrs"].get("id") or "", starred, prefix,
                            _fn_glyph(it), be])
        if fns:
            cont_fns.append((cont, fns, cont_first))

    def _strip_lead_num(e):
        # маркер «N.»/«N)» голым текстом в начале тела (не в span.num) — срезаем
        # при совпадении с ФИНАЛЬНЫМ номером; звёздно-очищенные не трогаем,
        # (?!\d) бережёт «22 буквы» при num=2 (186A)
        if e[0] is not None and e[1] and not e[3]:
            # ведущий ЛИТЕРАЛЬНЫЙ самомаркер «[^N]» (1BI: `<li><sup>N</sup> текст` —
            # голый sup номера сноски → inline даёт «[^N]» в начале тела) — срезаем,
            # только если N == номер самой сноски (не настоящий кросс-реф)
            e[1] = re.sub(r"^\[\^%d\]\s*" % e[0], "", e[1]).strip()
            e[1] = re.sub(r"^\**\s*0*%d(?!\d)\s*[.):—-]?\s*" % e[0], "", e[1]).strip()

    def _reserialize(e):
        # второй проход: тело заново через inline() с ПОЛНОЙ FN_ID_MAP (кросс-
        # рефы между группами), затем те же срезы маркеров, что в item-loop
        be = e[6]
        if be is None:
            return
        txt = _fn_text(be, art)
        mstar = re.match(r"^\*+\s*(\d+)\s*[.)]?\s*", _star_norm(txt or ""))
        if e[3] and mstar:
            txt = txt[mstar.end():].strip()
        elif e[4]:
            mb = re.match(r"^(\*+)\s+", _star_norm(txt or ""))
            if mb:
                txt = txt[mb.end():].strip()
        e[1] = txt
        _strip_lead_num(e)
        e[1] = b6_seealso(e[1])  # B6: канон «См. также» (все сноски, вкл. групповые)

    groups = []
    if len(cont_fns) <= 1:
        # ── дефолт-группа (норма корпуса): хвост с notes_title, как раньше ──
        fns = cont_fns[0][1] if cont_fns else []
        nums = [e[0] for e in fns if e[0] is not None]
        if len(nums) != len(set(nums)):
            flag(art, "коллизия номеров в одном контейнере → перенумерация (%d шт.)" % len(fns))
            for i, e in enumerate(fns):
                e[0] = i + 1
        for e in fns:
            if e[2]:
                # значение карты: номер ИЛИ звёздный маркер ('**') — ссылка в
                # теле, целящая в этот якорь, станет [^**] (кликабельно)
                FN_ID_MAP[e[2]] = e[0] if e[0] is not None else (e[4] or None)
        for e in fns:
            _reserialize(e)
        return ([(n, t, pre) for n, t, _a, _s, pre, _g, _b in fns if t],
                groups, consumed, first_item)

    # ── ГРУППЫ (fn-ревью, вердикты 1+3+5): несколько контейнеров — каждый своя
    # именованная группа sK; пер-групповая авторская нумерация; глиф-серии. ──
    flag(art, "пер-секционные сноски → группы [refs] (%d контейнеров)" % len(cont_fns))
    default_fns = []
    staged = []  # (gname, numbered, glyph, cfirst) — пока без финальных текстов
    for gi, (cont, fns, cfirst) in enumerate(cont_fns, 1):
        gname = "s%d" % gi
        numbered = [e for e in fns if e[0] is not None]
        anon = [e for e in fns if e[0] is None]
        nums = [e[0] for e in numbered]
        if len(nums) != len(set(nums)):
            flag(art, "группа %s: коллизия номеров → перенумерация внутри группы (%d шт.)" % (gname, len(numbered)))
            for i, e in enumerate(numbered):
                e[0] = i + 1
        # глиф серии: единый по всем numbered-айтемам группы (¤ ¶ ^ ‡ — 1CM; '*' — 341A)
        glyphs = {e[5] for e in numbered}
        glyph = glyphs.pop() if len(glyphs) == 1 and None not in glyphs else None
        if glyph is None and numbered and all(e[3] for e in numbered):
            glyph = "*"  # звёздная серия «*1/*2» (341A) → [refs=… glyph=*]
        for e in numbered:
            if e[2]:
                FN_ID_MAP[e[2]] = "%s.%d" % (gname, e[0])
        # анон/звёздные определения внутри группового контейнера групповой формы
        # не имеют (§4.1 — группы числовые) → дефолт-хвост + флаг
        for e in anon:
            if e[2]:
                FN_ID_MAP[e[2]] = e[4] or None
            default_fns.append(e)
            flag(art, "группа %s: анонимное/звёздное определение → дефолт-хвост" % gname)
        staged.append((gname, numbered, glyph, cfirst))
    # карта якорей ПОЛНА → финальная сериализация тел (кросс-рефы групп верны)
    for gname, numbered, glyph, cfirst in staged:
        for e in numbered:
            _reserialize(e)
        if numbered:
            groups.append({"name": gname,
                           "items": [(e[0], e[1]) for e in numbered if e[1]],
                           "first_id": cfirst, "glyph": glyph})
    for e in default_fns:
        _reserialize(e)
    return ([(n, t, pre) for n, t, _a, _s, pre, _g, _b in default_fns if t],
            groups, consumed, first_item)


def _fn_text(be, art):
    """Тело сноски; 📏 — многострочность через continuation (отступ 4 пробела).
    Строки = <br>-переносы ИЛИ построчные спаны (.vsub — стих-в-сноске, 182)."""
    line_els = [k for k in be["kids"] if isinstance(k, dict)
                and (cls(k) & {"vsub", "line", "ln", "verse-line"})]
    if len(line_els) >= 2:
        lines = [re.sub(r"\s+", " ", inline(l, art, "space")).strip() for l in line_els]
    else:
        lines = _mark_lines(be, art)
    lines = [strip_backref(l) for l in lines if l]
    lines = [l for l in lines if l]
    if not lines:
        return ""
    return "\n    ".join(lines)


def _fn_number(fn):
    """Authoritative note number: .num/.marker span → back-arrow href → id."""
    numspan = first(fn, lambda x: bool(cls(x) & MARKER_CLS))
    if numspan:
        m = re.search(r"\d+", raw_text(numspan))
        if m:
            return int(m.group())
        if "*" in raw_text(numspan):
            return None  # звёздочная анон-сноска
    back = first(fn, lambda x: x["tag"] == "a" and (bool(cls(x) & BACKREF_CLS) or "back" in " ".join(cls(x))))
    if back:
        m = re.search(r"#r(?:ef)?[-_]?(\d+)", back["attrs"].get("href", ""))
        if m:
            return int(m.group(1))
    fid = fn["attrs"].get("id", "")
    m = re.search(r"fn[-_]?(\d+)", fid)  # «s7-fn3» → 3, не 7 (217A)
    if m:
        return int(m.group(1))
    nums = re.findall(r"\d+", fid)
    if nums:
        return int(nums[-1])
    return None


def strip_backref(s):
    return re.sub(r"\s*[↑↩↪⮌⤴⬆]\s*$", "", s).strip()


def find_notes_title(root, art, first_item):
    """Последний <h2> в документ-порядке перед ПЕРВЫМ айтемом сносок (не
    контейнером: в sec-block-схеме заголовок «Полезные ссылки» лежит ВНУТРИ
    контейнера, перед айтемами — 237)."""
    if first_item is None:
        return ""
    state = {"h2": "", "found": None}

    def walk(n):
        for k in n["kids"]:
            if not isinstance(k, dict) or state["found"] is not None:
                continue
            if id(k) == id(first_item):
                state["found"] = state["h2"]
                return
            if k["tag"] == "h2":
                state["h2"] = re.sub(r"\s+", " ", inline(k, art).strip())
            walk(k)

    walk(root)
    return state["found"] or ""


# ── единый walk (v2) ─────────────────────────────────────────────────────────
CHROME_TAGS = {"header", "nav", "footer", "h1", "hr", "button", "form",
               "iframe", "svg", "template", "audio", "video", "canvas"}
CHROME_CLS = {"crumbs", "breadcrumbs", "toc", "byline", "artline", "colophon",
              "corpus-nav", "corpusnav", "section-nav", "sectionnav", "nav",
              "license", "attrib", "attribution", "build-date", "hashtag",
              "hero", "cover", "lead-img", "rule-orn", "title-orn", "ornament",
              "rule", "divider", "sep", "pager", "prevnext", "pagenav",
              "back-to-top", "totop", "skip", "sr-only",
              "epi-label", "epigraph-label", "epi-h", "epi-tag"}
INLINE_TAGS = {"a", "em", "i", "b", "strong", "span", "sup", "sub", "small",
               "u", "s", "code", "mark", "cite", "abbr", "br", "img", "wbr", "time"}
DIALOG_CLS = {"q", "a", "qa", "dialog", "dialogue", "question", "answer",
              "speaker", "replica", "line-q", "line-a"}

# строка-дата (киккер-даты и пр.): «25 февраля 2021 г.» / 2021-02-25 / 20.02.23
_DATEISH_RX = re.compile(
    r"\d{1,2}\s+[а-яё]+\s+\d{4}|\d{4}[/.\-]\d{2}[/.\-]\d{2}|\d{2}[.\-/]\d{2}[.\-/]\d{2,4}", re.I)


def _hangnum(p_node):
    """Висячая ручная нумерация (вердикт 7): <p><span class="n">1.</span>текст…
    → (номер, скобко-знак) либо None. Только В ТЕЛЕ (сноски consumed раньше)."""
    if not (isinstance(p_node, dict) and p_node["tag"] == "p"):
        return None
    for x in p_node["kids"]:
        if isinstance(x, str):
            if x.strip():
                return None
            continue
        if x["tag"] == "span" and (cls(x) & {"n", "num", "pnum"}):
            m = re.fullmatch(r"(\d+)\s*([.)])?", raw_text(x).strip())
            return (int(m.group(1)), m.group(2) or ".") if m else None
        return None
    return None


# ── подпись автора → [sig] (C11; вердикт «sig-извлечение», 2026-06-17) ─────────
# Авторские сайн-оффы (.sign/.signature/.signoff/.signed) → [sig] (правовыключка,
# курсив). Чистая дата-строка («Написано 7 Апреля 2022 г.» — 247/2AA) → [line
# kind=dateline] (§2.3, byline всё равно рисует manifest-дату). Форум-лейбл
# «Подпись пользователя» (.sig-label/.cap/декор-текст — 2CQ/324) снимается (§12).
# Инлайн <span class="sign"> внутри прозы (24F) НЕ трогаем — это хвост абзаца.
SIGN_CLS = {"sign", "signature", "signoff", "signed", "podpis"}
SIG_LABEL_CLS = {"sig-label", "siglabel", "sig-head", "cap"}
_SIG_LABEL_RX = re.compile(r"^[\s\-—–=*~_]*подпись\s+пользоват\w*[\s\-—–=*~_:.]*$", re.I)
_SIG_DATE_HEAD = re.compile(r"(?i)\b(написано|написана|дата|от)\b")


def _strip_sig_label(node):
    """Копия узла без форум-лейбла «Подпись пользователя» (класс или декор-текст)."""
    sh = _shallow(node)
    sh["kids"] = [x for x in sh["kids"] if not (
        isinstance(x, dict)
        and ((cls(x) & SIG_LABEL_CLS)
             or _SIG_LABEL_RX.match(re.sub(r"\s+", " ", raw_text(x)).strip())))]
    return sh


def _is_dateline_only(body):
    """Подпись — чистая дата-строка? («Написано 7 Апреля 2022 г.»). Многострочная
    подпись (имя+город+дата — 31E/262) НЕ дата."""
    if "\n" in body or not _DATEISH_RX.search(body):
        return False
    residue = _SIG_DATE_HEAD.sub("", _DATEISH_RX.sub("", body))
    return len(re.sub(r"[\s.,:;г.\-–—()]", "", residue)) <= 1


def _label_marker_to_heading(blocks, art):
    """Маркер сноски на label [mus] при ## с ТОЙ ЖЕ надписью прямо над карточкой
    (11H «Песнь Ступеней[^7]») → перенос маркера в ## — сноска видна, надпись
    не дублируется (вердикт 20:27 2026-06-12)."""
    if len(blocks) < 2 or not blocks[-1].startswith('[mus="') \
            or not blocks[-2].startswith("##"):
        return
    m = re.match(r'\[mus="([^"]*)"\]', blocks[-1])
    if not m:
        return
    marks = re.findall(r"\[\^[^\]]+\]", m.group(1))
    if not marks:
        return
    plain = re.sub(r"\[\^[^\]]+\]", "", m.group(1)).strip().rstrip(":").strip()
    mh = re.match(r"^(#{2,3})\s+(.*?)(\s*\{[^}]*\})?$", blocks[-2])
    if not mh or mh.group(2).strip().lower() != plain.lower():
        return
    blocks[-2] = "%s %s%s%s" % (mh.group(1), mh.group(2).strip(),
                                "".join(marks), mh.group(3) or "")
    blocks[-1] = blocks[-1].replace(m.group(0), '[mus="%s"]' % plain, 1)
    flag(art, "маркер с label [mus] перенесён в ## «%s» (без дубля надписи)" % plain[:30])


def _rich_li(x):
    """Блочный ребёнок li, который нельзя плющить в текст пункта: цитаты,
    заголовки, вложенные списки/таблицы, треки-details (35Q), div с абзацами."""
    return (x["tag"] in ("blockquote", "h2", "h3", "table", "ol", "ul",
                         "details", "iframe")
            or (x["tag"] == "div" and first(x, lambda y: y["tag"] == "p") is not None))


def _toc_heading(k, blocks, art, st):
    """Пункт оригинального TOC на БЕЗЗАГОЛОВОЧНЫЙ блок → настоящий ## из текста
    пункта («идём за оригиналом», вердикт 19:21 2026-06-12; обобщение муз-правила
    158/17BA: 2BG «Эпиграф» → #epigraph-секция, 0BH «Текст» → #body)."""
    kid = k["attrs"].get("id")
    if kid and kid in st.get("toc_items", {}) and first(
            k, lambda x: x["tag"] in ("h1", "h2", "h3", "h4")) is None:
        blocks.append("## %s {%s}" % (st["toc_items"][kid], kid))
        st["started"] = True
        flag(art, "TOC-пункт «%s» → ## (беззаголовочный блок)" % st["toc_items"][kid][:30])


# ── №2 форум-тред (standalone-header) ────────────────────────────────────────
# Эталон — форум ccastaneda.ru: пост-в-рамке с меткой-спикером. У части статей
# метка живёт ОТДЕЛЬНЫМ узлом (.speaker/.answer-label «Ник написал(а):», «Ответ:»),
# а ТЕЛО реплики — следующие сиблинги (blockquote/голые <p>/.answer/.body-prose/
# verse). Конвертер втягивает тело под метку в один пост; метку помечает явным
# маркером «>> » (render так точно знает границы постов, без хрупкой эвристики по
# двоеточию — иначе строки тела вида «Свойство зеркальце имело: …» ловятся ложно).
# классы блок-метки спикера. Оригиналы свёрстаны вразнобой — у одной и той же роли
# в разных статьях разный класс (speaker/who/poster/answer-head/src-label/…); собрано
# сканом корпуса. inline-`<span>`-метки (Доброжелатель:/Бина Анеле:) живут уже в [dlg]
# (19 статей) — их ловит splitSpeaker в render, здесь они не нужны.
SPEAKER_LABEL_CLS = DIALOG_CLS | {"answer-label", "reply-label", "who", "poster",
                                  "src-label", "answer-head"}
# узлы, обрывающие тело поста (их роль — НЕ реплика): лид/подпись/источник/хром/
# музыка/сноски/ПОЭМА-блок (33H/55K: стих-речь — отдельный [poem], не форум-пост).
# blockquote.verse (335) — НАОБОРОТ валидное тело (цитата-стих внутри поста).
DLG_BODY_STOP_CLS = {"lead", "end", "byline", "dateline", "source",
                     "music", "music-label", "notes", "colophon", "corpusnav",
                     "rail", "kicker", "poem", "stanza", "epi", "epigraph"} \
    | SIGN_CLS  # подпись/сайн-офф — не тело форум-поста, а отдельный [sig]/dateline
DLG_BODY_STOP_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6",
                      "ul", "ol", "details", "table", "section"}


def _dlg_label_text(x, art):
    """Текст метки-спикера (inline-резолв: [^N]/ссылки/{term}), без хвостового ':'
    и без «написал(а)» (как splitSpeaker в render для inline-меток 19 статей)."""
    s = re.sub(r"\s+", " ", inline(x, art)).strip().rstrip(":").strip()
    s = re.sub(r"\s*написал\(а\)\s*$", "", s).strip()
    return s


def _is_speaker_label(x):
    """DIALOG-узел, чей текст — короткий ярлык спикера (а не сама реплика).
    Признак ярлыка — хвостовое ':' («Ник написал(а):» / «Ответ:» / «Имя:»);
    реплика-строка («"- Что означает смерть?"», «Вопрос(…) Например?») — НЕ ярлык."""
    if not (isinstance(x, dict) and x["tag"] in ("p", "div")):
        return False
    txt = re.sub(r"\s+", " ", raw_text(x)).strip()
    if not (0 < len(txt) <= 80):
        return False
    # муз-этикетка / см.-также, ложно оканчивающиеся ':' — НЕ метка
    if re.match(r"(?i)\s*(музык|мызка|рекоменд\w*\s+муз|см\.?\s*(также|тж))", txt):
        return False
    # СИЛЬНЫЙ форум-сигнал: «Ник написал(а):» — класс не важен (оригиналы вёрстаны
    # вразнобой: speaker/who/poster/author/…), такой хвост встречается ТОЛЬКО в
    # форум-атрибуции, ложных срабатываний на прозе нет.
    if re.search(r"написал\(а\)\s*:?\s*$", txt):
        return True
    # маркер-реплика как САМОСТОЯТЕЛЬНЫЙ короткий ярлык (± «(…)», ± ':')
    if re.fullmatch(r"(?i)(вопрос|ответ|реплика)(\s*\([^)]*\))?\s*[:.]?", txt):
        return True
    # прочий короткий ':'-ярлык — ТОЛЬКО при форум-классе (защита от прозы вида
    # «Свойство зеркальце имело:»)
    return txt.endswith(":") and bool(cls(x) & SPEAKER_LABEL_CLS)


def _is_dlg_body_stop(x):
    if not isinstance(x, dict):
        return False
    if x["tag"] == "hr":               # разделитель — не тело и не стоп (пропустить)
        return False
    if x["tag"] in CHROME_TAGS or x["tag"] in DLG_BODY_STOP_TAGS:
        return True
    return bool(cls(x) & (DLG_BODY_STOP_CLS | CHROME_CLS)) or is_music_container(x)


def _dlg_body_paras(node, art):
    """Тело-узел → плоские абзац-строки. Стих НЕ оборачивается в [poem] (идёт
    строками через <br> внутри поста); строфы-группы → отдельные абзацы."""
    bkids = [x for x in node["kids"]
             if isinstance(x, dict) and x["tag"] in ("p", "div", "blockquote")]
    if bkids:
        out = []
        for x in bkids:
            out.extend(_dlg_body_paras(x, art))
        return out
    # стих (blockquote.verse / .v-строки, 335 «Наше Мама») → строки через \n
    # (render даст <br>); _mark_lines их бы схлопнул (текст-переносы между .v).
    if (cls(node) & {"verse", "poem"}) or first(
            node, lambda y: bool(cls(y) & {"v", "line", "ln", "verse-line", "st", "stanza"})):
        vl = _verse_lines(node, art)
        return ["\n".join(vl)] if vl else []
    groups = _line_groups(_mark_lines(node, art))
    out = []
    for g in groups:
        txt = "\n".join(re.sub(r"\s{2,}", " ", l).strip() for l in g if l.strip())
        if re.search(r"\w", txt):
            out.append(txt)
    return out


def _emit_forum_thread(kids, i, art, st):
    """Если kids[i] — метка-спикер с тело-сиблингом: собрать форум-тред
    (метка → тело)→ строка «[dlg]…» и индекс конца. Иначе (None, i)."""
    posts = []
    j = i
    while j < len(kids):
        x = kids[j]
        if isinstance(x, str):
            if x.strip():
                break
            j += 1
            continue
        if id(x) in st["consumed"]:
            j += 1
            continue
        if not _is_speaker_label(x):
            break
        label = _dlg_label_text(x, art)
        body = []
        j += 1
        while j < len(kids):
            y = kids[j]
            if isinstance(y, str):
                if y.strip():
                    break
                j += 1
                continue
            if id(y) in st["consumed"] or (isinstance(y, dict) and y["tag"] == "hr"):
                j += 1
                continue
            if _is_speaker_label(y) or _is_dlg_body_stop(y):
                break
            body.extend(_dlg_body_paras(y, art))
            j += 1
        posts.append((label, body))
    # тред «настоящий», только если хотя бы у одного поста есть тело-сиблинг
    if not posts or not any(b for _, b in posts):
        return None, i
    segs = []
    for label, body in posts:
        segs.append("\n\n".join([">> " + label] + body))
    return "[dlg]\n" + "\n\n".join(segs) + "\n[/dlg]", j


def walk(node, blocks, art, st):
    """Единый проход: документ-порядок, спуск во всё незнакомое, эмит по роли.
    st: {'consumed': ids сносок, 'started': bool, 'refs_at': {item-id→group},
    'refs_done': set, 'dates': str|None, 'toc_done': bool, 'epi_pending': bool}."""
    kids = node["kids"]
    runbuf = []

    def emit_refs_for(item_node):
        """[refs=…] на месте первого айтема группы (§4.1)."""
        ref = st.get("refs_at", {}).get(id(item_node))
        if ref is not None and ref["name"] not in st["refs_done"]:
            st["refs_done"].add(ref["name"])
            gl = " glyph=%s" % ref["glyph"] if ref.get("glyph") else ""
            blocks.append("[refs=%s%s]" % (ref["name"], gl))
            st["started"] = True

    def flush_run():
        if not runbuf:
            return
        syn = {"tag": "p", "attrs": {}, "kids": list(runbuf)}
        runbuf.clear()
        out = para_blocks(syn, art)
        if out:
            st["started"] = True
        blocks.extend(out)

    i = 0
    while i < len(kids):
        k = kids[i]
        if isinstance(k, str):
            runbuf.append(k)
            i += 1
            continue
        t, c = k["tag"], cls(k)
        if id(k) in st["consumed"]:        # сноски собраны отдельно
            flush_run()
            emit_refs_for(k)  # группы (§4.1): [refs] на месте первого айтема
            i += 1
            continue
        if t in INLINE_TAGS and not (c & {"track"}) and t != "img":
            # голый inline-лейбл «ЭПИГРАФ» на блочном уровне (35Q: <strong>Эпиграф
            # </strong> + blockquote в li) → epi-роль следующему блоку (вердикт 9)
            if t in ("strong", "b") and not any(
                    (isinstance(x, str) and x.strip()) or isinstance(x, dict)
                    for x in runbuf):
                lbl = re.sub(r"\s+", " ", raw_text(k)).strip().rstrip(":").lower()
                if lbl in ("эпиграф", "эпиграфы"):
                    st["epi_pending"] = True
                    flag(art, "inline-лейбл ЭПИГРАФ → [epi]-роль")
                    i += 1
                    continue
            # висячий номер-метка СНАРУЖИ абзаца (16J: <span class="num-h">1.</span>
            # + <p>тезис</p>) → нумерованный абзац [num] (решение оператора 14:55)
            if t == "span" and (c & {"num-h", "numh", "num-head", "para-num"}) and not any(
                    isinstance(x, str) and x.strip() or isinstance(x, dict) for x in runbuf):
                mnum = re.fullmatch(r"(\d+)\s*([.)])?", raw_text(k).strip())
                if mnum:
                    j = i + 1
                    while j < len(kids) and isinstance(kids[j], str) and not kids[j].strip():
                        j += 1
                    if j < len(kids) and isinstance(kids[j], dict) and kids[j]["tag"] == "p":
                        out = para_blocks(kids[j], art)
                        if out and not out[0].startswith("["):
                            # kind=toc конвертер НЕ ставит (15:08: опция ручная,
                            # деф. ВЫКЛ) — включается правкой тега в источнике
                            blocks.append("[num]\n%s%s %s\n[/num]"
                                          % (mnum.group(1), mnum.group(2) or ".", out[0]))
                            blocks.extend(out[1:])
                            st["started"] = True
                            flag(art, "висячий номер-метка span.num-h → [num]")
                            i = j + 1
                            continue
            runbuf.append(k)
            i += 1
            continue
        flush_run()
        # ---- [toc]-маркер (вердикт 11): авторское место TOC, ДО хром-скипа ----
        if t in ("details", "nav", "div", "ol", "ul", "aside", "section") \
                and (any("toc" in cc for cc in c) or k["attrs"].get("id") == "toc"):
            if not st["toc_done"]:
                st["toc_done"] = True
                collapsed = (t == "details" and "open" not in k["attrs"])
                blocks.append("[toc collapsed]" if collapsed else "[toc]")
            i += 1
            continue
        # ---- хром ----
        if t in CHROME_TAGS or (c & CHROME_CLS):
            i += 1
            continue
        if t == "img":
            if st["started"]:
                flag(art, "изображение в теле статьи — вне формата (потеряно, нужен разбор)")
            i += 1
            continue
        if "kicker" in c and not st["started"]:
            # шапочный киккер — [sub] (вердикт 11); киккер-ДАТА («25 февраля
            # 2021 г.», 4 ст.) — дата-строка → [line kind=dateline] на месте
            # (решение 13:59: дата-строки в теле, дубль с byline — норма)
            sub = re.sub(r"\s+", " ", inline(k, art).strip())
            if sub and len(sub) < 40 and _DATEISH_RX.search(sub):
                blocks.append("[line kind=dateline]%s[/line]" % sub)
                st["started"] = True
                flag(art, "kicker-дата → [line kind=dateline]")
            elif sub and sub.lower() in st.get("sec_names", set()):
                # вердикт 21:22: киккер = точный дубль названия раздела из
                # крошек («Конфронтология Духа»…) — мусор адаптатора, снять
                flag(art, "kicker-дубль раздела снят («%s»)" % sub[:30])
            elif sub:
                blocks.append("[sub]%s[/sub]" % sub)
                flag(art, "kicker (надзаголовок) → [sub]")
            i += 1
            continue
        if c & {"dateline", "secmeta"}:
            # вердикт 8 + решение 13:59: ВСЕ дата-строки (вкл. диапазон 163A) —
            # [line kind=dateline] на своём месте; byline всегда manifest-дата
            dt = re.sub(r"\s+", " ", inline(k, art).strip())
            if dt:
                blocks.append("[line kind=dateline]%s[/line]" % dt)
                st["started"] = True
            i += 1
            continue
        if "date" in c and t in ("p", "div"):
            # .date-строка ГДЕ УГОДНО (шапка 16 ст. / даты стихов сборника 184A)
            # — дата-строка → [line kind=dateline] на месте (решение 13:59)
            dt = re.sub(r"\s+", " ", inline(k, art).strip())
            if dt:
                blocks.append("[line kind=dateline]%s[/line]" % dt)
                st["started"] = True
                flag(art, ".date → [line kind=dateline]")
            i += 1
            continue
        if "tags" in c and t in ("p", "div"):
            txt = re.sub(r"\s+", " ", inline(k, art).strip())
            if txt:
                blocks.append("[line kind=tags]%s[/line]" % txt)
                st["started"] = True
            i += 1
            continue
        if c & {"seealso", "see-also"} and t in ("p", "div"):
            # div-контейнер с НЕСКОЛЬКИМИ <p> (42DA/34O/1CI/215A/12PB): раньше
            # inline(div) склеивал всё в одну строку-простыню. Структура разнородна:
            # маркер («См. также:»/«А также:») и контент бывают в РАЗНЫХ <p> (12PB:
            # пустой маркер-p + link-p; 215A: висячий пустой «См. также:»; 1CI:
            # label-p «Полный слайд…» + link-p). ГРУППИРОВКА: <p> с label/marker-
            # классом ИЛИ начинающийся «также»-маркером НАЧИНАЕТ строку; контент-<p>
            # (голая ссылка/текст) ПРИЛИПАЮТ к текущей; пустые/висячие — отбрасываются.
            seealso_p = ([x for x in k["kids"] if isinstance(x, dict)
                          and x["tag"] == "p" and "tag" not in cls(x)] if t == "div" else [])
            if len(seealso_p) >= 2:
                MARK_RX = re.compile(r"(?i)^\s*(см\.?\s*также|а\s+также|и\s+(?:ещё|еще)|ещё|еще)\b")
                SEEALSO_LBL = {"label", "marker", "lbl", "seealso-label"}
                rows = []  # [{label: bool, parts: [str]}]
                for r in seealso_p:
                    txt = re.sub(r"\s+", " ", inline(r, art).strip())
                    is_lbl = (bool(cls(r) & SEEALSO_LBL)
                              or first(r, lambda x: bool(cls(x) & SEEALSO_LBL)) is not None
                              or bool(MARK_RX.match(txt)))
                    if is_lbl or not rows:
                        rows.append({"label": is_lbl, "parts": [txt] if txt else []})
                    elif txt:
                        rows[-1]["parts"].append(txt)
                n = 0
                for g in rows:
                    line = " ".join(g["parts"]).strip()
                    if not MARK_RX.sub("", line).strip(" :"):
                        continue  # висячий маркер без содержимого (215A) / пустой <p>
                    if not g["label"] and not MARK_RX.match(line):
                        line = "См. также: " + line
                    blocks.append(line)
                    n += 1
                if n:
                    st["started"] = True
                    flag(art, "блок «См. также» (div, %d <p> → %d строк)" % (len(seealso_p), n))
                else:
                    flag(art, "пустой «См. также:» опущен")
                i += 1
                continue
            # «См. также» — блок со смыслом примечаний (оператор 15:31, 158):
            # тело (+ соседние p.tag-хэштеги) → видимая строка «См. также: …»
            # на авторском месте; пустой шаблон-огрызок опускается
            body = re.sub(r"\s+", " ", inline(k, art).strip())
            body = re.sub(r"(?i)^см\.?с?\.?\s*также\s*:?\s*", "", body).strip()  # +опечатка «Смс.» (179)
            j = i + 1
            while j < len(kids):
                k2 = kids[j]
                if isinstance(k2, str):
                    if k2.strip():
                        break
                    j += 1
                    continue
                if k2["tag"] == "p" and "tag" in cls(k2):
                    tg = re.sub(r"\s+", " ", inline(k2, art).strip())
                    if tg:
                        body = (body + " " + tg).strip()
                    j += 1
                    continue
                break
            if body:
                # вердикт 21:12 (59C): см.-также остаётся НА АВТОРСКОМ МЕСТЕ
                # видимой строкой (анон-сноска утаскивала вниз в Примечания)
                blocks.append("См. также: %s" % body)
                st["started"] = True
                flag(art, "блок «См. также» → строка на месте")
            else:
                flag(art, "пустой «См. также:» опущен")
            i = j
            continue
        if "tag" in c and t == "p":
            # одиночный p.tag (хэштег) без seealso — служебная тег-строка
            txt = re.sub(r"\s+", " ", inline(k, art).strip())
            if txt:
                blocks.append("[line kind=tags]%s[/line]" % txt)
                st["started"] = True
            i += 1
            continue
        if c & {"closing", "banner", "shout", "call", "center-call", "resume", "crow"} and t in ("p", "div"):
            # вердикт 8: роль-строки .closing/.banner → [cry]; + .shout/.call/
            # .center-call (вердикт 20:53: в оригинале выделены — 16J/11T/12FA/
            # 17DB/21L/2B6… 13 ст.; span-носители внутри абзацев НЕ трогаем);
            # + .resume (35Q «Резюме: ВО ВСЕЙ ВСЕЛЕННОЙ…» — плашка, вердикт 21:41)
            lines = [l for l in _mark_lines(k, art) if l]
            if lines:
                blocks.append("[cry]\n" + "\n".join(lines) + "\n[/cry]")
                st["started"] = True
            i += 1
            continue
        if (c & SIGN_CLS) and t in ("p", "div"):
            # авторская подпись/сайн-офф → [sig]; чистая дата → [line kind=dateline];
            # форум-лейбл «Подпись пользователя» снят (§12). Инлайн span.sign (24F)
            # сюда НЕ попадает — там класс на span внутри <p>, не на самом блоке.
            body = "\n".join(l for l in _mark_lines(_strip_sig_label(k), art) if l).strip()
            if not body:
                flag(art, "пустая подпись (.%s) опущена" % "/".join(sorted(c & SIGN_CLS)))
            elif _is_dateline_only(body):
                blocks.append("[line kind=dateline]%s[/line]" % body)
                st["started"] = True
                flag(art, "подпись-дата → [line kind=dateline]")
            else:
                blocks.append("[sig]\n%s\n[/sig]" % body)
                st["started"] = True
            i += 1
            continue
        if "dedication" in c and t in ("p", "div", "blockquote"):
            b = emit_epi(k, art, kind="dedi")  # вердикт 8: посвящение
            if b:
                blocks.append(b)
                st["started"] = True
            i += 1
            continue
        if "coda" in c and t in ("p", "div", "blockquote"):
            b = emit_epi(k, art)  # вердикт 8: кода = хвостовое обрамление [epi]
            if b:
                blocks.append(b)
                st["started"] = True
            i += 1
            continue
        # ---- роли ----
        if st.get("epi_pending") and (t == "blockquote" or t in ("p", "div")):
            # вердикт 9: за снятым лейблом «ЭПИГРАФ» контент уходит в [epi]-роль
            st["epi_pending"] = False
            b = emit_epi(k, art)
            if b:
                blocks.append(b)
                st["started"] = True
                flag(art, "лейбл ЭПИГРАФ → [epi] (постатейная проверка)")
                i += 1
                continue
        if is_epi(k):
            _toc_heading(k, blocks, art, st)
            b = emit_epi(k, art)
            if b:
                blocks.append(b)
                st["started"] = True
            i += 1
            continue
        if t in ("h2", "h3", "h4"):
            if c & {"poemsub", "poem-sub", "poemtitle", "poem-title"}:
                # вердикт 4: poemsub (239 «Dream On…») — НЕ заголовок → [subsec]
                b = emit_subsec(k, art)
                if b:
                    blocks.append(b)
                    flag(art, "poemsub → [subsec] (не заголовок)")
                i += 1
                continue
            htext = re.sub(r"\s+", " ", inline(k, art).strip())
            low = re.sub(r"\[\^[^\]]*\]", "", htext).strip().lower()
            hid = k["attrs"].get("id", "")
            if hid in ("epigraph", "epigraf", "s-epi", "epi") or low in ("эпиграф", "эпиграфы"):
                if re.search(r"\[\^", htext):
                    # маркер сноски НА лейбле (16J/1CI/571 — источник эпиграфа):
                    # снять нельзя, сноска осиротеет → оставляем ## (спорное)
                    flag(art, "лейбл ЭПИГРАФ несёт маркер сноски — оставлен заголовком (спорное, оператору)")
                else:
                    # вердикт 19:21 2026-06-12: эпиграф-заголовок, бывший пунктом
                    # оригинального TOC, остаётся настоящим ## (TOC ведёт на него);
                    # содержимое следом всё равно уходит в [epi]-роль
                    anchor = hid if hid in st.get("toc_items", {}) else (
                        node["attrs"].get("id")
                        if node["attrs"].get("id") in st.get("toc_items", {}) else None)
                    if anchor:
                        blocks.append("## %s {%s}" % (htext, anchor))
                        st["started"] = True
                        flag(art, "TOC-пункт «%s» → ## перед [epi]" % htext[:30])
                    # вердикт 9: лейбл снимается, СОДЕРЖИМОЕ следом → [epi]-роль
                    st["epi_pending"] = True
                    i += 1
                    continue
            if htext:
                # слаг: id самого h2 → id родителя-СЕКЦИИ (sec-див с единственным
                # h2, 237) → <a name>. Родителя-контейнера с многими h2 не брать.
                slug = k["attrs"].get("id")
                if not slug and node["attrs"].get("id") and 1 == sum(
                        1 for x in node["kids"]
                        if isinstance(x, dict) and x["tag"] in ("h2", "h3", "h4")):
                    slug = node["attrs"].get("id")
                if not slug:
                    a = first(k, lambda x: x["tag"] == "a" and x["attrs"].get("name"))
                    slug = a["attrs"].get("name") if a else None
                # вердикт 4: h2 → ##; h3 И h4 → ### (один вложенный уровень)
                hh = "##" if t == "h2" else "###"
                blocks.append("%s %s%s" % (hh, htext, " {%s}" % slug if slug else ""))
                st["started"] = True
                if t == "h4":
                    flag(art, "h4 «%s» → ### (брат h3 — проверить структуру)" % htext[:40])
            i += 1
            continue
        if is_music_container(k):
            # заголовок ВНУТРИ муз-секции (28MA: section.music-summary > h2
            # «Песнь Ступеней») — эмитить ## ПЕРЕД [mus], не терять (вердикт A5б)
            hd = first(k, lambda x: x["tag"] in ("h2", "h3"))
            if hd is None and k["attrs"].get("id") in st.get("toc_items", {}):
                # «идём за оригиналом» (15:31): муз-блок был ПУНКТОМ TOC без
                # заголовка (158/17QA) → настоящий ## из текста TOC-пункта;
                # render скроет дубль-этикетку карточки (has-heading)
                ttxt = st["toc_items"][k["attrs"]["id"]]
                blocks.append("## %s {%s}" % (ttxt, k["attrs"]["id"]))
                st["started"] = True
                flag(art, "TOC-пункт «%s» → ## перед [mus]" % ttxt[:30])
            if hd is not None:
                htext = re.sub(r"\s+", " ", inline(hd, art).strip())
                slug = hd["attrs"].get("id") or k["attrs"].get("id")
                if htext:
                    blocks.append("%s %s%s" % ("##" if hd["tag"] == "h2" else "###",
                                               htext, " {%s}" % slug if slug else ""))
                    st["started"] = True
            b = emit_music(collect_music(k), art)   # порядок + inter-заметки (Б2) + .num (Б1)
            if b:
                blocks.append(b)
                st["started"] = True
                _label_marker_to_heading(blocks, art)
            i += 1
            continue
        if is_track(k) or (c & LABEL_CLS):
            run = []
            while i < len(kids):  # пробельные текст-ноды между плитками не рвут ран
                k2 = kids[i]
                if isinstance(k2, str):
                    if k2.strip():
                        break
                    i += 1
                    continue
                if is_track(k2) or (cls(k2) & LABEL_CLS) or _is_inter_note(k2):
                    run.append(k2)
                    i += 1
                else:
                    break
            b = emit_music(run, art)
            if b:
                blocks.append(b)
                st["started"] = True
                _label_marker_to_heading(blocks, art)
            continue
        if c & {"sec-sub", "deck", "standfirst"}:
            # .sec-sub (поясн. под ##) + дескриптивные деки под H1 (.deck — italic;
            # .standfirst — muted; СВОЯ CSS отлична от .subtitle) → [subsec]
            # «концептуально под общим заголовком» (§1.3). NB: .lede НЕ сюда —
            # в корпусе это смесь (метадата-блок 462, контент-реплика 35J).
            b = emit_subsec(k, art)
            if b:
                blocks.append(b)
                if c & {"deck", "standfirst"}:
                    flag(art, "дек/стэндфёрст (.%s) → [subsec]"
                         % "/".join(sorted(c & {"deck", "standfirst"})))
            i += 1
            continue
        if "subtitle" in c and t in ("div", "p", "h2", "h3") \
                and blocks and re.match(r"^#{2,3} ", blocks[-1]):
            # subtitle СРАЗУ ПОД ##/###-заголовком = подзаголовок секции (158: под
            # «ВМЕСТО ВСТУПЛЕНИЯ») → [subsec], а НЕ шапочный [sub]. Признак —
            # предыдущий блок есть заголовок (st["started"] ненадёжен: киккер/
            # дата-строка в шапке тоже его взводят, ложно утягивая шапочный subtitle)
            b = emit_subsec(k, art)
            if b:
                blocks.append(b)
                flag(art, "subtitle в теле (под ##) → [subsec]")
            i += 1
            continue
        if ("subtitle" in c or ("sub" in c and not st["started"])) \
                and t in ("div", "p", "h2", "h3"):
            # класс subtitle ИЛИ шапочный div.sub (35Q «Коллекция Целемов · …»,
            # вердикт 21:41) → жанровая пометка [sub]
            sub = re.sub(r"\s+", " ", inline(k, art).strip())
            if sub and sub.lower() in st.get("sec_names", set()):
                # [sub] = точный дубль названия раздела из крошек (1CM «Роза Среди
                # Шипов») — мусор адаптатора, снять (как киккер-дубль, вердикт 21:22)
                flag(art, "[sub]-дубль раздела снят («%s»)" % sub[:30])
            elif sub:
                blocks.append("[sub]%s[/sub]" % sub)
            i += 1
            continue
        if c & {"verse", "poem"} or t == "pre":
            # сборник стихов (184A): section.poem ДЕРЖИТ h2-заголовки/даты
            # стихов — цельный emit их плющил; спуск обрабатывает по ролям
            if t != "pre" and first(k, lambda x: x["tag"] in ("h2", "h3", "h4")):
                walk(k, blocks, art, st)
                i += 1
                continue
            vb = emit_verse_blocks(k, art)
            if vb:
                blocks.extend(vb)
                st["started"] = True
            i += 1
            continue
        if c & {"stanza", "st"}:
            run = []
            while i < len(kids):  # пробельные текст-ноды между строфами не рвут ран (182)
                k2 = kids[i]
                if isinstance(k2, str):
                    if k2.strip():
                        break
                    i += 1
                    continue
                if cls(k2) & {"stanza", "st"}:
                    run.append(k2)
                    i += 1
                else:
                    break
            b = emit_stanzas(run, art)
            if b:
                blocks.append(b)
                st["started"] = True
            continue
        if c & {"qlabel", "q-label", "quote-label"} and t in ("div", "p"):
            # label-строка «Цитата» СНАРУЖИ цитаты (35Q ol.celems) — снимается
            flag(art, "label-строка «Цитата» (отдельным узлом) снята")
            i += 1
            continue
        if t == "blockquote" or (t in ("div", "p") and any(
                "quote" in cc and "label" not in cc for cc in c)):
            # blockquote ИЛИ div.quote/longquote (12F/35Q) → [quote]
            b = emit_quote(k, art)
            if b:
                blocks.append(b)
                st["started"] = True
            i += 1
            continue
        if t == "ol":
            # consumed-айтемы внутри ol walk'ом не посещаются — [refs] ставим здесь
            for li in [x for x in k["kids"] if isinstance(x, dict) and id(x) in st["consumed"]]:
                emit_refs_for(li)
            lis = [x for x in k["kids"] if isinstance(x, dict) and x["tag"] == "li"
                   and id(x) not in st["consumed"]]
            try:
                ol_start = int(str(k["attrs"].get("start", "1")).strip())
            except ValueError:
                ol_start = 1
            # «богатый» li (35Q: лейблы+blockquote/longquote, треки-details) → ОДИН
            # [num] со СКВОЗНОЙ нумерацией (honor start=), богатые пункты =
            # ВЛОЖЕННЫЕ блоки под своим номером ([epi]/[quote]/[mus]). Вердикт
            # оператора 2026-06-13: «[mus]/[epi] внутри [num]», 1:1 с оригиналом
            # (заменил развёртку-наверх 21:35/21:41, рвавшую нумерацию и плодившую
            # дефолт-плашки на встроенных плеерах). render: renderNum рисует номер
            # в жёлобе, вложенный блок — телом пункта, у [mus] плашка гасится.
            if any(first(li, _rich_li) for li in lis):
                flag(art, "ol с блочными пунктами → [num] с вложенными блоками (нумерация сквозная)")
                items = []
                for idx, li in enumerate(lis):
                    num = ol_start + idx
                    if first(li, _rich_li):
                        sub = []
                        walk(li, sub, art, st)
                        inner = "\n\n".join(s for s in sub
                                            if isinstance(s, str) and s.strip())
                        items.append("%d. %s" % (num, inner) if inner else "%d." % num)
                    else:
                        txt = "\n".join(l for l in _mark_lines(li, art) if l).strip()
                        items.append("%d. %s" % (num, txt) if txt else "%d." % num)
                if items:
                    blocks.append("[num]\n" + "\n".join(items) + "\n[/num]")
                    st["started"] = True
                i += 1
                continue
            items = []
            for li in lis:
                # инвариант 14:25: переносы внутри пункта сохраняются (\n → <br>)
                txt = "\n".join(l for l in _mark_lines(li, art) if l).strip()
                if txt:
                    items.append(txt)
            if items:
                blocks.append("[num]\n" + "\n\n".join(items) + "\n[/num]")
                st["started"] = True
            i += 1
            continue
        if t == "ul":
            # вердикт 12: ul → блок [ul], пункты строками «- »
            for li in [x for x in k["kids"] if isinstance(x, dict) and id(x) in st["consumed"]]:
                emit_refs_for(li)
            uls = [x for x in k["kids"] if isinstance(x, dict) and x["tag"] == "li"
                   and id(x) not in st["consumed"]]
            if any(first(li, _rich_li) for li in uls):
                flag(art, "ul с блочными пунктами — богатые развёрнуты, плоские раны остались [ul]")
                plain = []
                for li in uls:
                    if first(li, _rich_li):
                        if plain:
                            blocks.append("[ul]\n" + "\n".join(plain) + "\n[/ul]")
                            plain = []
                        walk(li, blocks, art, st)
                    else:
                        lns = [l for l in _mark_lines(li, art) if l]
                        if lns:
                            plain.append("- " + "\n".join(lns))
                if plain:
                    blocks.append("[ul]\n" + "\n".join(plain) + "\n[/ul]")
                st["started"] = True
                i += 1
                continue
            items = []
            for li in [x for x in k["kids"] if isinstance(x, dict) and x["tag"] == "li"
                       and id(x) not in st["consumed"]]:
                # инвариант 14:25: внутренние переносы пункта — continuation-строки
                lns = [l for l in _mark_lines(li, art) if l]
                if lns:
                    items.append("- " + "\n".join(lns))
            if items:
                blocks.append("[ul]\n" + "\n".join(items) + "\n[/ul]")
                st["started"] = True
            i += 1
            continue
        if t == "dl":
            # T-A: словарь dt/dd (roza_mira «Глоссарий» 40, 071 «Словарь» 8) →
            # [ul] строками «- {term|Термин} — определение» (без нового тега).
            items = []
            term = None
            for row in find(k, lambda x: x["tag"] in ("dt", "dd")):
                txt = re.sub(r"\s+", " ", inline(row, art, "space")).strip()
                if not txt:
                    continue
                if row["tag"] == "dt":
                    if term is not None:  # dt без dd — отдельная строка-термин
                        items.append(("- {term|%s}" if _TERM_SAFE_RX.match(term)
                                      else "- %s") % term)
                    term = txt
                elif term is not None:
                    items.append((("- {term|%s} — %s" if _TERM_SAFE_RX.match(term)
                                   else "- %s — %s")) % (term, txt))
                    term = None
                else:
                    items.append("- %s" % txt)
            if term is not None:  # висячий последний dt
                items.append(("- {term|%s}" if _TERM_SAFE_RX.match(term)
                              else "- %s") % term)
            if items:
                blocks.append("[ul]\n" + "\n".join(items) + "\n[/ul]")
                st["started"] = True
                flag(art, "dl-словарь (%d) → [ul] с {term|} (T-A)" % len(items))
            i += 1
            continue
        if t == "table":
            for row in find(k, lambda x: x["tag"] == "tr"):
                txt = re.sub(r"\s+", " ", inline(row, art, "space")).strip()
                if txt:
                    blocks.append(txt)
            flag(art, "table — вне формата, строки выгружены прозой (нужен ручной/LLM разбор)")
            i += 1
            continue
        if t == "p" and _hangnum(k) is not None:
            # вердикт 7: ран соседних <p> с висячим span.n/.num → [num] с
            # АВТОРСКИМИ номерами и скобко-стилем («1.»/«1)»)
            items = []
            while i < len(kids):
                k2 = kids[i]
                if isinstance(k2, str):
                    if k2.strip():
                        break
                    i += 1
                    continue
                hn = _hangnum(k2)
                if hn is None:
                    break
                sh = _shallow(k2)
                prune(sh, lambda x: x["tag"] == "span" and bool(cls(x) & {"n", "num", "pnum"}))
                # инвариант 14:25: переносы внутри пункта сохраняются
                txt = "\n".join(l for l in _mark_lines(sh, art) if l).strip()
                if txt:
                    items.append("%d%s %s" % (hn[0], hn[1], txt))
                i += 1
            if items:
                blocks.append("[num]\n" + "\n\n".join(items) + "\n[/num]")
                st["started"] = True
                flag(art, "висячая нумерация span.n/.num → [num] (%d п.)" % len(items))
            continue
        # №2 форум-тред: standalone-блок метка-спикер (.speaker/.who/.poster/
        # .answer-head/… — классы разнятся по статьям) + тело-сиблинги → [dlg] с
        # метками «>> ». Срабатывает ТОЛЬКО на короткой ':'-метке, у которой есть
        # тело. Исключения (индивидуально, по оракулу): 55K — пьеса (стих-монолог,
        # форум-рамка стиху не идёт → [poem]); 32K — оригинал в инлайн-стиле (метки
        # акцентом в строку, без боксов), часть реплик inline-в-прозе → бокс одной
        # реплики среди инлайна рассогласовал бы вид; оставляем как в оригинале.
        if art not in ("55K", "32K") and _is_speaker_label(k):
            blk, j = _emit_forum_thread(kids, i, art, st)
            if blk is not None:
                blocks.append(blk)
                st["started"] = True
                flag(art, "форум-тред standalone-header → [dlg]")
                i = j
                continue
        if c & DIALOG_CLS:
            # вердикт 21:27 2026-06-12 (сменил «прозой-тире»): опознанный диалог
            # ПОМЕЧАЕТСЯ — ран соседних диалог-узлов (p.speaker×N, section.question/
            # answer, div.dialog…) → один [dlg]; внутри только абзацы, иначе фолбэк
            run = [k]
            i += 1
            while i < len(kids):
                k2 = kids[i]
                if isinstance(k2, str):
                    if k2.strip():
                        break
                    i += 1
                    continue
                if cls(k2) & DIALOG_CLS:
                    run.append(k2)
                    i += 1
                    continue
                break
            tmp = []
            for k2 in run:
                if k2["tag"] == "p":
                    tmp.extend(para_blocks(k2, art))
                else:
                    walk(k2, tmp, art, st)
            plain = all(not b2.lstrip().startswith(("[", "#")) for b2 in tmp)
            if tmp and plain:
                blocks.append("[dlg]\n" + "\n\n".join(tmp) + "\n[/dlg]")
                st["started"] = True
                flag(art, "диалоговая разметка → [dlg] (%d узлов)" % len(run))
            elif tmp:
                blocks.extend(tmp)
                st["started"] = True
                flag(art, "диалог с НЕ-абзацными блоками внутри — оставлен прозой (фолбэк)")
            continue
        if t == "p":
            # вердикт A5в: label-строка «Музыка под настроение» перед карточкой —
            # дубль лейбла [mus] (и ловит буквицу) → съедается
            ptxt = re.sub(r"\s+", " ", raw_text(k)).strip().rstrip(":").lower()
            if ptxt == "музыка под настроение":
                flag(art, "label-строка «Музыка под настроение» перед [mus] снята")
                i += 1
                continue
            out = para_blocks(k, art)
            if out:
                st["started"] = True
            blocks.extend(out)
            i += 1
            continue
        # значимый голый текст прямо в контейнере → лист-абзац (аудит: 1277 узлов)
        direct = "".join(x for x in k["kids"] if isinstance(x, str))
        has_block_kids = any(isinstance(x, dict) and x["tag"] not in INLINE_TAGS
                             for x in k["kids"])
        if re.sub(r"\s+", "", direct) and not has_block_kids:
            out = para_blocks(k, art)
            if out:
                st["started"] = True
            blocks.extend(out)
            i += 1
            continue
        # неопознанная обёртка → спуск (НИЧЕГО не выбрасываем молча)
        _toc_heading(k, blocks, art, st)
        walk(k, blocks, art, st)
        i += 1
    flush_run()


# ── оракул покрытия ──────────────────────────────────────────────────────────
# "dateline"/"date" больше НЕ хром: ВСЕ дата-строки переносятся в тело
# ([line kind=dateline], решение 13:59) и считаются с обеих сторон оракула.
ORACLE_CHROME = CHROME_CLS | {"pop", "fn-pop", "fnpop",
                              "prev", "next"}


def visible_text(root):
    def deep(n):
        out = []
        for k in n["kids"]:
            if isinstance(k, str):
                out.append(k)
                continue
            if k["tag"] == "header":
                # header — хром, КРОМЕ спасённых описат. подзаголовков (они теперь
                # в теле как [sub]/[subsec]/[line] → должны считаться и в ov)
                out.append(" " + lead_subtitle_text(k) + " ")
                continue
            if k["tag"] in ("nav", "footer", "h1"):
                continue
            if cls(k) & ORACLE_CHROME:
                continue
            out.append(deep(k))
        return "".join(out)
    return deep(root)


_BLOCK_TAG_RX = re.compile(r"^\[/?(mus|poem|epi|quote|num|sub|subsec|spl|sig|cry|shir|ul|line|refs|toc)\b[^\]]*\]\s*$")


def zml_visible_text(zml):
    out = []
    mfm = re.match(r"^---(.*?)---\s*", zml, flags=re.S)
    body = zml[mfm.end():] if mfm else zml
    if mfm:  # notes_title из FM рисуется render'ом — видимый текст
        mt = re.search(r"^notes_title:\s*(.+)$", mfm.group(1), re.M)
        if mt:
            out.append(mt.group(1))
    for ln in body.split("\n"):
        s = ln.strip()
        if _BLOCK_TAG_RX.match(s):
            # текст в атрибутах блока (cite=/label) — тоже видимый контент
            out.append(" ".join(re.findall(r'="([^"]*)"', s)))
            if re.match(r"^\[mus\]\s*$", s):
                out.append("Музыка под настроение")  # дефолт-лейбл render'а
            continue
        if s.startswith("## "):
            out.append(s[3:])
            continue
        if s.startswith("### "):
            out.append(s[4:])
            continue
        # трек-строка [url|title|author] — поля могут нести маркеры [^N]
        if s.startswith("[") and s.endswith("]") and "|" in s and not s.startswith("[^"):
            parts = s[1:-1].split("|")
            if len(parts) >= 2:
                out.append(re.sub(r"\[\^[^\]]*\]", "", " ".join(parts[1:])))
                continue
        s = re.sub(r"\[/?(?:mus|poem|epi|quote|num|sub|subsec|spl|sig|cry|shir|ul|line)\b[^\]]*\]",
                   " ", s)  # однострочная форма [sub]…[/sub] / [line kind=…]…[/line]
        if s.startswith("[^]:"):
            out.append("См. также")  # дефолт-префикс анон-сноски рисует render
        s = re.sub(r"\[\^[^\]]*\]:?", "", s)  # маркеры/определения, вкл. группы [^s1.3]
        s = re.sub(r"\[\^?\d*\]:?", "", s)
        s = re.sub(r"\[[^\]|]*\|([^\]]*)\]", r"\1", s)
        # [[ID]] render резолвит в заголовок статьи — он видим в оригинале
        s = re.sub(r"\[\[([^\]]*)\]\]",
                   lambda m: MANIFEST.get(m.group(1), {}).get("title", ""), s)
        s = re.sub(r"\{(?:term|leit)\|([^}\n]+)\}", r"\1", s)  # {term|X}/{leit|X} — X видим
        s = re.sub(r"\{[^}]*\}", "", s)  # {ch|N} зохар → ссылка (анкор резолвит render)
        out.append(s)
    return " ".join(out)


def coverage(root, zml):
    ov = len(re.sub(r"\s+", "", visible_text(root)))
    zv = len(re.sub(r"\s+", "", zml_visible_text(zml)))
    return round(zv / ov, 3) if ov else None


# ── main ─────────────────────────────────────────────────────────────────────
def convert(art):
    html = (ART / f"{art}.html").read_text("utf-8")
    meta = {}
    mm = re.search(r'id="yanik-meta"[^>]*>\s*(\{.*?\})\s*</script>', html, re.S)
    if mm:
        try:
            meta = json.loads(mm.group(1))
        except Exception:
            pass
    body_html = re.search(r"<body[^>]*>(.*)</body>", html, re.S).group(1)
    body_html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", body_html, flags=re.S)
    t = Tree()
    t.feed(body_html)
    root = t.root

    rec = MANIFEST.get(art, {})
    # scheme/theme/width бывшего пер-артикульного дефолта УДАЛЕНЫ (Ф8′ 2026-06-18):
    # умолчания темы/ширины обнулены, дефолты живут в центральном конфиге
    # (раздел/тип → дизайн+ширина). См. вывод `type:` и эмит frontmatter ниже.

    # title — ZML3 B8: in-article H1 takes PRIORITY over the manifest title.
    # Вердикт 2 (fn-ревью): маркеры [^N] в H1 СОХРАНЯЮТСЯ в title: (позиция
    # значима; render рисует sup в H1, чистит в <title>/крошках). NB: inline()
    # резолвит маркеры ПОСЛЕ collect_footnotes (FN_ID_MAP) — h1txt берём ниже.
    h1 = first(root, lambda x: x["tag"] == "h1")

    # audio narration 🎧 → frontmatter audio:[{url,label}]. Озвучка — это ЯВНЫЙ
    # признак: класс audio-link / «ауди»-подпись / t.me-ссылка в шапке (h1 или
    # рядом с лейблом «Аудиоверсия»). Голая t.me-ссылка в ТЕЛЕ — контент (42DA),
    # остаётся обычной ссылкой.
    audio = []
    seen_audio = set()
    h1_ids = {id(x) for x in find(h1, lambda y: True)} if h1 else set()
    # ссылки внутри явных аудио-контейнеров (p.audio > span.label «Аудиоверсия:» — 29M)
    # «audiopost» (42DA) — НЕ аудио-контейнер: yanik-meta прямо говорит «телеграм-
    # аудиопост — не плеер, а плоская ссылка»; класс содержит подстроку «audio», а
    # текст начинается «Аудио…», поэтому исключаем его явно (и по классу, и по тексту),
    # иначе t.me-ссылка тела уезжает в FM audio: и «Аудиопост —» повисает с тире.
    for box in find(root, lambda x: any("audio" in cc and cc != "audiopost" for cc in cls(x))
                    or (re.match(r"(?i)\s*(аудио|озвучк)", raw_text(x) or "")
                        and not re.match(r"(?i)\s*аудиопост", raw_text(x) or "")
                        and len(raw_text(x)) < 120)):
        h1_ids |= {id(x) for x in find(box, lambda y: True)}
    AUDIO_HREFS.clear()
    for a in find(root, lambda x: x["tag"] == "a" and (x["attrs"].get("href") or "")):
        href = (a["attrs"].get("href") or "").strip()
        c = cls(a)
        label = (a["attrs"].get("title") or a["attrs"].get("aria-label") or "").strip()
        is_audio = ("audio-link" in c
                    or ("t.me/" in href and (
                        re.search(r"(?i)ауди|озвуч", label)
                        or id(a) in h1_ids
                        or "audio" in " ".join(c))))
        if not is_audio or not href or href in seen_audio:
            continue
        seen_audio.add(href)
        AUDIO_HREFS.add(href)
        audio.append({"url": href, "label": label})

    # сноски — ДО walk (walk скипает consumed-узлы; FN_ID_MAP — до резолва ссылок)
    FN_ID_MAP.clear()
    # трек-плеер как цель сноски — ДО collect_footnotes: чтобы (1) маркеры внутри
    # ТЕЛ сносок резолвились (collect сериализует тела), (2) collect мог ПЕРЕЗАПИСАТЬ
    # общий id, если трек на самом деле обычная сноска (id fn-N + is_track).
    register_music_footnotes(root, art)
    fns, groups, consumed, first_cont = collect_footnotes(root, art)

    # title — теперь, когда FN_ID_MAP заполнена (маркеры в H1 резолвятся верно)
    h1txt = re.sub(r"\s+", " ", inline(h1, art).strip()).replace("🎧", "").strip() if h1 else ""
    h1txt = re.sub(r"\[\^\]", "", h1txt).strip()  # пустые (неразрешённые) маркеры
    title = h1txt or rec.get("title") or art
    if re.search(r"\[\^[^\]]+\]", title):
        flag(art, "маркер сноски в title: сохранён (вердикт 2)")

    # обложка (вердикт A1): ТОЛЬКО реальный <img src> оригинала; нет — нет поля
    img_el = first(root, lambda x: x["tag"] == "img" and (x["attrs"].get("src") or "").strip())
    image = ""
    if img_el:
        msrc = re.search(r"([^/\\?#]+)(?:[?#].*)?$", img_el["attrs"]["src"].strip())
        image = msrc.group(1) if msrc else ""
    if not fns:
        # схема 1CB: notes-секции НЕТ, определения живут ВНУТРИ inline-попапов
        # span.fnref («1Целем (ивр.) - …») — маркер inline() извлекает, тело
        # иначе пропадало бы. Цифра + содержательное тело → [^N]-определение.
        seen_n = set()
        for sp in find(root, lambda x: x["tag"] in ("span", "sup")
                       and bool(cls(x) & FNREF_A_CLS)):
            txt = re.sub(r"\s+", " ", raw_text(sp)).strip()
            m = re.match(r"^(\d+)\s*(\S.{15,})$", txt)
            if m and int(m.group(1)) not in seen_n:
                seen_n.add(int(m.group(1)))
                fns.append((int(m.group(1)), m.group(2).strip(), ""))
        if fns:
            flag(art, "inline-определения сносок (в .fnref-попапах) → [^N] (%d шт.)" % len(fns))
    fn_lines = []
    for num, txt, prefix in fns:
        if _B6_EMPTY.match(txt or ""):
            flag(art, "пустой «См. также:» обрубок в сноске — оставлен (авто-удаление сломало бы маркер)")
        if num is not None:
            fn_lines.append("[^%d]: %s" % (num, txt))
        elif prefix and re.fullmatch(r"\*+", prefix):
            fn_lines.append("[^%s]: %s" % (prefix, txt))  # звёздная сноска (первоклассная)
        elif prefix == "bare":
            fn_lines.append("[^|]: %s" % txt)  # А1: голый анон — render без ярлыка
        elif prefix:
            fn_lines.append("[^|%s]: %s" % (prefix, txt))
        else:
            fn_lines.append("[^]: %s" % txt)

    blocks = []
    # пункты ОРИГИНАЛЬНОГО TOC (якорь → текст): беззаголовочные блоки, бывшие
    # пунктами TOC, получают настоящий ## («идём за оригиналом», 15:31)
    toc_items = {}
    for tocel in find(root, lambda x: x["tag"] in ("details", "nav", "div", "ol", "ul")
                      and (any("toc" in cc for cc in cls(x)) or x["attrs"].get("id") == "toc")):
        for a in find(tocel, lambda x: x["tag"] == "a"
                      and (x["attrs"].get("href") or "").startswith("#")):
            toc_items[a["attrs"]["href"].lstrip("#")] = re.sub(
                r"\s+", " ", raw_text(a)).strip()

    # названия разделов из крошек (для подавления киккеров-дублей, вердикт 21:22)
    sec_names = {re.sub(r"\s+", " ", raw_text(a)).strip().lower()
                 for a in find(root, lambda x: x["tag"] == "a" and re.fullmatch(
                     r"\.\./[A-Za-z0-9_-]+/index\.html", x["attrs"].get("href") or ""))}
    st = {"consumed": consumed, "started": False,
          "refs_at": {g["first_id"]: g for g in groups if g.get("first_id") is not None},
          "refs_done": set(), "toc_done": False, "epi_pending": False,
          "toc_items": toc_items, "sec_names": sec_names}
    walk(root, blocks, art, st)
    # группа, чей первый айтем не встретился в walk (вложенные схемы) — [refs] хвостом
    for g in groups:
        if g["name"] not in st["refs_done"]:
            gl = ' glyph=%s' % g["glyph"] if g.get("glyph") else ""
            blocks.append("[refs=%s%s]" % (g["name"], gl))
            flag(art, "[refs=%s] не нашёл позицию первого айтема — выведен хвостом" % g["name"])

    # спасаем описат. подзаголовки из <header> (walk их дропнул) — НА МЕСТО под H1
    # (концептуально под общим заголовком, §1.3); порядок: ПЕРЕД телом из walk
    lead_blocks = []
    for n in find_lead_subtitles(root):
        sub = re.sub(r"\s+", " ", inline(n, art).strip())
        if not sub:
            continue
        if sub.lower() in sec_names:
            flag(art, "header-подзаголовок = дубль раздела — снят («%s»)" % sub[:30])
        elif _is_dateline_only(sub) or re.match(r"(?i)^(написано|записано)\b.*\d", sub):
            lead_blocks.append("[line kind=dateline]%s[/line]" % sub)
            flag(art, "header-подзаголовок (дата) спасён → [line kind=dateline]")
        elif cls(n) & LEAD_DECK_CLS:
            b = emit_subsec(n, art)
            if b:
                lead_blocks.append(b)
                flag(art, "header-дек (.%s) спасён → [subsec]"
                     % "/".join(sorted(cls(n) & LEAD_DECK_CLS)))
        else:
            lead_blocks.append("[sub]%s[/sub]" % sub)
            flag(art, "header-подзаголовок спасён → [sub]")
    blocks = [b for b in lead_blocks if b] + blocks

    # соседние [num]-блоки → один (16J: нумерованные абзацы живут в РАЗНЫХ
    # section-обёртках, walk эмитит их по одному; авторские номера в li value).
    # Сливаются только блоки с ОДИНАКОВОЙ головой ([num] ≠ [num kind=toc]).
    merged = []
    for b in blocks:
        if (merged and isinstance(b, str) and b.startswith("[num")
                and isinstance(merged[-1], str) and merged[-1].startswith("[num")
                and merged[-1].endswith("\n[/num]")
                and b.split("\n", 1)[0] == merged[-1].split("\n", 1)[0]):
            merged[-1] = merged[-1][:-len("\n[/num]")] + "\n\n" + b.split("\n", 1)[1]
        else:
            merged.append(b)
    blocks = merged

    # [toc nonum]: если САМИ заголовки начинаются с номера (1CM «1 / 1.1 / 1.1.1»,
    # 17BA «1 Кетер / 2 Хохма»…), авто-числа <ol> в TOC дают двойную нумерацию →
    # гасим их. Детект: большинство ##/###-строк начинаются с цифры. (Опция РУЧНАЯ
    # тоже доступна — render читает флаг nonum; здесь ставим автоматически.)
    heads = []
    for b in blocks:
        if isinstance(b, str) and re.match(r"^#{2,3}\s", b):
            ht = re.sub(r"^#{2,3}\s+", "", b)
            ht = re.sub(r"\s*\{[^}]*\}\s*$", "", ht)        # slug
            ht = re.sub(r"\[\^[^\]]*\]", "", ht).strip()    # маркеры сносок
            if ht:
                heads.append(ht)
    if heads:
        numbered = sum(1 for h in heads if re.match(r"^\d", h))
        if numbered >= max(2, (len(heads) + 1) // 2):
            for i, b in enumerate(blocks):
                if isinstance(b, str) and re.match(r"^\[toc\b", b) and "nonum" not in b:
                    blocks[i] = b[:-1] + " nonum]"
                    flag(art, "TOC nonum (%d/%d заголовков нумерованы) — авто-числа <ol> сняты"
                         % (numbered, len(heads)))

    # notes_title (A2): авторский заголовок секции сносок → frontmatter.
    # ТОЛЬКО одиночный контейнер (группы сами держат свои заголовки — вердикт A2:
    # не красть заголовки секций); подавляем in-body дубль ТОЛЬКО если это
    # ПОСЛЕДНИЙ заголовок статьи (иначе украли секцию — guard 12F/1CM).
    notes_title = find_notes_title(root, art, first_cont) if (fns and not groups) else ""
    if notes_title:
        pat = re.compile(r"##\s+" + re.escape(notes_title) + r"(?:\s+\{[^}]*\})?\s*$")
        m_idx = [i for i, b in enumerate(blocks) if isinstance(b, str) and pat.match(b)]
        h_idx = [i for i, b in enumerate(blocks) if isinstance(b, str) and b.startswith("## ")]
        if m_idx and h_idx and m_idx[-1] == h_idx[-1]:
            del blocks[m_idx[-1]]
        elif m_idx:
            flag(art, "notes_title «%s» совпал с НЕ-последним ## — не подавлен, поле сброшено" % notes_title[:40])
            notes_title = ""

    # сирота-лейбл аудио после выноса 🎧 в FM
    if audio:
        blocks = [b for b in blocks if not (isinstance(b, str) and re.match(
            r"(?i)^(аудио[\w-]*|озвучк[аи]|слушать(\s+аудио\w*)?)\s*:?\s*$", b.strip()))]

    # дубль title первым абзацем (бывает эхо H1) — не трогаем: H1-приоритет уже в FM

    # ── тип работы `type:` (Ф8′, вердикт оператора 2026-06-18) ──────────────
    # Выводится из тела ZML; редактор может переопределить вручную. Приоритет:
    # dialog → prose_num → (poem|verse) → prose. poem = стих-доминанта по объёму И
    # оглавление ≥2 ##-разделов; «обычный стих» (verse) = стих-доминанта с <2.
    _bs = [b for b in blocks if isinstance(b, str)]
    _verse_chars = sum(len(b) for b in _bs if b.startswith("[poem]"))
    _prose_chars = sum(len(b) for b in _bs if not re.match(r"^(\[|#|>|\|)", b))
    _sec_h2 = sum(1 for b in _bs if re.match(r"^##\s", b))
    if any(re.match(r"^\[dlg\b", b) for b in _bs):
        art_type = "dialog"
    elif any(re.match(r"^\[num\]", b) for b in _bs):
        art_type = "prose_num"
    elif _verse_chars and _verse_chars >= _prose_chars:
        art_type = "poem" if _sec_h2 >= 2 else "verse"
    else:
        art_type = "prose"

    fm = ["---",
          "title: %s" % title,
          'art: "%s"' % art,
          "date: %s" % rec.get("date_chosen", "")]
    if image:
        fm.append("image: %s" % image)  # вердикт A1: только реальный src
    # theme/width БОЛЬШЕ НЕ эмитятся (Ф8′): дефолты в центральном конфиге; поле
    # остаётся допустимым во frontmatter как осознанный per-article override.
    fm.append("type: %s" % art_type)
    if notes_title and notes_title != "Примечания":
        fm.append("notes_title: %s" % notes_title)
    if audio:
        fm.append("audio: %s" % json.dumps(audio, ensure_ascii=False))
    # Ф8′: сохранить РУЧНЫЕ per-article override-поля (view/theme/width) из уже
    # существующего .zml — конвертер пересобирает frontmatter с нуля и иначе стёр бы
    # их. `view: zml|html` форсит версию показа (перебивает админский default_view);
    # theme/width — форс дизайна/ширины вью. Конвертер их НЕ создаёт, только бережёт.
    existing_zml = ART / f"{art}.zml"
    if existing_zml.exists():
        m_old = re.match(r"^---(.*?)---", existing_zml.read_text("utf-8"), flags=re.S)
        if m_old:
            for fld in ("view", "theme", "width"):
                mo = re.search(r"(?m)^%s:[ \t]*(.+?)[ \t]*$" % fld, m_old.group(1))
                if mo and mo.group(1).strip():
                    fm.append("%s: %s" % (fld, mo.group(1).strip()))
    fm += ["---", ""]
    # см.-также больше НЕ уходят в хвост анон-сносками — остаются на авторском
    # месте видимой строкой (вердикт 21:12 2026-06-12, кейс 59C)

    # определения групп (§4.1) — хвостом, в документ-порядке групп, до дефолтных
    group_lines = []
    for g in groups:
        for num, txt in g["items"]:
            group_lines.append("[^%s.%d]: %s" % (g["name"], num, txt))
    zml = "\n".join(fm) + "\n\n".join(b for b in blocks if b) + "\n"
    if group_lines or fn_lines:
        zml += "\n\n" + "\n\n".join(group_lines + fn_lines) + "\n"

    # оракул-гейт: текст-масса оригинал↔ZML (вариант B аудита)
    cov = coverage(root, zml)
    if cov is not None and cov < 0.97:
        flag(art, "ОРАКУЛ: покрытие %.3f < 0.97 — потеря текста, нужен разбор" % cov)
    elif cov is not None and cov > 1.20:
        flag(art, "ОРАКУЛ: покрытие %.3f > 1.20 — хром утёк в текст?" % cov)

    (OUT / f"{art}.zml").write_text(zml, "utf-8")
    (OUT / f"{art}.flags.txt").write_text(
        "\n".join(f for f in FLAGS if f.startswith(f"[{art}]")) or "(нет флагов)", "utf-8")
    return zml, cov


if __name__ == "__main__":
    ids = sys.argv[1:] or ["654", "237"]
    for art in ids:
        FLAGS.clear()
        try:
            zml, cov = convert(art)
            print("OK", art, "cov=%.3f" % cov if cov is not None else "cov=?")
        except Exception as e:
            import traceback
            print("ERR", art, e)
            traceback.print_exc()

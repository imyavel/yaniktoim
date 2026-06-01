"""HTML → ZML transformation via headless `claude -p` with lossless validation.

Pipeline per article:
  raw/<stem>.html
    → article_text()      : H1 + plain body, <a> wrapped as ⟦A href="X"⟧Y⟦/A⟧
    → classify_links()    : ⟦A⟧ → ⟦INT n="<art>"⟧Y⟦/INT⟧ / ⟦EXT url="X"⟧Y⟦/EXT⟧
                              + bare URLs in body  → ⟦EXT url="X"⟧⟦/EXT⟧
    → convert_italic()    : authorial [фраза] → _фраза_ (word-boundary; outside markers)
    → call_claude()       : LLM returns final ZML (frontmatter + body)
    → inject_art()        : substitute `art:` value from manifest into frontmatter
    → validate_lossless() : strip all ZML/marker noise from both sides → compare
    → zml/<art>.zml

Usage:
  python 3_transform.py <art> [<art> ...]
  python 3_transform.py --stem <YYYY_MM_DD_NNN> [...]
  python 3_transform.py --pilot
  python 3_transform.py --all
  python 3_transform.py <art> --force        # overwrite existing zml/<art>.zml
"""
from __future__ import annotations
import io
import re
import sys
import json
import time
import shutil
import subprocess
import html as html_mod
from datetime import date
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
ZML_DIR = ROOT / "zml"
LOGS = ROOT / "_logs"
MANIFEST = ROOT / "manifest.json"
ZOHAR_INDEX = LOGS / "zohar_index.json"
PROMPT_MD = ROOT / "src" / "transform_prompt.md"

# Direct path into the Claude MSIX-package container — обходим symlink
# в %APPDATA%\Roaming\Claude, который не везде резолвится. См. CLAUDE.md.
CLAUDE_EXE = (
    r"C:\Users\admin\AppData\Local\Packages\Claude_pzs8sxrjxfjjc"
    r"\LocalCache\Roaming\Claude\claude-code\2.1.149\claude.exe"
)

# Pilot stems for `--pilot` mode (см. roadmap §6).
PILOT_STEMS = [
    "2026_05_04_367",   # philosophical / footnotes / youtube
    "2022_05_05_670",   # trilogy in verse with epigraphs
    "2024_01_06_1439",  # short dialog piece
]


# ═════════════════════════════════════════════════════════════════════════════
# 1. CANONICAL PLAIN TEXT
# ═════════════════════════════════════════════════════════════════════════════

# Section-marker words that the proza "::" corruption follows.
# Match form: "<word>::" → "<word>: " (colon+space).
_DCOLON_SECTION_RX = re.compile(
    r'(См\.\s*также|Цитата|Музыка|Источник|Автор'
    r'|Примечание|Дополнение|Параллели|Заповедь|Том|Глава|Книга|Сноска)'
    r'\s*::\s*',
    re.I,
)


def _restore_double_colon(text: str) -> str:
    """Restore `::` corrupted by proza's text engine.

    Two cases:
      1. After a known section-marker word ("См. также::") → ": " (colon+space).
      2. Anywhere else → " — " (em-dash with spaces).
    """
    text = _DCOLON_SECTION_RX.sub(lambda m: m.group(1).rstrip() + ': ', text)
    text = re.sub(r'\s*::\s*', ' — ', text)
    return text


def article_text(html: str) -> str:
    """Return plain text of <h1> + <div class="text">, with <a> wrapped as
    ⟦A href="X"⟧Y⟦/A⟧. This is the *canonical* string against which the
    LLM's ZML output is later validated."""
    h1 = ""
    m = re.search(r"<h1>(.*?)</h1>", html, re.S)
    if m:
        h1 = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    body = ""
    m = re.search(r'<div\s+class="text">(.*?)</div>\s*<br>', html, re.S)
    if m:
        body = m.group(1)
        # 1. <br> → \n (eat the trailing single newline so HTML formatting
        #    doesn't generate phantom blank lines).
        body = re.sub(r"<br\s*/?>\n?", "\n", body, flags=re.I)

        # 2. <a href="X">Y</a> → ⟦A href="X"⟧Y⟦/A⟧ (BEFORE stripping tags).
        def repl_a(m: re.Match) -> str:
            href = m.group("href")
            inner = m.group("inner")
            inner = re.sub(r"<[^>]+>", "", inner)
            return f'⟦A href="{href}"⟧{inner}⟦/A⟧'
        body = re.sub(
            r'<a\s+[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<inner>.*?)</a>',
            repl_a, body, flags=re.S | re.I,
        )
        # 3. Strip remaining tags.
        body = re.sub(r"<[^>]+>", "", body)
        # 4. HTML-entity decode (&quot;, &nbsp;, &ndash;, ...).
        body = html_mod.unescape(body)
        # 5. Typography normalisation (whitelisted format-only changes):
        body = (body
                .replace("“", '"').replace("”", '"')
                .replace("‘", "'").replace("’", "'")
                .replace(" ", " "))
        h1 = (h1
              .replace("“", '"').replace("”", '"')
              .replace("‘", "'").replace("’", "'")
              .replace(" ", " "))
        # 6. Drop proza.ru ";;…" garbage (corrupted Hebrew / specials).
        body = re.sub(r'[ \t]*;{2,}[ \t]*', ' ', body)
        body = re.sub(r'[ \t]{2,}', ' ', body)
        h1 = re.sub(r'[ \t]*;{2,}[ \t]*', ' ', h1)
        h1 = re.sub(r'[ \t]{2,}', ' ', h1)
        # 6b. Restore `::` corrupted by proza:
        #   - after a known section-marker word → ": " (colon+space)
        #   - otherwise → " — " (em-dash)
        body = _restore_double_colon(body)
        h1 = _restore_double_colon(h1)
        # 7. Drop CAPS-duplicate of <h1> that proza often places as the
        #    very first body line.
        body = body.lstrip("\n")
        body_lines = body.split("\n", 1)
        if body_lines and body_lines[0].strip().casefold() == h1.strip().casefold():
            body = body_lines[1] if len(body_lines) > 1 else ""
            body = body.lstrip("\n")
    return (h1 + "\n\n" + body).strip() + "\n"


# ═════════════════════════════════════════════════════════════════════════════
# 2. LINK CLASSIFICATION
# ═════════════════════════════════════════════════════════════════════════════

# Marker regex — matches BOTH ⟦A⟧ and the new ⟦INT/EXT/ZOH⟧ family.
_MARKER_RX = re.compile(
    r'⟦/?(?:A|INT|EXT|ZOH)(?:\s+\w+="[^"]*")*\s*⟧'
)

# Paired marker region: opening tag through matching close. Used to skip
# scanning for bare URLs / italic-conversion inside ⟦INT⟧…⟦/INT⟧ etc.,
# where the visible text may itself contain the URL or `[...]`.
_PAIRED_REGION_RX = re.compile(
    r'⟦(A|INT|EXT|ZOH)(?:\s+\w+="[^"]*")*\s*⟧.*?⟦/\1⟧',
    re.S,
)

# A proza.ru article URL like "https://proza.ru/2021/08/02/157".
_PROZA_ARTICLE_RX = re.compile(
    r'^https?://(?:www\.)?proza\.ru/\d{4}/\d{2}/\d{2}/\d+/?$',
    re.I,
)

# A bare URL in text (not inside any marker). Two forms:
#   1. with scheme: https?://...
#   2. schemaless but on a known well-formed domain (proza.ru, imyavel.github.io,
#      youtu.be, youtube.com, etc.) — author often writes "imyavel.github.io/x/"
#      as a plain reference. We auto-promote those to https.
_KNOWN_BARE_DOMAINS = (
    r'(?:'
    r'proza\.ru|imyavel\.github\.io|youtu\.be|(?:www\.)?youtube\.com'
    r'|(?:www\.)?facebook\.com|t\.me|wikipedia\.org|ru\.wikipedia\.org'
    r'|kabbalahmedia\.info|bneiadam\.com|ccastaneda\.ru|adam\.fandom\.com'
    r')'
)
_BARE_URL_RX = re.compile(
    r'(?<![/"=:.\w])(?:'
    r'https?://[^\s<>"\'\)\]⟦⟧]+'
    r'|' + _KNOWN_BARE_DOMAINS + r'/[^\s<>"\'\)\]⟦⟧]*'
    r')',
)


def _norm_proza_url(url: str) -> str:
    """Normalise a proza.ru URL for manifest lookup (drop trailing slash,
    coerce http→https, lower-case host)."""
    url = url.strip().rstrip("/")
    url = re.sub(r'^http://', 'https://', url, flags=re.I)
    return url


def classify_links(text: str, manifest_by_url: dict[str, str]) -> str:
    """Convert ⟦A href="X"⟧Y⟦/A⟧ markers + bare URLs into the three
    classes the prompt expects: ⟦INT⟧, ⟦EXT⟧ (Zohar not present in
    proza-raw corpus, see roadmap notes — leave to CMS post-edit).

    `manifest_by_url[normalised_url] = art_id`.
    """
    # 1. <a> markers first.
    def repl_a(m: re.Match) -> str:
        href = m.group("href")
        inner = m.group("inner")
        norm = _norm_proza_url(href)
        if _PROZA_ARTICLE_RX.match(norm) and norm in manifest_by_url:
            art = manifest_by_url[norm]
            return f'⟦INT n="{art}"⟧{inner}⟦/INT⟧'
        # External (incl. proza.ru/avtor/*, foreign authors, etc.)
        return f'⟦EXT url="{href}"⟧{inner}⟦/EXT⟧'

    text = re.sub(
        r'⟦A\s+href="(?P<href>[^"]+)"⟧(?P<inner>.*?)⟦/A⟧',
        repl_a, text, flags=re.S,
    )

    # 2. Bare URLs OUTSIDE any paired marker region (so the visible text
    #    of a link doesn't get re-classified).
    return _apply_outside_pairs(text, lambda seg: _wrap_bare_urls(seg, manifest_by_url))


def _apply_outside_pairs(text: str, fn) -> str:
    """Run `fn(segment)` on free-text regions OUTSIDE any paired
    ⟦TAG…⟧…⟦/TAG⟧ block. Paired regions are passed through verbatim."""
    out: list[str] = []
    pos = 0
    for m in _PAIRED_REGION_RX.finditer(text):
        out.append(fn(text[pos:m.start()]))
        out.append(text[m.start():m.end()])
        pos = m.end()
    out.append(fn(text[pos:]))
    return "".join(out)


def _wrap_bare_urls(segment: str, manifest_by_url: dict[str, str]) -> str:
    """Wrap every bare URL in a free-text segment.

    - proza.ru article URL present in manifest → ⟦INT n="<art>"⟧⟦/INT⟧
      (empty anchor — LLM emits `[[<art>]]` in ZML).
    - everything else → ⟦EXT url="X"⟧⟦/EXT⟧ (empty anchor → `[url]`)."""
    def repl(m: re.Match) -> str:
        url = m.group(0).rstrip(".,;:!?)”»")
        tail = m.group(0)[len(url):]
        # Promote schemaless known-domain URL to https.
        if not re.match(r'^https?://', url, re.I):
            url_full = 'https://' + url
        else:
            url_full = url
        norm = _norm_proza_url(url_full)
        if _PROZA_ARTICLE_RX.match(norm) and norm in manifest_by_url:
            art = manifest_by_url[norm]
            return f'⟦INT n="{art}"⟧⟦/INT⟧{tail}'
        return f'⟦EXT url="{url_full}"⟧⟦/EXT⟧{tail}'
    return _BARE_URL_RX.sub(repl, segment)


# ═════════════════════════════════════════════════════════════════════════════
# 3. ITALIC PRE-CONVERSION
# ═════════════════════════════════════════════════════════════════════════════

# Что считаем italic-кандидатом внутри `[...]`:
#   - содержимое: 1–60 символов
#   - НЕ начинается с цифры (тогда это [N] сноска)
#   - НЕ содержит '|' (тогда это ZML-ссылка [url|анкор])
#   - НЕ содержит '/' '\\' (URL-фрагмент)
#   - НЕ начинается с '^' (наш footnote-marker [^N])
#   - содержит хотя бы одну кириллическую букву
#   - boundary-context (см. _has_word_boundary) с обеих сторон
_ITALIC_BRACKET_RX = re.compile(r'\[([^\[\]\n|/\\]{1,60})\]')


_CYRILLIC_RX = re.compile(r'[а-яёА-ЯЁ]')


def _is_italic_candidate(content: str) -> bool:
    c = content.strip()
    if not c:
        return False
    if c.startswith("^"):           # [^N] footnote
        return False
    if c[0].isdigit():              # [N] / [10] / [1.2] — footnote
        return False
    if c[0] in "*¤¶‡":              # [¤ 5], [‡ 1], [¶.3] — footnote
        return False
    # named footnote pattern: ends with digits (e.g. [ezer-kenegdo 1], [b-a 7])
    if re.search(r'\s+\d+$', c) or re.search(r'[a-z]-[a-z]+\s*\d', c, re.I):
        return False
    if not _CYRILLIC_RX.search(c):  # purely latin / numeric — not italic
        return False
    return True


def _has_word_boundary(text: str, start: int, end: int) -> bool:
    """`text[start:end]` is `[фраза]`. Check both sides have word-boundary."""
    left_ok = (start == 0) or (text[start - 1] in " \t\n.,;:!?—–-«»\"'()")
    right_ok = (end == len(text)) or (text[end] in " \t\n.,;:!?—–-«»\"')(:")
    return left_ok and right_ok


def convert_italic(text: str) -> str:
    """`[фраза]` → `_фраза_` by word-boundary, OUTSIDE paired marker regions
    (so URL fragments and link anchors are protected)."""
    return _apply_outside_pairs(text, _italic_in_segment)


def _italic_in_segment(segment: str) -> str:
    """Apply italic-conversion to a single free-text segment."""
    out: list[str] = []
    last = 0
    for m in _ITALIC_BRACKET_RX.finditer(segment):
        if not _is_italic_candidate(m.group(1)):
            continue
        if not _has_word_boundary(segment, m.start(), m.end()):
            continue
        out.append(segment[last:m.start()])
        out.append("_" + m.group(1) + "_")
        last = m.end()
    out.append(segment[last:])
    return "".join(out)


# ═════════════════════════════════════════════════════════════════════════════
# 4. LLM CALL
# ═════════════════════════════════════════════════════════════════════════════

def call_claude(prompt: str, marked_text: str, art: str) -> str | None:
    """Send the prepared marked-text to headless claude -p and return its
    raw output (expected: full ZML — frontmatter + body)."""
    full_prompt = (
        prompt
        + "\n\n## Статья к преобразованию\n\n"
        + "```\n" + marked_text + "\n```\n"
    )
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / f"prompt_{art}.txt").write_text(full_prompt, encoding="utf-8")
    print(f"  [{art}] prompt: {len(full_prompt)} chars, marked: {len(marked_text)} chars",
          flush=True)
    cmd = [
        CLAUDE_EXE, "-p",
        "--model", "claude-opus-4-8",
        "--output-format", "json",
        "--max-turns", "1",
    ]
    t0 = time.time()
    proc = subprocess.run(
        cmd, input=full_prompt, capture_output=True, text=True, encoding="utf-8",
    )
    dur = time.time() - t0
    print(f"  [{art}] claude exit={proc.returncode} in {dur:.1f}s", flush=True)
    if proc.returncode != 0:
        (LOGS / f"transform_{art}.stderr.txt").write_text(
            proc.stderr or "", encoding="utf-8",
        )
        return None
    raw = proc.stdout.strip()
    # The "json" output mode wraps the assistant's reply in {"result": "..."}.
    try:
        envelope = json.loads(raw)
        inner = envelope.get("result", raw) if isinstance(envelope, dict) else raw
    except Exception:
        inner = raw
    # Strip ```...``` fences if present.
    inner = re.sub(r"^```(?:\w+)?\s*\n?", "", inner.strip())
    inner = re.sub(r"\n?```\s*$", "", inner)
    # Strip the "[HH:MM] Tokens: ..." telemetry tail injected by global
    # CLAUDE.md (inherited by headless run).
    inner = re.sub(r"\n*\[\d\d:\d\d\]\s+Tokens:[^\n]*\s*$", "", inner)
    (LOGS / f"transform_{art}.zml.raw.txt").write_text(inner, encoding="utf-8")
    return inner


# ═════════════════════════════════════════════════════════════════════════════
# 5. FRONTMATTER INJECTION
# ═════════════════════════════════════════════════════════════════════════════

def inject_art(zml: str, art: str) -> str:
    """Substitute `art:` value in the frontmatter.

    If the LLM emitted `art:` empty or with a placeholder — replace.
    If the LLM omitted the field entirely — insert before the closing `---`.
    """
    # Frontmatter ends at the second `---` line. Split safely.
    if not zml.startswith("---"):
        # No frontmatter at all → add one.
        return f"---\nart: \"{art}\"\n---\n\n" + zml.lstrip()
    m = re.match(r'^---\n(.*?)\n---\n?', zml, re.S)
    if not m:
        return f"---\nart: \"{art}\"\n---\n\n" + zml.lstrip()
    fm_body = m.group(1)
    rest = zml[m.end():]
    if re.search(r'^art:\s*.*$', fm_body, re.M):
        fm_body = re.sub(
            r'^art:\s*.*$', f'art: "{art}"', fm_body, count=1, flags=re.M,
        )
    else:
        # Insert after `title:` if present, else at top of frontmatter.
        if re.search(r'^title:', fm_body, re.M):
            fm_body = re.sub(
                r'^(title:.*)$', r'\1' + f'\nart: "{art}"',
                fm_body, count=1, flags=re.M,
            )
        else:
            fm_body = f'art: "{art}"\n' + fm_body
    return f"---\n{fm_body}\n---\n" + (rest if rest.startswith("\n") else "\n" + rest)


def inject_attribution(zml: str) -> str:
    """Stamp default attribution into the frontmatter (§0.6): an AI-built,
    not-yet-hand-edited article is signed `editor: Иван Иванович` with
    `edited: <build date>`. Only fills fields that are MISSING — never
    overrides values a human (the in-page editor) already set.
    """
    today = date.today().isoformat()
    m = re.match(r'^---\n(.*?)\n---\n?', zml, re.S)
    if not m:  # inject_art guarantees frontmatter, but stay defensive
        return zml
    fm_body = m.group(1)
    rest = zml[m.end():]
    if not re.search(r'^editor:\s*.*$', fm_body, re.M):
        fm_body += '\neditor: "Иван Иванович"'
    if not re.search(r'^edited:\s*.*$', fm_body, re.M):
        fm_body += f'\nedited: "{today}"'
    return f"---\n{fm_body}\n---\n" + (rest if rest.startswith("\n") else "\n" + rest)


# ═════════════════════════════════════════════════════════════════════════════
# 6. LOSSLESS VALIDATION
# ═════════════════════════════════════════════════════════════════════════════

# Авторские footnote-токены в основном тексте (для маскирования при валидации).
_FN_TOKEN_RX_LIST = [
    # [N] [10] [1.2]
    re.compile(r'\[\d+(?:\.\d+)*\]'),
    # [¤ 5] [¶.3] [‡ 1]
    re.compile(r'\[[¤¶‡]\s*\.?\s*\d+\]'),
    # [slug 5] [ezer-kenegdo 1] [b-a 7]
    re.compile(r'\[[a-zа-я]+(?:[- ][a-zа-я]+)*\s+\d+\]', re.I),
    # *N or **N or ***… (footnote tokens with optional number).
    # Match anywhere that is not preceded by another `*` (avoids munching
    # `**` as `*` + `*N`) and is followed by digit or whitespace/EOL.
    re.compile(r'(?<!\*)\*+\d+'),
    # bare * / ** / *** as a standalone token (preceded by word/punct,
    # followed by space/newline/punct so we don't catch markdown emphasis).
    re.compile(r'(?<=[А-Яа-яA-Za-z0-9»"\')])\*+(?=[\s.,;:!?»"\'\)]|$)'),
]

# Строки-маркеры специальных блоков в канон-тексте, которые в ZML
# превращаются в обёртки ([epi]…[/epi], [sub]…[/sub] и т.п.). Со стороны
# canon нужно удалить ИМЕННО эти строки, чтобы lossless-валидатор не падал.
_BLOCK_HEADER_RX = re.compile(
    r'^[ \t]*(?:'
    r'Эпиграф(?:\s*[\d№]+|\s+(?:первый|второй|третий|четвёртый|пятый))?'
    r'|ЭПИГРАФ(?:\s*[\d№]+)?'
    r'|Цитата\s+Эпиграф\b[^\n]*'
    r'|Эпилог|ЭПИЛОГ|Послесловие'
    r')\s*\(?\)?\s*$',
    re.M,
)

# Colophon-сигнатуры (Арт.# / Записано / Написано / голая дата).
_COLOPHON_RX_LIST = [
    # «Арт. #AP237, написано 7 Марта 2022 г.» / «Арт.#XX01»
    re.compile(
        r'^[ \t]*Арт\.\s*#\S+[^\n]*$',
        re.M | re.I,
    ),
    # «Записано 2 Августа 2021 г.» / «Написано в Декабре 2023»
    re.compile(
        r'^[ \t]*(?:Записано|Написано|Написан)[^\n]*$',
        re.M | re.I,
    ),
    # Голая дата на отдельной строке: «2 Августа 2021 г.» / «22.09.22» /
    # «Декабрь 2023»
    re.compile(
        r'^[ \t]*(?:\d{1,2}\.\d{1,2}\.\d{2,4}|'
        r'\d{1,2}\s+(?:Января|Февраля|Марта|Апреля|Мая|Июня|Июля|Августа|Сентября|Октября|Ноября|Декабря)\s+\d{4}\s*г?\.?|'
        r'(?:Январь|Февраль|Март|Апрель|Май|Июнь|Июль|Август|Сентябрь|Октябрь|Ноябрь|Декабрь)\s+\d{4}'
        r')\s*$',
        re.M | re.I,
    ),
]


def _mask_canon_for_validation(canon: str) -> str:
    """Reduce canon (marked-text) to a comparable plain form.

    `canon` starts with the H1 line, blank line, then body. H1 lives in the
    ZML frontmatter as `title:` (which we strip on the ZML side), so we
    also drop H1 here for a fair comparison.
    """
    s = canon
    # 0. Drop the leading H1 line (everything up to and including the first
    #    blank-line separator). canon format is "<h1>\n\n<body>".
    m = re.match(r'^[^\n]*\n\n', s)
    if m:
        s = s[m.end():]
    # 0.1. Cut footnote section: from a recognised "footnote-section header"
    #      line to end of canon. The ZML side also drops `[^N]:` bodies,
    #      so both sides lose the same span.
    s = re.sub(
        r'\n[ \t]*(?:'
        r'Пост\s*скриптум|Постскриптум|Примечания|Сноски'
        r'|См\.\s+также|Полезные\s+ссылки|ПОЛЕЗНЫЕ\s+ССЫЛКИ'
        r'|P\.?\s*S\.?|Дополнение|Параллели'
        r')\b[^\n]*(?:\n.*)?$',
        '', s, flags=re.I | re.S,
    )
    # 0.2. Cut music blocks: from "Музыка под настроение" /
    #      "Песнь Ступеней" / "Рекомендуемая музыка" line until the next
    #      blank line. The ZML side drops the entire [mus]...[/mus] block.
    s = re.sub(
        r'\n[ \t]*(?:Музыка\s+под\s+настроение|Песнь\s+[Сс]тупеней|Рекомендуемая\s+музыка)'
        r'[^\n]*(?:\n[^\n]+)*?(?=\n\n|\Z)',
        '', s, flags=re.I,
    )
    # 0.3. Drop block-header lines that turn into [epi]/[epil]/[sub] etc.
    #      The ZML wrapper consumes them; canon keeps them as plain lines.
    s = _BLOCK_HEADER_RX.sub('', s)
    # 0.35. Drop forum-style quote attribution lines `<Ник> написал(а):`
    #       which become `[quote cite="<Ник>"]` in ZML.
    s = re.sub(
        r'^[ \t]*[^\n]+\s+написал[аи]?\s*\(?а?\)?\s*:?\s*$',
        '', s, flags=re.M | re.I,
    )
    # 0.4. Drop colophon signatures (Арт.#, Записано, bare date lines).
    for rx in _COLOPHON_RX_LIST:
        s = rx.sub('', s)
    # 1. Footnote authorial tokens → __FN__.
    for rx in _FN_TOKEN_RX_LIST:
        s = rx.sub("__FN__", s)
    # 2. ⟦INT n="X"⟧Y⟦/INT⟧ → __INT_X__ (anchor Y is discarded in ZML too).
    s = re.sub(
        r'⟦INT\s+n="([^"]+)"⟧.*?⟦/INT⟧',
        lambda m: f'__INT_{m.group(1)}__',
        s, flags=re.S,
    )
    # 3. ⟦ZOH ch="X" n="N"⟧Y⟦/ZOH⟧ → __ZOH_X_N__ (anchor discarded).
    s = re.sub(
        r'⟦ZOH\s+ch="([^"]+)"\s+n="([^"]+)"⟧.*?⟦/ZOH⟧',
        lambda m: f'__ZOH_{m.group(1)}_{m.group(2)}__',
        s, flags=re.S,
    )
    # 4. ⟦EXT url="X"⟧Y⟦/EXT⟧:
    #    empty Y → __URL__X__   (bare URL case → ZML `[url]`)
    #    non-empty Y → __URL__X__::Y    (named-link → ZML `[url|Y]`)
    def ext_repl(m: re.Match) -> str:
        url = m.group(1)
        anchor = m.group(2)
        if anchor.strip() == "":
            return f'__URL__{url}__'
        return f'__URL__{url}__::{anchor}'
    s = re.sub(
        r'⟦EXT\s+url="([^"]+)"⟧(.*?)⟦/EXT⟧',
        ext_repl, s, flags=re.S,
    )
    return s


def _mask_zml_for_validation(zml: str) -> str:
    """Reduce ZML output to the same comparable plain form as canon."""
    s = zml
    # 1. Strip frontmatter.
    s = re.sub(r'^---\n.*?\n---\n?', '', s, flags=re.S, count=1)
    # 2. Drop entire [mus]...[/mus] blocks (canon-side cuts their text too).
    s = re.sub(r'\[mus(?:\s+[^\]]*)?\].*?\[/mus\]', '', s, flags=re.S)
    # 3. Drop footnote section: from the FIRST `[^...]:` body line (start
    #    of line or after \n) to end of file. Canon side cuts the matching
    #    span from "Пост скриптум"/"Примечания"/"См. также" onwards.
    s = re.sub(r'(?:^|\n)\[\^[^\]]*\]:[\s\S]*$', '', s)
    # 4. Section headings `## ... {slug}` → keep heading text only.
    s = re.sub(r'^##\s+(.*?)\s*\{[^}]*\}\s*$', r'\1', s, flags=re.M)
    s = re.sub(r'^##\s+(.*)$', r'\1', s, flags=re.M)
    # 5. Strip block container tags [poem]/[/poem], [epi cite="..."], etc.
    s = re.sub(
        r'\[(?:/?)(?:poem|epi|epil|quote|num|sub)(?:\s+[^\]]*)?\]',
        '', s,
    )
    # 6. Inline tags:
    #    [^N]  → __FN__
    s = re.sub(r'\[\^\d+\]', '__FN__', s)
    #    [^]   → __FN__ (anonymous, rare — anonymous bodies are dropped
    #    in step 3 anyway, but inline [^] markers could remain if author
    #    used them as in-text references)
    s = re.sub(r'\[\^\]', '__FN__', s)
    #    [[<art>]] → __INT_<art>__
    s = re.sub(r'\[\[([A-Za-z0-9]+)\]\]', lambda m: f'__INT_{m.group(1)}__', s)
    #    {chapter|N} → __ZOH_chapter_N__
    s = re.sub(
        r'\{([a-z-]+)\|(\d+)\}',
        lambda m: f'__ZOH_{m.group(1)}_{m.group(2)}__', s,
    )
    #    [url|anchor]  → __URL__url__::anchor
    #    [url]         → __URL__url__
    s = re.sub(
        r'\[(https?://[^\s\|\]]+)\|([^\]]+)\]',
        lambda m: f'__URL__{m.group(1)}__::{m.group(2)}', s,
    )
    s = re.sub(
        r'\[(https?://[^\s\]]+)\]',
        lambda m: f'__URL__{m.group(1)}__', s,
    )
    # 7. Drop italic markers `_фраза_` (we don't need them on either side
    #    for lossless compare — canon-side italic was pre-converted from
    #    [фраза] to _фраза_ already, so both sides have the same markup).
    #    Actually keep them; they are 1:1 between the two sides.
    return s


def _normalize_for_compare(s: str) -> str:
    """Normalise whitespace for the lossless diff.

    - \\r\\n → \\n
    - rstrip every line (incl. NBSP)
    - drop leading/trailing blank lines
    - collapse runs of ≥2 blank lines → 1 blank
    - then fold single blank lines between content lines (cosmetic blanks
      around block markers).
    """
    s = s.replace("\r\n", "\n")
    _TRAIL = " \t "
    # rstrip; also strip exactly ONE leading space (cosmetic indent before
    # quoted lines). Multi-space lesnitsa (poem ladder) is preserved.
    def _norm_ln(ln: str) -> str:
        ln = ln.rstrip(_TRAIL)
        if ln.startswith(" ") and (len(ln) < 2 or ln[1] != " "):
            ln = ln[1:]
        return ln
    lines = [_norm_ln(ln) for ln in s.split("\n")]
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    out: list[str] = []
    blank = 0
    for ln in lines:
        if ln == "":
            blank += 1
            if blank <= 1:
                out.append(ln)
        else:
            blank = 0
            out.append(ln)
    folded: list[str] = []
    i = 0
    while i < len(out):
        if (i + 2 < len(out) and out[i] != ""
                and out[i + 1] == "" and out[i + 2] != ""):
            folded.append(out[i])
            i += 2
            continue
        folded.append(out[i])
        i += 1
    return "\n".join(folded)


def validate_lossless(zml: str, marked_canon: str, art: str) -> tuple[bool, str]:
    a = _normalize_for_compare(_mask_zml_for_validation(zml))
    b = _normalize_for_compare(_mask_canon_for_validation(marked_canon))
    if a == b:
        return True, ""
    import difflib
    diff = list(difflib.unified_diff(
        b.splitlines(),
        a.splitlines(),
        fromfile=f"canon[{art}]", tofile=f"zml[{art}]",
        n=2, lineterm="",
    ))
    diff_text = "\n".join(diff[:300])
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / f"transform_{art}.diff.txt").write_text(diff_text, encoding="utf-8")
    (LOGS / f"transform_{art}.canon.masked.txt").write_text(b, encoding="utf-8")
    (LOGS / f"transform_{art}.zml.masked.txt").write_text(a, encoding="utf-8")
    return False, diff_text


# ═════════════════════════════════════════════════════════════════════════════
# 7. ORCHESTRATION
# ═════════════════════════════════════════════════════════════════════════════

def transform_one(rec: dict, prompt: str, manifest_by_url: dict[str, str],
                  force: bool = False) -> bool:
    art = rec.get("art")
    stem = rec.get("stem")
    if not art or not stem:
        print(f"  ! record missing art/stem: {rec.get('number')}", flush=True)
        return False
    out_path = ZML_DIR / f"{art}.zml"
    if out_path.exists() and not force:
        print(f"  skip {art} (zml already exists, pass --force to overwrite)",
              flush=True)
        return True
    src = RAW / f"{stem}.html"
    if not src.exists():
        print(f"  ! {art} ({stem}): html not found", flush=True)
        return False

    # 1. Extract canonical plain text.
    canon = article_text(src.read_text(encoding="utf-8"))
    # 2. Classify links: ⟦A⟧ → ⟦INT⟧/⟦EXT⟧, plus bare URLs → ⟦EXT⟧.
    marked = classify_links(canon, manifest_by_url)
    # 3. Pre-convert authorial [фраза] → _фраза_ outside markers.
    marked = convert_italic(marked)
    (LOGS / f"transform_{art}.marked.txt").write_text(marked, encoding="utf-8")

    # 4. Call LLM.
    zml_raw = call_claude(prompt, marked, art)
    if zml_raw is None:
        return False

    # 5. Inject art + default attribution into frontmatter.
    zml = inject_art(zml_raw, art)
    zml = inject_attribution(zml)

    # 6. Lossless validation.
    ok, diff = validate_lossless(zml, marked, art)
    if not ok:
        print(f"  ! [{art}] VALIDATION FAILED — see _logs/transform_{art}.diff.txt",
              flush=True)
        head = "\n".join(diff.splitlines()[:30])
        print(head, flush=True)
        return False
    print(f"  ✓ [{art}] validation passed", flush=True)

    # 7. Save.
    out_path.write_text(zml, encoding="utf-8")
    print(f"  ✓ saved → {out_path}", flush=True)
    return True


def _build_manifest_lookups(manifest: list[dict]) -> tuple[dict, dict, dict]:
    """Return (by_art, by_stem, by_url) lookup maps."""
    by_art: dict[str, dict] = {}
    by_stem: dict[str, dict] = {}
    by_url: dict[str, str] = {}        # normalised url → art
    for r in manifest:
        if "art" in r:
            by_art[r["art"]] = r
        if "stem" in r:
            by_stem[r["stem"]] = r
        if "url" in r and "art" in r:
            by_url[_norm_proza_url(r["url"])] = r["art"]
    return by_art, by_stem, by_url


def main(argv: list[str]) -> int:
    if not MANIFEST.exists():
        print(f"manifest not found: {MANIFEST}")
        return 2
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_art, by_stem, by_url = _build_manifest_lookups(manifest)

    force = "--force" in argv
    args = [a for a in argv if a != "--force"]

    # Mode selection.
    if "--pilot" in args:
        targets = [by_stem[s] for s in PILOT_STEMS if s in by_stem]
    elif "--all" in args:
        targets = manifest
    elif "--stem" in args:
        i = args.index("--stem")
        stems = args[i + 1:]
        targets = [by_stem[s] for s in stems if s in by_stem]
    else:
        targets = [by_art[a] for a in args if a in by_art]

    if not targets:
        print("No targets selected. Usage:")
        print("  python 3_transform.py <art> [<art> ...]")
        print("  python 3_transform.py --stem <YYYY_MM_DD_NNN> ...")
        print("  python 3_transform.py --pilot")
        print("  python 3_transform.py --all")
        return 1

    ZML_DIR.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    prompt = PROMPT_MD.read_text(encoding="utf-8")

    ok_count = 0
    for rec in targets:
        ok = transform_one(rec, prompt, by_url, force=force)
        if ok:
            ok_count += 1
        else:
            print(f"  ✗ failed for art={rec.get('art')} stem={rec.get('stem')}",
                  flush=True)
    print(f"\nDone: {ok_count}/{len(targets)} transformed", flush=True)
    return 0 if ok_count == len(targets) else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

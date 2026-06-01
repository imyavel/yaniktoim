"""yaniktoim post-check — LLM-аудит JSON статьи без перечитывания текста.

Цель — поймать ошибки классификации блоков (paragraph vs poem, missing
epigraph, проглоченный postscriptum, перепутаны h2 и paragraph и т.п.),
которые проходят посимвольную валидацию transform-а, но при этом
выглядят на сайте криво.

Архитектура — двухэтапная, но дешёвая:

  Этап 1 (skeleton-pass): питон строит для каждого блока статьи
  компактный «скелет» — тип, длина, число строк, CAPS-доля, превью
  первых и последних символов, флаги (есть ли ссылка / сноска). Это
  ~2 КБ JSON на статью, ничтожно по сравнению с самой статьёй. LLM
  даётся одна задача: вернуть JSON-массив подозрительных индексов
  с error-кодом и подсказанным типом. Если массив пустой — всё ок.

  Этап 2 (targeted-pass): пока НЕ реализован. Когда LLM пометит
  блок как подозрительный, можно будет отдельным проходом отдать
  ему полное тело блока + соседей и спросить «точно ли надо
  переклассифицировать». Сейчас этап 1 уже даёт превью — этого
  достаточно для первой ревизии оператором.

Usage:
  python src/7_postcheck.py 283
  python src/7_postcheck.py 081 169 350

Не правит JSON; результат — в `_logs/postcheck_<NNN>.json` + stdout.
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
import time
from pathlib import Path

# Force UTF-8 stdout — иначе Python 3.14 на Windows валится на → / Cyrillic
# в cp1251. Делаем до первого print().
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
JSON_DIR = ROOT / "json"
LOGS = ROOT / "_logs"

CLAUDE_EXE = r"C:\Users\admin\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude-code\2.1.149\claude.exe"

HEAD_CHARS = 80
TAIL_CHARS = 40
TAG_RX = re.compile(r"<[^>]+>")


def strip_html(s: str) -> str:
    """Drop HTML tags for the preview snippet so the model isn't distracted
    by `<a href=...>` boilerplate."""
    return TAG_RX.sub("", s or "")


def caps_ratio(text: str) -> float:
    """Fraction of alphabetic characters that are uppercase. Used as a
    heuristic flag — high CAPS-ratio inside a paragraph often signals
    a missed epigraph or a missed sub-heading."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    upper = sum(1 for c in letters if c.isupper())
    return round(upper / len(letters), 2)


def has_inline_link(html: str) -> bool:
    return "<a " in (html or "")


def has_inline_sup(html: str) -> bool:
    return "<sup" in (html or "")


def block_skeleton(blk: dict, idx: int, section_idx: int) -> dict:
    """Build one skeleton entry. Different block types contribute different
    fields, but the shape is uniform enough for the LLM to grok at a glance."""
    btype = blk.get("type", "?")
    out: dict = {
        "idx": idx,
        "section": section_idx,
        "type": btype,
    }
    if btype == "paragraph":
        txt = strip_html(blk.get("html", ""))
        out["len"] = len(txt)
        out["lines"] = txt.count("\n") + 1
        out["caps"] = caps_ratio(txt)
        out["head"] = txt[:HEAD_CHARS]
        out["tail"] = txt[-TAIL_CHARS:] if len(txt) > HEAD_CHARS else ""
        if has_inline_link(blk.get("html", "")):
            out["link"] = True
        if has_inline_sup(blk.get("html", "")):
            out["sup"] = True
    elif btype == "poem":
        lines = blk.get("lines") or []
        text = "\n".join(strip_html(ln) for ln in lines)
        out["lines_count"] = len(lines)
        out["nonblank"] = sum(1 for ln in lines if (ln or "").strip())
        out["len"] = len(text)
        out["caps"] = caps_ratio(text)
        out["head"] = strip_html((lines[0] if lines else ""))[:HEAD_CHARS]
        out["tail"] = strip_html((lines[-1] if lines else ""))[:TAIL_CHARS]
        avg_line = round(out["len"] / max(1, out["nonblank"]), 1) if out["nonblank"] else 0
        out["avg_line_len"] = avg_line
    elif btype == "epigraph":
        txt = strip_html(blk.get("html", ""))
        out["len"] = len(txt)
        out["lines"] = txt.count("\n") + 1
        out["caps"] = caps_ratio(txt)
        out["head"] = txt[:HEAD_CHARS]
        out["tail"] = txt[-TAIL_CHARS:] if len(txt) > HEAD_CHARS else ""
        if blk.get("cite"):
            out["cite"] = blk["cite"]
    elif btype == "music":
        out["label"] = blk.get("label") or ""
        out["performer"] = blk.get("performer") or ""
        out["title"] = blk.get("title") or ""
        out["has_url"] = bool(blk.get("raw_url"))
    else:
        # Unknown / future types — pass through what's there.
        out["raw_keys"] = list(blk.keys())
    return out


def build_article_skeleton(article: dict) -> dict:
    """Convert the article JSON into a flat list of block skeletons plus
    light metadata. The LLM sees this; it never sees full body text."""
    flat: list[dict] = []
    idx = 0
    for sec_i, sec in enumerate(article.get("sections", [])):
        if sec.get("heading"):
            flat.append({
                "idx": idx, "section": sec_i, "type": "h2",
                "head": strip_html(sec["heading"])[:HEAD_CHARS],
                "anchor": sec.get("anchor") or "",
            })
            idx += 1
        for blk in sec.get("blocks", []):
            flat.append(block_skeleton(blk, idx, sec_i))
            idx += 1
    return {
        "title": article.get("title", ""),
        "epigraph_count_top": len(article.get("epigraphs") or []),
        "music_blocks_top": len(article.get("music_blocks") or []),
        "footnote_count": len(article.get("footnotes") or []),
        "blocks": flat,
    }


PROMPT_HEADER = """Ты — пост-проверщик статей yaniktoim. Тебе дан компактный СКЕЛЕТ
статьи (без полного текста, только тип каждого блока + превью первых
~80 и последних ~40 символов + длина + CAPS-доля + флаги).

Найди подозрительные классификации блоков, которые формально валидируются
(текст 1:1), но логически неверны.

Конкретные паттерны, которые надо ловить:
- POEM_LOOKS_LIKE_PROSE: тип "poem", но строки длинные и однострочные →
   на самом деле это абзац прозы.
- P_LOOKS_LIKE_POEM: тип "paragraph", но текст явно состоит из коротких
   рифмованных строк (хотя в JSON он сохранился как один <p>… maybe это
   реже бывает в нашем JSON).
- MISSING_EPI: тип "paragraph" с очень высокой CAPS-долей (>0.7) и
   короткий — это, скорее всего, метка / шапка эпиграфа, или сам эпиграф,
   который LLM не обернул в EPI.
- LABEL_ONLY_EPI: тип "epigraph", но тело — только метка ("ЭПИГРАФ",
   "ЦИТАТА", "ПРЕДВАРЯЮЩАЯ МОЛИТВА") и больше ничего. Такой блок надо
   либо склеить с соседним EPI, либо удалить (метка добавляется
   рендером сама).
- TITLE_ECHO: тип "paragraph" со строкой, посимвольно совпадающей с
   полем "title" статьи (или почти совпадающей). Должен быть либо
   h2-подзаголовком, либо удалён.
- SEE_ALSO_TAIL: серия "paragraph" в конце статьи, каждый начинается
   с "См. также:" — это сноски/связи, а не основной текст. Помечать
   только если их подряд ≥2.
- DUPLICATE_BLOCK: соседние блоки с одинаковым содержанием.
- WRONG_TYPE_OTHER: что-то ещё, что выглядит криво (опиши коротко).

ВАЖНО:
- Будь консервативен. Если сомневаешься — не флагай.
- Каждое замечание — ОДНА строка JSON в итоговом массиве.
- НЕ предлагай правки текста, только переклассификацию блока.
- Если ничего не нашёл — верни ровно `[]` (пустой массив).

Формат ответа — строго JSON, без ```-обёрток, без пояснений до или после:

[
  {"idx": N, "current": "тип", "suggested": "новый тип ИЛИ drop ИЛИ merge_with:M",
   "code": "POEM_LOOKS_LIKE_PROSE", "reason": "одна короткая фраза"},
  ...
]

Если уверенности нет — массив пустой `[]`.

## Скелет статьи

"""


def call_claude(skel: dict, number: str) -> list[dict] | str:
    """Run headless claude with skeleton. Returns parsed findings array,
    or a raw string if parsing failed (caller decides what to do)."""
    body = json.dumps(skel, ensure_ascii=False, indent=2)
    full_prompt = PROMPT_HEADER + body + "\n"
    LOGS.mkdir(exist_ok=True)
    (LOGS / f"postcheck_prompt_{number}.txt").write_text(full_prompt, encoding="utf-8")
    cmd = [CLAUDE_EXE, "-p", "--model", "claude-opus-4-8",
           "--output-format", "json", "--max-turns", "1"]
    print(f"  [{number}] skeleton: {len(body)} chars, blocks: {len(skel['blocks'])}")
    t0 = time.time()
    proc = subprocess.run(cmd, input=full_prompt, capture_output=True,
                          text=True, encoding="utf-8")
    dur = time.time() - t0
    print(f"  [{number}] claude exit={proc.returncode} in {dur:.1f}s")
    if proc.returncode != 0:
        (LOGS / f"postcheck_{number}.stderr.txt").write_text(
            proc.stderr or "", encoding="utf-8")
        return f"<claude exit {proc.returncode}>"
    raw = proc.stdout.strip()
    try:
        envelope = json.loads(raw)
        inner = envelope.get("result", raw) if isinstance(envelope, dict) else raw
    except Exception:
        inner = raw
    # Strip ``` fences if any.
    inner = re.sub(r"^```(?:\w+)?\s*\n?", "", inner.strip())
    inner = re.sub(r"\n?```\s*$", "", inner)
    # Drop the inherited "[HH:MM] Tokens: …" telemetry tail.
    inner = re.sub(r"\n*\[\d{2}:\d{2}\]\s*Tokens:.*$", "", inner.strip())
    try:
        return json.loads(inner)
    except Exception as e:
        print(f"  [{number}] WARN: LLM reply isn't valid JSON ({e})")
        return inner


# ─────────────────── apply findings to JSON ────────────────────

# Map from finding code → канонический набор разрешённых suggested-значений.
# Применяем только то, что белом списке; всё прочее — лог и skip.
SUPPORTED_APPLY = {
    "LABEL_ONLY_EPI": {"drop", "drop_block", "delete"},
    "TITLE_ECHO":     {"h2", "subtitle"},
    "SEE_ALSO_TAIL":  {"see_also"},
}


def build_idx_map(article: dict) -> list[tuple[int, int] | None]:
    """Same traversal as build_article_skeleton — even h2-headings count as
    indices. Каждый idx маппится либо в (sec_i, blk_i) для блока, либо в
    None для виртуального h2-индекса (его править нельзя — это не блок)."""
    mp: list[tuple[int, int] | None] = []
    for sec_i, sec in enumerate(article.get("sections", [])):
        if sec.get("heading"):
            mp.append(None)
        for blk_i in range(len(sec.get("blocks", []))):
            mp.append((sec_i, blk_i))
    return mp


def apply_findings(article: dict, findings: list[dict], number: str) -> tuple[int, list[str]]:
    """Mutate article JSON based on findings. Returns (applied, notes)."""
    idx_map = build_idx_map(article)
    applied = 0
    notes: list[str] = []
    # Process drops in reverse-idx order to avoid index shift; type-change
    # operations don't shift, but для единообразия идём по убыванию idx.
    sorted_findings = sorted(
        [f for f in findings if isinstance(f, dict)],
        key=lambda f: -int(f.get("idx", -1)) if str(f.get("idx", "")).lstrip("-").isdigit() else -999,
    )
    for f in sorted_findings:
        idx = f.get("idx")
        code = f.get("code", "")
        sug = (f.get("suggested") or "").strip().lower()
        if not isinstance(idx, int) or idx < 0 or idx >= len(idx_map):
            notes.append(f"skip: bad idx {idx!r} ({code})")
            continue
        target = idx_map[idx]
        if target is None:
            notes.append(f"skip idx={idx}: it's a heading, not a block ({code})")
            continue
        if code not in SUPPORTED_APPLY:
            notes.append(f"skip idx={idx}: unsupported code {code}")
            continue
        if sug not in SUPPORTED_APPLY[code]:
            notes.append(f"skip idx={idx}: suggested '{sug}' not whitelisted for {code}")
            continue
        sec_i, blk_i = target
        block = article["sections"][sec_i]["blocks"][blk_i]
        if code == "LABEL_ONLY_EPI":
            del article["sections"][sec_i]["blocks"][blk_i]
            # idx_map is invalidated for later operations only if their idx is
            # in the SAME section AND > blk_i; since мы идём по убыванию, all
            # remaining operations target lower idx and are safe.
            # But we still must update idx_map для self-consistency:
            idx_map = build_idx_map(article)
            applied += 1
            notes.append(f"applied idx={idx}: drop label-only epigraph")
        elif code == "TITLE_ECHO":
            block["type"] = "subtitle"
            applied += 1
            notes.append(f"applied idx={idx}: paragraph → subtitle (title-echo)")
        elif code == "SEE_ALSO_TAIL":
            block["type"] = "see_also"
            applied += 1
            notes.append(f"applied idx={idx}: paragraph → see_also")
    return applied, notes


# ─────────────────── render chaining ────────────────────

def run_render(number: str) -> int:
    """Re-render NNN after JSON mutation. Returns rc."""
    # Canonical renderer is docs/editor/render.js via the Node build.
    cmd = ["node", str(ROOT / "tools" / "build.mjs"), number]
    print(f"  [{number}] render…")
    return subprocess.run(cmd, check=False).returncode


def main(argv: list[str]) -> int:
    apply = False
    render = False
    numbers: list[str] = []
    for a in argv:
        if a == "--apply":
            apply = True
        elif a == "--render":
            render = True
        elif a.startswith("--"):
            print(f"unknown flag: {a}", file=sys.stderr)
            return 2
        else:
            numbers.append(a)
    if not numbers:
        print("usage: python src/7_postcheck.py [--apply] [--render] <NNN> [<NNN> ...]",
              file=sys.stderr)
        return 2
    LOGS.mkdir(exist_ok=True)
    rc = 0
    for n in numbers:
        n3 = n.zfill(3)
        path = JSON_DIR / f"{n3}.json"
        if not path.exists():
            print(f"  [{n3}] MISSING json/{n3}.json — skip")
            rc = 1
            continue
        article = json.loads(path.read_text(encoding="utf-8"))
        skel = build_article_skeleton(article)
        (LOGS / f"postcheck_skel_{n3}.json").write_text(
            json.dumps(skel, ensure_ascii=False, indent=2), encoding="utf-8")
        findings = call_claude(skel, n3)
        out_path = LOGS / f"postcheck_{n3}.json"
        out_path.write_text(json.dumps(findings, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        if isinstance(findings, list):
            if not findings:
                print(f"  [{n3}] [OK] no findings — clean")
            else:
                print(f"  [{n3}] {len(findings)} finding(s):")
                for f in findings:
                    idx = f.get("idx", "?")
                    code = f.get("code", "?")
                    cur = f.get("current", "?")
                    sug = f.get("suggested", "?")
                    reason = f.get("reason", "")
                    print(f"    #{idx}  {cur} -> {sug}  [{code}]  {reason}")
                if apply:
                    backup = JSON_DIR / f"{n3}.before_postcheck.json"
                    if not backup.exists():
                        backup.write_text(json.dumps(article, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
                        print(f"    backup → json/{n3}.before_postcheck.json")
                    applied, notes = apply_findings(article, findings, n3)
                    path.write_text(json.dumps(article, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
                    print(f"  [{n3}] applied {applied}/{len(findings)} finding(s) to JSON")
                    for note in notes:
                        print(f"    · {note}")
                    if render:
                        rrc = run_render(n3)
                        if rrc != 0:
                            print(f"  [{n3}] ! render failed rc={rrc}")
                            rc = 1
        else:
            print(f"  [{n3}] ! malformed response — saved raw to {out_path}")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

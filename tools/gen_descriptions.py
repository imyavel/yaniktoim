"""Сгенерировать нейтрально-описательные meta-description для статей корпуса.

Для каждой docs/art/<art>.html берётся <title> + фрагмент текста и отправляется
в Opus 4.8 (headless `claude -p`). Ответ — СТРОГО JSON {"description": "..."};
поле вытаскивается регуляркой, поэтому любой хвост (напр. служебная строка
токенов из глобального CLAUDE.md) игнорируется.

Результаты складываются в descriptions.json инкрементально → повторный запуск
НЕ перегенерирует уже готовые (резюмируемо). Инъекцию в HTML делает отдельный
apply_seo.py.

  python tools/gen_descriptions.py --limit 3      # пилот на 3 статьях
  python tools/gen_descriptions.py --only art/654.html
  python tools/gen_descriptions.py --workers 4    # полный прогон, 4 параллельно
  python tools/gen_descriptions.py --regen art/654.html   # переgenerировать одну
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART_DIR = ROOT / "docs" / "art"
OUT = ROOT / "descriptions.json"
MAX_BODY = 3500          # символов текста статьи в промпт
MAX_DESC = 160           # целевой максимум длины описания

TITLE_RX = re.compile(r"<title>(.*?)</title>", re.S | re.I)
BODY_RX = re.compile(r"<body[^>]*>(.*)</body>", re.S | re.I)
SCRIPTSTYLE_RX = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
TAG_RX = re.compile(r"<[^>]+>")
WS_RX = re.compile(r"\s+")
DESC_FIELD_RX = re.compile(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', re.S)

PROMPT_TMPL = (
    "Ты пишешь мета-описание (тег description) для веб-страницы со статьёй.\n"
    "Стиль строго НЕЙТРАЛЬНО-ОПИСАТЕЛЬНЫЙ: что это за текст, в какой форме "
    "(статья, эссе, диалог, стихотворение, заметка и т.п.) и о чём он. "
    "Без рекламных крючков, без кавычек, без эмодзи, без многоточий в конце. "
    "По-русски. Одно-два предложения, СТРОГО не длиннее 160 символов.\n\n"
    "Заголовок: {title}\n\n"
    "Текст (фрагмент):\n{body}\n\n"
    'Верни СТРОГО JSON в одну строку и больше ничего: {{"description": "..."}}'
)


def extract(html: str) -> tuple[str, str]:
    mt = TITLE_RX.search(html)
    title = WS_RX.sub(" ", TAG_RX.sub("", mt.group(1)) if mt else "").strip()
    mb = BODY_RX.search(html)
    body = mb.group(1) if mb else html
    body = SCRIPTSTYLE_RX.sub(" ", body)
    body = WS_RX.sub(" ", TAG_RX.sub(" ", body)).strip()
    return title, body[:MAX_BODY]


def sanitize(desc: str) -> str:
    desc = WS_RX.sub(" ", desc).strip().strip('"').strip()
    if len(desc) > MAX_DESC + 10:           # мягкий предел + аккуратная обрезка
        cut = desc[:MAX_DESC]
        if " " in cut:
            cut = cut[: cut.rfind(" ")]
        desc = cut.rstrip(" ,.;—-")
    return desc


def call_claude(prompt: str) -> str:
    proc = subprocess.run(
        ["claude", "-p", "--model", "opus", "--output-format", "json"],
        input=prompt, capture_output=True, text=True, encoding="utf-8",
        shell=True, timeout=240,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude rc={proc.returncode}: {proc.stderr[:300]}")
    data = json.loads(proc.stdout)
    result = data.get("result", "")
    m = DESC_FIELD_RX.search(result)
    if not m:
        raise RuntimeError(f"no description in result: {result[:200]!r}")
    return sanitize(json.loads(f'"{m.group(1)}"'))


def gen_one(path: Path) -> tuple[str, str]:
    key = f"art/{path.name}"
    title, body = extract(path.read_text(encoding="utf-8"))
    prompt = PROMPT_TMPL.format(title=title, body=body)
    return key, call_claude(prompt)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="обработать только N статей")
    ap.add_argument("--only", action="append", default=[], help="только указанные art/NNN.html")
    ap.add_argument("--regen", action="append", default=[], help="перегенерировать указанные (игнор кэша)")
    ap.add_argument("--workers", type=int, default=1, help="параллельных вызовов")
    args = ap.parse_args()

    done: dict[str, str] = {}
    if OUT.exists():
        done = json.loads(OUT.read_text(encoding="utf-8"))

    regen = {f"art/{Path(x).name}" for x in args.regen}
    files = sorted(ART_DIR.glob("*.html"))
    if args.only:
        only = {Path(x).name for x in args.only}
        files = [f for f in files if f.name in only]
    todo = [f for f in files if f"art/{f.name}" not in done or f"art/{f.name}" in regen]
    if args.limit:
        todo = todo[: args.limit]

    print(f"Всего статей: {len(files)} · уже готово: {len(done)} · к генерации: {len(todo)}")
    if not todo:
        return 0

    ok = err = 0

    def save():
        OUT.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(gen_one, f): f for f in todo}
        for fut in as_completed(futs):
            f = futs[fut]
            try:
                key, desc = fut.result()
                done[key] = desc
                ok += 1
                print(f"[OK {ok+err}/{len(todo)}] {key} ({len(desc)}): {desc}")
                save()
            except Exception as e:  # noqa
                err += 1
                print(f"[ERR] {f.name}: {e}", file=sys.stderr)

    save()
    print(f"Готово. Успешно: {ok}, ошибок: {err}. Файл: {OUT}")
    return 0 if err == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

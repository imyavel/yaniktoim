"""LLM-переоценка дат публикации по корпусу через headless claude.exe -p (Opus 4.8).

Политика (согласована с оператором 2026-05-31):
  • Нужна САМАЯ РАННЯЯ дата авторства (когда автор написал/создал текст).
  • В корпусе смешаны форматы ДД.ММ.ГГ и ГГ.ММ.ДД. Якорь: дата авторства
    ВСЕГДА ≤ даты публикации в URL. Из двух трактовок берём ту, что ≤ URL и
    ближе к ней.
  • Если в «написано» две даты / диапазон — берём раннюю.
  • Игнор: даты внутри ссылок (proza.ru/stihi.ru/…), даты песен/фильмов,
    даты комментариев читателей, пометки «Музыка/добавлено», числовые
    перечисления и диапазоны, поздние «Дополнено/обновлено» (если есть дата
    создания раньше).
  • Нет настоящей даты авторства → null (потом откат на URL-дату).

Резюмируемо: результат каждого батча → _logs/redate/batch_NNN.json. Повтор
запуска пропускает уже готовые батчи.
"""
from __future__ import annotations
import io, sys, json, subprocess, time, re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "_logs" / "redate_input.json"
OUTDIR = ROOT / "_logs" / "redate"
OUTDIR.mkdir(exist_ok=True)

CLAUDE = r"C:\Users\admin\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude-code\2.1.156\claude.exe"
BATCH = 15

SYSTEM = """\
Ты — точный экстрактор ДАТ из русскоязычных статей (корпус proza.ru). Твоя
задача — НЕ выбирать одну дату, а НАЙТИ И КЛАССИФИЦИРОВАТЬ ВСЕ датовые
упоминания в каждой статье. Выбор итоговой даты сделает код по твоей разметке.

Для КАЖДОЙ даты в тексте укажи:
  • value  — нормализованная дата YYYY-MM-DD.
  • raw    — точная строка-источник из текста.
  • kind   — тип записи:
        "header"   — дата-заголовок в самом начале статьи (до/у названия);
        "written"  — у маркера «Написано/Сложено/Сочинено»;
        "recorded" — у маркера «Записано»;
        "created"  — у маркера «Создано/Дано/Рождено»;
        "range"    — концы диапазона авторства («18/04/20 - 03/01/21» → две
                     записи kind=range);
        "added"    — «Дополнено/обновлено/добавлено» (поздняя правка);
        "event"    — дата внутри прозы, описывающая СОБЫТИЕ/референс, часто
                     с сноской («…в Круге Жизни 17.03.2020*7…»), НЕ дата письма;
        "comment"  — дата комментария читателя («22.05.15 X написал(а):»);
        "media"    — дата песни/фильма/клипа («Часики (2019)», «Музыка …»);
        "url"      — дата внутри ссылки (proza.ru/2022/06/04/135, stihi.ru/…);
        "other"    — прочее.
  • role   — "authorship" (header/written/recorded/created/range) | "reference"
             (event/added/url/media/comment/other).

РАЗБОР НЕОДНОЗНАЧНОГО ФОРМАТА (важно): автор пишет и ДД.ММ.ГГ, и ГГ.ММ.ДД
(«21/11/15» = 2021-11-15, но «06.04.19» = 2019-04-06). Для числовых дат
перебери обе трактовки и для value возьми ту, что ≤ URL_DATE и БЛИЖЕ всего к
ней (дата написания всегда ≤ даты публикации). Двузначный год: 15→2015,
19→2019, 21→2021, 24→2024. Если обе трактовки > URL_DATE — это, скорее всего,
не дата авторства (пометь role=reference, kind=other).

Если в статье НЕТ ни одной даты — верни "dates": [].

ВЫВОД: только МИНИФИЦИРОВАННЫЙ JSON-массив, без markdown, без пояснений.
Каждый элемент:
{"number":"NNN","dates":[{"value":"YYYY-MM-DD","raw":"...","kind":"...","role":"authorship|reference"}],"note":"<кратко если спорно>"}
Порядок и состав number — РОВНО как во входе.
"""


def build_prompt(chunk: list[dict]) -> str:
    parts = [SYSTEM, "\n\n=== СТАТЬИ ===\n"]
    for r in chunk:
        parts.append(
            f"\n--- NUMBER {r['number']} | URL_DATE {r['url_date']} ---\n"
            f"{r['snippet']}\n"
        )
    parts.append("\n=== КОНЕЦ. Верни JSON-массив на "
                 f"{len(chunk)} элементов. ===")
    return "".join(parts)


def extract_json_array(text: str):
    """Вытащить первый JSON-массив из ответа.

    Headless-claude может дописать хвост (напр. токен-футер из CLAUDE.md
    «[HH:MM] Tokens: …»), поэтому берём первый валидный массив через
    raw_decode и игнорируем всё после него.
    """
    # 1) предпочесть содержимое ```json … ``` fence, если есть
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    if fence:
        return json.loads(fence.group(1))
    # 2) иначе — первый массив объектов «[{…» (минуя мусор вроде «[12:06]»)
    m = re.search(r"\[\s*\{", text)
    if not m:
        raise ValueError("no JSON array-of-objects in response")
    arr, _ = json.JSONDecoder().raw_decode(text[m.start():])
    return arr


def run_batch(chunk: list[dict], idx: int) -> list[dict]:
    prompt = build_prompt(chunk)
    cmd = [CLAUDE, "-p", "--model", "claude-opus-4-8",
           "--output-format", "json", "--max-turns", "3", "--tools", "none"]
    t0 = time.time()
    proc = subprocess.run(cmd, input=prompt, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    dt = time.time() - t0
    if proc.returncode != 0:
        (OUTDIR / f"batch_{idx:03d}.err.txt").write_text(
            f"exit={proc.returncode}\n=STDOUT=\n{proc.stdout}\n=STDERR=\n{proc.stderr}",
            encoding="utf-8")
        raise RuntimeError(f"batch {idx}: claude exit {proc.returncode}")
    j = json.loads(proc.stdout)
    res = j.get("result", "") if isinstance(j, dict) else ""
    arr = extract_json_array(res)
    print(f"  batch {idx:03d}: {len(arr)} items in {dt:.0f}s "
          f"(cost ${j.get('total_cost_usd', 0):.3f})", flush=True)
    return arr


def main() -> int:
    rows = json.loads(INPUT.read_text(encoding="utf-8"))
    chunks = [rows[i:i + BATCH] for i in range(0, len(rows), BATCH)]
    print(f"{len(rows)} articles -> {len(chunks)} batches of {BATCH}", flush=True)
    only = None
    if len(sys.argv) > 1:
        only = int(sys.argv[1])  # run a single batch index for testing
    for idx, chunk in enumerate(chunks):
        if only is not None and idx != only:
            continue
        outf = OUTDIR / f"batch_{idx:03d}.json"
        if outf.exists():
            print(f"  batch {idx:03d}: skip (done)", flush=True)
            continue
        arr = run_batch(chunk, idx)
        # минимальная валидация состава
        got = {str(x.get("number")) for x in arr}
        want = {r["number"] for r in chunk}
        if got != want:
            print(f"  WARN batch {idx:03d}: number mismatch "
                  f"missing={want - got} extra={got - want}", flush=True)
        outf.write_text(json.dumps(arr, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

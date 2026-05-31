"""Batch HTML runner for yaniktoim — прямая LLM-вёрстка (roadmap3).

Архитектура по образцу ZoharTGBatch:
  • батч = N статей, которые верстаются ПАРАЛЛЕЛЬНО (пул потоков, по одному
    blocking-claude на статью); per-article прогресс печатается с flush и
    стримится в gui ПОСТРОЧНО (gui читает наш stdout reader-потоком);
  • публикация (5_index + git push) — РОВНО ОДИН РАЗ за батч, когда все
    параллельные статьи готовы;
  • лимит (429) ловится по коду; есть время сброса — спим до него; нет —
    транзиент с анти-спам предохранителем (MAX_STALL);
  • graceful-stop кооперативный: кнопка Stop пишет флаг run_html.stop, раннер
    проверяет его МЕЖДУ батчами, доводит текущий батч и выходит чисто. Жёсткий
    kill (крестик окна) делает gui через taskkill /T /F.

raw/<stem>.html → docs/art/<art>.html (самодостаточный HTML, без ZML).
Переиспользует обвязку run_batch.py (lock/parse_reset/git) через импорт;
шаг вёрстки 3b_transform_html.py грузится как модуль и зовётся в потоках.

ВАЖНО: у этого раннера СВОЙ lock (run_html.lock) и state (state_html.json),
чтобы не конфликтовать со старым ZML-раннером run_batch.py.

Usage (из корня yaniktoim/):
  python batch_runner/run_batch_html.py                  # весь корпус
  python batch_runner/run_batch_html.py --section best   # один раздел
  python batch_runner/run_batch_html.py --limit 10       # сколько статей
  python batch_runner/run_batch_html.py --numbers 215,299 # ровно эти
  python batch_runner/run_batch_html.py --dry-run        # показать очередь
  python batch_runner/run_batch_html.py --no-push        # не пушить
  python batch_runner/run_batch_html.py --batch-size 5   # размер пачки
"""
from __future__ import annotations
import argparse
import datetime as dt
import importlib.util
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Импортируем проверенную обвязку из соседнего ZML-раннера. Его main() висит
# под __main__, поэтому import побочных эффектов не вызывает.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_batch as rb  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ART_DIR = ROOT / "docs" / "art"
MANIFEST = ROOT / "manifest.json"

# Шаг вёрстки (3b_transform_html.py) грузим как МОДУЛЬ (имя файла с цифры —
# обычный import невозможен) и зовём transform_one() в потоках-воркерах. Так
# per-article прогресс печатается прямо в наш stdout → gui стримит построчно.
_th_spec = importlib.util.spec_from_file_location(
    "transform_html", SRC / "3b_transform_html.py")
th = importlib.util.module_from_spec(_th_spec)
_th_spec.loader.exec_module(th)  # noqa: E402

# СВОИ lock/state/log/stop — не пересекаются с ZML-раннером.
STATE = HERE / "state_html.json"
LOCK = HERE / "run_html.lock"
STOP_FLAG = HERE / "run_html.stop"  # кооперативный graceful-stop (пишет gui)

DEFAULT_BATCH_SIZE = rb.DEFAULT_BATCH_SIZE
SECTION_ORDER = rb.SECTION_ORDER

# Анти-спам. Если батчи идут без прогресса (429 без распарсенного времени
# сброса, либо просто ничего не построилось) — ретраим, но не бесконечно:
# MAX_STALL итераций подряд без прогресса → аварийное завершение. Именно
# отсутствие такого предохранителя дало «холостой пробег» на 251 статью.
MAX_STALL = 5
TRANSIENT_BACKOFF_S = 60  # пауза перед ретраем 429 без времени сброса

# Подменяем модульные пути run_batch на наши, чтобы переиспользуемые
# lock/state-функции работали с нашими файлами, а не с ZML-раннеровскими.
rb.LOCK = LOCK
rb.STATE = STATE


# ---------- queue (по docs/art/<art>.html, а не json/<NNN>.json) ----------

def _is_built(art: str) -> bool:
    """Статья считается готовой, если есть docs/art/<art>.html И это НОВАЯ
    страница (содержит data-scheme — маркер нашего HTML-пайплайна). Старые
    ZML-страницы без data-scheme → перевёрстываем заново."""
    p = ART_DIR / f"{art}.html"
    if not p.exists():
        return False
    # data-scheme живёт на <body>, но перед ним — большой инлайн <style> в
    # <head>, поэтому читаем весь файл (страница ~30-50 КБ, дёшево).
    try:
        return "data-scheme=" in p.read_text(encoding="utf-8")
    except OSError:
        return False


def _seam_articles(manifest: list[dict]) -> list[str]:
    """Арт-id на стыках разделов: последняя статья каждого раздела и первая
    следующего. Именно у них prev/next ведёт в СОСЕДНИЙ раздел, поэтому при
    правке кросс-секционной навигации их нужно перевёрстывать в первую очередь
    (концы корпуса — первая best и последняя other — сюда НЕ входят: их nav
    не меняется)."""
    buckets: dict[str, list[dict]] = {}
    for r in manifest:
        sec = r.get("section")
        if sec and isinstance(r.get("section_order"), int) and r.get("art"):
            buckets.setdefault(sec, []).append(r)
    for sec in buckets:
        buckets[sec].sort(key=lambda r: r["section_order"])
    present = [s for s in SECTION_ORDER if buckets.get(s)]
    seams: list[str] = []
    for i in range(len(present) - 1):
        seams.append(buckets[present[i]][-1]["art"])      # последняя текущего
        seams.append(buckets[present[i + 1]][0]["art"])   # первая следующего
    seen: set[str] = set()
    return [a for a in seams if not (a in seen or seen.add(a))]


def pending_articles(manifest: list[dict], section: str | None,
                     limit: int | None) -> list[str]:
    """Очередь арт-id в порядке разделов (SECTION_ORDER) и section_order
    внутри. Пропускаем уже построенные (новые) страницы.

    Непостроенные СТЫКОВЫЕ статьи (в т.ч. только что удалённые ради
    перевёрстки кросс-секционной навигации) идут ПЕРВЫМИ — чтобы соседские
    ссылки появились уже в первом батче."""
    sections = [section] if section else SECTION_ORDER
    front: list[str] = []
    if section is None:
        front = [a for a in _seam_articles(manifest) if not _is_built(a)]
    front_set = set(front)
    out: list[str] = list(front)
    for sec in sections:
        rows = [r for r in manifest if r.get("section") == sec and r.get("art")]
        rows.sort(key=lambda x: x.get("section_order", 9999))
        for r in rows:
            art = r["art"]
            if art in front_set or _is_built(art):
                continue
            out.append(art)
            if limit and len(out) >= limit:
                return out
    return out


def pick_by_numbers(manifest: list[dict], raw: str) -> list[str]:
    """--numbers '215,299' → арт-id этих статей (по полю number)."""
    by_number = {r["number"]: r for r in manifest if r.get("number")}
    queue: list[str] = []
    for token in raw.split(","):
        t = token.strip()
        if not t:
            continue
        n = t.zfill(3)
        rec = by_number.get(n)
        if not rec or not rec.get("art"):
            rb.log(f"WARN: --numbers {n} — нет в manifest или без art, пропуск")
            continue
        art = rec["art"]
        if _is_built(art):
            rb.log(f"NOTE: --numbers {n} (art={art}) уже построен, пропуск "
                   f"(удалите docs/art/{art}.html чтобы пересобрать)")
            continue
        queue.append(art)
    return queue


# ---------- cooperative stop ----------

def _stop_requested() -> bool:
    """Graceful-стоп: флаг-файл (его пишет кнопка Stop в gui) ИЛИ сигнал.
    Проверяется между батчами — текущий батч доводится до конца и пушится."""
    return STOP_FLAG.exists() or rb._shutdown_requested


# ---------- parallel batch (потоки-воркеры, каждый = blocking claude) ----------

def run_batch_parallel(batch: list[str], by_art: dict[str, dict],
                       base_prompt: str, manifest: list[dict]) -> list:
    """Сверстать батч ПАРАЛЛЕЛЬНО (по одному потоку на статью). Возвращает
    list[ArtResult]. Воркеры пишут только в свои файлы (art/img/_logs) —
    гонок нет; их [art]-прогресс с flush стримится в gui построчно."""
    def work(art: str):
        rec = by_art.get(art)
        if rec is None:
            return th.ArtResult(art, "fail", "нет записи в manifest")
        try:
            return th.transform_one(rec, base_prompt, manifest)
        except Exception as e:  # воркер не должен ронять весь батч
            rb.log(f"  ! [{art}] worker crashed: {e!r}")
            return th.ArtResult(art, "fail", repr(e))

    results: list = []
    with ThreadPoolExecutor(max_workers=max(1, len(batch)),
                            thread_name_prefix="verst") as ex:
        futs = {ex.submit(work, a): a for a in batch}
        for fut in as_completed(futs):
            results.append(fut.result())
    return results


# ---------- main loop ----------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--section", help="ограничить разделом")
    ap.add_argument("--limit", type=int, help="макс статей в этом запуске")
    ap.add_argument("--numbers", help="ровно эти номера через запятую")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                    help=f"размер пачки (default: {DEFAULT_BATCH_SIZE})")
    ap.add_argument("--dry-run", action="store_true", help="только очередь")
    ap.add_argument("--no-push", action="store_true", help="не делать git push")
    args = ap.parse_args()

    if not rb.acquire_lock():
        return 3
    rb._install_signal_handlers()
    try:
        return _run(args)
    finally:
        rb.release_lock()


def _run(args: argparse.Namespace) -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.numbers:
        if args.section or args.limit:
            rb.log("NOTE: --numbers overrides --section/--limit")
        pending = pick_by_numbers(manifest, args.numbers)
        mode = f"numbers={args.numbers}"
    else:
        pending = pending_articles(manifest, args.section, args.limit)
        mode = f"section={args.section or 'any'}"
    rb.log(f"START(html) · pid={os.getpid()} · pending={len(pending)} · "
           f"batch_size={args.batch_size} · {mode}")

    if not pending:
        rb.log("Nothing to do.")
        return 0
    if args.dry_run:
        rb.log(f"DRY RUN: {pending}")
        return 0

    # git_pull перед прогоном отключён: рабочее дерево обычно с незакоммиченными
    # изменениями (новые страницы/скрипты), из-за чего pull --rebase падал rc=128
    # без пользы. Синхронизацию с remote, если нужна, делаем вручную/при push.
    # if not args.no_push:
    #     rb.git_pull()

    base_prompt = th.PROMPT_MD.read_text(encoding="utf-8")
    by_art = {r["art"]: r for r in manifest if r.get("art")}
    STOP_FLAG.unlink(missing_ok=True)  # снять возможный устаревший флаг

    state = rb.load_state()
    i = 0
    stall = 0  # подряд батчей без единого успеха (анти-спам)
    while i < len(pending):
        if _stop_requested():
            rb.log("STOP (graceful) — выходим перед следующим батчем")
            break

        batch = pending[i:i + args.batch_size]
        rb.log(f"BATCH start ({len(batch)} параллельно): {' '.join(batch)}")
        results = run_batch_parallel(batch, by_art, base_prompt, manifest)

        # 1. Жёсткий auth/quota-отказ (401/403/…) — авария.
        for r in results:
            m = rb.FATAL_RX.search(r.detail or "")
            if m:
                rb.log(f"FATAL: {m.group(0)} ({r.art}) — abort")
                return 2

        # 2. Прогресс батча. ok включает skip уже построенных — это НЕ стоп-стол.
        ok_now = [r.art for r in results if r.ok]
        done_now = [a for a in ok_now if a not in state["done"]]
        failed_now = [r.art for r in results if r.kind == "fail"]
        limit_now = [r for r in results if r.kind == "limit"]
        state["done"].extend(done_now)
        for a in failed_now:
            if a not in state["failed"]:
                state["failed"].append(a)
        rb.save_state(state)
        if ok_now:
            stall = 0

        # 3. Публикация — РОВНО один раз за батч (индексы + push), если что-то
        #    новое построилось.
        if done_now:
            if rb.rebuild_indices():
                if not args.no_push:
                    rb.git_push(
                        f"html: +{len(done_now)} ({done_now[0]}..{done_now[-1]})")
            else:
                rb.log("SKIP push — index rebuild failed")
        if failed_now:
            rb.log(f"FAILED in batch: {failed_now}")

        # 4. Лимит (429) — у кого-то в батче. Успехи уже сохранены/запушены;
        #    ретраим ТОТ ЖЕ батч (построенные скипнутся быстро).
        if limit_now:
            detail = limit_now[0].detail
            reset = rb.parse_reset(detail)
            if reset:
                wait = (reset - dt.datetime.now()).total_seconds() + 60
                rb.log(f"429 LIMIT ({len(limit_now)} шт.) · sleep {int(wait)}s "
                       f"until {reset.isoformat(timespec='minutes')}")
                rb._interruptible_sleep(max(60.0, wait))
                stall = 0  # легитимное ожидание сброса — не спам
                if _stop_requested():
                    rb.log("STOP во время ожидания лимита — выходим")
                    break
                continue  # retry same i
            # 429 без распарсенного времени → транзиент. Ретрай, но не бесконечно.
            stall += 1
            rb.log(f"429 без времени сброса · попытка {stall}/{MAX_STALL}")
            if stall >= MAX_STALL:
                rb.log(f"FATAL: спам-защита — 429 без сброса {MAX_STALL} раз "
                       "подряд, аварийное завершение")
                return 2
            rb._interruptible_sleep(TRANSIENT_BACKOFF_S)
            if _stop_requested():
                rb.log("STOP во время backoff — выходим")
                break
            continue  # retry same i

        # 5. Нет лимита, но и ни одного успеха (чистые fail) — анти-спам.
        if not ok_now:
            stall += 1
            rb.log(f"батч без прогресса · {stall}/{MAX_STALL}")
            if stall >= MAX_STALL:
                rb.log(f"FATAL: спам-защита — {MAX_STALL} батчей подряд без "
                       "прогресса, аварийное завершение")
                return 2

        i += args.batch_size

    STOP_FLAG.unlink(missing_ok=True)
    rb.log(f"DONE(html) · built={len(state['done'])} · "
           f"failed={len(state['failed'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

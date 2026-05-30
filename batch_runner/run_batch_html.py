"""Batch HTML runner for yaniktoim — прямая LLM-вёрстка (roadmap3).

Прогоняет корпус через src/3b_transform_html.py пачками по BATCH_SIZE:
raw/<stem>.html → docs/art/<art>.html (самодостаточный HTML, без ZML).
После успешного батча — 5_index (пересборка индексов) + git push (опц).
При «hit your limit» — спит до сброса и повторяет батч.

Переиспользует проверенную обвязку run_batch.py (lock/signals/hit-limit/
git) через импорт; новое здесь — очередь по docs/art/<art>.html, шаг
трансформации (3b_transform_html.py) и публикация без build.mjs.

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
import json
import os
import sys
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

# СВОИ lock/state/log — не пересекаются с ZML-раннером.
STATE = HERE / "state_html.json"
LOCK = HERE / "run_html.lock"

DEFAULT_BATCH_SIZE = rb.DEFAULT_BATCH_SIZE
SECTION_ORDER = rb.SECTION_ORDER

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


def pending_articles(manifest: list[dict], section: str | None,
                     limit: int | None) -> list[str]:
    """Очередь арт-id в порядке разделов (SECTION_ORDER) и section_order
    внутри. Пропускаем уже построенные (новые) страницы."""
    sections = [section] if section else SECTION_ORDER
    out: list[str] = []
    for sec in sections:
        rows = [r for r in manifest if r.get("section") == sec and r.get("art")]
        rows.sort(key=lambda x: x.get("section_order", 9999))
        for r in rows:
            art = r["art"]
            if _is_built(art):
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


# ---------- transform step (3b_transform_html.py) ----------

def run_transform(arts: list[str]) -> tuple[bool, str]:
    """Перевести батч статей в HTML. (success, combined_output).
    3b_transform_html.py сам имеет ретрай и пробрасывает «hit your limit»
    в stdout — мы его ловим в combined_output как и ZML-раннер."""
    import subprocess
    cmd = [sys.executable, "-X", "utf8",
           str(SRC / "3b_transform_html.py")] + arts
    rb.log(f"HTML-TRANSFORM start: {' '.join(arts)}")
    timeout_s = 900 * max(1, len(arts))  # ~5-15 мин/статья + ретрай
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or "") + "\n" + (e.stderr or "")
               if hasattr(e, "stdout") else "")
        rb.log(f"HTML-TRANSFORM TIMEOUT after {timeout_s}s")
        return False, out + f"\n[run_batch_html] timeout after {timeout_s}s\n"
    out = (proc.stdout or "") + "\n--- STDERR ---\n" + (proc.stderr or "")
    rb.log(f"HTML-TRANSFORM exit={proc.returncode}")
    return proc.returncode == 0, out


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

    state = rb.load_state()
    i = 0
    while i < len(pending):
        if rb._shutdown_requested:
            rb.log("SHUTDOWN requested — stopping before next batch")
            break

        batch = pending[i:i + args.batch_size]
        ok, out = run_transform(batch)

        # 1. Hard auth/quota failure — abort.
        m = rb.FATAL_RX.search(out)
        if m:
            rb.log(f"FATAL: {m.group(0)} — abort")
            return 2

        # 2. Hit limit — sleep until reset, retry SAME batch.
        if rb.HIT_LIMIT_RX.search(out):
            reset = rb.parse_reset(out)
            if reset:
                wait = (reset - dt.datetime.now()).total_seconds() + 60
                rb.log(f"HIT LIMIT · sleep {int(wait)}s until "
                       f"{reset.isoformat(timespec='minutes')}")
                rb._interruptible_sleep(max(60.0, wait))
            else:
                rb.log("HIT LIMIT · no reset time parsed, sleep 5h")
                rb._interruptible_sleep(5 * 3600)
            if rb._shutdown_requested:
                rb.log("SHUTDOWN during hit-limit sleep — stopping")
                break
            continue  # retry same i

        # 3. Какие реально построились (файл есть И data-scheme внутри).
        done_now = [a for a in batch if _is_built(a) and a not in state["done"]]
        failed_now = [a for a in batch if not _is_built(a)]
        state["done"].extend(done_now)
        for a in failed_now:
            if a not in state["failed"]:
                state["failed"].append(a)
        rb.save_state(state)

        # 4. Публикация: индексы + push (без build.mjs — страницы уже готовы).
        if done_now:
            index_ok = rb.rebuild_indices()
            if index_ok:
                if not args.no_push:
                    rb.git_push(
                        f"html: +{len(done_now)} ({done_now[0]}..{done_now[-1]})")
            else:
                rb.log("SKIP push — index rebuild failed")

        if failed_now:
            rb.log(f"FAILED in batch (нет html/data-scheme): {failed_now}")

        i += args.batch_size

    rb.log(f"DONE(html) · built={len(state['done'])} · "
           f"failed={len(state['failed'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

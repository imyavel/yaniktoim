# batch_runner — план обработки результата аудита

**Создан:** 2026-05-26 21:44, после headless `claude.exe -p --model claude-opus-4-8` аудита.

## Где мы сейчас

- Базовая система `batch_runner/` собрана и запушена в `imyavel/yaniktoim` (commit `24ba502` + последующие). Файлы: `run_batch.py`, `gui.pyw`, `README.md`.
- Прогнан **первый продакшн-batch** руками: 8 статей из best (#169, #081, #170, #283, #215, #299, #195, #234) трансформированы за ~33 минуты, отрендерены, индексы пересобраны, на сайте. На gh-pages 10/32 best кликабельны, остальные серые pending.
- **Сам `batch_runner` ещё ни разу не запускался** оператором — ни CLI, ни GUI.
- Проведён аудит через `python _logs/run_audit.py` (headless `claude.exe -p --model claude-opus-4-8 --output-format json --max-turns 30 --add-dir C:\Users\admin\ZoharTGBatch --add-dir C:\Users\admin\yaniktoim`), 120s, exit=0. Прочитаны все 6 файлов: `run_batch.py`, `gui.pyw`, `README.md`, плюс эталон — `main.py`, `orchestrator.py`, `gui.pyw` из `ZoharTGBatch`. 10 находок с привязкой к конкретным строкам эталона.

## Где лежит аудит

- **`_logs/audit_prompt.md`** — текст промпта (3.6 KB).
- **`_logs/audit_raw.txt`** — сырой stdout+stderr subprocess'а (отладочно).
- **`_logs/audit_result.json`** — полный JSON-ответ headless claude (8.4 KB).
- **`_logs/audit_result.md`** — выжимка `.result` из JSON, **читать ЭТО** (4.7 KB, 10 находок + summary-таблица).
- **`_logs/run_audit.py`** — лаунчер (можно перезапускать для повторного аудита).

## Сводка находок (полный текст в audit_result.md)

| # | Приоритет | Файл | Суть | Эталон в ZoharTGBatch |
|---|---|---|---|---|
| 1 | **CRITICAL** | run_batch.py | нет `signal.signal(SIGBREAK/SIGINT)` handler — `CTRL_BREAK_EVENT` из GUI обрывает subprocess посреди итерации | `main.py:125-137` |
| 2 | **CRITICAL** | run_batch.py + gui.pyw | нет lockfile / single-instance guard — двойной запуск сожжёт двойную квоту и подерётся за `json/NNN.json` | `current_run.json` как state-lock |
| 3 | HIGH | run_batch.py:49-53 | `HIT_LIMIT_RX` и `HIT_RESET_RX` разделены — orchestrator.py делает один regex с `re.DOTALL`; плюс не парсится UTC → сон по локалу (Москва ≠ UTC) | `orchestrator.py` HIT_LIMIT_RX |
| 4 | HIGH | run_batch.py:154 | `git add -A` в `site/` без `.gitignore` — случайный мусор уедет в публичный gh-pages | — |
| 5 | HIGH | run_batch.py:220-221 | `done_now` определяется по `exists()`, без `json.loads`-валидации — частично записанный мусор будет отмечен success | — |
| 6 | MEDIUM | run_batch.py:144,149 | `rebuild_indices` / `run_render` — `check=False`, rc не проверяется → push частичного сайта при сбое рендера | — |
| 7 | MEDIUM | gui.pyw:439 | Tk Text без trim — на 350 статей сотни тысяч строк лога, фриз UI | — |
| 8 | MEDIUM | gui.pyw:412 | в `_refresh_buttons` дисэйблится только `section_combo`, остальные параметры (`limit`, `batch-size`, `no-push`) активны во время прогона | — |
| 9 | LOW | run_batch.py:42,69-70 | `batch.log` append-only без ротации, растёт неограниченно | `main.py:34-38` (RotatingFileHandler) |
| 10 | LOW | run_batch.py:108-123 | `parse_reset` — частный случай п.3, без явного UTC/TZ | — |

## Что дальше

1. **Оператор** просмотрит `_logs/audit_result.md`, решит:
   - какие пункты чинить сразу (CRITICAL 1–2 + HIGH 3–5 — рекомендую);
   - какие отложить (MEDIUM/LOW — после первой реальной прогонки);
   - что игнорировать.
2. **После решения** — внесу правки одной серией коммитов, по одному пункту = один коммит. Для п.1 и п.3 шаблон можно копировать прямо из эталона ZoharTGBatch (`main.py:125-137`, `orchestrator.py` HIT_LIMIT_RX).
3. После фиксов — оператор открывает `batch_runner/gui.pyw` и пробует реальный прогон (например `--section best --limit 5`).
4. По итогам тестового прогона — если что-то ещё вылезет, новая итерация аудита (`python _logs/run_audit.py`, `audit_result.md` перезапишется автоматически).

## Параллельный фон

В текущий момент (21:44) **ничего не крутится** в фоне. Все batch'и завершены. Можно запускать `batch_runner` без риска коллизий.

---

**Этот файл:** `C:\Users\admin\yaniktoim\batch_runner\PLAN.md`
**Аудит читать:** `C:\Users\admin\yaniktoim\_logs\audit_result.md`
**Лаунчер аудита:** `C:\Users\admin\yaniktoim\_logs\run_audit.py`

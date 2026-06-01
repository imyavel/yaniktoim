"""yaniktoim batch_runner GUI — простая обёртка над run_batch_html.py.

Двойной клик по этому файлу запускает приложение через pythonw.exe (без
чёрной консоли). Окно одно:
  • Сверху — параметры запуска (section / limit / batch-size / no-push).
  • Посредине — лог субпроцесса run_batch.py.
  • Снизу — статусная строка с PID/состоянием.

Кнопки Start/Stop. Stop = terminate() субпроцессу — он на следующей
итерации цикла сохранит state.json и выйдет, либо при Force на закрытие
окна — kill.

По образцу ZoharTGBatch/gui.pyw, но в один файл и без .env / Telegram /
параллелизма.
"""
from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
# HTML-пайплайн (roadmap3): GUI запускает run_batch_html.py (прямая
# LLM-вёрстка raw→docs/art/<art>.html). Старый ZML-раннер run_batch.py
# заморожен и здесь не используется.
RUN_BATCH = HERE / "run_batch_html.py"
STATE_FILE = HERE / "state_html.json"
LOCK_FILE = HERE / "run_html.lock"
STOP_FILE = HERE / "run_html.stop"  # кооперативный graceful-stop (читает раннер)
LOG_FILE_FMT = HERE / "gui_{}.log"
MANIFEST = PROJECT_ROOT / "manifest.json"

POLL_LOG_MS = 100
POLL_STATE_MS = 1000

# Cap on lines kept in the Tk Text widget — at ~50 lines/article × 350 articles
# the naive append-forever path drags Tk into multi-hundred-ms freezes.
LOG_TRIM_MAX = 5000
LOG_TRIM_DROP = 1000

SECTION_ORDER = [
    ("any",      "(все разделы)"),
    ("best",     "Избранное"),
    ("dreamon",  "Мечтай!!"),
    ("cyberson", "Киберсон"),
    ("dabudet",  "Да будет Свет!"),
    ("confront", "Конфронтология Духа"),
    ("shoshana", "Роза Среди Шипов"),
    ("other",    "Без категории"),
]

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def _pid_alive(pid: int) -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, check=False,
            creationflags=CREATE_NO_WINDOW,
        ).stdout
        return str(pid) in out
    except Exception:
        return False


def _lock_owner_pid() -> int | None:
    """Return live PID owning the lock, or None if free / stale."""
    if not LOCK_FILE.exists():
        return None
    try:
        prev = LOCK_FILE.read_text(encoding="ascii").strip()
        pid = int(prev) if prev.isdigit() else 0
    except Exception:
        return None
    if pid and _pid_alive(pid):
        return pid
    return None


# ---------------------------------------------------------------------------
# Subprocess management
# ---------------------------------------------------------------------------

def _python_exe() -> str:
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        cand = exe[: -len("pythonw.exe")] + "python.exe"
        if Path(cand).is_file():
            return cand
    return exe


class BatchProcess:
    def __init__(self, log_queue: "queue.Queue[str | None]") -> None:
        self.proc: subprocess.Popen | None = None
        self.log_queue = log_queue
        self._reader: threading.Thread | None = None

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, args: list[str]) -> None:
        if self.is_running():
            return
        # Снять возможный устаревший стоп-флаг (если прошлый раннер упал, не
        # сняв его) — иначе новый прогон остановится на первом же батче.
        try:
            STOP_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        cmd = [_python_exe(), "-u", str(RUN_BATCH)] + args
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
        )
        self._reader = threading.Thread(
            target=self._read_loop, name="batch-reader", daemon=True,
        )
        self._reader.start()

    def _read_loop(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        try:
            for line in self.proc.stdout:
                self.log_queue.put(line)
        except Exception as e:
            self.log_queue.put(f"[gui] reader error: {e!r}\n")
        finally:
            # proc may have been killed and cleared by stop_force; guard wait().
            rc: int | str
            try:
                rc = self.proc.wait() if self.proc else "?"
            except Exception as e:
                rc = f"wait-failed:{e!r}"
            self.log_queue.put(f"\n[gui] процесс завершён, exit={rc}\n")
            self.log_queue.put(None)

    def stop_graceful(self) -> bool:
        """Кооперативный graceful-stop: пишем флаг-файл, раннер увидит его
        МЕЖДУ батчами, доведёт текущий батч (с пушем) и выйдет сам. Консольные
        сигналы (Ctrl-Break) под pythonw не доставляются — потому флаг."""
        if not self.is_running():
            return False
        try:
            STOP_FILE.write_text("stop", encoding="utf-8")
            return True
        except OSError:
            return False

    def stop_force(self) -> None:
        if not self.is_running():
            return
        # proc.kill() убивает ТОЛЬКО раннер-родитель, а его дети
        # (3b_transform_html.py → claude.exe) остаются сиротами и держат
        # работу. На Windows валим всё дерево через taskkill /T /F.
        pid = self.proc.pid
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True, timeout=10,
                )
            except Exception:
                pass
        try:
            self.proc.kill()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Clipboard / context menu — Ctrl+C/V/X/A by keycode (locale-independent)
# ---------------------------------------------------------------------------

_KC = {67: "<<Copy>>", 86: "<<Paste>>", 88: "<<Cut>>"}
_KC_SELECT_ALL = 65


def _is_entry(w: tk.Misc) -> bool:
    try:
        return w.winfo_class() in ("TEntry", "Entry")
    except tk.TclError:
        return False


def _is_text(w: tk.Misc) -> bool:
    try:
        return w.winfo_class() == "Text"
    except tk.TclError:
        return False


def _select_all(w: tk.Misc) -> None:
    try:
        if _is_entry(w):
            w.select_range(0, "end"); w.icursor("end")
        elif _is_text(w):
            w.tag_add("sel", "1.0", "end-1c"); w.mark_set("insert", "end-1c")
        w.focus_set()
    except tk.TclError:
        pass


def _on_ctrl(event: tk.Event) -> str | None:
    v = _KC.get(event.keycode)
    if v:
        try: event.widget.event_generate(v)
        except tk.TclError: return None
        return "break"
    if event.keycode == _KC_SELECT_ALL:
        _select_all(event.widget); return "break"
    return None


def _install_clipboard(root: tk.Misc) -> None:
    for cls in ("TEntry", "Entry", "Text"):
        root.bind_class(cls, "<Control-KeyPress>", _on_ctrl)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("yaniktoim — batch transform")
        root.geometry("960x640")
        root.minsize(720, 480)

        self.log_queue: queue.Queue[str | None] = queue.Queue()
        self.batch = BatchProcess(self.log_queue)

        # mirror log to file (per-day, append)
        self.log_path = LOG_FILE_FMT.with_name(
            LOG_FILE_FMT.name.format(time.strftime("%y%m%d")))
        try:
            with open(self.log_path, "a", encoding="utf-8", newline="\n") as f:
                f.write(f"[gui] === yaniktoim GUI started "
                        f"{time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        except Exception:
            self.log_path = None

        _install_clipboard(root)
        self._build_ui()
        self._refresh_buttons()

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(POLL_LOG_MS, self._pump_log)
        root.after(POLL_STATE_MS, self._poll_state)

    # ----- UI -----

    def _build_ui(self) -> None:
        # Top: params
        top = ttk.Frame(self.root); top.pack(fill="x", padx=8, pady=(8, 4))

        ttk.Label(top, text="Раздел:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.section_var = tk.StringVar(value="(все разделы)")
        self.section_combo = ttk.Combobox(
            top, textvariable=self.section_var,
            values=[label for _, label in SECTION_ORDER],
            state="readonly", width=24,
        )
        self.section_combo.grid(row=0, column=1, sticky="w", padx=(0, 16))

        ttk.Label(top, text="Лимит:").grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.limit_var = tk.StringVar(value="")
        self.limit_entry = ttk.Entry(top, textvariable=self.limit_var, width=8)
        self.limit_entry.grid(row=0, column=3, sticky="w", padx=(0, 16))

        ttk.Label(top, text="Размер пачки:").grid(row=0, column=4, sticky="w", padx=(0, 6))
        self.batch_size_var = tk.StringVar(value="5")
        self.batch_size_entry = ttk.Entry(
            top, textvariable=self.batch_size_var, width=6)
        self.batch_size_entry.grid(row=0, column=5, sticky="w", padx=(0, 16))

        self.no_push_var = tk.BooleanVar(value=False)
        self.no_push_check = ttk.Checkbutton(
            top, text="--no-push", variable=self.no_push_var)
        self.no_push_check.grid(row=0, column=6, sticky="w", padx=(0, 16))

        # Row 1: explicit articles by number (overrides section/limit).
        ttk.Label(top, text="Номера:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(6, 0))
        self.numbers_var = tk.StringVar(value="")
        self.numbers_entry = ttk.Entry(top, textvariable=self.numbers_var, width=40)
        self.numbers_entry.grid(row=1, column=1, columnspan=5, sticky="we", padx=(0, 16), pady=(6, 0))
        ttk.Label(top, text="напр. 283 или 283,310,367 — игнорирует Раздел/Лимит",
                  foreground="#888").grid(row=1, column=6, columnspan=2,
                                           sticky="w", pady=(6, 0))

        self.btn_start = ttk.Button(top, text="Start", command=self._on_start, width=10)
        self.btn_start.grid(row=0, column=7, sticky="e", padx=(8, 4))
        self.btn_stop = ttk.Button(top, text="Stop", command=self._on_stop, width=10)
        self.btn_stop.grid(row=0, column=8, sticky="e")

        top.columnconfigure(6, weight=1)

        # Status row
        st = ttk.Frame(self.root); st.pack(fill="x", padx=8, pady=(0, 4))
        self.queue_var = tk.StringVar(value=self._queue_summary())
        ttk.Label(st, textvariable=self.queue_var, foreground="#666").pack(side="left")
        self.btn_push = ttk.Button(st, text="Push", command=self._on_push, width=10)
        self.btn_push.pack(side="right")
        ttk.Button(st, text="Обновить", command=self._refresh_queue, width=10).pack(
            side="right", padx=(0, 4))

        # Log
        log_frm = ttk.LabelFrame(self.root, text="Лог процесса")
        log_frm.pack(fill="both", expand=True, padx=8, pady=4)
        mono = tkfont.nametofont("TkFixedFont").actual()
        self.log_text = tk.Text(
            log_frm, wrap="none", state="disabled",
            font=(mono["family"], 9),
            background="#1e1e1e", foreground="#e0e0e0",
            insertbackground="#e0e0e0",
        )
        ysb = ttk.Scrollbar(log_frm, orient="vertical", command=self.log_text.yview)
        xsb = ttk.Scrollbar(log_frm, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        log_frm.rowconfigure(0, weight=1)
        log_frm.columnconfigure(0, weight=1)

        # Bottom status
        bar = ttk.Frame(self.root); bar.pack(fill="x", padx=8, pady=(0, 6))
        self.proc_var = tk.StringVar(value="Не запущен")
        ttk.Label(bar, textvariable=self.proc_var, foreground="#888").pack(side="left")

    # ----- params -> CLI args -----

    def _section_key(self) -> str | None:
        label = self.section_var.get()
        for key, lab in SECTION_ORDER:
            if lab == label:
                return None if key == "any" else key
        return None

    def _args(self, *, dry: bool = False) -> list[str] | None:
        args: list[str] = []
        numbers = self.numbers_var.get().strip()
        if numbers:
            # Validate: digits + commas + whitespace only.
            tokens = [t.strip() for t in numbers.split(",")]
            tokens = [t for t in tokens if t]
            if not tokens or not all(t.isdigit() and 1 <= len(t) <= 3 for t in tokens):
                messagebox.showerror(
                    "yaniktoim",
                    "Номера: 1-3-значные числа через запятую (напр. 283 или 1,42,283).",
                )
                return None
            args += ["--numbers", ",".join(tokens)]
            # --section / --limit silently ignored by run_batch when --numbers
            # is set; we still pass --batch-size + --no-push.
        else:
            sec = self._section_key()
            if sec: args += ["--section", sec]
            limit = self.limit_var.get().strip()
            if limit:
                try:
                    n = int(limit)
                    if n <= 0: raise ValueError
                    args += ["--limit", str(n)]
                except ValueError:
                    messagebox.showerror("yaniktoim", "Лимит должен быть положительным числом")
                    return None
        bs = self.batch_size_var.get().strip()
        if bs:
            try:
                n = int(bs)
                if n <= 0 or n > 50: raise ValueError
                args += ["--batch-size", str(n)]
            except ValueError:
                messagebox.showerror("yaniktoim", "Размер пачки — целое 1..50")
                return None
        if self.no_push_var.get():
            args += ["--no-push"]
        if dry:
            args += ["--dry-run"]
        return args

    # ----- actions -----

    def _check_external_lock(self) -> bool:
        """Returns True iff it is safe to launch (no external run_batch is
        holding the lock). Shows a dialog otherwise."""
        pid = _lock_owner_pid()
        if pid is None:
            return True
        messagebox.showerror(
            "yaniktoim",
            f"Уже запущен другой раннер (PID {pid}).\n"
            f"Lock-файл: {LOCK_FILE}\n\n"
            f"Дождитесь его завершения, либо, если процесс мёртв, "
            f"удалите вручную lock-файл.",
        )
        return False

    def _on_start(self) -> None:
        if self.batch.is_running(): return
        if not self._check_external_lock(): return
        args = self._args()
        if args is None: return
        try:
            self.batch.start(args)
        except Exception as e:
            messagebox.showerror("yaniktoim", f"Не могу запустить:\n{e}")
            return
        self._append_log(f"[gui] start: {' '.join(args) or '(no args)'}\n")
        self._refresh_buttons()

    def _on_push(self) -> None:
        """Manual git add/commit/push of the whole repo (zml/ + docs/ + config…).
        Single-repo model (§0): the repo root is PROJECT_ROOT; .gitignore keeps
        raw/_backups/etc out. Used after batch runs with --no-push, when the
        operator has reviewed the local result."""
        if self.batch.is_running():
            messagebox.showinfo(
                "yaniktoim",
                "Сначала остановите текущий transform-процесс — он сам пушит.")
            return
        repo = PROJECT_ROOT
        if not (repo / ".git").exists():
            messagebox.showerror(
                "yaniktoim",
                f"{repo} не git-репозиторий — push невозможен.")
            return
        # Snapshot status to decide commit message and whether anything changed.
        try:
            st = subprocess.run(
                ["git", "-C", str(repo), "status", "--short"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", check=False,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as e:
            messagebox.showerror("yaniktoim", f"git status failed:\n{e}")
            return
        changed = [l for l in (st.stdout or "").splitlines() if l.strip()]
        if not changed:
            self._append_log("[gui] push: нет изменений в репо\n")
            return
        # Show preview + ask confirmation.
        preview = "\n".join(changed[:20])
        more = "" if len(changed) <= 20 else f"\n…(+{len(changed)-20} ещё)"
        ok = messagebox.askyesno(
            "yaniktoim",
            f"Запушить {len(changed)} изменений в репо?\n\n{preview}{more}",
        )
        if not ok: return
        msg = f"manual push: {len(changed)} files ({time.strftime('%Y-%m-%d %H:%M')})"
        for cmd, label in [
            (["git", "-C", str(repo), "add", "."], "add"),
            (["git", "-C", str(repo),
              "-c", "user.name=imyavel",
              "-c", "user.email=imyavel@gmail.com",
              "commit", "-m", msg], "commit"),
            (["git", "-C", str(repo), "push", "origin", "main"], "push"),
        ]:
            self._append_log(f"[gui] git {label}…\n")
            r = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", check=False,
                creationflags=CREATE_NO_WINDOW,
            )
            if r.stdout: self._append_log(r.stdout.rstrip() + "\n")
            if r.stderr: self._append_log(r.stderr.rstrip() + "\n")
            if r.returncode != 0 and label != "commit":
                # commit может вернуть rc!=0 если уже нечего коммитить — это ОК;
                # для add/push такая ошибка фатальна.
                self._append_log(f"[gui] git {label} failed rc={r.returncode}\n")
                return
        self._append_log("[gui] push готов\n")

    def _on_stop(self) -> None:
        if not self.batch.is_running(): return
        # Graceful: ставим флаг и НЕ убиваем. Раннер доведёт текущий батч до
        # конца (с пушем) и выйдет сам — reader-поток это увидит и закроет.
        if self.batch.stop_graceful():
            self._append_log("[gui] Stop (graceful) → флаг поставлен; "
                             "раннер завершит текущий батч и выйдет\n")
        else:
            self._append_log("[gui] Stop: не удалось поставить флаг → force kill\n")
            self.batch.stop_force()
        self._refresh_buttons()

    def _on_close(self) -> None:
        if not self.batch.is_running():
            self._close_log_file(); self.root.destroy(); return
        ok = messagebox.askyesno(
            "yaniktoim",
            "Процесс работает. Остановить его и закрыть окно?\n\n"
            "(Текущая статья оборвётся; уже готовые страницы сохранены.)",
        )
        if not ok: return
        # При ЗАКРЫТИИ окна не ждём graceful-завершения целого батча (это до
        # часа на 5 длинных статьях — окно казалось бы зависшим). Сразу валим
        # всё дерево процессов (раннер + 3b_transform + claude.exe) и закрываемся.
        self.batch.stop_force()
        self._close_deadline = time.time() + 5.0
        self.root.after(50, self._await_kill_step)

    def _await_kill_step(self) -> None:
        if not self.batch.is_running() or time.time() >= self._close_deadline:
            self._close_log_file(); self.root.destroy(); return
        self.root.after(50, self._await_kill_step)

    def _close_log_file(self) -> None:
        if self.log_path is None: return
        try:
            with open(self.log_path, "a", encoding="utf-8", newline="\n") as f:
                f.write(f"[gui] === GUI closed "
                        f"{time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        except Exception:
            pass
        self.log_path = None

    # ----- queue summary -----

    def _queue_summary(self) -> str:
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            return "manifest.json не читается"
        # «Готово» = новая HTML-страница docs/art/<art>.html (по data-scheme).
        # Переиспущем ровно ту же проверку, что и раннер, чтобы не разъехаться.
        from run_batch_html import _is_built
        total = len(manifest)
        done = sum(1 for r in manifest if r.get("art") and _is_built(r["art"]))
        pending = total - done
        # Тот же порядок, что в run_batch_html.pending_articles: section_order
        # внутри SECTION_ORDER. Первая непостроенная — «следующая».
        sec_order = ["best", "dreamon", "cyberson", "dabudet",
                     "confront", "shoshana", "other"]
        next_num: str | None = None
        for sec in sec_order:
            rows = [r for r in manifest
                    if r.get("section") == sec and r.get("art")]
            rows.sort(key=lambda x: x.get("section_order", 9999))
            for r in rows:
                if not _is_built(r["art"]):
                    next_num = f"{r['number']} (art={r['art']})"
                    break
            if next_num:
                break
        next_part = f", следующая: {next_num}" if next_num else ""
        state_info = ""
        if STATE_FILE.exists():
            try:
                s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                state_info = f"  · last run done={len(s.get('done', []))}, failed={len(s.get('failed', []))}"
            except Exception:
                pass
        return (f"В корпусе: {total}, трансформировано: {done}, "
                f"в очереди: {pending}{next_part}{state_info}")

    def _refresh_queue(self) -> None:
        self.queue_var.set(self._queue_summary())

    # ----- log / state polling -----

    def _refresh_buttons(self) -> None:
        running = self.batch.is_running()
        self.btn_start.configure(state=("disabled" if running else "normal"))
        self.btn_push.configure(state=("disabled" if running else "normal"))
        self.btn_stop.configure(state=("normal" if running else "disabled"))
        self.section_combo.configure(
            state=("disabled" if running else "readonly"))
        for w in (self.limit_entry, self.batch_size_entry, self.no_push_check,
                  self.numbers_entry):
            w.configure(state=("disabled" if running else "normal"))
        if running and self.batch.proc:
            self.proc_var.set(f"Запущен (PID {self.batch.proc.pid})")
        else:
            pid = _lock_owner_pid()
            if pid is not None:
                self.proc_var.set(
                    f"Чужой раннер активен (PID {pid}) — Start заблокирован")
            else:
                self.proc_var.set("Не запущен")

    def _pump_log(self) -> None:
        drained = 0
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item is None:
                    self._refresh_buttons()
                    self._refresh_queue()
                    continue
                self._append_log(item)
                drained += 1
                if drained >= 500: break
        except queue.Empty:
            pass
        if not self.batch.is_running() and self.btn_start.cget("state") == "disabled":
            self._refresh_buttons()
        self.root.after(POLL_LOG_MS, self._pump_log)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        # Trim oldest lines once we cross the threshold. Keeps Tk responsive
        # across 350-article runs (~17k log lines otherwise).
        try:
            nlines = int(self.log_text.index("end-1c").split(".")[0])
            if nlines > LOG_TRIM_MAX:
                self.log_text.delete("1.0", f"{LOG_TRIM_DROP}.0")
        except (tk.TclError, ValueError):
            pass
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        if self.log_path is not None:
            try:
                with open(self.log_path, "a", encoding="utf-8", newline="\n") as f:
                    f.write(text)
            except Exception:
                pass

    def _poll_state(self) -> None:
        # Lightweight: only refresh the queue summary; state of subprocess
        # is reflected in proc_var via _refresh_buttons already.
        if not self.batch.is_running():
            self._refresh_queue()
        self.root.after(POLL_STATE_MS, self._poll_state)


def main() -> int:
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

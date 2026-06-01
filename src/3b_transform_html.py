"""raw/<stem>.html → docs/art/<art>.html — прямая LLM-вёрстка по текстовому
промпту (две стилевые схемы, без образцов, без ZML). См. roadmap3.md.

Отличие от 3_transform.py (заморожённый ZML-путь):
  - НИКАКОЙ разметки на входе: тело статьи отдаётся LLM как сырой plain-text,
    ровно как его видит читатель на proza.ru. Скрипт только:
      * вытаскивает тело из страницы proza (убирает обвязку: меню/шапку/подвал);
      * <br> → перевод строки, вырезает теги (на proza текст — plain, <a>
        автолинкуются и URL остаётся видимой строкой → ничего не теряется);
      * декодирует HTML-сущности (&quot; → " и т.п. — читатель видит символ);
      * убирает мусор импорта `;;`/`;;;;` (покорёженные движком буквы иврита).
    БОЛЬШЕ НИЧЕГО: ни ссылок-маркеров, ни починки `::`, ни снятия дубль-H1,
    ни нормализации кавычек — это решает LLM сама.
  - Название и URL статьи на proza подаются ОТДЕЛЬНЫМ метаблоком промпта,
    а не внутри текста статьи (текст — самостоятельная сущность).
  - Выход — готовый самодостаточный HTML прямо в docs/art/<art>.html,
    минуя zml/ и build.mjs.

Usage (из корня yaniktoim/):
  python src/3b_transform_html.py <art> [<art> ...]
  python src/3b_transform_html.py --number 215 [...]
  python src/3b_transform_html.py --stem 2026_05_04_367 [...]
  python src/3b_transform_html.py <art> --force      # перезаписать существующий html
"""
from __future__ import annotations
import io
import os
import re
import sys
import json
import time
import shutil
import html as html_mod
import subprocess
from pathlib import Path
from typing import NamedTuple

# ВНИМАНИЕ: stdout НЕ оборачиваем на уровне модуля — этот файл импортируется
# раннером (batch_runner/run_batch_html.py) как библиотека воркеров, и переписать
# sys.stdout импортёру было бы вторжением. Обёртку ставит только CLI-main().

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
SITE = ROOT / "docs"
ART_DIR = SITE / "art"
LOGS = ROOT / "_logs"
MANIFEST = ROOT / "manifest.json"
PROMPT_MD = ROOT / "batch_runner" / "convert_prompt_005.md"

# Системный промпт для headless-вызова. ЗАМЕНЯЕТ дефолтный системный промпт
# Claude Code и тем самым ИЗОЛИРУЕТ верстальщика от глобального CLAUDE.md /
# auto-memory (иначе агент тянет правила «отвечай по-русски кратко» и хвост
# «[HH:MM] Tokens: …»). Проверено: --bare ломает OAuth Max-подписки, а
# --system-prompt сохраняет вход и убирает примеси CLAUDE.md. См. roadmap3.
HTML_SYSTEM_PROMPT = (
    "You are a meticulous web typesetter. You convert one article's raw text "
    "into a single self-contained HTML page per the user's instructions, and "
    "you WRITE that page to the destination file path given in the user "
    "message using the Write tool. For a large document, create the file with "
    "the Write tool (first portion), then append the rest with the Edit tool "
    "in parts, so that no single tool call carries too much text. Do NOT print "
    "the HTML in your reply — your final message must be a single short "
    "confirmation line."
)

# Path into the Claude MSIX-package container — обходим symlink в
# %APPDATA%\Roaming\Claude, который не везде резолвится. См. CLAUDE.md.
# Версия в пути растёт сама (2.1.149 → .156 → …), поэтому резолвим последнюю
# по числовому порядку, а не хардкодим конкретную папку.
_CLAUDE_CODE_DIR = Path(
    r"C:\Users\admin\AppData\Local\Packages\Claude_pzs8sxrjxfjjc"
    r"\LocalCache\Roaming\Claude\claude-code"
)


def _resolve_claude_exe() -> str:
    """Найти claude.exe в самой свежей версии-папке (semver-сортировка).
    Фолбэк — `claude` из PATH, если контейнерных папок нет."""
    if _CLAUDE_CODE_DIR.is_dir():
        def _ver_key(p: Path) -> tuple:
            return tuple(int(x) if x.isdigit() else -1
                         for x in p.name.split("."))
        cands = sorted(
            (p for p in _CLAUDE_CODE_DIR.iterdir()
             if p.is_dir() and (p / "claude.exe").exists()),
            key=_ver_key,
        )
        if cands:
            return str(cands[-1] / "claude.exe")
    return "claude"


CLAUDE_EXE = _resolve_claude_exe()

# Транзиентные сбои headless-вызова (пустой ответ, обрыв API) — повторяем.
# Лимит (429) НЕ ретраим здесь — возвращаем kind="limit" наверх, раннер сам
# решает (спать до сброса / спам-защита).
RETRIES = 2
RETRY_BACKOFF_S = 10
CLAUDE_TIMEOUT_S = 3600  # потолок на одну статью (claude headless, 60 мин), затем — fail.
# Инкрементальная запись большого документа (Write+Edit за несколько ходов)
# идёт дольше single-shot — потому потолок поднят с 30 до 60 мин.

# Потолок вывода на ОДНО сообщение модели. По умолчанию Claude Code шлёт 64000
# для opus-4-8 и НЕ зажимает значение к максимуму модели (>потолка → HTTP 400).
# Серверный максимум opus-4-8 на Messages API = 128000 — ставим его, чтобы
# реже упираться и дробить файл на меньшее число кусков. Инжектим в окружение
# headless-процесса (env-блок settings.json сабпроцессом claude -p НЕ
# наследуется — только реальное окружение процесса).
MAX_OUTPUT_TOKENS = "128000"

# Лимит подписки = HTTP 429 (и session, и weekly). Детектим по коду, а не по
# нестабильной формулировке. Текст сброса («resets …») разбирает раннер.
_ERR_429_RX = re.compile(
    r'"api_error_status"\s*:\s*429|too\s+many\s+requests', re.IGNORECASE)


class CallResult(NamedTuple):
    """Итог одного headless-вызова claude."""
    html: str | None
    kind: str    # "ok" | "limit" | "fail"
    detail: str  # текст ответа/ошибки (для parse_reset и диагностики)


class ArtResult(NamedTuple):
    """Итог вёрстки одной статьи (то, что воркер возвращает раннеру)."""
    art: str
    kind: str    # "ok" | "limit" | "fail"
    detail: str  # причина/хвост лимита

    @property
    def ok(self) -> bool:
        return self.kind == "ok"


# ═════════════════════════════════════════════════════════════════════════════
# 1. PLAIN-TEXT BODY EXTRACTION (как видит читатель на proza.ru)
# ═════════════════════════════════════════════════════════════════════════════

def extract_body(html: str) -> str:
    """Вернуть тело статьи как plain-text — то, что видит читатель на proza.ru.

    Минимальная обработка, БЕЗ разметки:
      1. взять только <div class="text"> (обвязка страницы отброшена);
      2. <br> → \\n;
      3. вырезать оставшиеся теги (URL у автолинков остаётся видимой строкой);
      4. html.unescape (&quot; → ", &nbsp; → ' ', &mdash; → —);
      5. убрать `;;`-мусор импорта (схлопнуть в один пробел);
      6. нормализовать NBSP → пробел (читатель видит обычный пробел).
    Заголовок (<h1>) НЕ включается — он подаётся как метаданные отдельно.
    """
    m = re.search(r'<div\s+class="text">(.*?)</div>\s*<br>', html, re.S)
    if not m:
        return ""
    body = m.group(1)
    # 2. <br> → \n (съедаем один завершающий перевод строки, чтобы не плодить
    #    фантомных пустых строк из HTML-форматирования).
    body = re.sub(r"<br\s*/?>\n?", "\n", body, flags=re.I)
    # 3. Вырезать остальные теги.
    body = re.sub(r"<[^>]+>", "", body)
    # 4. Декодировать HTML-сущности.
    body = html_mod.unescape(body)
    # 5. Убрать `;;`-мусор (2+ подряд `;`) и схлопнуть пробелы вокруг.
    body = re.sub(r"[ \t]*;{2,}[ \t]*", " ", body)
    # 6. NBSP → обычный пробел.
    body = body.replace(" ", " ")
    return body.strip("\n")


# ═════════════════════════════════════════════════════════════════════════════
# 2. CORPUS NAVIGATION (хлебные крошки + prev/next + колофон)
# ═════════════════════════════════════════════════════════════════════════════

# Авторские названия разделов — канон, зеркалит src/5_index.py SECTION_NAMES
# и docs/editor/render.js SECTION_HUMAN. НЕ переименовывать.
SECTION_NAMES = {
    "best":     "Избранное",
    "dreamon":  "Мечтай!!",
    "cyberson": "Киберсон",
    "dabudet":  "Да будет Свет!",
    "confront": "Конфронтология Духа",
    "shoshana": "Роза Среди Шипов",
    "other":    "Без категории",
}

# Канонический порядок разделов (зеркалит src/5_index.py ORDER и
# batch_runner/run_batch.py SECTION_ORDER). Нужен, чтобы prev/next на стыке
# разделов уводили в соседний раздел (последняя/первая статья соседа).
SECTION_ORDER = ["best", "dreamon", "cyberson", "dabudet",
                 "confront", "shoshana", "other"]


def _section_articles(manifest: list[dict]) -> dict[str, list[dict]]:
    """section → статьи, отсортированные по section_order (как индексы/рендер)."""
    buckets: dict[str, list[dict]] = {}
    for r in manifest:
        sec = r.get("section")
        if sec and isinstance(r.get("section_order"), int) and r.get("art"):
            buckets.setdefault(sec, []).append(r)
    for sec in buckets:
        buckets[sec].sort(key=lambda r: r["section_order"])
    return buckets

# Колофон корпуса — дословно из templates/article.html (общий для всех страниц
# текст об авторстве и лицензии). Вставляется в каждую сгенерированную страницу,
# чтобы она оставалась частью корпуса.
FOOTER_HTML = (
    '<p class="attrib">Адаптировано Claude Opus 4.8 от Anthropic и Элиягу Бар Малей.</p>'
    '<p class="license">Текст доступен на условиях '
    '<a href="https://creativecommons.org/licenses/by/4.0/deed.ru" rel="license">'
    'Creative Commons Attribution 4.0 (CC BY 4.0)</a> — при указании автора '
    '(Элиягу Бар Малей) и ссылки на этот сайт.</p>'
)


def image_source(rec: dict) -> Path | None:
    """Найти ИСХОДНЫЙ jpg статьи в raw/ — БЕЗ копирования. None, если нет.
    Раздельно с публикацией: href для промпта знаем заранее, а файл копируем
    только после успешной вёрстки (иначе упавшие статьи плодят сирот в img/)."""
    if not rec.get("art"):
        return None
    srcs = []
    img_name = rec.get("img")  # напр. "2022_05_05_670.jpg"
    if img_name:
        srcs.append(RAW / img_name)
    stem = rec.get("stem")
    if stem:  # подстраховка, если поле img пустое, но stem-картинка есть
        srcs.append(RAW / f"{stem}.jpg")
    return next((p for p in srcs if p.exists()), None)


def image_href(rec: dict, src: Path | None) -> str | None:
    """Путь картинки для HTML (../img/<art>.jpg) — если исходник есть."""
    if src is None or not rec.get("art"):
        return None
    return f"../img/{rec['art']}{src.suffix.lower() or '.jpg'}"


def publish_image(rec: dict, src: Path | None) -> None:
    """Скопировать найденный исходник → docs/img/<art>.jpg. Зовётся ТОЛЬКО
    после успешной вёрстки страницы."""
    if src is None or not rec.get("art"):
        return
    dst_dir = SITE / "img"
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_dir / f"{rec['art']}{src.suffix.lower() or '.jpg'}")


def build_nav(rec: dict, manifest: list[dict], image: str | None = None) -> dict:
    """Собрать навигацию корпуса для одной статьи.

    Страницы лежат плоско в docs/art/<art>.html, разделы — в docs/<section>/.
    Относительно art/<art>.html: главная = ../index.html, раздел =
    ../<section>/index.html, соседи = <art>.html (та же папка).
    Prev/next — по section_order внутри раздела (как docs/editor/render.js).
    image — готовый путь к иллюстрации (../img/<art>.jpg) или None.
    """
    section = rec.get("section")
    section_label = SECTION_NAMES.get(section, section or "")
    nav = {
        "home_href": "../index.html",
        "home_label": "Главная",
        "section_href": f"../{section}/index.html" if section else "",
        "section_label": section_label,
        "image": image,
        "prev": None,
        "next": None,
        "footer_html": FOOTER_HTML,
    }
    buckets = _section_articles(manifest)
    sibs = buckets.get(section, [])
    idx = next((i for i, r in enumerate(sibs)
                if r.get("art") == rec.get("art")), -1)

    def _link(r: dict) -> dict:
        return {"href": f"{r['art']}.html", "title": r.get("title") or r["art"]}

    # Непустые разделы в каноническом порядке — для переходов на стыке.
    present = [s for s in SECTION_ORDER if buckets.get(s)]
    pos = present.index(section) if section in present else -1

    # prev: предыдущая в разделе, иначе — ПОСЛЕДНЯЯ статья предыдущего раздела.
    if idx > 0:
        nav["prev"] = _link(sibs[idx - 1])
    elif idx == 0 and pos > 0:
        nav["prev"] = _link(buckets[present[pos - 1]][-1])

    # next: следующая в разделе, иначе — ПЕРВАЯ статья следующего раздела.
    if 0 <= idx < len(sibs) - 1:
        nav["next"] = _link(sibs[idx + 1])
    elif idx == len(sibs) - 1 and 0 <= pos < len(present) - 1:
        nav["next"] = _link(buckets[present[pos + 1]][0])

    return nav


# ═════════════════════════════════════════════════════════════════════════════
# 3. LLM CALL
# ═════════════════════════════════════════════════════════════════════════════

def build_prompt(base_prompt: str, rec: dict, body: str, nav: dict,
                 out_path: Path) -> str:
    """Собрать полный промпт: указание верстальщику + метаблок proza
    (url + название — ВНЕ текста статьи) + навигация корпуса (JSON) +
    путь файла назначения (агент пишет туда Write/Edit) + сырое тело статьи."""
    url = rec.get("url", "")
    title = rec.get("title", "")
    meta = (
        "## Метаданные статьи (с proza.ru — НЕ часть текста)\n\n"
        f"- Адрес оригинала: {url}\n"
        f"- Название на proza.ru: {title}\n\n"
        "> Это справочные метаданные источника, а не содержимое статьи. "
        "Само название статьи (как заголовок страницы) бери отсюда. Текст "
        "статьи ниже — самостоятельная сущность; если в нём заголовок "
        "продублирован, реши сам, как это подать.\n"
    )
    nav_block = (
        "## Навигация корпуса (для обязательной обвязки — см. одноимённый раздел)\n\n"
        "Готовые ссылки и колофон; вставляй URL/тексты дословно:\n\n"
        "```json\n"
        + json.dumps(nav, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    dest_block = (
        "## Файл назначения\n\n"
        "Сохрани готовую HTML-страницу ИМЕННО в этот файл (инструментом Write; "
        "большой документ дописывай инструментом Edit по частям). Путь дан "
        "дословно — не меняй его, ничего больше не создавай:\n\n"
        f"`{out_path}`\n"
    )
    return (
        base_prompt
        + "\n\n" + meta
        + "\n" + nav_block
        + "\n" + dest_block
        + "\n## Текст статьи к вёрстке\n\n"
        + "```\n" + body + "\n```\n"
    )


_HTML_SPAN_RX = re.compile(r"(<!DOCTYPE html>|<html[\s>]).*?</html>", re.S | re.I)


def extract_html(raw: str) -> str | None:
    """Достать чистый HTML-документ из ответа LLM: от <!DOCTYPE html>/<html>
    до </html>. Срезает ```-ограждения, преамбулу и telemetry-хвост
    «[HH:MM] Tokens: …», который инжектит глобальный CLAUDE.md."""
    m = _HTML_SPAN_RX.search(raw)
    if m:
        return m.group(0).strip()
    return None


def _read_valid_html(path: Path) -> str | None:
    """Содержимое out_path, если это валидный HTML-документ (от
    <!DOCTYPE html>/<html> до </html>); иначе None — файла нет либо агент
    записал обрывок/мусор. Это и есть критерий успеха новой схемы: страницу
    пишет сам агент на диск, а не возвращает текстом."""
    if not path.exists():
        return None
    try:
        txt = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return txt if _HTML_SPAN_RX.search(txt) else None


def call_claude(full_prompt: str, art: str, out_path: Path) -> CallResult:
    """Headless claude -p: агент САМ пишет страницу в out_path инструментами
    Write/Edit (большой документ — инкрементально, за несколько ходов). Успех
    определяем по наличию ВАЛИДНОГО файла на диске, а не по тексту ответа:
    раньше весь HTML возвращался в `result` и терял «голову» при авто-continue
    на выводе сверх потолка сообщения — теперь документ собирается на диске
    мимо этого лимита. Лимит (429) не ретраим: сразу наверх."""
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / f"html_prompt_{art}.txt").write_text(full_prompt, encoding="utf-8")
    print(f"  [{art}] prompt: {len(full_prompt)} chars", flush=True)
    # Только файловые инструменты (без bash/web); bypassPermissions — headless
    # не может отвечать на запросы доступа; --add-dir — право писать в каталог
    # статей; --max-turns 60 — запас ходов на инкрементальную дописку большого
    # документа; --system-prompt → изоляция от CLAUDE.md.
    cmd = [
        CLAUDE_EXE, "-p",
        "--model", "claude-opus-4-8",
        "--output-format", "json",
        "--allowedTools", "Write,Edit,Read",
        "--permission-mode", "bypassPermissions",
        "--add-dir", str(out_path.parent),
        "--max-turns", "60",
        "--system-prompt", HTML_SYSTEM_PROMPT,
    ]
    # Потолок вывода на сообщение → серверный максимум модели. Отдаём через
    # РЕАЛЬНОЕ окружение процесса (env-блок settings.json сабпроцессом claude -p
    # НЕ наследуется — проверено).
    env = os.environ.copy()
    env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = MAX_OUTPUT_TOKENS
    last_err = ""
    for attempt in range(1, RETRIES + 1):
        # Файл пишет сам агент — начинаем с чистого листа, чтобы успех
        # проверялся по СВЕЖЕ записанному файлу (важно и для --force поверх
        # существующего, и для ретрая после обрывка прошлой попытки).
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        t0 = time.time()
        try:
            # Захват в БАЙТАХ + ручной decode(errors="replace"): claude иногда
            # пишет в stderr не-UTF-8 байты (особенно при убийстве процесса), и
            # текстовый reader-поток subprocess на них падает (UnicodeDecodeError),
            # теряя stdout. Бинарный режим это исключает.
            proc = subprocess.run(
                cmd, input=full_prompt.encode("utf-8"),
                capture_output=True, timeout=CLAUDE_TIMEOUT_S,
                env=env, cwd=str(ROOT),
            )
        except subprocess.TimeoutExpired:
            dur = time.time() - t0
            # Fail-fast: не уложился в потолок → почти наверняка зависшая
            # генерация; обрывок-файл убираем, чтобы не отравить очередь, и не
            # ретраим (ретрай тем же промптом лишь удвоит простой воркера).
            try:
                out_path.unlink(missing_ok=True)
            except OSError:
                pass
            print(f"  ! [{art}] claude TIMEOUT {dur:.0f}s — fail (без ретрая)",
                  flush=True)
            return CallResult(None, "fail", f"timeout after {CLAUDE_TIMEOUT_S}s")
        dur = time.time() - t0
        out = (proc.stdout or b"").decode("utf-8", "replace")
        err = (proc.stderr or b"").decode("utf-8", "replace")
        print(f"  [{art}] claude exit={proc.returncode} in {dur:.1f}s "
              f"(attempt {attempt}/{RETRIES})", flush=True)
        # Всегда сохраняем сырой stdout+stderr — для диагностики.
        (LOGS / f"html_{art}.stdout.json").write_text(out, encoding="utf-8")
        if err.strip():
            (LOGS / f"html_{art}.stderr.txt").write_text(err, encoding="utf-8")

        # Лимит подписки (429)? Не ретраим — наверх, пусть раннер ждёт сброса.
        if _ERR_429_RX.search(out):
            print(f"  ! [{art}] лимит (429) — отдаю наверх", flush=True)
            return CallResult(None, "limit", out)

        # Успех = агент завершился без ошибки И на диске лежит валидный
        # HTML-документ (от <!DOCTYPE/<html> до </html>).
        html_doc = _read_valid_html(out_path)
        if proc.returncode == 0 and html_doc:
            return CallResult(html_doc, "ok", "")

        # Неуспех: убираем возможный обрывок, чтобы _is_built не счёл статью
        # готовой и не выкинул её из очереди следующего прогона.
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        last_err = (out + "\n" + err).strip()
        print(f"  ! [{art}] нет валидного HTML-файла (exit={proc.returncode}), "
              f"attempt {attempt}/{RETRIES}", flush=True)
        if attempt < RETRIES:
            time.sleep(RETRY_BACKOFF_S)
    return CallResult(None, "fail", last_err[-2000:])


# ═════════════════════════════════════════════════════════════════════════════
# 4. ORCHESTRATION
# ═════════════════════════════════════════════════════════════════════════════

def transform_one(rec: dict, base_prompt: str, manifest: list[dict],
                  force: bool = False) -> ArtResult:
    """Сверстать одну статью. Возвращает ArtResult (ok/limit/fail). Безопасна
    для параллельного вызова из потоков: пишет только в свои пути
    (docs/art/<art>.html, docs/img/<art>.jpg, _logs/html_<art>.*)."""
    art = rec.get("art") or rec.get("number") or "?"
    stem = rec.get("stem")
    if not rec.get("art") or not stem:
        print(f"  ! record missing art/stem: {rec.get('number')}", flush=True)
        return ArtResult(art, "fail", "missing art/stem")
    art = rec["art"]
    out_path = ART_DIR / f"{art}.html"
    if out_path.exists() and not force:
        print(f"  skip {art} (html уже есть)", flush=True)
        return ArtResult(art, "ok", "skip")
    src = RAW / f"{stem}.html"
    if not src.exists():
        print(f"  ! {art} ({stem}): raw html not found", flush=True)
        return ArtResult(art, "fail", "raw not found")

    body = extract_body(src.read_text(encoding="utf-8"))
    if not body.strip():
        print(f"  ! {art} ({stem}): пустое тело после извлечения", flush=True)
        return ArtResult(art, "fail", "empty body")
    (LOGS / f"html_{art}.body.txt").write_text(body, encoding="utf-8")

    # Картинку НЕ копируем до вёрстки — только узнаём её будущий href для
    # промпта/навигации. Файл публикуем после успеха (см. ниже), чтобы упавшие
    # статьи не оставляли сирот в docs/img/.
    src_img = image_source(rec)
    nav = build_nav(rec, manifest, image=image_href(rec, src_img))
    ART_DIR.mkdir(parents=True, exist_ok=True)  # агент будет писать сюда сам
    full_prompt = build_prompt(base_prompt, rec, body, nav, out_path)
    res = call_claude(full_prompt, art, out_path)
    if res.kind != "ok" or res.html is None:
        return ArtResult(art, res.kind, res.detail)

    # Страницу уже записал на диск сам агент (call_claude проверил валидность).
    publish_image(rec, src_img)  # успех → теперь публикуем иллюстрацию
    print(f"  ✓ saved → art/{art}.html", flush=True)
    return ArtResult(art, "ok", "")


def _lookups(manifest: list[dict]) -> tuple[dict, dict, dict]:
    by_art: dict[str, dict] = {}
    by_stem: dict[str, dict] = {}
    by_number: dict[str, dict] = {}
    for r in manifest:
        if "art" in r:
            by_art[r["art"]] = r
        if "stem" in r:
            by_stem[r["stem"]] = r
        if "number" in r:
            by_number[r["number"]] = r
    return by_art, by_stem, by_number


def main(argv: list[str]) -> int:
    # CLI-режим: оборачиваем stdout в utf-8 (при импорте раннером — не трогаем).
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  line_buffering=True)
    if not MANIFEST.exists():
        print(f"manifest not found: {MANIFEST}")
        return 2
    if not PROMPT_MD.exists():
        print(f"prompt not found: {PROMPT_MD}")
        return 2
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_art, by_stem, by_number = _lookups(manifest)

    force = "--force" in argv
    args = [a for a in argv if a != "--force"]

    if "--stem" in args:
        i = args.index("--stem")
        targets = [by_stem[s] for s in args[i + 1:] if s in by_stem]
    elif "--number" in args:
        i = args.index("--number")
        targets = [by_number[n.zfill(3)] for n in args[i + 1:]
                   if n.zfill(3) in by_number]
    else:
        targets = [by_art[a] for a in args if a in by_art]

    if not targets:
        print("No targets. Usage:")
        print("  python src/3b_transform_html.py <art> [<art> ...]")
        print("  python src/3b_transform_html.py --number 215 [...]")
        print("  python src/3b_transform_html.py --stem <YYYY_MM_DD_NNN> [...]")
        return 1

    LOGS.mkdir(parents=True, exist_ok=True)
    base_prompt = PROMPT_MD.read_text(encoding="utf-8")

    ok = 0
    for rec in targets:
        res = transform_one(rec, base_prompt, manifest, force=force)
        if res.ok:
            ok += 1
        else:
            print(f"  ✗ {res.kind} art={rec.get('art')} stem={rec.get('stem')}",
                  flush=True)
    print(f"\nDone: {ok}/{len(targets)} transformed", flush=True)
    return 0 if ok == len(targets) else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

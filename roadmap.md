# yaniktoim — Roadmap (актуально на 2026-05-29)

Самодостаточная инструкция для свежего контекста Claude. Описывает целостную архитектуру проекта: source-of-truth = ZML, рендер = `render.js`, публикация = gh-pages legacy `main /docs`, правка = inline-редактор на самих страницах.

> **§0 — текущая (живая) картина**, согласована и реализована: сайт развёрнут на `https://imyavel.github.io/yaniktoim/`, миграция-flip выполнена. §1-§10 ниже — справка (ZML-формат, pipeline по файлам, оставшиеся этапы, история TODO). Документ приведён в соответствие с фактом 2026-05-29; явных противоречий с §0 быть не должно.

---

## 0. АКТУАЛЬНАЯ КАРТИНА (2026-05-29) — план миграции на боевой gh

Всё в этой секции согласовано с оператором и готово к реализации. Это перекрывает противоречащие места ниже.

### 0.1 Цель и адрес
- Боевой сайт — **`https://imyavel.github.io/yaniktoim/`**, репозиторий **`imyavel/yaniktoim`** (PUBLIC). Старое содержимое репо затёрто force-push'ем (выполнено 2026-05-29). `gh` залогинен как `imyavel` (scope `repo`). Рабочая папка — `C:\Users\admin\yaniktoim\` (прежнее имя `-cms` ушло при flip).
- Pages source = `main /docs`, есть `docs/.nojekyll`. Сборка `built`, сайт отдаёт наш контент.

### 0.2 Модель деплоя — БЫСТРАЯ, без CI («компромисс старого и нового»)
- **CI-сборки НЕТ.** html генерит `render.js` в двух местах одним и тем же кодом: (а) **браузер редактора** при «Сохранить» (рендерит ПОЛНУЮ страницу) и (б) **локальный батч** `tools/build.mjs` (пачкой). Идентичный вывод → нет дрейфа.
- Pages у `imyavel/yaniktoim` остаётся **legacy**, но источник переключаем **«корень» → `main /docs`**. Собранный сайт лежит в **`docs/`** и **коммитится** (готовый html в репо — это норм: он всегда машинно-сгенерён, руками не трогаем).
- Обновление боевой страницы после правки = коммит + пропагация Pages ≈ **30-60 сек** (без ожидания сборки). gh не делает вычислений — только хранит и отдаёт статику через CDN.
- Читатель получает **готовый статический html** (SEO ок). Рендер «в браузере» — только у РЕДАКТОРА в момент сохранения, не у читателя.

### 0.3 Единый источник истины = git
- `zml/` (исходник) живёт **только в репозитории**; локальная папка = его клон. Все правки (редактор на gh / батч локально) идут через коммиты в один репо; git — слой синхронизации.
- html всегда производный (генерится `render.js`), **руками не редактируется** → расхождений нет.
- **Батч перед работой делает `git pull --rebase`** → видит правки из редактора; добавляет только НОВЫЕ статьи; коммитит/пушит. Редактор и батч правят разные файлы → конфликтов почти нет.

### 0.4 Рендер — один движок
- **`docs/editor/render.js`** — ЕДИНСТВЕННЫЙ рендер ZML→HTML. Экспортит `renderArticleParts` (нутро `<article>`), `renderArticleHtml` (полная страница), `parseFrontmatter`. Питон `4_render.py` **retired** (в `_backups/`, gitignored). Parity-обвязки нет.
- Имена собственные (CAPS→Заглавная) — редактируемый `config/proper-nouns.txt` (базовые формы; склонения regex; `!СЛОВО`=точное, стоит `!ХОД`). Фраза «Благословен Он»/«Свят Благословен Он» — правило в `render.js`. (Сделано и проверено.)

### 0.5 Редактирование на gh (inline, wiki-стиль)
- ✎ на самих статьях (edit-режим `?edit=1`). На https модули/fetch/GitHub-API работают — проблема `file://` не возникает.
- **Save**: редактор нормализует ZML к LF, проставляет frontmatter `editor`/`edited`, рендерит ПОЛНУЮ страницу `renderArticleHtml` (шаблон — `docs/editor/data/template.html`), и **одним логическим коммитом** пишет `zml/<art>.zml` + `docs/<section>/<art>.html` через **GitHub Git Data API** (blobs→tree→commit→ref).
- **Авторизация интерим**: твой **fine-grained PAT** (только репо `yaniktoim`, Contents: write) в ⚙ редактора (localStorage). «Подписываюсь как…» — выбор из `config/users.json`. Полноценный вход — Этап 8 (см. ниже, переписанный).

### 0.6 Система пользователей и атрибуция
- **Атрибуция (делаем сразу, без Worker):** frontmatter-поля `editor:` и `edited:` в каждом `zml`. Пайплайн-дефолт при генерации статьи: `editor: Иван Иванович`, `edited: <дата сборки>` («сгенерено ИИ, человеком не правилось»). Правка в редакторе перезаписывает на текущего пользователя + сегодня. `render.js` выводит на странице «Последняя правка: <дата> · <editor>» — видно любому читателю.
- **`config/users.json`** — 3 дефолтных пользователя: **Иван Иванович** (ИИ/авто), **Элиягу Бар Малей**, **Бина Анеле**.
- Полный логин/роли/пароли — Этап 8.

### 0.7 Состав публичного репо (репо ПУБЛИЧНЫЙ!)
- **Включаем**: `zml/`, `manifest.json`, `_logs/zohar_index.json`, `templates/`, `config/` (`proper-nouns.txt`, `users.json`), `tools/`, `src/` (питон-пайплайн, нужен локальному клону для батча — мелкий, не секрет), `docs/` (собранный сайт + код редактора), `package.json`.
- **ИСКЛЮЧАЕМ** (`.gitignore`): `src/*.sqlite` (⚠ **куки Chrome!**), `_backups/`, `raw/` (≈350 html с proza — для деплоя не нужны, перекачиваются `1_fetch.py`), `_research/`, `node_modules/`, аудит-логи из `_logs/` (кроме `zohar_index.json`).

### 0.8 ПОРЯДОК миграции (необратимое — последним; staging НЕ поднимаем)
Делает свежий контекст; код пишем «предположительно корректным», проверку откладываем (баги ловим после переноса):
1. **[СДЕЛАНО 2026-05-29]** Подготовлено в текущей `yaniktoim-cms\` (обратимо, без flip):
   - `site/` → `docs/` (вместе с editor-кодом render.js/inline.js); пути обновлены в `tools/build.mjs`, `run_batch.py`, `5_index.py`, `7_postcheck.py`, `build_progress.py`, `gui.pyw`, обоих `.claude/launch.json`.
   - `build.mjs` рендерит в `docs/`; в `docs/editor/data/` выгружает `template.html` (полная страница для Save) и `users.json`.
   - `run_batch.py`: `git pull --rebase` в начале (если не `--no-push`); `git_push` коммитит ВЕСЬ репо из ROOT (`zml`+`docs` одним коммитом, по `.gitignore`).
   - `inline.js`: дефолт репо `imyavel/yaniktoim`; селектор «как:» из `users.json` (авто-юзер «Иван Иванович» скрыт); Save = stamp `editor`/`edited` (LF-нормализация) → `renderArticleHtml` полной страницы → **один коммит** `zml/<art>.zml`+`docs/<section>/<art>.html` через Git Data API (blobs→tree→commit→ref).
   - Атрибуция: `render.js` выводит `<p class="editinfo">Последняя правка: <дата> · <editor></p>`; пайплайн-дефолт `editor:"Иван Иванович"`, `edited:<дата>` ставит `3_transform.py::inject_attribution` (только если поля отсутствуют).
   - `config/users.json` (3 юзера) создан. `src/6_deploy.py` (создавал вложенный git-репо в site/ — противоречит однорепной модели) убран в `_backups/`.
   - Проверено локально (Preview MCP, art 237): ✎-вход, селектор подписи (Элиягу/Бина), live-предпросмотр (5×h2/3 поэмы/26 сносок), editinfo на странице, `setFrontmatter` (add+replace), full-page render с датой. НЕ проверено вживую: сам коммит в GitHub (нужен PAT+репо — после flip).
2. **[СДЕЛАНО 2026-05-29] Flip выполнен (необратимо):** старая `C:\Users\admin\yaniktoim\` переименована в `C:\Users\admin\yaniktoim_OLD_preflip\` (бэкап, можно удалить); `yaniktoim-cms\` → `yaniktoim\` (с `.git`). История пересоздана с нуля (`rm -rf .git && git init`) — старый fork-коммит трекал `raw/`+куки. В `.gitignore` добавлены `_research/`, `_logs/*` (кроме `zohar_index.json`), `json/`, `manifest_pre_art.json`. Аудит staged: куки-sqlite/cookies.txt/raw/_research НЕ попали. `remote origin = imyavel/yaniktoim`; **force-push** в `main` (67 файлов); `docs/.nojekyll`; Pages → `main /docs` через `gh api`. Сборка `built`, сайт живой.
3. **[СДЕЛАНО] Боевой сайт проверен (HTTP 200):** `/`, `/best/237.html` (с подписью правки), `/editor/render.js`, `/editor/inline.js`, `/editor/data/{users.json,template.html}`, `/style.css`. Корпус — 3 тестовые статьи (237/416A/654); остальные 339 — прогоном через `gui.pyw` из новой `yaniktoim\`.
4. **[остаётся оператору]** Проверить inline-Edit **вживую**: `…/best/237.html?edit=1` → ✎ → ⚙ PAT (репо `yaniktoim`, Contents: write) → подпись → Сохранить. Единственное, что не тестировалось без реального токена.

### 0.9 Что выяснено про автоматизацию трансформа (research-агент, 2026-05-29)
HTML→ZML **нельзя** сделать чистым JS-скриптом: механика (colophon, перенумерация сносок, forum-quote, `[num]`, CAPS-секции) переносима, но **граница стих↔проза, epi/секция/молитва, mus-в-сноске, summary** требуют LLM. JS-only «начисто» вытянул бы ~20-35% (короткая проза); стихово-эпиграфные (основа корпуса) — нет. Главный риск — тихие ошибки (lossless-валидатор сверяет только текст 1:1, кривую сегментацию пропустит). **Вывод:** трансформ остаётся локальным (claude.exe/батч), рендер уже на JS везде. Гибрид (LLM только на спорном) — возможная будущая оптимизация, не сейчас.

---

## 1. Что делаем

`C:\Users\admin\yaniktoim\` — рабочая папка и клон репо `imyavel/yaniktoim`. (Историческая справка: проект начинался как форк `yaniktoim-cms\`; при flip 2026-05-29 эта папка стала боевой `yaniktoim\`, прежнее содержимое репо затёрто, старая папка сохранена как `yaniktoim_OLD_preflip\`.) Две цели:

1. **Адаптированный корпус статей** автора Элиягу Бар Малей (≈350 статей с proza.ru) — статический сайт на GitHub Pages, **`https://imyavel.github.io/yaniktoim/`**.
2. **Мини-CMS** — редактор прямо на страницах (inline ✎, wiki-стиль). Интерим-вход — PAT (см. §0.5); многопользовательский — Cloudflare Worker-прокси (Этап 8).

Корпус наполняется через **локальный desktop GUI** (Tk), который батчами прогоняет статьи через LLM-агента (headless `claude -p`), рендерит в HTML (`tools/build.mjs`) и пушит в репо. Техбаза готова и отлажена на 3 статьях; дальше — массовый прогон оставшихся ≈339.

---

## 2. Что имеем

### 2.1. Готово и не трогаем

- **Корпус raw**: `raw/*.html` — 350 страниц с proza.ru уже скачаны. Источник стабилен, повторять fetch не нужно.
- **Manifest и порядок**: `manifest.json` (section, number, section_order, dates) + `2_manifest.py` + `2b_section_order.py` — структура корпуса собрана корректно.
- **Картинки**: cover-картинок в frontmatter ZML не пересобираем — inline-картинок в исходниках proza.ru нет (там они были недоступны на отдачу).
- **База Зоар**: внешний корпус `https://imyavel.github.io/zohar-sulam/` с новой URL-структурой `<chapter>/<NNN>.html` (например `akdama/004.html`). Локальный first-source: `C:\Users\admin\Heb\Translated\Site\`.
- **GUI batch-runner**: `batch_runner/gui.pyw` (Tk) + `batch_runner/run_batch.py` (оркестратор) — внешняя обвязка работает: батч, single-instance lock, hit-limit-handling (парсит **session-формат** «resets at Xpm (UTC)» / «resets in N hours», спит, retry батча), fatal-abort (401/403/quota), atomic state.json, render+index+push после батча. **Не переписывать.** Адаптируем только то, что вызывает (`subprocess.run([sys.executable, "src/3_transform.py", ...])` — внутрь идёт новая логика).
  - ✅ weekly-лимит Max-плана (`«resets Feb 4, 9pm (TZ)»`) теперь парсится (`HIT_LIMIT_WEEKLY_RX` в `run_batch.py`, TODO 11). Session (5h) и relative («in N hours») — тоже.

### 2.2. Устарело, переписываем

*(Статусы на 2026-05-29 — основное уже сделано, см. §0 и TODO.)*

- **`src/3_transform.py`**: ✅ переписан — **HTML → ZML напрямую** (LLM сразу выдаёт финальный source с ASCII-тегами) + lossless-валидация + `inject_attribution`.
- **`src/4_render.py`**: ⛔ **retired** (в `_backups/`). Рендер целиком на JS — `docs/editor/render.js` (+`tools/build.mjs`).
- **`src/6_deploy.py`**: ⛔ **retired** (в `_backups/`) — создавал вложенный git в `site/`, противоречит однорепной модели §0.3. Деплой теперь — `git_push` из `run_batch.py`/`gui.pyw` (push всего репо из ROOT).
- **`src/5_index.py`**: главный index + section indexes; читает manifest, пишет в `docs/`. Работает.
- **`src/7_postcheck.py`**: LLM-аудит блоков. Сейчас просто вызывает `node tools/build.mjs` для ре-рендера; полноценный аудит под ZML — опционально позже (TODO 8).
- **`src/transform_prompt.md`**: ✅ переписан под прямой ZML-выход.
- **`_logs/zohar_index.json`**: ✅ перекомпилирован под URL `<chapter>/<NNN>.html` (52 главы, 1777 статей).

### 2.3. ZML-спека готова (Этап 0)

- `_zml_spec/SPEC.md` — формальная спецификация (v0.1, draft).
- `_zml_spec/demo.zml` + `_zml_spec/demo.html` + `_zml_spec/style.css` — образец со всеми типами блоков, рендерится как полноценная статья.

---

## 3. Целевая архитектура

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ЛОКАЛЬНО (наполнение корпуса)                                            │
│   raw/<stem>.html (≈350, gitignored)                                     │
│         │                                                                │
│   GUI batch-runner (Tk) → run_batch.py (оркестратор, hit-limit retry)    │
│         │   git pull --rebase                                            │
│         ├─ 3_transform.py  (headless claude -p)  HTML → zml/<art>.zml     │
│         ├─ tools/build.mjs (render.js)           ZML → docs/<sec>/<a>.html│
│         ├─ 5_index.py                            docs/index + разделы     │
│         └─ git_push (весь репо из ROOT: zml + docs)                       │
└─────────────────────┼──────────────────────────────────────────────────┘
                      │ git push (origin main)
                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ GitHub: imyavel/yaniktoim (PUBLIC)                                        │
│   main:  zml/ (source) + docs/ (готовый сайт+редактор) + src/ + config/…  │
│   Pages: legacy, source = main /docs  (+ docs/.nojekyll)                  │
└─────────────────────┼──────────────────────────────────────────────────┘
                      │  CDN (≈30-60с после коммита, без CI)
        ┌─────────────┴───────────────┐
        ▼                             ▼
   читатель                      редактор (inline ✎, ?edit=1)
   готовый статичный html        тот же render.js в браузере
        │                             │ Save: stamp editor/edited →
        │                             │ render полной страницы →
        │                             ▼
        │                        ИНТЕРИМ: PAT (localStorage) → Git Data API
        │                        ПОЗЖЕ:  Cloudflare Worker (Этап 8), токен на Worker
        │                             │  один коммит zml+html
        ▼                             ▼
   /yaniktoim/…                  origin main ←──┘  (страница обновляется ~30-60с)
```

**Принцип**: один source-of-truth — `.zml` в `zml/` ветки main; html всегда производный (тот же `render.js` в батче и в браузере-редакторе) и коммитится в `docs/`. Никаких параллельных JSON, никакого CI.

---

## 4. ZML-формат (резюме)

Полная спека — `_zml_spec/SPEC.md`. Здесь только синтаксис-памятка.

| Категория | Синтаксис | Назначение |
|-----------|-----------|------------|
| Frontmatter | `---\ntitle: ...\nsummary: ...\nart: "182"\ndate: 2 Августа 2021 г.\nimage: 1695.jpg\n---` | YAML. `art` обязателен — арт-id `XYZ[n]`, кодирует date_chosen (SPEC §2.3). `date`, `image` опциональны. `image` → файл из `pics/`. |
| Секция h2 | `## АКТ ПЕРВЫЙ {slug}` | slug опционален. |
| Параграф | _обычный текст_ | default; CAPS-строки auto → `<span class="sb">` small-caps. |
| Нумерованная группа | `[num]...[/num]` | внутри параграфы через пустую строку, рендер ставит «1.», «2.» автоматом → `<ol class="num">`. |
| Стих | `[poem]...[/poem]` или `[poem title="..."]` | пустая строка = строфа; CAPS-runs склеиваются. |
| Эпиграф | `[epi]...[/epi]`, `[epi cite="..."]` | метка «Эпиграф», прижат справа. |
| Эпилог *(спящий)* | `[epil]...[/epil]` | в текущей коллекции пока не встречается. |
| Цитата *(спящая)* | `[quote]...[/quote]`, `[quote cite="..."]` | пока не встречается. |
| Подзаголовок | `[sub]...[/sub]` | h2-эхо H1. |
| Музыка | `[mus]...[/mus]` или `[mus="<label>"]` + внутри `[url\|title\|author]` построчно | парный контейнер. label один на группу, default «Музыка под настроение». |
| Сноски (тело) | в конце: `[^N]: текст` / `[^]: текст` (анон, авто «См. также:») / `[^\|<префикс>]: текст` | multi-line с indent. Анонимные после нумерованных, без backref. |
| Сноска marker | `[^N]` | inline. |
| Внутренний линк | `[[<art>]]` | арт-id целевой статьи (3-4 знака); резолв из `manifest.json` (поле `art`); broken → `<a class="broken">` + warning. |
| Zohar-линк | `{chapter\|N}` | резолв из `zohar_index.json`. URL: `zohar-sulam/<chapter>/<NNN>.html` (NNN padded к 3). |
| Внешний линк | `[url\|анкор]` или `[url]` | анкор опционален. |
| Italic | `_слово_` / `_фраза_` | inline-эмфаза → `<em>`. Авто-конвертится из авторских `[фраза]` на этапе `3_transform.py` (по правилу word-boundary). |
| CAPS-keep | `^СЛОВО` слитно | внутри CAPS-pass — первая буква остаётся Заглавной. |

**Голых URL в теле ZML быть не должно** — все ссылки в тегах. Оборачивает `3_transform.py` при переносе.

**Порядок парсинга inline**: `[^N]` → `[[<art>]]` → `{chapter|N}` → `[url|анкор]` → `_italic_` → CAPS-pass → `^WORD`.

---

## 5. Полный pipeline (по файлам)

| # | Файл | Status | Назначение |
|---|------|--------|------------|
| 1 | `src/1_fetch.py` | готово, не трогаем | proza.ru → `raw/*.html`. |
| 1b | `src/1b_fetch_missing.py` | готово, не трогаем | добор пропущенных. |
| 2 | `src/2_manifest.py` | готово, не трогаем | `manifest.json` (section, number, section_order, dates, original-titles). |
| 2b | `src/2b_section_order.py` | готово, не трогаем | заполнение `section_order` (порядок автора). |
| - | `src/cookie_eater.py` | готово | utility для proza.ru. |
| - | `src/build_progress.py` | проверить | сборка `progress.json`. |
| 3 | `src/3_transform.py` | **переписать** | HTML → ZML через headless `claude -p`. Выход: `zml/<NNN>.zml`. Lossless-валидация: strip разметку из ZML → сравнить с canon-текстом из raw → diff в `_logs/transform_<NNN>.diff.txt`. |
| - | `src/transform_prompt.md` | **переписать** | Инструкция LLM: «верни мне исходный текст с разметкой ZML»; перечень всех тегов; правила оборачивания URL, распознавания CAPS/эпиграфов/стихов/etc. |
| 4 | ~~`src/4_render.py`~~ → `tools/build.mjs` + `docs/editor/render.js` | ✅ retired (py в `_backups/`) | Рендер ZML → `docs/<section>/<art>.html` целиком на JS. frontmatter, блочные теги (§4), inline-цепочка (§5), `[[art]]` через manifest, `{chapter\|N}` через zohar_index. |
| 5 | `src/5_index.py` | готово | `docs/index.html` + `docs/<section>/index.html`. Читает manifest. |
| 6 | ~~`src/6_deploy.py`~~ | ✅ retired (`_backups/`) | Деплой — `git_push` из `run_batch.py`/`gui.pyw` (push всего репо из ROOT по `.gitignore`), Pages legacy `main /docs`. |
| 7 | `src/7_postcheck.py` | переписать или отключить | LLM-аудит ZML-блоков (skeleton-pass). На первое время можно скипнуть. |
| - | `batch_runner/run_batch.py` | готово | оркестратор: transform → render → index → push. Hit-limit-handling готов. |
| - | `batch_runner/gui.pyw` | готово | Tk-GUI launcher. |
| - | `_logs/zohar_index.json` | **перекомпилировать** | под новый URL `<chapter>/<NNN>.html`. |

---

## 6. План этапов

### Этап 0 — ZML-спека *(готово)*

`_zml_spec/SPEC.md` + demo. Мелкие уточнения возможны по ходу следующих этапов (тогда bump version в SPEC).

### Этап 1 — Перекомпилировать `zohar_index.json`

Без него `4_render.py` не сможет резолвить `{chapter|N}`. Сборщик: парсинг `<title>`/`<h1>` страниц `https://imyavel.github.io/zohar-sulam/<chapter>/<NNN>.html` либо чтение локального корпуса `C:\Users\admin\Heb\Translated\Site\`.

Структура нового индекса:

```json
{
  "chapters": {
    "akdama":  "Введение (Акдама)",
    "beresheet": "Берешит",
    ...
  },
  "articles": {
    "akdama": {
      "1": "Заголовок статьи 1",
      "4": "«МИ бара ЭЛЕ» Элияhу",
      ...
    },
    "beresheet": { "1": "...", ... }
  }
}
```

Резолвинг в рендере: `{akdama|4}` → `"Книга Зоар. Введение (Акдама). «МИ бара ЭЛЕ» Элияhу"` с золотым стилем.

### Этап 2 — Вычистить `[...]` из исходников

ZML использует квадратные скобки для разметки — нужно убрать конфликты в исходном тексте.

1. Grep по `raw/*.html` (и для контроля по существующим `json/*.json` поле `paragraph.html`) — все вхождения `[...]` вне HTML-тегов.
2. Выдать оператору список файлов с примерами фрагментов.
3. Оператор вручную правит raw (заменяет `[...]` на `(...)` или удаляет, как уместно).
4. Запускать массовый ZML-перенос только после чистки.

### Этап 3 — Новый `3_transform.py` + `transform_prompt.md`

Headless `claude -p` получает на вход:
- `raw/<stem>.html` (canonical plain text после `article_text()` — берётся из старой реализации).
- `transform_prompt.md` (новая инструкция: разметка ZML, перечень тегов, правила).

LLM возвращает готовый `.zml`. Скрипт:
- Парсит frontmatter — заполняет `id`, по возможности `date` (из тела или заголовка автора).
- **Удаляет** из тела вхождения «Арт. #XX01» и «Записано/Написано» (попадают во frontmatter или выкидываются).
- Оборачивает все URL: proza.ru-ссылки автора → `[[<NNN>]]` (по manifest), внешние → `[url|анкор]`, zohar-sulam → `{chapter|N}`. **Голых URL в ZML быть не должно.**
- Lossless-валидация: strip ZML-разметку → сравнить с canon-текстом. Diff в `_logs/transform_<NNN>.diff.txt`.
- Сохраняет `zml/<NNN>.zml`.

### Этап 4 — Рендер ZML → HTML *(готово, на JS)*

Реализован НЕ как `4_render.py`, а как `docs/editor/render.js` (+ `tools/build.mjs` для пачки). Парсер по спеке использует: `manifest.json` (`[[art]]`), `_logs/zohar_index.json` (`{chapter|N}`), `pics/<file>` (frontmatter.image), `templates/article.html` (прямая подстановка `{{…}}`), CSS_VERSION. Выход: `docs/<section>/<art>.html` (LF).

### Этап 5 — `5_index.py`, деплой, `7_postcheck.py` *(в основном готово)*

- **5_index.py** — читает manifest, пишет в `docs/`. Работает.
- **Деплой** — `git_push` из `run_batch.py`/`gui.pyw`, Pages legacy `main /docs` (см. §0.2/§0.8). `6_deploy.py` retired.
- **7_postcheck.py** — сейчас лишь ре-рендерит через `node tools/build.mjs`. Полноценный аудит ZML-блоков — опционально (TODO 8).

### Этап 6 — Отладка на 3-5 статьях вручную

Прогон через новый pipeline 3-5 заранее выбранных пилотных статей разного характера:
- стихи с эпиграфами (`2022_05_05_670`),
- философская проза со сносками и YouTube (`2026_05_04_367`),
- короткий диалог (`2024_01_06_1439`),
- статья с zohar-ссылками,
- статья с внутренними `[[nnn]]`-линками.

Цель — увидеть все типы блоков в живом рендере, поправить парсер/промт/CSS, добиться идентичности с эталонными старыми JSON-рендерами там, где это применимо (frontmatter, поэзия, сноски).

### Этап 7 — Массовый автоматический прогон

Через GUI batch-runner: section за section, по 5 в батче (текущий default), с автоматическим hit-limit-sleep. Хвост: ~339 оставшихся. Ожидаемое время — несколько дней при подписочной квоте.

### Этап 8 — Многопользовательский логин (Cloudflare Worker proxy) — АКТУАЛЬНЫЙ ДИЗАЙН (2026-05-29)

> Заменяет прежнюю «OAuth-relay» модель. Запускаем, когда захотим пускать редактировать не только себя. До этого — интерим на PAT (см. §0.5). Не блокирует выкатку базы.

Цель оператора: друзья **без своего GitHub** правят «под общим аккаунтом», но логинятся каждый под своим ником; «доступ только через этот сайт и больше никак».

Принцип — **Worker как прокси-коммитер, токен НИКОГДА не у клиента**:
- **`config`/KV на Worker** хранит пользователей (ник → хеш пароля + роль). Это серверная БД Worker’а, НЕ репозиторий и НЕ gh-pages (туда регистрация не пишется, коммита не делает).
- На сайте — **свой лёгкий логин** (друзьям GitHub не нужен). Регистрация: `self-register → роль pending` (войти может, писать нет). Оператор (`admin`) промоутит pending → `editor`. Опционально — **инвайт-ссылки** против спама.
- **Save**: браузер шлёт правку+сессию на Worker → Worker проверяет роль → сам коммитит в `imyavel/yaniktoim` своим **fine-grained токеном (только этот репо, Contents: write)**, который живёт ТОЛЬКО на Worker. Так «только через сайт» становится реально enforced; отзыв токена — в одном месте.
- **Атрибуция настоящая**: Worker подставляет `author`/`committer` коммита = ник редактора (в git-истории видно «кто правил», хотя GitHub-аккаунт один).
- Чтение сайта остаётся публичной статикой, без логина. Cloudflare Workers free (100k req/день) — с запасом.
- Граница безопасности — **роль на Worker**, а не аккаунт: самой регистрацией прав к репо не получить.

Это маленькое, но СВОё управление пользователями (хранилище, хеши, сессии, роли) — отдельный аккуратный шаг. UI редактирования (inline ✎ + `render.js`-превью) уже готов из §0; меняется только то, что Save идёт на Worker, а не напрямую в GitHub API.

---

## 7. TODO / Конкретные пункты к выполнению

*Каждый пункт ниже — конкретный артефакт или скрипт, который нужно создать/изменить. По мере выполнения помечаем `[x]`.*

1. **[x] Перекомпилировать `_logs/zohar_index.json`** под новую структуру `<chapter>/<NNN>.html` (Этап 1) — собран из локального корпуса `C:\Users\admin\Heb\Translated\Site\` скриптом `src/build_zohar_index.py`. 52 главы, 1777 статей. Старый индекс → `_logs/zohar_index_LEGACY.json`. Лукап `{akdama|4}` → «Книга Зоар. Введение (Акдама). «МИ бара ЭЛЕ» Элияhу» / `…/akdama/004.html`.
2. **[x] Grep `[...]` в `raw/*.html`** — отчёт `_research/brackets_report.md` готов. 350 файлов сканировано, 330 вхождений: 79 A (числовые сноски) + 91 B (именованные сноски) + 160 C (авторские пояснения и спец-разметка). 136 C-случаев конвертятся автоматом в `_..._` (italic) в `3_transform.py`; 24 boundary-case покрываются полировкой regex (HTML-decode + точка/тире). Остаются ~5-7 спец-случаев (якоря `[*]`/`[*=>{#XX}]` в `175`/`195`/`198`/`203`/`211`; BB-code в `209`/`224`) — точечная правка ZML в CMS после первого рендера (Этап 6).
3. **[x] Переписать `src/transform_prompt.md`** под прямой ZML-выход — готово. 11 разделов: lossless-правило, frontmatter, URL-маркеры `⟦INT/ZOH/EXT⟧` (pre-resolved python-обвязкой), блочные теги (`[poem]/[epi]/[mus]/[num]/[sub]`), сноски (числовые/именованные/анонимные), colophon-чистка, минимальный пример. Italic `_..._` приходит pre-converted, LLM не трогает.
4. **[x] Переписать `src/3_transform.py`** — HTML → ZML через `claude -p`. Готово (≈550 строк). Pipeline: `article_text()` → `classify_links()` (⟦INT⟧/⟦EXT⟧ + bare URLs) → `convert_italic()` (`[фраза]` → `_фраза_`) → headless `claude -p --model claude-opus-4-8 --max-turns 1` → `inject_art()` → `validate_lossless()` (двусторонний strip с маскированием music-блоков, footnote-section, эпиграф-маркеров, colophon) → `zml/<art>.zml`. **3 пилота прошли валидацию**: `416A` (4404 chars, 23s), `654` (18556 chars, 277s), `237` (15727 chars, 795s). CLI: `<art> [<art>...]` / `--stem <YYYY_MM_DD_NNN>` / `--pilot` / `--all` / `--force`.
5. **[x] Переписать `src/4_render.py`** — ZML → HTML. Готово (≈580 строк). Парсер frontmatter + блоков (paragraph, heading `## … {slug}`, `[poem]`, `[epi cite=…]`, `[epil]`, `[quote cite=…]`, `[num]`, `[mus|mus="label"]` с `[url|title|author]`-треками, `[sub]` в обоих формах — multi-line и single-line). Inline-cascade из SPEC §7: `[^N]` → sup+ref/note pair, `[[<art>]]` → internal с заголовком из manifest, `{chapter|N}` → zohar-link «Книга Зоар. <kniga>. <article>», `[url|анкор]` / `[url]`, `_фраза_` → `<em>`, CAPS-pass → `<span class="sb">` с lowercase + PROPER_NOUNS (40+ слов: Орёл, Творец, Адам, Кли, Нагваль, сфирот, …), `^WORD` → forced capital. Поэма: CAPS-runs склеиваются в один span. TOC из h2-секций + back-to-toc `↑`. Footnotes: numbered (`<sup>`+backref) + anonymous (`См. также:`/кастомный prefix). Pilot render OK: `site/confront/416A.html`, `site/best/654.html`, `site/best/237.html`. CSS: `style.css` v=20260528-01 копия `_zml_spec/style.css`.
6. **[x] `src/5_index.py`** — пишет в `docs/`, читает manifest. Работает.
7. **[x] Деплой** — `6_deploy.py` retired; push через `git_push` (`run_batch.py`/`gui.pyw`) всего репо из ROOT, Pages legacy `main /docs`. См. §0.2/§0.8.
8. **[ ] Переписать или скипнуть `src/7_postcheck.py`** — сейчас лишь ре-рендер через `build.mjs`; полноценный LLM-аудит ZML — опционально.
9. **[ ] Отладка на 3-5 пилотных статьях** через GUI batch-runner (Этап 6).
10. **[ ] Массовый прогон 339 статей** (Этап 7).
11. **[x] Weekly hit-limit парсер** — портирован в `run_batch.py` (`HIT_LIMIT_WEEKLY_RX` + `_MONTH_ABBR`, ветка в `parse_reset`, пробуется ПЕРВОЙ). Формат `resets <Месяц> <день>, <H>pm [(TZ)]` → датированный `datetime` (катится на след. год если месяц прошёл; recognized TZ конвертится в локальное). Протестировано на weekly/session/in. Недельный Max-лимит теперь не уходит в 5h-fallback.
12. **[x] `src/build_art_ids.py`** — арт-id сгенерены для всех **350/350** записей `manifest.json` (поле `art`). Алгоритм — SPEC §2.3.
13. **[x] Мини-CMS (локальная, MVP)** — **СУПЕРСЕДНУТА** браузерным inline-редактором (TODO 13c). Старая `cms/` (HTTP-сервер на localhost:8765) перенесена в `_backups/` (gitignored).
13c. **[x] Браузерный редактор для gh-pages (2026-05-29)** — отказ от server-CMS в пользу статики, отлаживаемой локально как финальный gh-pages-артефакт. Решение оператора: «сделать всё как будет потом использоваться». Компоненты:
    - **`site/editor/render.js`** — **ЕДИНСТВЕННЫЙ рендер** ZML→HTML (Node-сборка + live-preview в браузере, один код). Нормализует CRLF→LF на входе. Экспортит `renderArticleParts` (нутро `<article>` без шаблона) для inline-предпросмотра + `renderArticleHtml` (полная страница) для сборки.
    - **Консолидация в один рендер (2026-05-29)**: `src/4_render.py` помечен DEPRECATED (баннер в шапке), все живые вызывающие (`run_batch.py:run_render`, `7_postcheck.py:run_render`) переключены на `node tools/build.mjs`. Parity-обвязка (`parity.mjs`/`parity_render.py`/`render_cli.mjs`) удалена — она требовала второй живой реализации и порождала дрейф версий. На раннем этапе (правила ZML ещё в разработке) golden-эталона нет; «оракул» = правила SPEC + глаз оператора в live-preview. `4_render.py` физически жив только из-за `cms/server.py` (суперседнут) — уйдёт вместе с `cms/`.
    - **`tools/build.mjs`** — Node-сборка: `zml → site/<section>/<art>.html` (LF) + выгрузка данных редактора в `site/editor/data/` (trimmed manifest, zohar_index, копии zml, **proper-nouns.txt**). rc≠0 если статья не отрендерилась (пайплайн проверяет перед push).
    - **Имена собственные вынесены в `config/proper-nouns.txt`** (2026-05-29) — редактируемый список БАЗОВЫХ форм; склонения добавляет regex (основа+падежные окончания, ё/е-нечувств.); `!СЛОВО` — только точная форма (стоит на `!ХОД`, иначе «ход/хода» массово в Заглавную). Убраны МЕССИЯ, ВОИН; добавлены КАРЛОС, ЙЕГУДА. СВЯТ/БЛАГОСЛОВЕН убраны из пословного списка → честна́я фраза «Благословен Он»/«Свят Благословен Он» капитализируется как единое целое (правило в `render.js`, не в списке). Известные щели: оборот «Благословен и Свят Он» (творческая переделка в стихах, [237.zml:61](zml/237.zml:61)/[:289](zml/237.zml:289)/[:303](zml/237.zml:303)) не правится (смешанный регистр, свёртка не трогает); косвенные «Христа» (род. от ХРИСТОС теряет -ОС) не капитализируются.
    - **Inline-редактор на самой странице** (wiki-стиль, БЕЗ отдельной формы/страницы — это итоговое требование оператора, см. 2-й раунд уточнения): `site/editor/inline.js`. ✎ на статье → область `<article>` превращается в ZML-textarea + sticky-тулбар (Сохранить / Предпросмотр(toggle) / Отмена / ↓zml / ⚙). Предпросмотр рендерит `<article>` тем же `renderArticleParts` (пути и стиль резолвятся как на странице — base не нужен) и обновляет h1/`<title>`. Сохранение — GitHub Contents API (PAT/branch/owner/repo в localStorage `yanik_gh`, диалог ⚙); «↓ zml» — локальный фолбэк. Отмена восстанавливает исходный рендер.
    - **Шаблон** `templates/article.html`: `<body data-art>`, кнопка ✎ (`#edit-fab`, скрыта для читателей), скрипты статьи (music lazy + footnote bubble) обёрнуты в идемпотентный `window.yanikBindArticle()` (re-bind после предпросмотра). В edit-режиме (`?edit=1` → `localStorage.yanik_edit`) страница динамически подгружает `../editor/inline.js` (читатели его не грузят).
    - **WYSIWYG отвергнут**: правка идёт в ZML-исходнике (обратный HTML→ZML транзформ невозможен из-за капители/сносок/ссылок).
    - **Локальный прогон**: `node tools/build.mjs` → `python -X utf8 -m http.server 8770 --directory docs` (или Preview MCP, `.claude/launch.json`, имя `site`). Проверено в браузере (DOM): ✎-gating, вход в правку, live-предпросмотр (5×h2/3 поэмы/4 эпиграфа/26 сносок), реактивность h1, отмена-восстановление.
    - **Осталось (13d)** — перекрыто §0: деплой по §0.8 (быстрая модель: legacy `main /docs`, **без CI**, push через `gui.pyw`); многопользовательский вход — Этап 8 (Worker-прокси, НЕ OAuth-relay). `cms/` + `4_render.py` уже перенесены в `_backups/` (gitignored).
13b. **[x] gh-deploy / flip** — выполнено 2026-05-29 (см. §0.8 шаги 2-3): репо `imyavel/yaniktoim`, Pages `main /docs`, сайт живой. Осталось оператору — live-тест inline-Save с PAT (§0.8 шаг 4). Многопользовательский вход — Этап 8.

---

## 8. Структура `yaniktoim\`  (★ = в `.gitignore`, в публичный репо НЕ идёт)

```
yaniktoim/
├── zml/             ← SOURCE-OF-TRUTH: <art>.zml (frontmatter + тело + editor/edited)
├── docs/            ← SERVED ROOT (gh-pages main /docs); всё машинно-сгенерено, руками не править
│   ├── .nojekyll
│   ├── index.html, style.css, img/      статика + главная
│   ├── <section>/<art>.html             собранные статьи (+ <section>/index.html)
│   └── editor/      ← код редактора (отдаётся и импортируется страницей)
│       ├── render.js   ЕДИНСТВЕННЫЙ рендер (Node-сборка + браузерный preview/Save)
│       ├── inline.js   inline ✎-редактор; Save через Git Data API
│       └── data/       выгрузка build.mjs: manifest(subset), zohar_index,
│                       proper-nouns.txt, template.html, users.json, zml/<art>.zml
├── config/          ← proper-nouns.txt (CAPS→Заглавная), users.json (3 юзера)
├── templates/       ← article.html, main_index.html, section_index.html ({{…}}-подстановка)
├── tools/build.mjs  ← Node-сборка: zml → docs/, + docs/editor/data/
├── src/             ← python-пайплайн наполнения корпуса
│   ├── 1_fetch.py / 1b_fetch_missing.py / 2_manifest.py / 2b_section_order.py  (готовы)
│   ├── 3_transform.py + transform_prompt.md   HTML→ZML (готово)
│   ├── 5_index.py                              docs-индексы (готово)
│   ├── 7_postcheck.py                          ре-рендер через build.mjs
│   ├── build_progress.py / build_zohar_index.py / build_art_ids.py / cookie_eater.py
│   └── (4_render.py, 6_deploy.py — retired, в _backups/)
├── batch_runner/    ← Tk-GUI + run_batch.py (оркестратор, hit-limit retry) + state.json
├── _zml_spec/       ← SPEC.md, demo.zml/html/css
├── manifest.json    ← метаданные статей (section, art, title, order, dates)
├── progress.json, package.json, roadmap.md
├── _logs/           ← ★ кроме zohar_index.json (он коммитится — нужен сборке)
├── raw/             ← ★ исходные HTML proza.ru (≈350) + куки-файлы
├── _research/       ← ★ служебное (в т.ч. копия куки-sqlite!)
├── _backups/        ← ★ retired-скрипты (4_render.py, 6_deploy.py, cms/)
├── json/, manifest_pre_art.json   ← ★ старые JSON-интермедиаты
└── node_modules/    ← ★ (если появится)
```
**.gitignore-инвариант (репо PUBLIC):** куки/`*.sqlite`/`raw/`/`_research/` НЕ должны попадать в коммиты — проверять перед любым новым `git add` (см. §0.7).

---

## 9. Полезные мелочи

- **CLAUDE_EXE** = `C:\Users\admin\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude-code\2.1.149\claude.exe` (прямой путь в MSIX-sandbox, обходит сломанный симлинк в `%APPDATA%\Roaming\Claude`).
- **UTF-8 stdout**: при кракозябрах из `python -c` или PowerShell — `python -X utf8 ...` или `[Console]::OutputEncoding=[Text.Encoding]::UTF8` первой строкой.
- **Hit-limit-handling** в `batch_runner/run_batch.py` покрывает session (5h, «resets 6:40pm»), relative («in N hours») И weekly (Max, «resets Feb 4, 9pm (TZ)») — все три формата (`parse_reset`, TODO 11).
- **Версии файлов**: для `<name>_NNN.<ext>` НИКОГДА не править в-месте; каждая правка = `cp _NNN.ext _NNN+1.ext` затем Edit. (К `roadmap.md`, `SPEC.md`, скриптам без `_NNN` это правило НЕ относится.)
- **Headless claude-subagent**: предпочитать `claude.exe -p` (subprocess) над встроенным Task/Agent tool — у первого наследуется thinking-mode оператора, у второго нет.

---

## 10. С чего продолжить в свежем контексте

1. Прочитать §0 (живая картина) + при необходимости `_zml_spec/SPEC.md`.
2. Локальный прогон: Preview MCP имя `site` (отдаёт `docs/`) или `python -X utf8 -m http.server 8770 --directory docs`.
3. Сборка: `node tools/build.mjs [<art>…]` → `docs/`; индексы — `python -X utf8 src/5_index.py`.
4. Оставшаяся работа (по приоритету оператора):
   - **Live-тест inline-Save** на сайте с реальным PAT (§0.8 шаг 4).
   - **Доводка UI/рендера** статей (по списку правок оператора).
   - **Массовый прогон корпуса** ≈339 статей через `gui.pyw` (Этап 7).
   - **Этап 8** — Cloudflare Worker-логин (когда понадобится пускать друзей).
   - Опционально: `7_postcheck.py` полноценный аудит (TODO 8).

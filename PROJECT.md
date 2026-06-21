# imyavel / yaniktoim — карта проекта

> **Входной документ.** Единственная каноничная копия — здесь, в репо `yaniktoim/PROJECT.md`
> (на github и локально). Описывает **актуальную** структуру: миграция корпуса на ZML и
> сборка CMS **завершены**, режим живой (правки идут на боевой сайт). Это карта, не лог.
> История «как пришли» — `roadmap_cms.md` (+ `_archive.md`) в корне репо: для «почему», не «что делать».

## Запуск с чистого компа
Весь проект (сайт + движок + воркер + спека формата + руководство) лежит в **одном репо `yaniktoim`**.
1. `git clone https://github.com/imyavel/yaniktoim` — получаешь `docs/` (сайт) и `cms-revival/` (исходники движка).
2. Поставить среду: **node**, **python** (+`pypdf`,`pymupdf`,`Pillow`), **pagefind**, **wrangler**, **Chrome**.
3. `cd cms-revival/worker && npm i` (его `node_modules` в git не хранится).
4. Готово к работе: правка ZML, пересборка вью, локальная отладка, push.
- **Редеплой воркера** требует свежего `CLOUDFLARE_API_TOKEN` (даёт оператор); правка/сборка/пуш **сайта** его не требуют.
- Соседние сайты (`zohar-sulam`, `imyavel.github.io`) — отдельные репо, клонируются рядом по желанию (нужны только для общего `push.bat`).

## Где что
Один репо `yaniktoim` = весь проект: `docs/` (сайт; Pages: ветка `main`, отдаёт **только** `/docs`) +
`cms-revival/` (исходники движка) + `PROJECT.md`/roadmap'ы/`tools/`/`manifest.json`. Всё вне `docs/`
живёт в репо и видно на github.com, но на публичный сайт не попадает.

---

# Сайт — `yaniktoim/docs/`
Корпус из **352 статей** (проза и стихи), https://imyavel.github.io/yaniktoim/ . Источник истины контента —
**ZML** (свой текстовый формат). У каждой статьи ОДИН публичный адрес `art/NNN.html` (ZML-рендер с полным
OG, индексируется). Вид — 5 ZML-тем + «оригинал (старый html)» как 6-й дизайн — выбирается рантайм-
резолвером из `display.json`/личных настроек **без пересборки**; `.view.html` упразднён как маршрут
(оставлены тонкие редирект-заглушки на старые ссылки). Правка — прямо на сайте
(логин → редактор ZML → коммит в репо через Cloudflare Worker).

- **`art/`** — корпус: на статью `<id>.zml` (источник) → `<id>.html` (единый рендер-контейнер;
  `<id>.view.html` — редирект-заглушка `→ .html`). Вход «old»-варианта — `cms-revival/legacy_html/<id>.html` (архив старого LLM-html).
- **`img/`** — иллюстрации (~209).
- **`config/`** — состояние CMS: `structure.json` (разделы/порядок/статусы), `display.json` (глобальный вид «дизайн+ширина» + правила по разделам/типам; дизайн включает «old»). `forced_views.json`/`default_view` **упразднены** (один URL, вид резолвится рантаймом; пер-статейный override — `frontmatter.theme`).
  ↳ **Контракт через репо:** `structure.json` в рантайме читает заглавная домена `imyavel.github.io/index.html` (счётчик «N статей в M разделах», тот же origin) — при смене его схемы (`articles[].status`, `sections[].archived`) проверить этого потребителя.
- **`editor/`**, **`themes/`** — **производные** (синкаются из `cms-revival/` сборкой `build_views.mjs`; руками не править).
- **CMS-клиент** (hand-maintained прямо в `docs/`): `ze-core.js` (общий движок правки + модальный логин/`ensureFreshSession`) ·
  `ya-edit.js` (статья) · `ya-struct.js` (структура+создание) · `ya-songs.js` (песни) · `ya-auth.js` (логин на главной). Переключение вида (5 тем + «old») целиком в boot-скрипте шаблона (зеркало `resolveDisplay`); отдельного `ya-switch` больше нет.
- **Страницы:** `index.html` · 7 разделов (`best` Избранное · `dreamon` · `cyberson` · `dabudet` · `confront` · `shoshana` · `other`) ·
  `songs/` («Песнь Ступеней») · `admin.html` · `structure.html` · `search.html` · `privacy.html`.
- **`zml/SPEC.md`** — публичная копия спеки. **`guide/rukovodstvo.pdf`** — руководство (A4). **`pagefind/`** — индекс поиска.

# Движок — `yaniktoim/cms-revival/` (исходники, в репо)
- **`zml3/SPEC.md`** — канон формата ZML. Публичная копия — `docs/zml/SPEC.md` (копировать вручную при правке спеки).
- **`editor/`** — `render.js` (+ `verse_split.js`, `faw_markup.js`, шаблоны `data/template_*.html`) и сборщики.
  `node cms-revival/editor/build_views.mjs [id…]` рендерит `.zml`→`art/NNN.html` (читает `cms-revival/legacy_html/` для «old»-оверлея, пишет редирект-заглушки `.view.html`) И синкает render+шаблоны+темы в `docs/`. OG/индексация — в `template_view.html`.
  Тот же `render.js` крутится в браузерном редакторе → паритет байт-в-байт, без дрейфа.
- **`themes/`** — 5 CSS-тем (`A_editorial`,`B_manuscript`,`swiss`,`cyberpunk`,`ar_deco`) — единственный источник (`docs/themes/` производный).
- **`worker/`** — Cloudflare Worker `yaniktoim-auth.imyavel.workers.dev`: логин (HMAC-сессия, TTL 12 ч) ·
  `/api/save` · `/api/commit` · `/api/settings` · users/promote. Секреты (`GH_TOKEN`,`SESSION_SECRET`,`ADMIN_BOOTSTRAP`) —
  в Cloudflare (`wrangler secret`), **не в репо**. Учётки/хеши — в KV `USERS` (3 admin). Тесты: `cd cms-revival/worker && node test_commit.mjs`.
- **`guide_build/`** — источник руководства: `guide.html` + `build_pdf.py` → `guide.pdf`, затем `cp guide.pdf ../../docs/guide/rukovodstvo.pdf`.
- **`config/`**, **`plans/`** — конфиги/планы; `zml1/`,`zml2/`,`cms-superseded/` — исторические референсы формата.

## Как править, собирать, деплоить
- **Правка на сайте**: статья — ✎ на `art/NNN.html`; структура/новая статья — `structure.html` (admin); песни — `songs/index.html`. Всё → Worker → коммит (Worker пишет `NNN.html` + заглушку `.view.html`).
- **Добавление по сырому тексту**: `add_art.md` / `add_art_roza.md`, драйвер `.batch/add_one_transform.py`.
- **Пересборки**: вью+синк — `node cms-revival/editor/build_views.mjs`; песни — `gen_songs_zml.py` + `build_songs.mjs`;
  поиск+sitemap — `reindex.bat` (перед каждым push); руководство — `cms-revival/guide_build/build_pdf.py`.
- **Локальная отладка**: превью `preview_*` (конфиг `zml-preview`, порт 8099) или `viewshots.py` → JPEG. Вёрстку отлаживать **локально ПЕРЕД push**.
- **Деплой**: `imyavel/push.bat` (reindex + commit + push трёх репо). Воркер: `cd cms-revival/worker && wrangler deploy` (нужен токен).

---

# Инварианты и правила
- **Один публичный URL** `art/NNN.html` на статью; `.view.html` как маршрут не существует (только тонкие редирект-заглушки для старых ссылок). Вид (5 тем + «old») резолвится рантаймом — `display.json`/`frontmatter.theme` меняются без пересборки корпуса.
- 352 статьи, 0 ошибок рендера; **пересборка идемпотентна** — `build_views.mjs` не меняет уже отрендеренные/правленные файлы (проверять `git diff docs/` = пусто).
- Файлы вида `<name>_NNN.ext` не править в-месте: копия `_NNN+1`.
- Правки — на живой сайт через `push.bat`, отладка вёрстки — всегда локально до выката.

# Legacy / не для работы
- В репо, но мёртвое (для истории): `legacy/` · `docs/proza-design/` · разрозненный скретч (`.batch/`, `_history_1AT/`, `wave2_*`, `music_*`, …) ·
  в `cms-revival/`: `zml1/`,`zml2/`,`cms-superseded/`,`design_review/` и часть `convert/*.py` (миграционные, могут иметь хардкод-пути).
- **Не в git** (регенерируемое/тяжёлое, см. `.gitignore`): `node_modules/`, `.wrangler/`, `__pycache__/`, `cms-revival/recon/` (~145M скриншотов Ф1),
  `cms-revival/convert/out*` (дубль `docs/art`), `raw/` (оригиналы proza.ru), `_viewshots/` (контейнерный скретч).

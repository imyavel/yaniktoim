# imyavel — карта проекта

> **Входной документ.** Описывает **актуальную** структуру всего контейнера
> `C:\Users\admin\imyavel\`. Главный блок — **yaniktoim** (сайт-корпус на ZML + CMS;
> миграция и сборка CMS завершены, режим живой). Остальные блоки — кратко.
> Это карта, а не лог. История «как пришли» — `roadmap_cms.md` (+ `_archive.md`),
> они локальные и входным документом не служат.
>
> Мастер этого файла — здесь (`imyavel/PROJECT.md`); на github он публикуется копией
> в корне репо `yaniktoim/` (см. «Публикация» внизу).

## Контейнер — четыре блока
| Папка | Назначение | Git / публикация |
|---|---|---|
| **`yaniktoim/`** | сайт-корпус (этот проект) | репо → `imyavel.github.io/yaniktoim/` (Pages: `main`, папка `/docs`) |
| `imyavel.github.io/` | корневой лендинг | репо → `imyavel.github.io` |
| `zohar-sulam/` | отдельный статичный сайт (перевод Зохара) | репо → под общим доменом; **ZML/CMS его не касаются** |
| `cms-revival/` | maintainable-исходники движка/тем/воркера/спеки формата | **пока не под git, только локально** |

**Деплой:** `imyavel/push.bat` — для yaniktoim сначала reindex поиска + sitemap, затем
commit+push всех трёх репо (`origin main`). Подтянуть с GitHub: `imyavel/pull.bat`.
Pages отдаёт только `docs/` — файлы вне `docs/` (этот документ, `tools/`, `manifest.json`)
живут в репо и видны на github.com, но на публичный сайт не попадают.

---

# yaniktoim — главный блок

Сайт-корпус из **352 статей** (проза и стихи) — https://imyavel.github.io/yaniktoim/ .
Источник истины контента — **ZML** (свой текстовый формат). Каждая статья доступна в двух
видах: исходная LLM-вёрстка `.html` и ZML-рендер `.view.html`; по умолчанию показывается
старая, со ссылкой «Новая версия (ZML)». Правка — прямо на сайте (логин → редактор ZML →
коммит в репозиторий через Cloudflare Worker).

## Живой сайт — `yaniktoim/docs/`
- **`art/`** — корпус: на статью `<id>.zml` (источник) · `<id>.view.html` (ZML-рендер) ·
  `<id>.html` (старая вёрстка; у новых статей её нет).
- **`img/`** — иллюстрации статей (~209).
- **`config/`** — состояние CMS: `structure.json` (разделы, порядок, статусы — 352 ст.),
  `display.json` (глобальный вид + правила тем/ширины), `forced_views.json` (пер-статейный форс zml/html).
- **`editor/`** — **производное** (сюда `build_views.mjs` синкает движок рендера + данные; руками не править).
- **`themes/`** — **производное**: 5 CSS-тем (`A_editorial`, `B_manuscript`, `swiss`, `cyberpunk`, `ar_deco`), синк из `cms-revival/themes/`.
- **CMS-клиент** (hand-maintained прямо здесь, без `?v`): `ze-core.js` (общий оверлей-движок
  правки) · `ya-edit.js` (правка статьи) · `ya-struct.js` (структура + создание) ·
  `ya-songs.js` (Песнь Ступеней) · `ya-switch.js` (редирект old↔zml, кнопка «Оригинал») · `ya-auth.js` (логин).
- **Страницы:** `index.html` (главная) · 7 разделов — `best` (Избранное) · `dreamon` ·
  `cyberson` · `dabudet` · `confront` · `shoshana` · `other`; спец-страница `songs/`
  («Песнь Ступеней») · `admin.html` (админка вида) · `structure.html` (управление структурой) ·
  `search.html` · `privacy.html`.
- **`zml/SPEC.md`** — публичная копия спеки формата (сырой .md). **`guide/rukovodstvo.pdf`** — руководство (A4).
- **`pagefind/`** — индекс поиска (производное, `reindex.bat`). `sitemap.xml` · `robots.txt` · `.nojekyll`.

## Источник истины и синхронизация (ключевое)
- **Формат ZML** — канон `cms-revival/zml3/SPEC.md`; публичная копия `docs/zml/SPEC.md`
  (копировать вручную при правке спеки).
- **Контент** — `docs/art/<id>.zml` (живёт в репо). `yaniktoim/manifest.json` — реестр 352
  (арт-id, раздел, дата, заголовок).
- **Движок рендера** — `cms-revival/editor/render.js` (+ `verse_split.js`, `faw_markup.js`,
  шаблоны `data/template_*.html`). `node cms-revival/editor/build_views.mjs [id…]` рендерит
  `.zml`→`.view.html` И синкает render+шаблоны+данные в `docs/editor/`, темы — в `docs/themes/`.
  Один и тот же код у серверной сборки и у браузерного редактора → паритет без дрейфа.
- **Темы** — `cms-revival/themes/*.css` — единственный источник; `docs/themes/` производный.
- **Бэкенд** — `cms-revival/worker/` (Cloudflare Worker `yaniktoim-auth.imyavel.workers.dev`):
  логин (HMAC-сессия, TTL 12 ч) · `/api/save` (коммит `.zml`+`.view.html`, опц. бинарь картинки) ·
  `/api/commit` (структура / новая статья) · `/api/settings` (display.json) · users/promote.
  Секреты (`GH_TOKEN` PAT, `SESSION_SECRET`, `ADMIN_BOOTSTRAP`) — в Cloudflare (`wrangler secret`),
  не в репо. Учётки/хеши паролей — в KV `USERS` (3 admin: Admin/Nipna/Anibe).

## Как править и добавлять
- **Правка статьи** — на `.view.html` кнопка «✎ Править» (editor/admin) → `ze-core` → `/api/save`.
- **Новая статья / структура** — `structure.html` (admin): минт art-id, reorder, move, архив (soft-delete «рукописи не горят»).
- **Песнь Ступеней** — правка на `songs/index.view.html`.
- **Добавление по сырому тексту** — процедуры `yaniktoim/add_art.md` / `add_art_roza.md`, драйвер `.batch/add_one_transform.py`.
- **Локальная отладка** — превью `preview_*` (конфиг `zml-preview`, порт 8099) или headless
  Chrome → JPEG для осмотра зрением. Вёрстку отлаживать **локально ПЕРЕД push**.
- **Пересборки** — вью+синк: `node cms-revival/editor/build_views.mjs` · поиск+sitemap:
  `yaniktoim/reindex.bat` (перед каждым push) · руководство: `cms-revival/guide_build/build_pdf.py`
  → `cp guide.pdf ../../yaniktoim/docs/guide/rukovodstvo.pdf`.

---

# Остальные блоки (кратко)

## `cms-revival/` — исходники движка (maintainable)
Сейчас **только локально**, не под git → единственная копия воркера, движка рендера, тем и
спеки формата. Живой набор: `editor/` · `themes/` · `worker/` (без `node_modules`/`.wrangler`) ·
`zml3/` (канон + teststand) · `guide_build/` (источник руководства: `guide.html` + `build_pdf.py`) ·
`config/` · `plans/roadmap_2_content-mgmt_PLAN.md`. Всё, что отсюда нужно сайту, синкается в
`yaniktoim/docs/` сборкой (`build_views.mjs`) или вручную (`SPEC.md`, PDF руководства).

## `imyavel.github.io/` — корневой лендинг
Заглавная страница домена `imyavel.github.io` (`index.html` + `modus-operandi/`), под которой
живут под-проекты (`/yaniktoim/`, Зохар). Счётчик «N статей в M разделах» на ней фетчит
`/yaniktoim/config/structure.json`. Правок почти не требует.

## `zohar-sulam/` — перевод Зохара
Отдельный статичный сайт (главы по парашам: `bereshit`, `bo`, `balak`, … + `idra-rabba` и т.д.).
Исторически самостоятельный проект под общим доменом. **ZML/CMS его не касаются** — отдельный
конвейер/оркестратор (см. память сессии), здесь не описывается.

## Файлы контейнера
`push.bat` / `pull.bat` (деплой/синк трёх репо) · `README.md` · `roadmap_cms.md` + `roadmap_cms_archive.md`
(локальная летопись миграции — **не входной документ**, для «почему», а не «что делать»).

---

# Инварианты и правила
- 352 статьи, 0 ошибок рендера; вью пересобраны после правок ZML / тем / шаблонов.
- Файлы вида `<name>_NNN.ext` не править в-месте: копия `_NNN+1`, старые версии — история.
- Правки — на живой сайт через `push.bat`, но отладка вёрстки — всегда локально до выката.

## Legacy / не трогать (миграционное — для истории, не для работы)
- В `yaniktoim/`: `legacy/` (старый конвейер) · `raw/` (оригиналы proza.ru, gitignored) ·
  `.batch/`, `_history_1AT/`, `_logs/`, разрозненный скретч (`wave2_*`, `zohar_quotes_*`,
  `music_*`, `descriptions.json`, `yaniktoim.txt`) · `docs/proza-design/` (дизайн-эксперименты,
  исключены из поиска/sitemap).
- В `cms-revival/`: `convert/out*` (артефакты конвертации) · `recon/` (разведка Ф1) ·
  `zml1/`, `zml2/`, `cms-superseded/`, `design_review/` (превзойдённые форматы/эксперименты).

## Публикация этого документа
Мастер — `imyavel/PROJECT.md` (здесь). Для присутствия на github копия кладётся в корень репо
`yaniktoim/` (`yaniktoim/PROJECT.md`) и уходит обычным `push.bat`. Pages её не отдаёт (вне `docs/`),
но она видна на github.com. При правке мастера — повторить копию (как с `zml3/SPEC.md` → `docs/zml/SPEC.md`).

# Roadmap — миграция yaniktoim на ZML + CMS

Живой документ. Обновлять здесь же (`imyavel\roadmap_cms.md`).

## Стартовый контекст (для запуска с чистого контекста)

**Корни (абсолютные пути):**
- Контейнер: `C:\Users\admin\imyavel\` — здесь `push.bat`/`pull.bat`, общий README, этот файл.
- Проект: `C:\Users\admin\imyavel\yaniktoim\` — git-репо (`.git` в корне). Публикуемое —
  подпапка `docs\`; сайт https://imyavel.github.io/yaniktoim/ (GitHub Pages: ветка
  `main`, папка `/docs` — уточнить настройку Pages при первом деплое). URL раздела —
  `…/yaniktoim/<section>/…`.
- Материалы CMS/ZML: `C:\Users\admin\imyavel\cms-revival\`.

**Ключевые входы:**
- Нынешняя вёрстка корпуса: `yaniktoim\docs\art\*.html` (352 файла; в каждом скрытый
  `<script id="yanik-meta">` со scheme/form/rationale/features).
- Оригиналы proza.ru: `yaniktoim\raw\` (351 html).
- Старый промпт-вёрстки (семантика элементов, эталон требований): `yaniktoim\legacy\batch_runner\convert_prompt_005.md`.
- Спеки-референсы: `cms-revival\zml1\SPEC.md` (ZML1 v0.1; + `demo.zml`/`demo.html`) **И
  `cms-revival\zml2\ZML2_SPEC_010.md`** (ЗАВЕРШЁННАЯ ZML2, 16/16 ратифиц.; реестр
  `zml2\decisions_open_003.md`) — оба ВХОДЫ, не база.
  **Канон формата — `cms-revival\zml3\SPEC.md`** (ZML3, СВОЯ спека, v2 — СОЗДАНА;
  обоснования — в архиве, даты 2026-06-10 «сверка с ZML2» и далее).
- Рендер ZML→HTML: `cms-revival\editor\render.js` (`[spl]`, эпилог-по-позиции, чтение
  `theme:`/`width:`); inline-правка: `cms-revival\editor\inline.js`. Шаблоны: ВЬЮ собирается из
  `editor\data\template_view.html` (CSS-правки вью — сюда), второй шаблон — `template.html`.
- Worker-логин (Cloudflare): `cms-revival\worker\` (без `node_modules` — `npm i` в папке; см. его README).
- План управления разделами (Задание B): `cms-revival\plans\roadmap_2_content-mgmt_PLAN.md`.
- Реестр статей (арт-id, разделы, даты): `yaniktoim\manifest.json` (ЖИВОЙ, 352;
  стенд читает именно его — копия в `editor\data` устарела).
- **Темы Ф2 (5):** `cms-revival\themes\*.css` + контракт `THEME_CONTRACT.md` + стенд
  `gallery.mjs` (`node gallery.mjs <theme> [zml]`) + галерея `gallery\index.html`.
- **Конвертер Ф4:** `cms-revival\convert\html_to_zml.py` (HTML→ZML, role-based) →
  `convert\out\*.zml` + флаги; просмотрщик `convert\viewer.html` (ZML×5 тем ↔ оригинал).
- **Сборка ZML-вью + визуальная проверка (локально):** `editor\build_views.mjs` (ZML→`<id>.view.html`
  через тему) + `convert\viewshots.py` (headless Chrome → JPEG-сегменты для осмотра зрением; **картинки в
  контекст модели — ТОЛЬКО JPEG**, PNG режутся/теряют разрешение; умеет `--theme=NAME`/`--width=narrow|wide` —
  рендер tmp-копии view.html с подменой темы, осмотр одной статьи во всех 5 темах; `songs`/`songs:<name>` — снимок спец-страницы). Локальный сервер: `launch.json` → `zml-docs` (8098).
- **Спец-страница «Песнь Ступеней» (`[shir]`, ZML3 §6 — ЗАКРЫТА 2026-06-18):** источник
  `yaniktoim\docs\songs\index.zml` (генерит `cms-revival\convert\gen_songs_zml.py` из `.batch\songs_data.json` +
  ручной канон `convert\songs_overrides.json` [17 авторов, резолв через YouTube]); сборка вью
  `editor\build_songs.mjs` → `docs\songs\index.view.html` (шаблон `editor\data\template_songs.html`, НЕ
  template_view; база-грид+lazy-YT+per-theme плитка в 5 темах). Недостающие треки — `imyavel\songs_missing.md`
  (`convert\songs_missing_report.py`; оператор добавит сам). Живой `docs\songs\index.html` НЕ трогаем до Ф9.
- **Разведка Ф1:** `cms-revival\recon\` (fingerprint/clusters/shots, отчёт `F1_recon_report.md`).

**Деплой:** `imyavel\push.bat` (коммит+пуш всех 3 репо; для yaniktoim сначала
`yaniktoim\reindex.bat` — Pagefind + sitemap). Подтянуть с GitHub: `imyavel\pull.bat`.

**Правила работы:** глобальные — `C:\Users\admin\CLAUDE.md` (общение по-русски; субагенты —
headless `claude.exe -p --model opus`; файлы вида `<name>_NNN.ext` не править в-месте —
копия `_NNN+1`; вывод токенов в конце задачи). Авто-память сессии подхватывается средой.

**Как читать этот документ (карта разделов):**
- **§ «Где мы сейчас + опорный порядок»** — ЕДИНСТВЕННЫЙ источник «где мы / что дальше». Читать первым.
- **§ «Зафиксированные решения»** — закрытые развилки: **А. процесс/проект** (1–7) + **Б. формат ZML3**
  (реестр). Не пересматривать без явного «go». **Канон формата = `cms-revival/zml3/SPEC.md`**; Б — указатель.
- **§ «Фаза сборки ZML3 — чек-лист»** — единый список отложенной реализации (чтобы ничего не потерять).
- **§ «Лестница Ф0–Ф10»** — детальные определения фаз + гейты, со статус-матрицей; это ДЕТАЛИЗАЦИЯ
  опорного порядка, не конкурент ему.
- **§ «Статус» и завершённые этапы** — вынесены в **`roadmap_cms_archive.md`** (летопись + Discovery + 4 этапа; читать для «почему», не «что делать»).
**Правило хода: исполнять только по «go» оператора.** **РЕЖИМ: ВЖИВУЮ (с 2026-06-18, commit `d3b935a`).** Первый
полный выкат Ф8′ состоялся — ZML/вход/админка/ZML-вью уже на боевом `imyavel.github.io/yaniktoim/` (`default_view=old`,
публика видит старые статьи + ссылку на ZML). **Дальше правки идут на живой сайт** (`imyavel\push.bat`), но отладку
вёрстки по-прежнему ведём ЛОКАЛЬНО (превью `preview_*` / headless Chrome → JPEG, осмотр зрением) ПЕРЕД пушем.

## Область
- Касается **только** `imyavel\yaniktoim`. `zohar-sulam` — исторически отдельный
  статичный проект (просто под общим адресом imyavel.github.io после появления
  заглавной); ZML/CMS его **не касаются ни в каком виде**.
- Цель ядра: единая поддерживаемая система — **ZML как источник истины**, красивый
  консистентный вид, правка прямо на сайте (CMS) — без потери качества нынешней
  LLM-вёрстки.

## Где мы сейчас + опорный порядок (ЧИТАТЬ ПЕРВЫМ)
*Единственный источник «где мы / что дальше». Обновлять при смене шага. Детали фаз — в «Лестнице»; летопись — в `roadmap_cms_archive.md`.*

**ТЕКУЩЕЕ (снимок 2026-06-19 02:34 — ЕДИНСТВЕННЫЙ актуальный; детали фич Ф8 — в `roadmap_cms_archive.md`, запись 2026-06-18). Боевой HEAD = `ee18d4b` (+ живые правки оператора могут идти дальше; imyavel.github.io = `de3e055`). Worker = `eda3d271`.**
**(NB: оператор/Nipna уже тестировал Ф8(d) вживую — коммиты `590f936`/`a95dbbc`/`c1e7d2c`: правка 654 → `forced_views.json={"654":"zml"}`, правка songs; всё подхвачено rebase'ом и сохранено.)**

**(+ правки 2026-06-19 после Ф8(c)):**
- **Кнопка «✎ Править» скрыта у анонима/не-редактора — ВЫКАЧЕНО ВЖИВУЮ (`ee18d4b`):** была видна серой (`disabled`).
  Теперь в шаблонах (`template_view.html` + `template_songs.html`) кнопка `hidden` по умолчанию; `ya-edit.js`/`ya-songs.js`
  снимают `hidden` (`btn.hidden=false`) только у editor/admin. Аноним и no-JS её не видят (без мигания), редактор —
  видит и правит. Пересборка 352 вью + songs. Доказано в превью: аноним `display:none`/невидима (статья+песни),
  admin — видима+активна, 0 ошибок. NB: пушилось поверх живой гонки (прилетели `237`/структура от Anibe/Admin) —
  интегрировано через reset на origin + пересборка из их исходников (их структуру/forced_views не задел).
- **Admin-настройки дизайна → анонимам В РАНТАЙМЕ (баг-фикс) — ВЫКАЧЕНО ВЖИВУЮ (`8070da8`):** раньше у анонима тема
  бралась ТОЛЬКО из запечённой на сборке (`build_views`), поэтому правки Admin (`global.design`, правила раздел/тип,
  `width`) до анонимов не доходили — доходил лишь редирект `default_view` (его `ya-switch.js` читает в рантайме).
  Симптом: Admin ставит swiss+new → залогинен видит и то и то, аноним получает редирект new, но тему `editorial`.
  Фикс: блок ре-резолва во `template_view.html` (зашит в каждый вью) теперь работает и для НЕзалогиненных — аноним
  фетчит `../config/display.json` и применяет тот же `resolveDisplay` (global → правила section/type → fm-приоритет),
  залогинен — `/api/settings` (как было). Запечённая тема осталась стартовым/no-JS дефолтом (build печёт текущий
  `display.json` → совпадает с резолвом → без мигания). Потребовало пересборки 352 вью (`node editor/build_views.mjs`).
  Доказано локально (превью 8099, аноним): правило `best→ar_deco/narrow` и `global=cyberpunk` подхватываются в рантайме
  без пересборки; swiss==запечённое → без флипа; 0 ошибок консоли. Побочно: восстановлен `forced_views["songs"]=zml`
  из frontmatter (терялся при инкрементальных правках Worker'а), индексы разделов → `.view.html` (т.к. `default_view=new`).
- **Авто-счётчики + prev/next (аудит 2026-06-19) — ВЫКАЧЕНО ВЖИВУЮ (`49f2360` + landing `de3e055`):**
  Аудит «какие числа авто-обновляются». ✔ Уже авто (из `structure.json`, регенерит `ya-struct`/`build_index`):
  счётчики по разделам на главной, тотал «N статья/и/ей в M разделах», «Статей: N» в разделах (склонение верное).
  ✗ Было НЕ авто → починено: (1) **«N композиций» Песни Ступеней на главной** — был литерал `structure.specials[].meta`;
  теперь динамический скрипт в `template_index.html` считает плитки `[shir]` в `docs/songs/index.zml` (валидные ≥2 поля),
  плюс `build_structure.py::count_shir_tiles` (сид/no-JS; НЕ запускать — затрёт live structure.json). (2) **корневая
  заглавная `imyavel.github.io/index.html`** «N статей в M разделах» — был статичный литерал; теперь скрипт фетчит
  `/yaniktoim/config/structure.json` (тот же origin) и считает. (3) **prev/next в подвале `.view.html`** — были из
  `manifest` (siblings) + не пересобирались → устаревали при вставке/удалении/перемещении/reorder; теперь
  `ya-edit.js::refreshSiblings` (грузится ВСЕМИ вью, до гейта прав) пересчитывает из ЖИВОГО `structure.json` (раздел+order,
  не-archived; заголовки из manifest/record). **Без пересборки 352** (правка одного общего `ya-edit.js`). Касается ТОЛЬКО
  zml-вью, оригинальные `.html` не трогаем. Проверено в превью: главная (220, склонения), prev/next 185A (654↔237), и
  СИМУЛЯЦИЯ архива 22SA → prev 185A стал 654 (восстановлено из git). 0 ошибок консоли.
- **Песнь Ступеней — view: zml паритет (Ф8(d), Worker `eda3d271`) — ВЫКАЧЕНО ВЖИВУЮ (`49f2360`):** `ya-songs.js`
  дописывает `view: zml`; Worker `page:"songs"` → `forced_views.json["songs"]` (общий `reflectForcedView`); шим в
  `songs/index.html` редиректит на `index.view.html`; «Оригинал» вью несёт `?orig=1`; `build_views.mjs` хранит ключ `songs`.
  Тесты воркера 51/51. Проверено в превью (инъекция, редирект, `?orig=1`).
- **Ф8(d) «Приоритет ZML при правке статьи» — ВЫКАЧЕНО ВЖИВУЮ 2026-06-19 (push `b180125`, Worker `f1ca3e4e`):** при открытии
  редактора статьи `docs/ya-edit.js::ensureViewZml` дописывает `view: zml` во frontmatter (только если строки `view:` нет;
  вход CRLF→LF как ze-core; строка видна в textarea — оператор может удалить → статья к общему дефолту, или сменить на
  `view: html` → форс старой; существующий `view:` не трогаем). Worker `/api/save` (новый `parseForcedView`) ТЕМ ЖЕ коммитом
  отражает `view:` в `docs/config/forced_views.json` (set при zml/html, delete если строки нет; коммитит только при реальном
  изменении ключа) → шим `ya-switch` сразу редиректит старый `.html` на `.view.html` даже при `default_view=old` — как
  новые статьи Ф10E и локальный `build_views.mjs` (карта идентична, без дрейфа). **Доказано:** `worker/test_commit.mjs`
  47/47 (+6 кейсов forced_views); `ensureViewZml` прогнан по всем 352 CRLF-`.zml` (нет задвоения fm, title цел, идемпотентно,
  паритет с `parseForcedView` и build_views-регэкспом); превью 8099 на 03H (редактор открывается с `view: zml` в нужном месте
  fm, «Просмотр» рендерит, 0 ошибок консоли). **Чтобы вживую нужно ДВА шага:** (1) redeploy воркера `cms-revival/worker`
  (нужен свежий `CLOUDFLARE_API_TOKEN`, прежний ролльнут) + (2) `push.bat` (выкат `ya-edit.js`). До деплоя воркера строка
  инертна (безвредна — подхватится при следующей `build_views.mjs`/пересборке). `ya-edit.js` без `?v` → после пуша Ctrl+F5
  или ~10 мин (Pages max-age=600). **СДЕЛАНО:** воркер задеплоен (`f1ca3e4e`, токен принят и ролльнуть оператору заново),
  `push.bat`-эквивалент по yaniktoim прогнан (reindex+sitemap+commit+push `181bfe4..b180125`). **Открытый хвост (НЕ блокер):**
  реальную авторизованную проверку (правка статьи под admin → редирект на `.view.html`) делает ОПЕРАТОР под своим паролем —
  сетевой коммит без пароля не гоняю.
- **Превью редактора — якоря (`181bfe4`):** в `srcdoc`-iframe база = URL боевой страницы → клик по `#оглавление`/`#сноска`/
  «↑ наверх» грузил боевой (СТАРЫЙ) файл, и правка в превью «откатывалась». `ze-core` вшивает в превью перехват
  `a[href^="#"]`→`scrollIntoView` (скролл ВНУТРИ srcdoc). Проверено на 654.
- **Фикс под-пути `/yaniktoim/` (`926ac66`):** `import()` в классич. скриптах резолвится от URL СКРИПТА (не документа) →
  `ya-edit.js`/`ya-songs.js` грузят модули абсолютно от `src` (`modUrl`); раньше «Править» падал на проде
  (`Failed to fetch …/editor/render.js`). Незаметно локально (`docs`=корень) — репро только под-путём (junction). См. NB-редактор.
- **Все 3 учётки = admin** (`user:nipna`/`user:anibe` подняты в KV editor→admin 2026-06-19); пароли сохранены.
- **Песни + админка (`52d45c3`, Worker `a6ff0c7f`):** (1) `songs/index.html` → ссылка «✦ Новая версия (ZML)», ZML-вид →
  «Оригинал»; (2) «Песнь Ступеней» = раздел **"songs"** в Ф8′-правилах (`renderSongsHtml` через `resolveDisplay`; frontmatter
  theme/width убран → правит admin в админке; клиент-ре-резолв; `admin.html` SECTIONS += songs); (3) **глобальные умолчания
  (анонимам) задаёт ТОЛЬКО ник `Admin`** — Worker гейт по нику (Nipna/Anibe-admin → ЛИЧНЫЕ), `admin.html` сообщение по нику.
  Проверено в превью (паритет песен, Оригинал, дропдаун, scope Admin/Nipna) + Worker-тест 41/41 (ныне 47/47 после Ф8(d)).

- **Руководство-PDF (2026-06-19) — СОБРАНО, ЛОКАЛЬНО; ждёт push:** книжечка A5 «Путь Восходящей Звезды»
  (35 стр., 2 части: I — управление сайтом для не-тех и тех; II — наглядный справочник ZML, пары «как пишется → как
  выглядит») с кликабельным оглавлением + закладками PDF. Источник (maintainable) — `cms-revival/guide_build/guide.html`
  + сборщик `build_pdf.py` (Chrome `--print-to-pdf` → pypdf добавляет outline по невидимым sentinel'ам `~MKnn~`; нужен
  `pymupdf` лишь для осмотра). Выход → `docs/guide/rukovodstvo.pdf`; ссылка врезана в `docs/admin.html` (рядом с
  «Управление структурой»). **Пересборка:** `cd cms-revival/guide_build && python build_pdf.py && cp guide.pdf
  ../../yaniktoim/docs/guide/rukovodstvo.pdf`. Содержимое справочника сверено с `zml3/SPEC.md`.

- **Публичная ZML-спека (2026-06-20):** канон `cms-revival/zml3/SPEC.md` опубликован как СЫРОЙ .md на сайте —
  `docs/zml/SPEC.md` → https://imyavel.github.io/yaniktoim/zml/SPEC.md (Pages отдаёт .md как текст; НЕ рендерится,
  нигде не слинкован, не в sitemap/Pagefind — те берут только `*.html`). **При правке спеки повторить копию:**
  `cp cms-revival/zml3/SPEC.md yaniktoim/docs/zml/SPEC.md` (как с guide PDF — ручной ре-копи перед push).

- **Новый тег `[faw]` (free-associative writing) — СОБРАНО ЛОКАЛЬНО 2026-06-20; ждёт push:** блок «стихов,
  записанных прозой». Спека — `zml3/SPEC.md §2.5`. Разметка строк знаком «\|»; если «\|» нет — движок размечает
  содержимое по слогам ПЕРЕД сохранением (кнопка «Сохранить»). **Алгоритм** — порт `Documents/verse_tool/
  verse_split_003.py` → `cms-revival/editor/verse_split.js` (словарь+правки вшиты; сверен с Python байт-в-байт:
  61H размер 8, 924 строки; самотест `editor/_faw_test/`). **Хук** — `editor/faw_markup.js::autoMarkupFaw`,
  подключён в `docs/ze-core.js` как `opts.preprocess` (правка статьи `ya-edit.js` + новая `ya-struct.js`),
  идемпотентно. **Рендер** — `render.js::renderFaw` (split по верхнеуровневым «\|» → `.faw-l.a/.b`), faw в `PAIRED`.
  **Вид** — монолит (inline) в swiss/A_editorial/cyberpunk, построчно (block) в B_manuscript/ar_deco; чередование
  двух стилей делает границы строк видимыми (CSS в 5 темах + базе `template_view.html`; THEME_CONTRACT обновлён).
  **Построчные темы:** первая буква строки — заглавная (render оборачивает в `.faw-cap`, темы поднимают в верхний
  регистр; монолит не трогает — проза в авторском регистре; корректно для тире-строк «- Не»). **`[faw sta=N]`** —
  строфы по N строк с пустой строкой-зазором (класс `.faw-se`), в монолите игнорируется. Всё проверено зрением.
  **Нумерованные пункты сквозь строки (2026-06-20):** прозо-стих с нумерованными пунктами (61H: `## 1..7` в
  оглавлении), где строки перетекают через границы — пункты идут ВНУТРИ одного `[faw]` маркерами `=== N {sN} ===`
  (автор) → при «Сохранить» движок режет весь поток разом и ставит инлайн `[fp="N" slug="sN"]` на позиции начала
  пункта (часто в середине строки, строку НЕ рвёт). render: `[fp]` → бейдж `.faw-pt` (id-якорь) + запись в TOC
  (уровень 2, как `##`). Проверено: 61H — 7 пунктов текут сквозь строки (в монолите бейдж в потоке прозы, в
  построчных у начала строки), TOC из 7 пунктов; 61T пунктов нет — сплошной `[faw]`. **Review-пакет:**
  `C:\Users\admin\Documents\faw_review\` — `61H.faw.zml`/`61T.faw.zml` (итоговый ZML, заменит живые при одобрении;
  музыка+сноски снаружи), `*.lines.txt` (61H=925 строк как в razum1, 61T=579 как в deti1), `61H__<тема>.html`/
  `61T__<тема>.html` (рендер в 5 темах).
  **Флаг `allow_faw` (frontmatter, деф. `false` ВЕЗДЕ; SPEC §1.1/§2.5):** стихотворный вид `[faw]` включается
  ТОЛЬКО `allow_faw: true` + Сохранить. По умолчанию разметка `[faw]` ИНЕРТНА — блок рисуется обычной прозой
  (`render.js::renderFawInert`: `|`→пробел, пункты `[fp]`→абзац+бейдж+TOC), но разметка `|`/`[fp]` остаётся в `.zml`.
  Авто-разметка на Сохранить работает независимо от флага (`|` проставляются всегда).
  **ВЫКАЧЕНО ВЖИВУЮ 2026-06-20 (commit `5e332ef`, push `ee18d4b..5e332ef`):** 61H/61T заменены на faw-версии с
  `allow_faw: false` (вид инертен — на живом выглядят обычной прозой: 61H — 7 пунктов+TOC, 61T — сплошной текст);
  весь faw-движок (render/verse_split/faw_markup/ze-core/ya-edit/ya-struct/темы/template_view) + Pagefind reindex +
  sitemap. Дефолт-показ статей не изменён (default_view=old, forced_views не трогали) → faw живёт в ZML-виде.
  **Оператор включит `allow_faw: true` на 61H/61T когда решит** (правка → флаг → Сохранить; либо вручную в `.zml`+пересборка).
  **Безымянные абзацы (2026-06-20, дофикс):** прозо-стих без нумерации (61T — 6 абзацев) размечается так же, но
  границы — ПУСТОЙ СТРОКОЙ внутри `[faw]` → markupFaw ставит `[fp]` без метки (parseText дробит не-секционную
  часть по пустым строкам). render: безымянный `[fp]` в начале строки → новый абзац-блок `.faw-p` (без бейджа/TOC)
  И в инертном виде (`<p>`), И в стихе — между `.faw-p` отступ (`.faw-p + .faw-p`), виден в монолите и построчно;
  внутри абзаца стих течёт/ломается по теме. 61T: 6 абзацев в ОБОИХ видах (579 строк стиха). Паритет 61H с Python
  (924 строки). **ВЫКАЧЕНО ВЖИВУЮ 2026-06-20:** `3d58174` (разметка абзацев) + `3b3885d` (промежутки `.faw-p` в стихе).
  Проверено локально: JS==Python, авто-разметка+идемпотентность (node И браузер, 0 ошибок), 5 тем зрением (JPEG).
  **Файлы:** новые `cms-revival/editor/{verse_split,faw_markup}.js` (+ синк в `docs/editor/` через `build_views.mjs`,
  добавлен туда), правки `render.js`/`ze-core.js`/`ya-edit.js`/`ya-struct.js`/`themes/*.css`/`template_view.html`.
  **Открытый хвост (НЕ блокер):** живой Save под admin (markup→commit) проверит ОПЕРАТОР (сетевой коммит без пароля
  не гоняю); 352 вью НЕ пересобраны (faw в корпусе пока нет — не требуется; появится при первой статье с тегом).

**Ф8 «CMS: правка ZML» — ПОЛНОСТЬЮ ВЖИВУЮ** (роль editor/admin, логин через Worker; боевой `imyavel.github.io/yaniktoim/`):
- **правка статьи** (✎ на ZML-виде → общий `ze-core`, save `/api/save`; `57d3d4e`) + **иллюстрация `image:`** —
  загрузить/заменить/отвязать, бинарный коммит (Ф8(b) `fb6f1ed`, Worker `ae9607a5`);
- **создание новой статьи** (минт art-id, «+ статья» в `structure.html` → `ze-core`, commit `/api/commit`; фаза E `100ffba`);
- **редактирование «Песни Ступеней»** (✎ на `songs/index.view.html`; общий `render.js::renderSongsHtml` — паритет
  node↔браузер байт-в-байт; Ф8(c) `974d682`, Worker `efe2a94e`).
Движок правки — общий `docs/ze-core.js` (`mountZmlEditor`); тонкие обёртки `ya-edit.js`(статья) / `ya-struct.js`
(структура+создание) / `ya-songs.js`(песни). Тесты воркера `worker/test_commit.mjs` 41/41. Живой `songs/index.html`
остаётся как есть (Ф9-cutover СНЯТ — см. ниже). **Открытый хвост (НЕ блокер):** реальную авторизованную проверку live-операций (создание
статьи, загрузка картинки) делает ОПЕРАТОР под своим паролем — сетевой коммит без пароля не гоняю; вся логика
доказана Worker-в-Node + браузерными payload'ами. `ya-struct` image-блок пока не подключён (scope=правка).

**Ф9 «Фиксация» — СНЯТА (устарела, по решению оператора 2026-06-19).** Публичный cutover (снять старые ссылки→архив,
flip на new-by-default, заменить живой `songs/index.html`) НЕ нужен: финальная модель = **сосуществование Ф8′** (старый
HTML по умолчанию + ссылка/кнопка «Новая версия (ZML)»; старые файлы статей и `songs/index.html` остаются жить).
**→ Миграция/CMS завершены и вживую; дальше — поддержка + опц. живые проверки оператором. Остаток структуры (если есть)
— по `cms-revival/plans/roadmap_2_content-mgmt_PLAN.md`.**

**(+ Ф10E «Создание новой статьи» — ВЫКАЧЕНА ВЖИВУЮ 2026-06-18 22:50, `4c883c9`→`100ffba`; ОСТАЛОСЬ: live Save/commit
end-to-end должен проверить ОПЕРАТОР под admin — создать тестовую статью → в архив; я без его пароля не могу):**
кнопка «+ статья» в шапке каждого раздела (`docs/structure.html`/`ya-struct.js`, admin) → минт art-id (кодек
SPEC §2.3 перенесён в браузер; сегодня=`66I`, суффикс A..Z/a..z при коллизии, проверка по всем существующим art) →
шаблон ЧИСТОЙ статьи (эпиграф вверху · `[sub]` · `_курсив_` · `[url|подпись]` · сноска `[^1]`/`[^1]:` · `[poem]`)
открывается в НОВОМ общем оверлей-редакторе `docs/ze-core.js` (`mountZmlEditor`). На сайт попадает ТОЛЬКО по
«Сохранить»: «Просмотр» рисует в iframe БЕЗ фиксации, «Отмена»/закрытие — НИЧЕГО не коммитят (commitNewArticle зовётся
лишь из doSave). Commit через `/api/commit` (admin, 6 файлов одним коммитом: `docs/art/<art>.zml` + `.view.html` +
`config/structure.json` [запись с section/order/status/**title/date**] + `config/forced_views.json` [art→`zml`] +
перегенер. `docs/index.html` + `docs/<section>/index.html`). Новая статья **zml-only** (старого `.html` нет) → ссылка
списка ведёт на `.view.html`: `renderSectionIndexHtml` научен `forced`/`default_view` + фолбэк title/date из самой
записи structure (manifest её ещё не знает). `ya-edit.js` переведён на тот же `ze-core.js` (DRY — один движок правки;
попутно **вылечен латентный баг**: CRLF-исходник textarea нормализует в LF → раньше ложно «несохранённые изменения»,
теперь baseline тоже к LF). Byline БЕЗ пустого «· Источник:» когда url нет (новые оригиналы; единый плейсхолдер
`{{ORIGIN_BYLINE}}`) — **352 корпусных байт-в-байт** (проверено 5 шт.: 03H/53KA/654/075/31C). **Проверено локально**
(превью 8099 + node): шаблон рендерится (эпиграф сверху, byline `#66I · 2026-06-18`, `data-art/-section/-worker`
проставлены → потом правится обычным ✎); создание открывает редактор с минтом; правка 03H открыть/Просмотр/Отмена ОК;
страж правок (чисто→молча, грязно→подтверждение) работает. **ПРОВЕРЕНО ЛОКАЛЬНО end-to-end (без живого сайта и без
пароля оператора):** (1) браузер с перехватом `fetch` — настоящий `ya-struct.commitNewArticle` собрал ВЕРНЫЙ
6-файловый payload (66I/best, `forced=zml`, ссылка списка на `.view.html` [не голый `.html`], счётчик 352→353,
title/date в записи) + обработал успех (popup, дерево обновилось); (2) НАСТОЯЩИЙ код Worker'а в Node (фейк-KV +
мок-GitHub) — тест **`cms-revival/worker/test_commit.mjs`** (14/14): `login`→token, `/api/commit` принял payload,
проверил роль admin + пути `docs/`, собрал коммит из 6 blob'ов с верным содержимым (декод base64), обновил ref;
негативы (editor-роль косвенно через path/auth, путь-вне-`docs/`→400, без токена→401, пустой `files[]`→400). **НЕ
покрыт лишь реальный сетевой вызов GitHub API** — тот же `commitFiles`, доказан вживую B–G/Ф8. **Файлы (6,
все под `docs/`):** `ze-core.js`(НОВЫЙ, hand-maintained, без версии — как `ya-edit.js`), `ya-edit.js`, `ya-struct.js`,
`structure.html`(ver `?v=20260618-05`), `editor/render.js` + `editor/data/template_view.html` (СИНК из cms-revival).
**Источники в `cms-revival/editor/` (НЕ git-репо, не деплоится — синкается в docs/editor через `build_views.mjs` или
вручную `cp`):** `render.js` (renderSectionIndexHtml forced/title-fallback + byline `{{ORIGIN_BYLINE}}`),
`build_index.mjs` (проброс `forced`+`defaultView`), `data/template_view.html` (byline). **Кэш:** правка
`template_view.html` подхватится, т.к. оба редактора фетчат его с `cache:"no-store"`; `ya-edit.js`/`ze-core.js` без
`?v` — старая/новая версии обе рабочие (старый ya-edit — самодостаточный монолит), 352 вью НЕ пересобирались.

**Доработки редактора (одобрены 2026-06-18) — ВСЕ ТРИ ЗАКРЫТЫ:** (1) «Просмотр» новой статьи без фиксации — сделано в
фазе E; (2) иллюстрация `image:` — Ф8(b) `fb6f1ed`; (3) редактирование «Песни Ступеней» — Ф8(c) `974d682`. Полные ТЗ +
реализация — в `roadmap_cms_archive.md` (запись 2026-06-18). Открытый микро-хвост: `ya-struct` (создание) image-блок не
подключён (scope=правка).

**(+ Ф10 B–G ВЫКАЧЕНЫ ВЖИВУЮ 21:28, `23f8a0e`→`4c883c9`):** управление структурой на сайте. Фундамент (A): `structure.json`
(единый источник) + живой генератор главной/разделов (`build_index.mjs`+render-функции; склонение «N статей» исправлено).
Редактор (B–G): `docs/structure.html`+`ya-struct.js` (admin-only, ссылка в admin.html) — reorder/rename/add/delete
разделов, reorder/move/archive(soft-delete «рукописи не горят»)/restore статей; разделы сворачиваются. Save→Worker
`/api/commit` (новый admin-эндпоинт, version `6bda83ee`; проверен end-to-end). **Остаток Ф10:** только фаза E — создание
НОВОЙ статьи (минт art-id). NB-предел: крошки ВНУТРИ статей при rename/move раздела обновятся при полной пересборке;
переименование заголовка статьи — через ZML-редактор «Править».
**(+ Ф8 ВЫКАЧЕНА ВЖИВУЮ 20:46, commit `57d3d4e`; правка ZML работает в проде):** редактор `docs/ya-edit.js` на ZML-видах —
кнопка «✎ Править» (только editor/admin) заменяет просмотр статьи простым редактором ZML; Просмотр (рендер в браузере
тем же `render.js` → паритет байт-в-байт с `build_views.mjs`, доказан), Сохранить (→ Worker `/api/save` коммитит
`docs/art/<art>.zml` + `.view.html`), Отмена, popup. Движок+данные отдаются в `docs/editor/` (производное `build_views.mjs`,
исключено из поиска/sitemap). **Worker перевыпущен/задеплоен** (version `fb72548a`; патч путей на плоскую раскладку),
токен «Edit Cloudflare Workers» принят. **Живой Save проверен end-to-end** (временный editor-юзер в KV, ныне удалён;
правка 03H→коммит по верному пути→ревёрт; коммиты `b1a5948`/`ad17aa3`, затем `73e8093` вернул LF в 03H.zml). **Остаток
Ф8 (добор):** создание НОВОЙ статьи тем же редактором (пустой ZML из шаблона + минт art-id) — ещё не сделано.
**(+ автономный добор 19:52, запушено `5e9a0bb`):** закрыт баг «поиск не находит статью по арт-id» — в 352 статьи добавлен
скрытый индексируемый Pagefind-токен «Артикль №<ID>» (weight=10), поиск по `654/237/03H/22SA/1AQA` (с `#` и без) теперь
ставит саму статью первой; инструмент `yaniktoim/tools/add_artid_search.py` (идемпотентный). Заодно `proza-design/`
(дизайн-эксперименты, нигде не слинкованы) исключён из поиска (`data-pagefind-ignore`) и из sitemap (`build_sitemap.py`
→ EXCLUDE_DIRS) → индекс/sitemap = 363 стр. (было 374); Pagefind переиндексирован начисто (убраны stale `.pf_meta`).
**Позиция: Ф8′ «Сосуществование (old-by-default) + персональная админка стилей» — РЕАЛИЗОВАНА И ЗАПУШЕНА ВЖИВУЮ** (commit `d3b935a`, 2026-06-18; спека
`cms-revival/plans/admin_display_PLAN.md`, 6 шагов, проверена в превью; ОТМЕНЯЕТ прежнюю модель доступа Ф9). Ф5-гейт
заморозки пропущен по решению оператора (формат больше не трогаем). **Что сделано (Ф8′ — РЕАЛИЗОВАНО И ВЖИВУЮ, см. блок «ВЫКАЧЕНО ВЖИВУЮ» ниже):** (1) конвертер —
поле `type:` (verse/poem/prose/dialog/prose_num), эмит `theme/width` убран → 352 переконвертированы (тело не тронуто,
CHANGED=0); (2) `docs/config/display.json` (default_view + global + rules); (3) резолвер `resolveDisplay` в render.js
(fm-override → правило раздела/типа сверху-вниз → global), запекание анон-вида в 352 вью + клиент-ре-резолвинг
залогиненных; (4) шим `docs/ya-switch.js` (редирект по default_view, гард `?orig=1`) во всех 352
старых; кнопка «Оригинал» во вью; (5) Worker `GET/PUT /api/settings` (editor→KV, admin→коммит display.json); (6) вход
`docs/ya-auth.js` на главной + `docs/admin.html` (тумблер old/new, global, таблица правил +/↑↓/✕, общий select
раздел|тип). **(+ дополнение 16:16):** per-article forced `view: zml|html` во frontmatter перебивает `default_view`
(конвертер сохраняет ручные `view/theme/width` при реконверсии; `build_views.mjs` пишет `docs/config/forced_views.json`
и переписывает ссылки `docs/<section>/index.html`; шим учитывает forced) — ссылка из списка раздела открывает нужную
версию напрямую. Побочно закрыт пробел: **списки разделов теперь по умолчанию ведут на СТАРЫЙ html** (были на .view.html).
**(+ дополнение 17:50):** (7) добавлена страница приватности `docs/privacy.html` + линк в подвале главной (cookies для
публики НЕ ставятся; токен входа = localStorage, технически необходимый → баннер-согласие не нужен; аналитика
GoatCounter без cookies); вход «Войти» перенесён в подвал главной, в одну строку со счётчиком просмотров (справа).
**(+ дополнение 18:09):** убран чёрный верхний бар на старых статьях — ссылка «✦ Новая версия (ZML)» теперь
вставляется СПРАВА в строку «хлебных крошек» (Главная / Раздел), цвет/шрифт/uppercase наследуются от `.crumbs`
темы (однородно); вход/выход со статей убраны (логин только на главной). Шапка-крошки проверена: 352/352 имеют
`.crumbs`/`.breadcrumbs` (варианты nav.crumbs · header.crumbs>nav · nav.breadcrumbs · div.crumbs) — `ya-switch.js`
цепляет родителя первой ссылки и равняет вправо (float; flex-ветка про запас, в корпусе flex-крошек нет).
Проверено в превью на 654/075/31C. Ссылка наследует обычный вес крошек (font-weight НЕ задаём).
Плюс `tightenTopGap()` режет вдвое верхний отступ шапки (computed `paddingTop`/`marginTop` крошек И внутр.
линии, дубль исключён, idempotent) — на всех 352 статьях; отступ в корпусе всегда от padding крошек/внутр.nav
(654: 30→15, 075: 28→14, 31C: 16→8, full-bleed бар остаётся у верха). Касается только статей (шим ya-switch.js).
**(+ дополнение 18:43):** тот же верхний отступ срезан вдвое и на ОСТАЛЬНЫХ типах страниц через `.wrap{padding-top}`:
ZML-вью — в 5 темах `cms-revival/themes/*.css` (A/cyber 2.4→1.2rem · B/ar 2.6→1.3rem · swiss 3→1.5rem), синк в
`docs/themes` + пересборка `build_views.mjs`; заглавная + 9 списков разделов (+admin/privacy/search) — общий
`docs/style.css` 2.5→1.25rem (одна правка). Кэш-бастер бампнут: `style.css?v=20260531-02`→`20260618-01` в 11 html
(songs/index.html НЕ трогал — по правилу «не трогать до Ф9»; .wrap всё равно подхватит при свежем заходе) +
`render.js CSS_VERSION 20260613-01`→`20260618-01` (вью линкуют `themes/*.css?v=…`). Проверено в превью: вью=19px,
заглавная=20px, список раздела=20px; все 5 тем отдают урезанный padding.
**(+ дополнение 19:00, запушено `2fc7a2f`):** крошки «Главная / Раздел» во ВЬЮ всегда слева — базовое правило шаблона
`header.breadcrumbs .crumbs{text-align:left}` (грузится после темы → перебивает центрирующие B_manuscript/ar_deco;
центрирование их заголовков/byline сохранено); 352 вью пересобраны, проверено на manuscript/ar_deco.
**CLOUDFLARE-ЧАСТЬ ЗАКРЫТА (17:43):** Worker **задеплоен** с новым кодом (CORS для localhost + `/api/settings`,
version 9250fc78); заведены **3 учётки в KV** — `Admin`(admin) / `Nipna`(editor) / `Anibe`(editor), один пароль (у
оператора, в roadmap НЕ пишем); вход проверен end-to-end через превью-браузер (верный пароль→токен, неверный→401,
CORS localhost ОК, админка Admin грузит настройки воркером). Деплой-токен (`Edit Cloudflare Workers`) после работы
**ролльнут оператором** — для будущих деплоев нужен свежий `CLOUDFLARE_API_TOKEN`.
**ВЫКАЧЕНО ВЖИВУЮ (2026-06-18 18:49, commit `d3b935a`):** `push.bat`-эквивалент прогнан для yaniktoim (Pagefind reindex +
sitemap 374 стр. + commit + push `origin main`; `origin/main==HEAD`). 1074 файла, 0 удалений, ничего вне `docs/`;
zohar-sulam и imyavel.github.io были чисты (нечего пушить). `docs/config/display.json` уже в репо (`default_view=old`).
`songs/index.html` в выкат НЕ менялся (правило «не трогать до Ф9»); songs `index.view.html`/`index.zml` добавлены как
файлы (нигде публично не слинкованы). **ОСТАЛОСЬ:** замена тем A/B и полнота `[shir]` (`songs_missing.md` у оператора)
— обе ЗАКРЫТЫ по решению оператора (2026-06-18), сняты с очереди работ.

**Сделано в фазе сборки:** ВСЕ формат-пункты закрыты — перечень статусом в § «Фаза сборки ZML3», полная летопись
(как/почему, по датам) — в `roadmap_cms_archive.md`.

**Остаток / порядок дальше** (Ф8′ ВЫПОЛНЕНА И ВЖИВУЮ; Ф5-гейт заморозки формата ПРОПУЩЕН — формат финализирован
де-факто): **Ф8** (inline-правка + иллюстрация + создание статьи + песни) и **Ф10** (управление структурой:
rename/reorder/add/перемещение + архив-soft-delete «рукописи не горят», editor/admin) — **ОБЕ ВЫПОЛНЕНЫ И ВЖИВУЮ**
(трекер структуры: `cms-revival/plans/roadmap_2_content-mgmt_PLAN.md`). **Ф9 фиксация — СНЯТА (устарела, решение
оператора 2026-06-19):** публичный cutover не нужен, финал = сосуществование Ф8′. Дальше — поддержка + опц. живые
проверки оператором.
**Закрыто по решению оператора (2026-06-18), вне очереди работ:** замена тем **A/B** (отложена/снята) и **полнота
songs** (`songs_missing.md` у оператора — добавит сам).

**Инварианты (держать при каждом прогоне):** 352/0 ошибок · коридор покрытия 338/352 · FN_DEFS 971 ·
out⇄docs/art синхронны · вью пересобраны.

**NB для холодного старта:** вью собирает `editor/data/template_view.html` (НЕ `template.html`) — CSS-правки вью туда ·
источник тем = `cms-revival/themes/` (`docs/themes/` производный, `build_views.mjs` синкает) · пересборка после правок
ZML = `cp convert/out/*.zml ../yaniktoim/docs/art/` + `node editor/build_views.mjs` · корпус-прогон+инварианты =
`python convert/_run_check.py` · скрин-осмотр зрением = `python convert/viewshots.py <id>` → `_viewshots/*.jpg`
(в контекст модели ТОЛЬКО JPEG) · **пересборка songs** = `python convert/gen_songs_zml.py` + `node editor/build_songs.mjs`
(→ `docs/songs/index.view.html`; живой `index.html` НЕ трогать) · `yaniktoim/` — СОСЕД `cms-revival/` (из cms-revival в bash нужен путь `../yaniktoim/...`) ·
локальный preview (инструменты `preview_*`) = конфиг **`zml-preview` (8099)** в `~/.claude/launch.json` — порт 8098 обычно занят ручным сервером оператора (туда `preview_start` не встаёт).
**NB редактор (Ф8/Ф10E):** движок правки — общий `docs/ze-core.js` (`mountZmlEditor({label,initialZml,renderView,save,…})`,
hand-maintained в docs/, без `?v`); `docs/ya-edit.js` (правка существующей, save=`/api/save`) и `docs/ya-struct.js`
(структура + создание, save=`/api/commit`) — тонкие обёртки над ним, тоже hand-maintained в docs/. `docs/editor/render.js`
+ `docs/editor/data/*` — ПРОИЗВОДНЫЕ от `cms-revival/editor/` (синк `build_views.mjs` или `cp`); правишь render/шаблон —
правь в `cms-revival/editor/`, ПОТОМ синкай в `docs/editor/`. **Динамический `import()` в этих классических скриптах
резолвится от URL САМОГО СКРИПТА** (все три лежат в `docs/` → на проде `/yaniktoim/<script>.js`), НЕ от документа
(прежняя заметка ошибалась). Поэтому `ya-edit.js`/`ya-songs.js` (грузятся со страниц в ПОД-папках `docs/art|songs/`)
резолвят модули **абсолютно от своего `src`** — `modUrl(p)=new URL(p, SELF_SRC)`, где `SELF_SRC=document.currentScript.src`;
иначе на под-пути `/yaniktoim/` `../editor/render.js` вылетает в корень (`Failed to fetch …/editor/render.js`; фикс
`926ac66`, баг был НЕВИДИМ локально, где `docs`=корень и `../`=`/yaniktoim/` совпадают). `ya-struct.js` (его страница
`structure.html` — в той же `docs/`) использует `./editor/…`/`./ze-core.js` — корректно и так (не трогали). **fetch'и**
остаются document-relative (верно резолвятся от страницы). **Репро под-пути ЛОКАЛЬНО:** junction `<tmp>/yaniktoim`→`docs`
+ `python -m http.server` на `<tmp>` → `…/yaniktoim/art/<id>.view.html` (иначе баг не воспроизвести — обычный preview даёт
`docs`=корень). **Кэш:** скрипты без `?v` → после правки нужен hard-refresh (Ctrl+F5) либо ~10 мин (Pages `max-age=600`).
Локальная проверка редактора: фейк-сессия `localStorage.ya_session={token:…,role:"admin",nick:"Admin"}` (UI-гейт по роли;
live Save/commit на фейк-токене даст 401 — безвредно, репо не трогает).

**NB Cloudflare/Worker (состояние на 2026-06-19, version `f1ca3e4e` — Ф8(d) forced_views в /api/save):** воркер `cms-revival/worker/` ЗАДЕПЛОЕН и живёт на
`https://yaniktoim-auth.imyavel.workers.dev` (эндпоинты: login/me/save · GET/PUT `/api/settings` · `/api/commit` · admin/users,promote).
**Ф8(b):** `/api/save` принимает опц. `image:{name,content}` (бинарь→`docs/img/`); `commitFiles` чтит `f.binary` (content =
ЧИСТЫЙ base64, без utf8-обёртки) — общий для save/commit. **Ф8(c):** `/api/save` `page:"songs"` → фикс. пути
`docs/songs/index.zml`+`index.view.html` (editor+admin, без art). **Настройки (2026-06-19):** `GET/PUT /api/settings`
ГЛОБАЛЬ (анонимам, коммит `display.json`) — гейт по НИКУ `admin` (`isMasterAdmin`), не по роли; прочие admin/editor →
личные KV. **Ф8(d):** `/api/save` (статья) теперь `parseForcedView(zml)` → обновляет `forced_views.json` тем же коммитом
(per-article `view:` форс). Тест: `worker/test_commit.mjs` (47/47, мок-GitHub в Node; +`contents/` GET-мок для чтения forced_views).
KV-namespace **USERS** id `2a6d63cdc96c447491471c80cb62bb5c`; в нём 3 учётки `user:admin`(admin)/`user:nipna`(admin)/`user:anibe`(admin)
(**Nipna+Anibe подняты editor→admin 2026-06-19** правкой role в KV; пароль/соль/хеш сохранены), один пароль (у оператора). · **Деплой/правка KV из CLI:** нужен СВЕЖИЙ `CLOUDFLARE_API_TOKEN` (env var; прежний ролльнут
оператором 2026-06-18) — шаблон токена «Edit Cloudflare Workers»; затем `cd cms-revival/worker; wrangler deploy`. ·
**Сброс/перезавод паролей:** `cms-revival/worker/seed_users.ps1` (скрытый ввод) ИЛИ запись в KV напрямую — формат
`{nick,role,salt,hash,createdAt}`, хеш = PBKDF2-HMAC-SHA256, 100000 итер., соль 16 байт, выход 32 байта, обе в base64
(совпадает побайтно с `derive()` воркера). · **DNS-нюанс песочницы:** из Bash/PowerShell `*.workers.dev` НЕ резолвится
(curl→exit6), но **превью-браузер ходит в сеть** — HTTP-тесты воркера (login/CORS) гонять через `preview_eval` fetch, не curl.
· CORS воркера: боевой `imyavel.github.io` + любой `localhost/127.0.0.1` (правка `corsAllowOrigin`).

**Опорный порядок (каждый шаг — по «go» оператора). Это ГЛАВНАЯ последовательность; Лестница Ф0–Ф10 — её детализация.**
- ✔ **Шаги 1–5а пройдены** (детали — в архиве/Лестнице): пред-проход render/converter · дизайн-аудит 5 тем ·
  аудит обобщаемости → конвертер v2 (решение B+C) · корпус 352 конвертирован по продакшен-путям · навигация
  каталог→вью (клик по названию → ZML-вью; ПОЗЖЕ заменено моделью Ф8′) · спот-чек вью + флаг-вопросы (fn-ревью · хвост 22 ст. · решения А–Г).
- 🔧 **6. Фаза сборки ZML3 — ВСЕ формат-пункты закрыты.** Статус — в блоках «Сделано в фазе сборки» и «Остаток»
  выше; детальный чек-лист — § «Фаза сборки ZML3». Ф5-заморозка пропущена оператором (формат финализирован де-факто).
- ✅ **7. Ф8′ «Сосуществование (old-by-default) + персональная админка стилей» — ВЫПОЛНЕНА И ЗАПУШЕНА ВЖИВУЮ**
  (2026-06-18, `d3b935a`; спека `cms-revival/plans/admin_display_PLAN.md`). Дефолт показа = старый HTML + ссылка
  «Новая версия (ZML)» в строке крошек; мини-админка (логин по нику через Worker) на пользователя — тумблер old/new +
  таблица правил «раздел/тип → дизайн+ширина»; Admin = анон-дефолт (колофон «Иван Иванович»), Nipna/Anibe — личные.
  Front-matter `theme`/`width` обнулены, умолчания → центральный конфиг; `type:` — новое поле. **ОТМЕНИЛА** прежнюю
  модель доступа Ф9 (клик по названию → ZML) и вобрала Worker-логин из Ф8.
- 🆕 **8. СЛЕДУЮЩЕЕ** (всё по «go», ВЖИВУЮ через `push.bat`):
  - ✅ **(a) ВЫКАТ фазы E** — ВЫКАЧЕНО ВЖИВУЮ 2026-06-18 (`100ffba`, 6 файлов) + **проверено локально end-to-end**
    (браузерный payload + Worker-в-Node `worker/test_commit.mjs`, 14/14). Реальный сетевой GitHub-вызов не гонялся
    (тот же доказанный `commitFiles`); оператор может опц. создать тестовую статью вживую, но это не блокер.
  - ✅ **(b) Иллюстрация (`image:`) в ZML-редакторе** — upload/replace/delete; ВЫКАЧЕНО ВЖИВУЮ (`fb6f1ed` + Worker `ae9607a5`),
    проверено локально (Worker-в-Node 28/28 + браузерный payload). Живой тест загрузки ПРОПУЩЕН по решению оператора (2026-06-18). ЗАКРЫТО.
  - ✅ **(c) Редактируемость «Песни Ступеней»** — ✎ + браузерный рендер-паритет с `build_songs.mjs`; ВЫКАЧЕНО ВЖИВУЮ
    (`974d682` + Worker `efe2a94e`); паритет доказан байт-в-байт + браузер end-to-end. ЗАКРЫТО.
  - 🔒 **Ф9 фиксация — СНЯТА (устарела, по решению оператора 2026-06-19):** cutover не нужен — финальная модель =
    сосуществование Ф8′ (старое остаётся, новое доступно по ссылке/кнопке). Старые ссылки/файлы/`songs/index.html` НЕ снимаем.
  - План структуры — `cms-revival/plans/roadmap_2_content-mgmt_PLAN.md` (фазы A–G + трекер). Замена тем **A/B** и
    **полнота songs-данных** — закрыты оператором (2026-06-18), вне очереди.

## Зафиксированные решения (развилки закрыты)
*Две группы: **А. Процесс/проект** (1–7) и **Б. Формат ZML3** (реестр в конце раздела). Канон формата —
`cms-revival/zml3/SPEC.md`; здесь — указатели + даты вердиктов в архиве.*

### А. Процесс и проект
1. **Формат истины — ZML3** (= база ZML1 + `[spl]` + опции frontmatter). Lineage:
   zml1 → zml2 (отказ от капс/списка/`^`) → LLM→html → ныне **zml3**. Канон и перечень
   добавлений — `cms-revival/zml3/SPEC.md` (v2).
2. **Источник конвертации — HTML→ZML**: текст+структуру тянем из утверждённой живой
   вёрстки; **старая HTML сохраняется как оракул** для сверки переноса.
3. **Красота → 2–5 тем-дизайнов:**
   - Разведку (фингерпринт), проектирование тем и стартовую классификацию делает
     **LLM, не оператор**. CSS оператор не пишет нигде — только выбирает тему.
   - Темы — **плоский набор, НЕ привязанный к форме**: каждая тема полная и
     form-agnostic (умеет красиво рендерить и стих, и прозу, и эпиграф/сноски/
     музыку/TOC). Нет правила «стихам — тему стихов».
   - `theme:` во frontmatter — **свободный выбор оператора в редакторе** на каждую
     статью. LLM-привязка при миграции = лишь **стартовый дефолт** (ближайший
     фингерпринт), переопределяется в любой момент.
   - **Ширина колонки — отдельное поле** `width` во frontmatter
     **ортогональное теме**. Набор значений
     `width` **определяет сама разведка Ф1** по фактическим ширинам корпуса — не
     презюмируем «2» (навскидку ~820px и ~2/3, но сколько реально стандартов —
     скажут данные). CSS к ширине жёстко не привязан.
     **Гарантия качества — тема при её РОДНОЙ ширине** (преобладавшей в её кластере)
     и в ZML-отражении с тем же выбором ширины. При смене ширины тема **обязана
     корректно отрисоваться** (не ломаться), но менее благовидный вид в неродной паре
     допустим и **не блокирует** выбор темы/ширины. Width-aware лишь детали
     (выравнивание поэмы, мера строки). Кластеризация в Ф1
     идёт по эстетике **без** ширины — чтобы не воссоздать «узкую/широкую тему».
     Два независимых рычага на статью: ширина × тема.
   - **→ ЗАКРЫТО в Ф1 (2026-06-10):** K=**5** тем (A editorial, B manuscript,
     cyberpunk, swiss, ar-deco), **ширины = 2** (~820 narrow / ~1080 wide). Метод
     разведки оказался не токен-фингерпринт (слишком груб), а **рендер-арбитр**
     (headless Chrome → визуальная кластеризация зрением); см. `recon/F1_recon_report.md`.
4. **Сосуществование двух версий:** в каталоге у каждой статьи **две ссылки** —
   «новая» (ZML-рендер + CMS-правка) и «старая» (нынешний статичный HTML).
   Старая **не удаляется**, пока весь корпус не перенесён в ZML, не сверен и не
   получил edit. Публикуем инкрементально по мере готовности.
   **(Уточнено:** модель «новая (ZML) ссылка per-article по мере готовности, список растёт постатейно; старая
   есть всегда» — это ФИНАЛЬНОЕ сосуществование (Ф6/Ф9). Разработку/проверку ведём ЛОКАЛЬНО, на сайт публикуем
   целиком по готовности.)** **[СУПЕРСИД Ф8′ 2026-06-18:** реализована ДРУГАЯ модель — old-by-default + ссылка
   «Новая версия (ZML)» в крошках + per-user админка стилей; выкат уже СОСТОЯЛСЯ ВЖИВУЮ (`d3b935a`), режим теперь
   live-инкрементальный. Текст выше — для истории.]
5. **Порядок:** разведка кластеров → пилот «1 статья на кластер» → массово по кластерам.
   (По разделу — отвергнуто: раздел мешает темы.)
6. **prompt3-A** (`[spl]`) — в фазу финализации формата (Ф3). **prompt3-B**
   (управление разделами) — финальная фаза (Ф10).
7. **[СУПЕРСИД Ф8′ 2026-06-18 — оставлено для истории.]** ФАКТ: разработка теперь ВЖИВУЮ (выкат состоялся `d3b935a`),
   доступ к ZML — через ссылку «Новая версия (ZML)» в крошках / кнопку (НЕ клик по названию); Ф8 (реальная inline-правка)
   ещё впереди. Ниже — прежняя (отменённая) формулировка: ~~«разработка ЛОКАЛЬНАЯ; в финале к новой версии ведёт клик по
   названию статьи»~~.
   ZML-вид (`<id>.view.html`, read-only, переключатель темы(5)/ширины(2)) собирается локально
   (`editor/build_views.mjs`), проверяется headless-скриншотами (`convert/viewshots.py`, осмотр зрением);
   публично не показывается до полной готовности (выкат целиком). Последовательность:
   - **СЕЙЧАС:** локальная доводка формата и вёрстки 5 тем.
   - **Ф8 — реальное редактирование** в окне ZML-вида (Worker-логин + inline-правка + коммит).
   - **Ф9 (финал):** клик по САМОМУ названию статьи ведёт на ZML-версию (как сейчас на оригинал) — это и есть
     финальный механизм доступа к новой версии.

### Б. Формат ZML3 (реестр решений; канон = `cms-revival/zml3/SPEC.md`, обоснования — в архиве по датам)
Все развилки формата A→C + микро-развилки **пройдены (2026-06-10)**. ZML3 = конструкции **ZML2** +
**3 осознанных расхождения** + **5 новых поверх**. Сведено в `zml3/SPEC.md` (v2; §13 = карта реализации).
- **Lineage:** ZML3 — СВОЯ спека, НЕ базируется на zml1/zml2; оба — референсные входы.
- **3 расхождения с ратифиц. ZML2:** A1 `caps`-флаг (деф. **OFF**=литерально, ≠ zml2) · A2 `notes_title`
  (хранить, ≠ zml2-выброс) · A3 orphan-сноска (сохраняет номер, но без backref-`↑` — уточняет zml2 Q11).
- **5 новых поверх ZML2:** `[spl]` (спойлер) · ортогональная `width` (820/1080) · `audio:` 🎧 ·
  `[shir]` (грид песен, line-based, закрыт 8/8) · `[subsec]` (section-subtitle).
- **+ `[faw]` (2026-06-20):** free-associative writing — стихи, записанные прозой; разбивка строк «\|» по счёту
  слогов (порт `verse_tool`), флаг `allow_faw` (деф. OFF → инертная проза), нумерованные пункты `=== N {slug} ===`
  → `[fp]`+TOC и безымянные абзацы (пустая строка) → `[fp]` без метки. Канон — `zml3/SPEC.md §1.1/§2.5`.
- **Взято из ZML2 батчем «всё» (C10–C14):** inline `{term|…}`/`{leit|…}` · блоки `[sig]`/`[cry]` ·
  `[quote kind=scripture]` · глифы `<\^/>`/`</v\>`/эмотиконы→`.glyph` + чистка `;;;;` · `[num]` обобщён.
- **Модель `[epi]` (A4+B5):** единый блок-роль «обрамление», ось `kind=prose|verse|aphorism`; эпилог =
  `[epi]` в хвостовой позиции (тег `[epil]` убран). [[project_yaniktoim_epigraph_functional]]
- **Прочее закрыто:** B6 см.-также → `См. также: [[ID]] — Автор` · B7 byline → канон art-id ·
  B8 H1-приоритет внутри-статьи над manifest · B9 cover → `frontmatter.image` (`../img/`) ·
  `lead-source` без изменений · выключка эпиграфа — per-theme · музыка-дубль не дедупим · `[mus]` валиден при ≥1 поле.

**Реализация отложенных пунктов — см. § «Фаза сборки».**

## Фаза сборки ZML3 — чек-лист (единый реестр отложенной реализации)
*Реестр того, что было отложено в фазу сборки. **✔ закрытые пункты — здесь только перечнем (имена/статус); полная
летопись «как/почему» по датам — в `roadmap_cms_archive.md`.** Открытое (🟡 нужна полировка/добор · ⏳ поздний этап ·
⬜ не начато) — ниже в полном объёме.*

**Конвертер (`convert/html_to_zml.py`) — ✔ всё закрыто:** role-based корпус 352 (коридор 338/0) · `[epi kind]` ·
`audio:` · `notes_title:` · H1-приоритет (B8) · `[subsec]` + спасение 18 header-подзаголовков · term/leit · sig · cry ·
глифы→`.glyph` · CAPS `caps:on` (proper-nouns по данным, 171) · B6 см.-также.

**Render (`editor/render.js`) + шаблоны — ✔ всё закрыто:** term/leit · sig/cry · глифы→`.glyph` · CAPS-флаг (деф. OFF) ·
`audio:` 🎧 · `notes_title:` · эпилог-по-позиции (`[epil]` убран).

**Темы (5 × `cms-revival/themes/*.css`) + контракт:**
- ✔ ЗАКРЫТО: per-theme эстетика ZML3-элементов (`.glyph`/`[sig]`/`[cry]`/term/leit · audio-🎧 · `.sec-sub` ·
  verse-эпиграф) · плитка `[shir]` 5 тем · шрифт-стеки.
- 🟡 Полировка 5 тем по отчёту дизайн-аудита (= завершение Ф2).
- 🔒 **ЗАМЕНА тем A_editorial + B_manuscript — ЗАКРЫТО по решению оператора (2026-06-18):** снято с очереди работ
  (ранее ⏳ поздний этап). Если вернёмся — переработать обе по образцу-эталону оператора; cyberpunk/swiss/ar_deco
  не трогать; не ломать переключатель тем и `THEME_CONTRACT.md`; A/B — дефолты editorial/manuscript-схем.

**Музыка / Песнь Ступеней (`[shir]`):**
- ✔ ЗАКРЫТО: канон «Назв — Автор» · форум `[dlg]` · `[shir]` ядро (парсер/`renderShir`/диагностика битой строки) +
  база-грид lazy-YouTube + 5 тем + миграция `docs/songs/`→`index.zml`→`index.view.html` (220 плиток, автор у всех 220;
  живой `index.html` НЕ тронут — cutover Ф9) · динамик-mute (`[mus]`+songs) + равнение трек-строк + равная высота плиток + фикс глифа.
- ✔ **Редактируемость «Песни Ступеней» (Ф8(c), 2026-06-18, `974d682`):** ✎ на `songs/index.view.html` → `ze-core`; общий
  `render.js::renderSongsHtml` (node `build_songs.mjs` ↔ браузер `docs/ya-songs.js`, паритет байт-в-байт); save `/api/save`
  `page:"songs"`. Живой `index.html` не тронут (cutover Ф9).
- 🔒 **(а) Полнота «Песни Ступеней» — ЗАКРЫТО по решению оператора (2026-06-18):** снято с очереди работ. Список у
  оператора `imyavel/songs_missing.md` (27 = 17 альт + 10 новых; ген. `convert/songs_missing_report.py`; для альтов
  указан дублируемый трек) — добавит сам строкой в `index.zml`/override → пересборка. Ничего не блокирует.

**Инфра/данные перед продакшеном:**
- ✔ Освежить `editor/data/*` — **расследовано 2026-06-18, действий не требуется:** proper-nouns ✔ (2026-06-17);
  `editor/data/manifest.json` — МЁРТВАЯ копия (активный `build_views.mjs` стр.26 читает живой `yaniktoim/manifest.json`,
  не её) → освежать незачем; `editor/data/zohar_index.json` build_views читает (стр.27) и она НОВЕЕ (Jun 9), чем
  `_logs/zohar_index.json` (May 28) → «живого» источника свежее нет, освежать не из чего. Латентных багов сборки нет.

## Лестница Ф0–Ф10 (детальные определения фаз + гейты; статус-матрица ниже)
*Это ДЕТАЛИЗАЦИЯ опорного порядка, а не конкурент ему. **РЕЖИМ ВЖИВУЮ (с 2026-06-18, `d3b935a`):** первый полный выкат
состоялся; дальше правки идут на боевой через `push.bat`, отладка — локально ПЕРЕД пушем. Статус-матрица:*

| Фаза | Статус | Примечание |
|---|---|---|
| Ф0 Стенд | ✔ | render.js гоняет demo локально |
| Ф1 Разведка | ✔ | K=5 тем, ширины=2 (820/1080) |
| Ф2 Канонизация тем | 🟡 базово | финальная полировка → «Фаза сборки» + дизайн-аудит |
| Ф3 Финализация ZML + `[spl]` | ✔ | далее формат дорос до полной ZML3-спеки (v2) |
| Ф4 Конвертер + рендер | ✔ (хвосты в сборке) | конвертер v2 + весь корпус 352 → `docs/art/` (2026-06-12); потерь нет; остаток (C10/C11/C13-извлечение, B6, флаг-вопросы) перенесён в фазу сборки |
| Ф7' Лок. миграция | ✔ | массовая конвертация выполнена локально за один проход v2; публичная Ф7 схлопнута в «выкат целиком» (Ф9) |
| Ф5 Пилот + ЗАМОРОЗКА формата | ✅ де-факто | пилот-поверхность (10 проверены зрением) пройдена; формат специфицирован (SPEC v2); формальный гейт-заморозки ПРОПУЩЕН оператором — формат не трогаем |
| Ф6 Каркас сосуществования | ✅ поглощён Ф8′ | сосуществование old-by-default + ссылка «Новая версия (ZML)» уже ВЖИВУЮ (`d3b935a`); «клик по названию» ОТМЕНён (доступ через ссылку/кнопку Ф8′) |
| Ф7 Массовая миграция | ✅ поглощён Ф7'/Ф8′ | конвертер + корпус 352 готовы и ВЖИВУЮ; публичная по-кластерам не нужна (выкат целиком состоялся) |
| Ф8 CMS: правка ZML | ✅ ВЖИВУЮ (правка + создание) | редактор переведён на общий `docs/ze-core.js` (`ya-edit.js` — тонкая обёртка); Просмотр/Сохранить/Отмена/popup; паритет рендера доказан; Worker `/api/save` (`fb72548a`), **живой Save проверен** (`57d3d4e`). **Создание НОВОЙ статьи (минт art-id) — ВЫКАЧЕНО ВЖИВУЮ (фаза E, `100ffba`); commit проверен локально (Worker-в-Node, `worker/test_commit.mjs` 14→28/28)**. **Иллюстрация (image:) — ВЖИВУЮ (Ф8(b), `fb6f1ed`). Правка «Песни Ступеней» (✎+паритет) — ВЖИВУЮ (Ф8(c), `974d682` + Worker `efe2a94e`). Все доборы Ф8 закрыты → далее Ф9** |
| **Ф8′ Сосуществование + админка стилей** | ✅ ВЖИВУЮ | запушено 2026-06-18 (`d3b935a`); 6 шагов + view:-override + privacy; **Worker задеплоен, 3 аккаунта в KV, вход проверен**; отменяет модель доступа Ф9 |
| Ф9 Фиксация | 🔒 СНЯТА | устарела (решение оператора 2026-06-19); cutover не нужен — финал = сосуществование Ф8′ (старое остаётся, новое по ссылке/кнопке) |
| Ф10 Управление структурой (← Задание B) | 🔄 B–G + E ВЖИВУЮ (`100ffba`) | `structure.json`+генератор (A) · редактор `structure.html`/`ya-struct.js` admin: reorder/rename/add/del разделов, reorder/move/archive/restore статей (B–G). **Фаза E (новая статья, минт art-id) — ВЫКАЧЕНА ВЖИВУЮ (`100ffba`); commit проверен локально (Worker-в-Node 14/14).** План+трекер: `cms-revival/plans/roadmap_2_content-mgmt_PLAN.md` |

*Определения фаз (со старыми гейтами ↩) — ниже без изменений:*

**Ф0. Стенд.** Рабочая ветка + распаковка cms-revival (render.js, worker, zml1) в
рабочее место. ✔ render.js гоняет `demo.zml`→HTML локально. ↩ docs/ не тронут.

**Ф1. Разведка кластеров.** Фингерпринт 352 (шрифты/палитра/типографика/фичи;
ширина и form вынесены из кластеризации тем, но **ширина разводится тоже**) →
кластеризация по эстетике → отчёт: сколько естественных тем-групп (2–5) и по
каким признакам; **сколько реальных стандартов ширины** в корпусе и какие; размеры,
разброс внутри. ✔ **гейт: оператор утверждает темы (K) и набор ширин.**
↩ только чтение, генерится отчёт.

**Ф2. Канонизация тем (LLM, не оператор).** На каждый кластер LLM собирает **одну
полную form-agnostic тему** `style.css` (любая тема рендерит любой тип контента;
покрывает проза/стих/эпиграф/сноски/музыка/TOC/крошки/byline/колофон; **отлично смотрится при своей
родной ширине**, при прочих — корректно рендерится без поломок). ✔ галерея: каждая
тема при родной ширине (гейт качества) + спот-чек неродных пар на «не сломалось»,
оператор утверждает. ↩ темы — отдельные файлы.

**Ф3. Финализация ZML + тег `[spl]` (← Задание A).** База — ZML1 v0.1; добавляю
`[spl]` (gif-обложка → клик-раскрытие, вложенность в `[sub]` и блоки: парсер + CSS
темы + JS); закрепляю свободные `theme:` и `width:` (значения из набора Ф1) во frontmatter. ✔ demo со `[spl]` и всеми
блоками рендерится во всех темах, спойлер раскрывается в т.ч. внутри `[sub]`. ↩ локально.

**Ф4. Конвертер HTML→ZML + рендер ZML→HTML.** Экстрактор: живая HTML (+yanik-meta)
→ `.zml` (frontmatter + блоки + inline + сноски), маппинг разнородных классов →
канонические блоки. Рендер ZML→HTML через тему. ✔ **оракул:** ZML→HTML сверяется
текстом с сохранённой старой HTML, расхождение = баг. ↩ всё локально, не публикуем.

**Ф5. Пилот — 1 статья на кластер, end-to-end.** Вся цепочка (HTML→ZML → тема →
рендер → сверка со старой) на репрезентанте каждого кластера. ✔ **гейт: оператор
утверждает вид и точность — здесь формат замораживается.** ↩ не нравится → правим
темы/спеку/конвертер, повтор.

**Ф6. Каркас сосуществования (первая публикация).** В каталоге у статьи две ссылки:
«новая»/«старая»; решаем пути (старая → `/legacy/` или остаётся, новая → канонический
URL). Публикуем пилоты. ✔ на живом сайте обе версии открываются, переключение из
каталога работает. ↩ старое не удаляется, новое — добавочные файлы.
**(Разработку/проверку ведём ЛОКАЛЬНО, на сайт публикуем целиком по готовности. Финал — клик по названию
ведёт на ZML-версию; legacy-раскладка, переключатель, полноценный гейт — здесь, в Ф6/Ф9.)** **[СУПЕРСИД Ф8′:**
выкат состоялся ВЖИВУЮ, доступ к новому — через ссылку/кнопку (не клик по названию); этот абзац — для истории.]

**Ф7. Массовая миграция по кластерам.** Кластер за кластером: HTML→ZML → рендер →
авто-сверка → публикация «новой» ссылки; LLM проставляет **стартовый** `theme:`
(переопределяемый). Гейт после каждого кластера. ✔ отчёт сверки (текст-расхождения =
0/разобраны) + спот-чек. ↩ постатейно, старое доступно, откат = снять «новую» ссылку.

**Ф8. CMS: правка ZML статьи (кнопка «Править» → редактор ZML ВМЕСТО просмотра).**
**Модель (оператор 2026-06-18, НЕ «по месту»):** на ZML-виде у залогиненного editor/admin — кнопка
**«Править»**; по ней просмотр статьи ЗАМЕНЯЕТСЯ **простым текстовым редактором ZML** (textarea с исходником
`docs/art/<art>.zml`). Кнопки: **Просмотр** (рендер правки в браузере тем же `render.js` → показ результата),
**Сохранить** (рендер → POST `/api/save`: коммит `docs/art/<art>.zml` + `docs/art/<art>.view.html` через Worker),
**Отмена**. После Сохранить/Отмена — возврат на исходную страницу + popup «Изменения сохранены. Обновление
ожидается через NN сек — нажмите Ctrl+R/F5» (NN = задержка деплоя GitHub Pages). Тот же редактор
переиспользуется для **создания новой статьи** (пустой ZML из шаблона + минт art-id — добор позже).
**Состояние (ВЫПОЛНЕНО 2026-06-18, `57d3d4e`):** редактор `docs/ya-edit.js`; движок+данные в `docs/editor/`
(эмит `build_views.mjs`); Worker `/api/save` задеплоен (`fb72548a`, пути `docs/art/<art>.zml`+`.view.html`).
✔ логин (только editor/admin видят кнопку) · Править→Просмотр (паритет с `build_views.mjs`, байт-в-байт) ·
**живой Save проверен end-to-end** (коммит по верному пути, старый `.html` не тронут, ревёрт). ↩ edit-слой только
на ZML-видах, старый `.html` заморожен (до Ф9). **Добор:** создание НОВОЙ статьи тем же редактором (минт art-id).

**Ф9. Фиксация переноса — 🔒 СНЯТА (устарела, решение оператора 2026-06-19).** Прежняя идея: снять «старые» ссылки из
каталога (старые файлы → архив), Pagefind/sitemap на новые, cutover `songs/index.html`. ОТМЕНЕНА: финальная модель —
сосуществование Ф8′ (старый HTML по умолчанию остаётся, новое доступно по ссылке/кнопке «Новая версия (ZML)»);
публичный flip на new-by-default не нужен. Текст ниже — для истории.
↩ ~~архив старого хранится, откат — вернуть ссылки.~~

**Ф10. Управление разделами и структурой (← Задание B).** Создание/перемещение/
переименование/удаление статей; правка списка разделов, их порядка и названий,
включая главную; модель структуры (эволюция `manifest.json`/`structure.json`) + роли
+ архив (soft-delete, «рукописи не горят»). = cms-revival roadmap 2 (фазы A–G).
**Детальный план + трекер прогресса — `cms-revival/plans/roadmap_2_content-mgmt_PLAN.md`
(фазы A–G, статус-таблица, открытые вопросы). Шло ПОСЛЕ Ф8; B–G + E уже ВЖИВУЮ (Ф9 снята как устаревшая).**
✔ создать тестовую статью, переименовать/переместить раздел, проверить главную и
навигацию. ↩ всё через git-коммиты.

## Статус и завершённые этапы → вынесены в архив

Хронологическая летопись (append-only), Discovery-снимок и завершённые этапы
(аудит обобщаемости · дизайн-аудит 5 тем · дизайн-ревью топ-10 · реализация fn-ревью)
вынесены в **`roadmap_cms_archive.md`** (2026-06-17). Ссылки вида «§Статус …» по датам — там же.
Новые хронологические записи добавлять в архив; здесь — только живой план.

## Открытые задачи (TODO, вне «Лестницы»)
- ✔ **Термины — расследование ВЫПОЛНЕНО** (2026-06-12) и внедрено как T-A/B/C (§ «Фаза сборки» → Конвертер);
  детали и правила A–D — отчёт `cms-revival/convert/term_investigation_001.md`.
- ✔ **Поиск по арт-id — ВЫПОЛНЕНО (2026-06-18, `5e9a0bb`).** В каждую статью добавлен скрытый
  индексируемый токен «Артикль №<ID>» (weight=10) — `tools/add_artid_search.py`; поиск по `654/237/03H/22SA/1AQA`
  (с `#` и без — Pagefind токенизирует `№`/`#` → чистый id) ставит статью первой, проверено в превью end-to-end.
  Без `data-pagefind-meta` (он рисовал англ. ярлык «Artid:» в UI); вес перебивает список раздела и шум. Побочно:
  `proza-design/` исключён из индекса и sitemap (363 стр.). [[project_yaniktoim_search]]

# Добавление одной статьи с proza.ru в корпus «Путь Восходящей Звезды»

Процедура для произвольной статьи `https://proza.ru/YYYY/MM/DD/NNN`. Корпус —
самодостаточные HTML-страницы в `docs/` (живое) + единый источник истины
`manifest.json`. Старый конвейер заморожен в `legacy/` (НЕ запускать целиком),
но отдельные его функции вёрстки переиспользуются (см. шаг 3). Живые
индексы (`docs/index.html`, `docs/<section>/index.html`, `docs/songs/`) —
самостоятельные файлы, их правим адресно (5_index.py из legacy их НЕ
перегенерирует — он затрёт богатую главную).

> Правка версионных файлов (`<name>_NNN.ext`) — копией в `NNN+1`, не в-месте
> (см. CLAUDE.md). Промпт вёрстки сейчас — `batch_runner/convert_prompt_005.md`;
> если правишь промпт — делай `convert_prompt_006.md` и обнови ссылку в
> `legacy/src/3b_transform_html.py` (`PROMPT_MD`).

---

## 0. Идентификаторы статьи

Из URL `https://proza.ru/2026/06/06/409`:
- `stem = 2026_06_06_409` (нецифры → `_`).
- `url_date = 2026-06-06`, `url_nnn = 409`.
- `date_chosen` — дата для сортировки/art-id. По умолчанию = `url_date`; если в
  теле статьи явно указана другая дата написания, берётся она (`date_source`).
- `art` — короткий id (см. `legacy/src/build_art_ids.py`):
  - **год**: `0..9` = 2020..2029; `Z..A` = 2019..1994.
  - **месяц**: `1..9`, `A`=10, `B`=11, `C`=12.
  - **день**: `1..9`, `A`=10 … `V`=31.
  - **суффикс** (N-я статья в тот же `date_chosen`, 0-based): пусто, затем `A..Z`
    (2-я..27-я), затем `a..z`.
  - Пример: 2026-06-06, единственная за день → `6`+`6`+`6` = **`666`**.
  - Проверь, что выбранный `art` не занят в `manifest.json` (коллизия → следующий
    суффикс).

Проверка занятости и счётчиков:
```bash
python -X utf8 -c "import json;m=json.load(open('manifest.json',encoding='utf-8'));print('total',len(m));print('art free', not any(r.get('art')=='666' for r in m));print('dabudet',sum(1 for r in m if r['section']=='dabudet'))"
```

---

## 1. Скачать сырьё в `raw/`

Отдельная статья на proza.ru публична — **логин не нужен** (cookies нужны были
только для листингов автора). Скачиваем HTML (кодировка cp1251) и первую
картинку из `<div class="maintext">`.

- `raw/<stem>.html` — сырой HTML страницы (как есть, cp1251→utf-8).
- `raw/<stem>.jpg` — иллюстрация статьи.

**ВАЖНО про картинку.** В публичном (незалогиненном) HTML страницы тег `<img>`
с иллюстрацией автора часто ОТСУТСТВУЕТ (виден только лого `/images/proza.svg` и
счётчики) — `find_first_img` из `legacy/src/1_fetch.py` его не найдёт. Но сам
файл лежит по **каноническому пути** `https://proza.ru/pics/YYYY/MM/DD/NNN.jpg`
(те же цифры, что в URL статьи). Поэтому надёжный порядок:
1. попробовать прямой `https://proza.ru/pics/<YYYY>/<MM>/<DD>/<NNN>.jpg`
   (HTTP 200 + `Content-Type: image/jpeg` → качать; 404 отдаёт HTML-страницу);
2. если 404 — попробовать `.png`/`.jpeg`;
3. если и там нет — статья действительно без иллюстрации (`img: null`).

Качать `requests`-ом с UA браузера и `Referer` на страницу статьи.

---

## 2. Запись в `manifest.json`

`manifest.json` — единый источник истины (массив объектов). Добавить новый
объект **в копию-инкремент не требуется** (это не версионный файл), но сделай
бэкап перед правкой: `cp manifest.json manifest.bak.json`.

Поля новой записи (по образцу существующих):
```json
{
  "stem": "2026_06_06_409",
  "url": "https://proza.ru/2026/06/06/409",
  "section": "dabudet",
  "title": "<точное название с proza.ru>",
  "html": "2026_06_06_409.html",
  "img": "2026_06_06_409.jpg",
  "url_date": "2026-06-06",
  "url_nnn": 409,
  "text_date": null,
  "date_chosen": "2026-06-06",
  "date_source": "url",
  "number": "351",
  "section_order": <позиция в каталоге раздела>,
  "art": "666"
}
```

- `number` — следующий по корпусу (текущий total + 1), 3 знака с ведущими нулями
  при <100.
- `section_order` — **позиция статьи в каталоге автора для этого раздела** (как
  её разместил автор), 0-based. Каноничный способ — `legacy/src/2b_section_order.py`
  (нужны `raw/proza_cookies.txt`): он перечитывает book-страницу раздела и
  проставляет индекс. Соответствие slug→book: dreamon=17, cyberson=24,
  **dabudet=13**, confront=16, shoshana=25, other=20; `best` — страница автора
  без `&book`. Для ОДНОЙ статьи проще: открыть листинг раздела на proza, найти,
  на какой позиции автор поставил новую статью, и:
  - присвоить ей этот `section_order`;
  - **сдвинуть на +1** `section_order` у всех статей раздела, что идут после неё
    (иначе дубль порядка). Если автор поставил статью в самый конец — просто
    `max(section_order раздела)+1`, сдвигать никого не надо.

`section_order` управляет и порядком в индексе раздела, и навигацией
prev/next — поэтому важно его проставить до вёрстки (nav берётся из manifest).

---

## 3. Вёрстка ТЕМ ЖЕ ПРОМПТОМ → `docs/art/<art>.html`

Это ядро. Используем тот же промпт и тот же headless-вызов, что и пакетный
раннер. Самый надёжный путь — переиспользовать функцию вёрстки напрямую:

```bash
cd C:\Users\admin\yaniktoim
python -X utf8 legacy/src/3b_transform_html.py --number 351
#  либо по art:  python -X utf8 legacy/src/3b_transform_html.py 666
#  --force  — перезаписать уже существующий docs/art/666.html
```

Что делает `transform_one` (см. `legacy/src/3b_transform_html.py`):
1. `extract_body` — из `raw/<stem>.html` достаёт ТОЛЬКО `<div class="text">` как
   plain-text (как видит читатель): `<br>`→`\n`, срез тегов, `html.unescape`,
   чистка `;;`-мусора, NBSP→пробел. Заголовок НЕ включается (подаётся метаданными).
2. `build_nav` — собирает обязательную обвязку из manifest: хлебные крошки
   (Главная + раздел), prev/next по `section_order` (на стыке раздела — в соседний
   раздел), колофон CC BY 4.0, путь картинки `../img/<art>.jpg`.
3. `build_prompt` — склеивает `convert_prompt_005.md` + метаблок (url, title) +
   nav-JSON + путь файла назначения + сырое тело.
4. `call_claude` — `claude.exe -p --model claude-opus-4-8 --output-format json
   --allowedTools Write,Edit,Read --permission-mode bypassPermissions
   --add-dir docs/art --max-turns 60 --system-prompt <изоляция от CLAUDE.md>`,
   с `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`. Агент САМ пишет страницу в
   `docs/art/<art>.html` (Write + дописки Edit). Успех = на диске валидный
   HTML от `<!DOCTYPE>` до `</html>`. 429 → лимит (ждать сброса). Лог и сырьё —
   в `_logs/html_<art>.*`.
5. После успеха: `_ensure_favicon` (дописывает favicon-линки после `<head>`) и
   `publish_image` (копирует `raw/<stem>.jpg` → `docs/img/<art>.jpg`).

> Промпт даёт две схемы: **manuscript** (узкая колонка, для стихов/поэм) и
> **editorial** (широкая, для прозы). Выбор — за моделью по доминирующей форме.
> Схема пишется в `data-scheme` на `<body>` (это же маркер «построено» для
> очереди раннера) и дублируется в скрытом блоке `yanik-meta` перед `</body>`.

Если `claude.exe` не находится по контейнерному пути — `_resolve_claude_exe`
берёт самую свежую версию-папку или `claude` из PATH (см. CLAUDE.md про headless).

---

## 4. Швы навигации у соседей

Новая страница уже содержит правильные prev/next (из manifest). Но её **два
соседа** по разделу (статья перед ней и статья после неё по `section_order`) уже
построены со старыми ссылками — у них внизу нужно обновить блок «предыдущая/
следующая», чтобы появился новый сосед `666`.

Два варианта:
- **Адресно (рекомендуется):** найти в `docs/art/<сосед>.html` нижний
  nav-блок и поправить href/название одной ссылки (prev у того, кто идёт ПОСЛЕ
  новой; next у того, кто идёт ДО неё).
- **Перевёрстка:** прогнать тех же соседей через шаг 3 с `--force` — но это
  меняет их вёрстку целиком, применять только если правка вручную неудобна.

Названия соседей и их `art` бери из manifest (раздел `dabudet`, сортировка по
`section_order`).

---

## 5. Списки (индексы)

Правим адресно (это самостоятельные HTML, не шаблоны):

**`docs/<section>/index.html`** (напр. `docs/dabudet/index.html`):
- вставить `<li>` на позицию, соответствующую `section_order`:
  ```html
  <li><span class="num">#666</span><a href="../art/666.html">НАЗВАНИЕ</a><span class="meta">ДД.ММ.ГГГГ</span></li>
  ```
  (дата в формате `dd.mm.YYYY` из `date_chosen`).
- счётчик `<p class="meta">Статей: 51</p>` → 52.
- в `<head>`: `description`/`og:description`/`twitter:description`
  «… — 51 статей …» → 52.

**`docs/index.html`** (главная):
- `<p class="meta">… 350 статей в 7 разделах.</p>` → 351.
- в `<ul class="toc">` строка раздела: `<span class="meta">51 статей</span>` → 52.
- meta `description` («350 статей, 7 разделов») и twitter/og — синхронно.

**`imyavel.github.io/index.html`** (заглавный хаб, отдельный репозиторий):
- в карточке «Путь Восходящей Звезды» счётчик `Корпус авторских
  произведений — 350 статей в 7 разделах…` инкрементировать (→ 351 и т.д.).
  Склонение: …1 → «статья» (351 статья), …2/3/4 → «статьи» (352 статьи),
  иначе → «статей» (355 статей); 11–14 всегда «статей».

---

## 6. Песнь Ступеней (`docs/songs/index.html`)

Только если в новой статье есть музыкальные треки с YouTube. Страница
генерируется из `.batch/songs_data.json` (videoID → `{arts:[...], title}`) +
`.batch/art_titles.json` (art → название статьи).

1. Найти в `docs/art/666.html` YouTube-плееры (атрибут `data-id="<videoID>"`)
   и их подписи (название — исполнитель).
2. В `.batch/songs_data.json`: для каждого videoID — если есть, добавить `666`
   в его `arts`; если нет — создать запись `{"<id>": {"arts": ["666"], "title":
   "Исполнитель — Название"}}`.
3. В `.batch/art_titles.json`: добавить `"666": "НАЗВАНИЕ СТАТЬИ"`.
4. Перегенерировать: `python -X utf8 .batch/songs_build.py` → перезапишет
   `docs/songs/index.html` и напечатает число треков.
5. Если общее число композиций выросло — обновить «217 композиций» в
   `docs/index.html` (строка songs в `<ul class="toc">`).

Если музыки в статье нет — шаг пропустить.

---

## 7. SEO-описание

```bash
python -X utf8 tools/gen_descriptions.py --only art/666.html   # → descriptions.json (Opus 4.8, headless)
python -X utf8 tools/apply_seo.py                              # идемпотентно вставит canonical/og/twitter/description во ВСЕ страницы docs/
```
`apply_seo.py` добавляет только недостающее — повторный прогон безопасен и
доберёт теги на новых/правленых индексах тоже.

---

## 8. Поиск + sitemap

```bash
reindex.bat
```
Делает: `pagefind --site docs` (перестроить индекс поиска по docs/) +
`python -X utf8 tools/build_sitemap.py` (sitemap.xml + robots.txt из текущего
состояния docs/). Запускать ПОСЛЕ всех правок страниц, ПЕРЕД push.

---

## 9. Публикация

```bash
push.bat add art 666 — <краткое название>
```
= `git add -A` + commit (от имени imyavel) + `git push origin main`. Сайт
обновится на GitHub Pages (`https://imyavel.github.io/yaniktoim/`).

---

## Чек-лист

- [ ] `raw/<stem>.html` + `raw/<stem>.jpg` скачаны
- [ ] запись добавлена в `manifest.json` (art, number, section_order проставлены;
      сдвинуты section_order соседей при вставке в середину)
- [ ] `docs/art/<art>.html` сверстан тем же промптом, favicon + `docs/img/<art>.jpg`
- [ ] prev/next у двух соседей по разделу поправлены
- [ ] `docs/<section>/index.html` — `<li>` вставлен, счётчик +1
- [ ] `docs/index.html` — total +1, счётчик раздела +1, meta синхронны
- [ ] Песнь Ступеней перегенерирована (если есть музыка) + счётчик на главной
- [ ] `gen_descriptions --only` + `apply_seo`
- [ ] `reindex.bat` (Pagefind + sitemap)
- [ ] `push.bat`
</content>
</invoke>

# yaniktoim — «Путь Восходящей Звезды»

Веб-публикация корпуса произведений Элиягу Бар Малей (`proza.ru/avtor/agent017`, 350 статей в 7 разделах), адаптированная для чтения и поиска. Эталон верстки — `bneiadam.com/poyasneniya/index.html` (страница расширенного формата article-page) и `bneiadam.com/index.html` (главная zohar-sulam).

**Живой сайт:** https://imyavel.github.io/yaniktoim/
**Репо публикации:** https://github.com/imyavel/yaniktoim (branch `main`, GitHub Pages из `/`)
**Локально:** `C:\Users\admin\yaniktoim\`

## Текущая фаза

**ПРОБЫ И ОШИБКИ → ФОРМАТ ЗАФИКСИРОВАН 2026-05-26 20:35.** Формат пилотов согласован, дальше можно идти на массовую LLM-трансформацию. До решения «запускать» остаётся одна страховка: любая новая правка правил → перетрансформировать всё.

### Что зафиксировали (визуально утверждено на пилотах #078 / #310 / #350)

- **Стихи** — одна колонка, шрифт `Book Antiqua` (fallback: Palatino → Georgia), размер 18px (в одну величину с прозой). Блок поэмы шириной по самой длинной строке, левый край прижат к 33% ширины `<article>`, строки внутри выровнены влево.
- **Проза** — Georgia 18px, `line-height: 1.4` (зазор между строками 0.4), красная строка `text-indent: 3em` у обычных `<p>`. Исключения без отступа: `.attribution`, `.colophon`, `.byline`, `.epigraph p`, `.epilogue p`, `blockquote.q p`, `details.music p`.
- **TOC статьи** (рендерится если ≥3 пунктов) — авто-добавляет пункты:
  - «Музыка под настроение» (если в последнем именованном разделе есть ≥2 музыкальных блоков — это считается «trailing music group»);
  - «Примечания» (если есть сноски).
  - На h2 обоих этих секций стрелка ↑ к началу статьи, как у обычных разделов.
- **Сноски `[N]`** — поп-ап «bubble» при наведении мыши: всплывающий блок с текстом сноски, стрелка-указатель, исчезает по `mouseleave` с задержкой 180ms (можно перевести курсор на сам пузырёк и кликать внутренние ссылки).
- **Музыка** — `<details class="music">` с `<iframe data-src=...>`, src переключается из data-src при первом раскрытии (фикс YouTube Error 153 «player setup error» в скрытых iframe), `referrerpolicy="strict-origin-when-cross-origin"` обязателен. Рядом с названием «↗» — ссылка на YouTube напрямую (fallback).
- **Музыка после раздела** — `position_after: "<anchor>"` ставит music в конце раздела `<anchor>`, не сразу после h2.

### В режиме проб

- **Стили в `site/style.css`** — корректировки точечные. Каждое изменение пушится в gh-pages для визуальной сверки.

## Что **уже сделано** (стабильно)

1. ✅ Полный корпус скачан с proza.ru через залогиненную сессию Chrome.
   - `raw/<STEM>.html` (350 файлов, cp1251 → utf-8)
   - `raw/<STEM>.<ext>` (195 иллюстраций; не у каждой статьи есть)
   - `raw/_corpus.json` (карта URL → метаданные)
   - cookies через **skill `/cookie_eater`** — обходит Chrome v20 ABE (`%LOCALAPPDATA%\Google\Chrome\…`, см. `~/.claude/skills/cookie_eater/SKILL.md`).
2. ✅ `manifest.json` — сквозная нумерация #001..#350 по дате (175 из текста, 175 из URL).
3. ✅ Авторский порядок внутри каждого раздела (`section_order`) — `2b_section_order.py` перечитывает каталоги proza.ru.
4. ✅ Шаблоны (`templates/article.html`, `section_index.html`, `main_index.html`) + общий `site/style.css`.
5. ✅ Главная + 7 оглавлений (`site/index.html`, `site/<slug>/index.html`).
6. ✅ Трёхэтажный pipeline:
   - `1_fetch.py` + `1b_fetch_missing.py` — скачивание (готово).
   - `2_manifest.py` — извлечь даты, сортировка, присвоить #N.
   - `2b_section_order.py` — авторский порядок внутри разделов.
   - `3_transform.py` — headless `claude -p --model opus`, JSON-выход.
   - `4_render.py` — JSON + шаблон → HTML.
   - `5_index.py` — главная + оглавления разделов.
   - `6_deploy.py` — git commit; gh-pages работает (`git push origin main`).
7. ✅ Три пилота отрендерены:
   - `site/best/350.html` — handcrafted JSON, эталонная копия `bneiadam.com/poyasneniya/index.html`.
   - `site/best/078.html` — LLM, поэма с TOC, 5 актов (одноколонный центр).
   - `site/confront/310.html` — LLM, проза с диалогом.

## Структура папок

```
yaniktoim/
├── README.md              ← этот файл
├── manifest.json          ← #001..#350, source of truth
├── yaniktoim.txt          ← оригинальный бриф оператора
├── src/
│   ├── 1_fetch.py
│   ├── 1b_fetch_missing.py
│   ├── 2_manifest.py
│   ├── 2b_section_order.py
│   ├── 3_transform.py
│   ├── 4_render.py
│   ├── 5_index.py
│   ├── 6_deploy.py
│   ├── cookie_eater.py             # = src/decrypt_v20.py (см. skill /cookie_eater)
│   └── transform_prompt.md         # промпт для headless `claude -p`
├── templates/
│   ├── article.html
│   ├── section_index.html
│   └── main_index.html
├── raw/                   ← 350 html + 195 img, _corpus.json, proza_cookies.txt
├── json/                  ← результат LLM-трансформации: <NNN>.json
├── site/                  ← публикуемая часть; в ней `.git` для gh-pages
└── _logs/                 ← prompts dump, debug
```

## Что ещё **предстоит**

- **Massive LLM transform.** 347 оставшихся статей (длинные стихи занимают до 13 мин каждая). Оценочно 5-29 ч серийно или 3-6 ч параллельно 3-5 процессами. Стоимость $20-200 (зависит от prompt-cache reuse в headless `claude -p`; на одном пилоте cache_creation_input_tokens=30702 → $0.19, последующие subprocess'ы цены пока не проверены).
- **Карта xrefs.** Каждая ссылка `proza.ru/YYYY/MM/DD/NNN` в тексте должна:
  - указывать на наш `yaniktoim/<section>/<N>.html` если статья принадлежит agent017 (есть в manifest);
  - указывать на `imyavel.github.io/zohar-sulam/` если это ссылка на Книгу Зоар (нужна резолверная логика для коротких ссылок вида «Книга Зоар, том 1, статья 1», «Заповеди Торы 9 и 10», и т.п.);
  - остальные внешние — сохранить как есть, ревизия оператора потом.
- **Поиск.** Pagefind как у zohar-sulam.
- **Доводка правил.** См. секцию «Открытые правила оформления» ниже.

## Правила оформления (зафиксированные)

Это всё уже в коде, общие правила, применяются ко всем 350 статьям при рендере.

| Правило | Где |
|---|---|
| Сквозная нумерация #001..#350 по дате (text-date в приоритете над URL-date, NNN из URL как тай-брейк) | `2_manifest.py` |
| Внутри раздела — авторский порядок proza.ru | `2b_section_order.py`, `5_index.py` |
| `.wrap.wide` 1200px для статей; `.wrap` 820px для главной/оглавлений | `style.css` |
| Главная: «Корпус произведений [Элиягу Бар Малей](proza.ru). N статей в M разделах» — имя автора кликабельно | `templates/main_index.html` |
| В оглавлениях разделов: ссылки на proza убраны | `templates/section_index.html` |
| Имя автора нигде не склоняется (только «Элиягу Бар Малей», не «Элиягу Бар Малея» / «Элиягу Бар Малеем»). Исключение — лицензия CC BY 4.0: «при указании автора (Элиягу Бар Малей)» — там «автора» сохранено как было до уточнения. | везде |
| `byline` статьи: «Элиягу Бар Малей · #N · DD.MM.YYYY · Оригинал: proza.ru/…» | `templates/article.html` |
| Подразделы статьи: H2 нормализован (CAPS → «Первая буква каждого предложения заглавная»), центрирован, размер 1.7rem (h3 — 1.3rem) | `_normalize_heading()` + CSS |
| Стрелка ↑ после h2/h3 (только если в статье есть TOC) → ведёт к `#article-title` (h1 под картинкой) | `render_section(has_toc=…)` |
| Стихи: Courier New, центр (одиночные строфы и широкие), full-CAPS строки → нижний регистр + `<span class="sb">` (semi-bold) | `_normalize_poem_line()`, `.sb { font-weight: 600; }` |
| Каждая строка стиха — с заглавной первой буквы | `_capitalize_first_letter()` |
| Атрибуция: ведущие короткие (≤200 chars) параграфы первой секции (подзаголовок, серия, формат, посвящение) — отдельный блок сразу после byline, перед TOC | `extract_attribution()` |
| Колофон: «Арт. # …», «Записано N даты», «Написано N даты» → вниз `<article>`, перед примечаниями | `extract_colophon()`, `is_colophon_paragraph()` |
| Сноски: авторские номера сохраняются как есть (`*4` → `[4]`); одиночные `*` без номера → LLM нумерует подряд (`[1]`, `[2]`…). Это **отвечает оригиналу**, потому что у автора так и сделано на proza.ru | `transform_prompt.md` (правило 5) |
| Музыкальные блоки: youtube-id извлекается; yandex.video → ссылка без iframe | `render_music()` |
| Лицензия: CC BY 4.0, «при указании автора (Элиягу Бар Малей)» | footer всех страниц |

## Открытые правила оформления (на согласовании)

- **Шрифт стихов**: пока Courier New 1.05rem. Сменить ли на проп.-шрифт?
- **Перекрёстные ссылки** — карта ещё не реализована.
- **Поиск** — pagefind ещё не подключён.

## Команды

Из `C:\Users\admin\yaniktoim\` все запускается так:

```bash
python src/cookie_eater.py proza.ru             # обновить proza_cookies.txt
python src/1_fetch.py                            # (один раз) скачать корпус
python src/1b_fetch_missing.py                   # пагинация больших разделов
python src/2_manifest.py                         # numbering by date
python src/2b_section_order.py                   # author-defined section order
python src/3_transform.py <NNN> [<NNN>...]       # LLM transform statей
python src/3_transform.py --all                  # всё подряд (долго!)
python src/4_render.py <NNN> [<NNN>...]          # render по json
python src/5_index.py                            # main + section indices
# деплой:
cd site && git add . && git commit -m "..." && git push origin main
```

`claude.exe` берётся по абсолютному пути:
`C:\Users\admin\AppData\Roaming\Claude\claude-code\2.1.149\claude.exe`

## Безопасность / приватность

- `raw/proza_cookies.txt` содержит активную сессионную куку залогиненного proza.ru. **Не коммитится** — она в `raw/`, не в `site/`.
- `_chrome_cookies_copy.sqlite` в `_research/` — временная VSS-копия, тоже локально.
- `site/` — единственное что в репо. `raw/`, `json/`, `_logs/`, `_research/`, `src/` — локально.
- Об операторе и его правках — см. CLAUDE.md в `C:\Users\admin\CLAUDE.md` (общие правила) и в `C:\Users\admin\.claude\projects\…\memory\MEMORY.md`.

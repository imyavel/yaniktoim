# cms-revival — возобновление CMS для yaniktoim

Здесь собрано **всё**, что относилось к идее превратить `yaniktoim` в редактируемую
CMS (правка статей и структуры прямо на сайте, логин по нику, коммиты через
Cloudflare Worker) и к разработке формата **ZML**. Материал вынут из двух мест
репозиториев (копии, оригиналы не тронуты — см. «Откуда что» внизу).

> Цель папки: чтобы при возобновлении проекта не бегать по `legacy/` и
> `design-experiment/`, а иметь спеки, код и планы в одном месте. Дев пока не
> начинаем — это подготовленная база, «потом продолжим».

---

## TL;DR статуса

- **База CMS — была сделана** (roadmap 1): ZML1-формат → `render.js` → HTML,
  inline-правка ✎ на странице, логин по нику + роли через Worker, Save = 1 коммит.
- **Управление структурой — спланировано, НЕ реализовано** (roadmap 2, фазы A–G):
  редактируемые главная/разделы, reorder/rename, архив, создание статей и т.д.
- **Проект заморожен 2026-05-30** (roadmap 3) в пользу прямой LLM-вёрстки без ZML;
  логин/редактирование сняты с сайта, а весь CMS-код 2026-06-01 убран в
  `yaniktoim/legacy/` как «мёртвый».
- **Возобновляем = расконсервируем roadmap 2.**

## ⚠️ Главная развилка перед стартом

CMS строился под старую модель сайта: источник истины — `zml/<art>.zml`, страницы
рендерятся из ZML в `docs/<section>/<art>.html`. **Сейчас сайт другой:** статьи —
самодостаточный HTML в плоском `docs/art/<art>.html`, свёрстанный LLM напрямую,
`zml/`-источник пуст. То есть `render.js`/inline-редактор в текущем виде к живым
страницам **не подходят** — их формат правки (ZML) разошёлся с тем, что на сайте.

Первое решение при возобновлении: **редактировать живой HTML напрямую** (тогда
ZML/render.js — в утиль, а от CMS берём только Worker-логин + inline-правку HTML),
**или** возвращать сайт на ZML-источник (тогда нужна обратная конвертация
существующих 350 HTML → ZML). Это надо решить до кода.

---

## Что где в этой папке

| Папка | Что | Состояние |
|---|---|---|
| `plans/` | 4 роадмапа (см. ниже) | планы/история |
| `zml3/` | **Спека ZML3 (`SPEC.md`) — КАНОН формата живого CMS (источник истины).** Опубликована в `yaniktoim/docs/zml/SPEC.md`; гайд → `docs/guide/rukovodstvo.pdf` | действующая, v2 |
| `zml1/` | Спека ZML1 (`SPEC.md`) + demo — **исторический референс-вход, НЕ канон** (правки формата — в `zml3/`!) | легаси, v0.1 |
| `zml2/` | Эксперимент ZML2: семантический слой + 5 тем-скинов (вся `design-experiment`) — **референс-вход, НЕ канон** | заморожен, ворота Фазы 3 пройдены |
| `editor/` | Inline-редактор браузера: `render.js` (ZML→HTML, Node+браузер), `inline.js` (✎ на странице), `data/` | рабочий код |
| `worker/` | Cloudflare Worker `yaniktoim-auth`: register/login/me/save/admin, роли pending→editor/admin, токен GitHub только здесь | рабочий код (без `node_modules`) |
| `config/` | `site.json` (workerUrl), `users.json`, `proper-nouns.txt` (CAPS→капитель) | настройки |
| `cms-superseded/` | Более ранний CMS отдельным Python-сервером (`server.py` + `static/editor.html`) — отвергнут в пользу gh-pages-варианта | только референс |

### Роадмапы (порядок чтения)
1. `plans/roadmap_1_base_DONE.md` — база: рендер + Worker-логин. **Сделано.**
2. `plans/roadmap_2_content-mgmt_PLAN.md` — **ключевой**: управление контентом и
   структурой (фазы A–G, модель `structure.json`, архив, создание статей, роли).
   Это то, что возобновляем.
3. `plans/roadmap_3_freeze.md` — решение о заморозке и развороте на прямую вёрстку.
4. `plans/roadmap_designexp_zml2-themes_FROZEN.md` — ветка ZML2 (семантика + темы).

---

## Архитектура CMS (как задумано)

```
браузер: страница статьи  ──✎ inline──►  render.js (ZML→HTML в браузере)
   │  Войти (ник/пароль)                         │ Save
   ▼                                             ▼
Cloudflare Worker  ── Bearer ──►  /api/save  ── 1 commit (author=ник) ──►  GitHub repo
(GH-токен только тут, роли в KV)                                            (gh-pages /docs)
```
Сайт остаётся публичной статикой; логин нужен только для правки. Источник истины —
файлы в репо, HTML — производное.

## Незакрытые вопросы оператора (из roadmap 2 §11)
«Избранное» — раздел или сквозная витрина (featured)? · `manifest.json` эволюционировать
или новый `structure.json`? · архив скрытием-по-статусу или переносом в `zml/_archive/`? ·
нужен ли `draft`-статус · вводный текст/обложка раздела · pin статей · пересборка
sitemap · стратегия конкурентных правок двух админов.

## Что нужно для запуска Worker (когда дойдём)
Node + free-аккаунт Cloudflare. `npm i -g wrangler` → `wrangler login` → создать KV
`USERS` → секреты `GH_TOKEN` (fine-grained PAT на репо, Contents:RW), `SESSION_SECRET`,
`ADMIN_BOOTSTRAP` → `wrangler deploy`. Детали — `worker/README.md`. `node_modules` тут
не лежит (164 МБ) — ставится `npm i` в `worker/`.

---

## Откуда что скопировано (канон-оригиналы)
- `plans/roadmap_1..3` ← `yaniktoim/legacy/roadmap{,2,3}.md`
- `plans/roadmap_designexp_*` ← `design-experiment/roadmap1.md`
- `zml1/` ← `yaniktoim/legacy/_zml_spec/`
- `zml2/` ← `design-experiment/` (целиком, минус `node_modules`)
- `editor/` ← `yaniktoim/legacy/editor/`
- `worker/` ← `yaniktoim/legacy/worker/` (минус `node_modules`)
- `config/` ← `yaniktoim/legacy/config/`
- `cms-superseded/` ← `yaniktoim/_backups/cms_superseded/`

Оригиналы остаются в репо `yaniktoim` (закоммичены в `legacy/`) и в `design-experiment/`
до решения об архивации.

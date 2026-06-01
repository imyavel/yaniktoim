# legacy/ — архив, НЕ использовать

Перенос корпуса proza.ru → статический сайт **завершён** (2026-06-01). Всё, что
здесь лежит, обслуживало одноразовую LLM-сборку или осиротевший CMS и в текущей
работе **не участвует**. Живой продакшен — только статика в `docs/` плюс
детерминированные скрипты-обслуживания в корневом `tools/` (работают по готовому
HTML).

## Что здесь и почему мертво

- `batch_runner/` — GUI + раннеры LLM-вёрстки (`run_batch_html.py`,
  `gui.pyw`, `convert_prompt_*.md`). Перенос статей закончен → не нужны.
- `src/` — весь конвейер: fetch → manifest → transform (`3b_transform_html.py`) →
  index, плюс `redate/`, `build_*`, `7_postcheck`, `cookie_eater`, `5_index`.
- `templates/` — HTML-шаблоны старой сборки (`article.html`, индексы). Живые
  страницы уже самодостаточны (CSS/JS инлайн), шаблоны не применяются.
- `editor/` — бывший gh-pages CMS (`render.js`/`inline.js`/`data`). ZML-источник
  пуст, точки входа (.html) нет, живые страницы на него не ссылаются.
- `worker/` — Cloudflare auth/commit-proxy **для этого CMS**. Код архивирован;
  сам воркер (`yaniktoim-auth.imyavel.workers.dev`) при необходимости удаляется
  вручную в дашборде Cloudflare.
- `config/` (`site.json`/`users.json`/`proper-nouns.txt`) — настройки сборки/CMS.
- `_zml_spec/`, `zml/` — спецификация и (опустевшие) исходники ZML. ZML заморожен.
- `tools/` — `build.mjs` (Node-сборка через render.js), `reader/`, relink-отчёты.
- корневые `style.css` (старый; живой — `docs/style.css`), `package.json`
  (`yaniktoim-cms`), `cms.bat`, `progress.json`, `roadmap*.md`.

Ничего отсюда подключать/запускать не нужно. Оставлено как история.

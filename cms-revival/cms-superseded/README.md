# yaniktoim-cms — local mini-CMS

Локальный веб-редактор ZML-исходников. Stdlib-only (без `pip install`), запускается одной командой.

## Запуск

```
cd C:\Users\admin\yaniktoim-cms
python cms/server.py
```

Открывается на `http://localhost:8765/`. Порт меняется флагом `--port 8888`.

## UI

### Список статей (`/`)

Все 350 записей из `manifest.json`. Колонки: art, дата, раздел, заголовок, статус (ZML / raw), действие.

Фильтры в шапке:
- галочки «с ZML» / «только raw» — что показывать
- селект раздела (best, confront, shoshana, …)
- поиск по заголовку и art

Действия по строке:
- статья с ZML → **✎ редактировать** (открыть редактор)
- статья без ZML → **⚙ transform** (запустить headless claude → render → перейти в редактор)

Transform — синхронный, занимает 25 секунд – 15 минут на статью. Вкладка должна оставаться открытой.

### Редактор (`/editor.html?art=<id>`)

Split-screen:
- **Левая колонка** — textarea с ZML-текстом (моноширинный шрифт).
- **Правая колонка** — iframe с превью HTML.

Сверху статусная строка: art-id (badge), индикатор `● изменено / ✓ сохранено`, кнопка **Сохранить · Ctrl+S**, кнопка **↻ preview**, ссылка на источник proza.ru.

Горячие клавиши:
- `Ctrl+S` (или `Cmd+S`) — сохранить + ре-render + обновить preview.
- При попытке закрыть вкладку с несохранёнными изменениями — браузер предупредит.

## API

| Method | Path | Описание |
|--------|------|----------|
| `GET`  | `/api/articles` | Список всех статей с пометкой `has_zml`. |
| `GET`  | `/api/article/<art>` | `{meta, zml}` для одной статьи. 404 если нет ZML. |
| `POST` | `/api/article/<art>` | Тело: `{"zml": "..."}`. Backup → запись → ре-render. |
| `POST` | `/api/transform/<art>` | Запустить `3_transform.py <art> --force`, затем render. Возвращает после завершения (долго). |
| `GET`  | `/preview/<art>` | Готовый HTML с инжектированным `<base>` (чтобы относительные пути работали в iframe). |
| `GET`  | `/site/<path>` | Раздача `site/*` (style.css, изображения, чужие статьи для cross-links). |
| `GET`  | `/static/<path>` | Раздача `cms/static/*` (CSS редактора, иконки). |

## Что происходит при сохранении

1. POST `/api/article/<art>` с новым ZML.
2. Текущий `zml/<art>.zml` копируется в `_backups/zml/<art>.<timestamp>.zml`.
3. Новый ZML записывается в `zml/<art>.zml`.
4. `4_render.render_article` импортируется и вызывается in-process (~50 мс).
5. Результат записывается в `site/<section>/<art>.html`.
6. Frontend получает `{ok: true, rendered: "site/...", backup: "_backups/..."}` и обновляет iframe.

Если render упал (ошибка парсера / неверный синтаксис ZML) — frontend получит `{ok: false, error, traceback}` и покажет сообщение, **ZML всё равно сохранён** (всегда есть backup в `_backups/`).

## Известные ограничения (на момент 2026-05-28)

- Нет создания **новых статей** — только редактирование существующих из `manifest.json`.
- Нет редактирования `manifest.json` (title/section/date) — только тела ZML.
- Нет картинок-upload — `frontmatter.image` указывается вручную, файл нужно положить в `pics/` отдельно.
- Нет syntax-highlighting в textarea (vanilla `<textarea>`); может быть добавлен позже (CodeMirror / Monaco).
- `Сохранить` блокирует до завершения render — на крупных статьях может занять ~500 мс.
- Index pages (главная сайта, разделы) пока не генерируются — будет в TODO 6.

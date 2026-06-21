# yaniktoim-auth — Cloudflare Worker (Этап 8)

Прокси-коммитер с логином по нику. GitHub-токен живёт только здесь, к браузеру не
попадает. Сайт остаётся публичной статикой; логин нужен только для правки.

## Что делает
- `POST /api/register` `{nick, password[, invite]}` → создаёт юзера с ролью `pending`.
- `POST /api/login` `{nick, password}` → `{token, nick, role}` (сессия HMAC, 12 ч).
- `GET  /api/me` (Bearer) → `{nick, role}` (роль читается свежей из KV).
- `POST /api/save` (Bearer, роль editor/admin) `{art, section, zml, html}` →
  один коммит `zml/<art>.zml` + `docs/<section>/<art>.html`, author = ник.
- `GET  /api/admin/users` / `POST /api/admin/promote` `{nick, role}` (роль admin).

Роли: `pending` (вошёл, писать нельзя) → `editor` (пишет) / `admin` (+управляет).

## Деплой (один раз)

Требуется Node + аккаунт Cloudflare (free).

```bash
cd worker
npm i -g wrangler            # если нет
wrangler login              # откроет браузер, авторизуй Cloudflare

# 1. KV для пользователей — впиши выданный id в wrangler.toml ([[kv_namespaces]].id)
wrangler kv namespace create USERS

# 2. Секреты
wrangler secret put GH_TOKEN          # fine-grained PAT: yaniktoim, Contents: RW
wrangler secret put SESSION_SECRET    # случайная строка (openssl rand -hex 32)
wrangler secret put ADMIN_BOOTSTRAP   # "ТвойНик:пароль" — станешь админом при 1-м логине

# 3. Выкатка
wrangler deploy
# → выдаст URL вида https://yaniktoim-auth.<sub>.workers.dev
```

## Привязка к сайту
В корне репо отредактируй `config/site.json`:
```json
{ "workerUrl": "https://yaniktoim-auth.<sub>.workers.dev" }
```
затем `node tools/build.mjs` (выгрузит `docs/editor/data/site.json`) и закоммить/запушь.
Пустой `workerUrl` ⇒ редактор остаётся в интерим-режиме (личный PAT в ⚙).

## Первый вход
1. Открой статью `…?edit=1` → ✎ → «Войти» → ник/пароль из `ADMIN_BOOTSTRAP`.
2. Друзья жмут «Регистрация» → попадают в `pending`. Ты в админ-панели (⚙ при роли
   admin) промоутишь их в `editor`. После этого они могут Сохранять.

## Замечания
- `ALLOW_ORIGIN` в `wrangler.toml` уже = `https://imyavel.github.io`. Для локальной
  отладки можно временно поставить `*`.
- Сменить роль — `promote` в админ-панели; вступает в силу со следующего запроса
  (роль читается из KV на каждый `/api/me` и `/api/save`).
- Отзыв доступа ко всему — поменять `GH_TOKEN` (в одном месте).

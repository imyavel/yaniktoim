// yaniktoim auth + commit-proxy Worker (Этап 8).
//
// Зачем: друзья без своего GitHub правят сайт «под общим аккаунтом», логинятся
// каждый под своим ником. GitHub-токен живёт ТОЛЬКО здесь (секрет Worker'а), к
// клиенту не попадает → «править можно только через сайт». Роль на Worker'е —
// граница безопасности (самой регистрацией прав к репо не получить).
//
// Хранилище: KV namespace USERS. Ключи:
//   user:<nick>      → { nick, role, salt, hash, createdAt }
//   settings:<nick>  → личные настройки вида editor'а (Ф8′, global+rules; дизайн вкл. «old»)
// Роли: "pending" (вошёл, писать нельзя) → "editor" (пишет) / "admin" (+управляет).
//
// Секреты (wrangler secret put …): GH_TOKEN, SESSION_SECRET, ADMIN_BOOTSTRAP.
// Vars (wrangler.toml): ALLOW_ORIGIN, REPO ("imyavel/yaniktoim"), [INVITE_CODE].
//
// Эндпоинты (JSON): POST /api/register, /api/login, GET /api/me,
//   POST /api/save (zml+view; опц. binary image: → docs/img/), GET /api/admin/users,
//   POST /api/admin/promote, POST /api/commit (admin мультифайл; files[].binary),
//   GET/PUT /api/settings (Ф8′: editor→KV; admin→коммит docs/config/display.json).

const enc = new TextEncoder();

// ── base64 / base64url helpers ──────────────────────────────────────────────
function bytesToB64(bytes) {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}
function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
const b64url = (b64) => b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64url = (s) => s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4);
function b64utf8(s) { return bytesToB64(enc.encode(s)); } // utf-8 string → base64

// ── password hashing (PBKDF2-HMAC-SHA256) ───────────────────────────────────
const PBKDF2_ITERS = 100000;
async function derive(password, salt) {
  const key = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt, iterations: PBKDF2_ITERS, hash: "SHA-256" }, key, 256);
  return new Uint8Array(bits);
}
async function hashPassword(password) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const hash = await derive(password, salt);
  return { salt: bytesToB64(salt), hash: bytesToB64(hash) };
}
function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}
async function verifyPassword(password, saltB64, hashB64) {
  const got = await derive(password, b64ToBytes(saltB64));
  return timingSafeEqual(got, b64ToBytes(hashB64));
}

// ── session token (HMAC-SHA256 over payload) ────────────────────────────────
const SESSION_TTL_SEC = 12 * 3600;
async function hmacKey(secret) {
  return crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}
async function signSession(env, nick, role) {
  const payload = { nick, role, exp: nowSec() + SESSION_TTL_SEC };
  const body = b64url(b64utf8(JSON.stringify(payload)));
  const key = await hmacKey(env.SESSION_SECRET);
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(body));
  return `${body}.${b64url(bytesToB64(new Uint8Array(sig)))}`;
}
async function verifySession(env, token) {
  if (!token || token.indexOf(".") < 0) return null;
  const [body, sig] = token.split(".");
  const key = await hmacKey(env.SESSION_SECRET);
  const ok = await crypto.subtle.verify("HMAC", key, b64ToBytes(unb64url(sig)), enc.encode(body));
  if (!ok) return null;
  let payload;
  try { payload = JSON.parse(new TextDecoder().decode(b64ToBytes(unb64url(body)))); }
  catch { return null; }
  if (!payload || payload.exp < nowSec()) return null;
  return payload; // { nick, role, exp }
}

const nowSec = () => Math.floor(Date.now() / 1000);

// ── KV user store ───────────────────────────────────────────────────────────
const userKey = (nick) => `user:${nick.toLowerCase()}`;
async function getUser(env, nick) {
  const raw = await env.USERS.get(userKey(nick));
  return raw ? JSON.parse(raw) : null;
}
async function putUser(env, user) {
  await env.USERS.put(userKey(user.nick), JSON.stringify(user));
}
// Seed the operator as admin from ADMIN_BOOTSTRAP="nick:password" if absent.
async function ensureBootstrapAdmin(env) {
  const bs = env.ADMIN_BOOTSTRAP;
  if (!bs || bs.indexOf(":") < 0) return;
  const idx = bs.indexOf(":");
  const nick = bs.slice(0, idx).trim();
  const pass = bs.slice(idx + 1);
  if (!nick || !pass) return;
  if (await getUser(env, nick)) return;
  const { salt, hash } = await hashPassword(pass);
  await putUser(env, { nick, role: "admin", salt, hash, createdAt: nowSec() });
}

// ── HTTP helpers ────────────────────────────────────────────────────────────
function corsHeaders(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOW_ORIGIN || "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}
function json(env, obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...corsHeaders(env) },
  });
}
const validNick = (n) => typeof n === "string" && /^[A-Za-zА-Яа-яЁё0-9 _.\-]{2,40}$/.test(n.trim());

async function authedPayload(env, req) {
  const h = req.headers.get("Authorization") || "";
  const m = /^Bearer\s+(.+)$/i.exec(h);
  if (!m) return null;
  return verifySession(env, m[1].trim());
}

// ── GitHub commit (Git Data API) — one commit for zml + html ────────────────
async function gh(env, path, opts = {}) {
  const res = await fetch(`https://api.github.com/repos/${env.REPO}/${path}`, {
    ...opts,
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "yaniktoim-worker",
      ...(opts.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!res.ok) throw new Error(`gh ${path}: ${res.status} ${(await res.text()).slice(0, 200)}`);
  return res.json();
}
async function commitFiles(env, { branch, message, author, files }) {
  const ref = await gh(env, `git/ref/heads/${encodeURIComponent(branch)}`);
  const headSha = ref.object.sha;
  const headCommit = await gh(env, `git/commits/${headSha}`);
  const tree = await Promise.all(files.map(async (f) => ({
    path: f.path, mode: "100644", type: "blob",
    // f.binary: content — уже ЧИСТЫЙ base64 байтов (картинки) → в blob как есть;
    // иначе content — текст → utf-8 → base64 (b64utf8).
    sha: (await gh(env, "git/blobs", { method: "POST", body: JSON.stringify({ content: f.binary ? f.content : b64utf8(f.content), encoding: "base64" }) })).sha,
  })));
  const newTree = await gh(env, "git/trees", { method: "POST", body: JSON.stringify({ base_tree: headCommit.tree.sha, tree }) });
  const stamp = new Date().toISOString();
  const commit = await gh(env, "git/commits", { method: "POST", body: JSON.stringify({
    message, tree: newTree.sha, parents: [headSha],
    author: { name: author, email: `${encodeURIComponent(author)}@yaniktoim.users`, date: stamp },
    committer: { name: author, email: `${encodeURIComponent(author)}@yaniktoim.users`, date: stamp },
  }) });
  await gh(env, `git/refs/heads/${encodeURIComponent(branch)}`, { method: "PATCH", body: JSON.stringify({ sha: commit.sha }) });
  return commit.sha;
}

// ── handlers ────────────────────────────────────────────────────────────────
async function handleRegister(env, body) {
  if (env.INVITE_CODE && body.invite !== env.INVITE_CODE) return json(env, { error: "нужен инвайт-код" }, 403);
  const nick = (body.nick || "").trim();
  if (!validNick(nick)) return json(env, { error: "ник: 2-40 симв., буквы/цифры/ _.-" }, 400);
  if (typeof body.password !== "string" || body.password.length < 6) return json(env, { error: "пароль ≥ 6 символов" }, 400);
  if (await getUser(env, nick)) return json(env, { error: "ник занят" }, 409);
  const { salt, hash } = await hashPassword(body.password);
  await putUser(env, { nick, role: "pending", salt, hash, createdAt: nowSec() });
  return json(env, { ok: true, role: "pending", message: "Заявка создана. Ждите, пока админ выдаст права." });
}

async function handleLogin(env, body) {
  await ensureBootstrapAdmin(env);
  const nick = (body.nick || "").trim();
  const user = await getUser(env, nick);
  if (!user || !(await verifyPassword(body.password || "", user.salt, user.hash))) {
    return json(env, { error: "неверный ник или пароль" }, 401);
  }
  const token = await signSession(env, user.nick, user.role);
  return json(env, { ok: true, token, nick: user.nick, role: user.role });
}

// Имя файла картинки-иллюстрации: только basename без путей (защита от traversal —
// нет точки-в-начале/слэша/«..»), расширение из набора растровых.
const IMG_NAME_RX = /^[A-Za-z0-9_-]{1,64}\.(jpe?g|png|gif|webp)$/i;
// art-id из реального корпуса: алфавитно-цифровой + «_»/«-» (есть напр. `roza_mira`).
// Без точки/слэша → art безопасно подставлять в путь docs/art/<art>.*
const ART_ID_RX = /^[A-Za-z0-9_-]{1,32}$/;

// url-unification: прежний NNN.view.html / songs/index.view.html → редирект-заглушка
// (уже расшаренные ссылки не ломаем). noindex + pagefind-ignore. Та же форма, что в
// editor/build_views.mjs. forced_views/`view:` упразднены — больше не отражаем.
function redirectStub(target) {
  return '<!doctype html><html lang="ru"><head><meta charset="utf-8">\n' +
    '<meta name="robots" content="noindex"><link rel="canonical" href="' + target + '">\n' +
    '<meta http-equiv="refresh" content="0; url=' + target + '"></head>\n' +
    '<body data-pagefind-ignore="all"><a href="' + target + '">→ Перейти к статье</a></body></html>\n';
}

async function handleSave(env, payload, body) {
  if (payload.role !== "editor" && payload.role !== "admin") {
    return json(env, { error: "нет прав на запись (роль: " + payload.role + ")" }, 403);
  }
  const { zml, html } = body;
  if (typeof zml !== "string" || typeof html !== "string") {
    return json(env, { error: "нужны zml, html" }, 400);
  }

  let files, message;
  if (body.page === "songs") {
    // спец-страница «Песнь Ступеней»: источник docs/songs/index.zml → единый
    // рендер docs/songs/index.html (renderSongsHtml = build_songs.mjs). Прежний
    // index.view.html → редирект-заглушка. «old»-варианта у songs нет.
    files = [
      { path: "docs/songs/index.zml", content: zml },
      { path: "docs/songs/index.html", content: html },
      { path: "docs/songs/index.view.html", content: redirectStub("index.html") },
    ];
    message = `cms: edit songs — ${payload.nick}`;
  } else {
    const art = body.art;
    if (!art) return json(env, { error: "нужны art, zml, html" }, 400);
    if (!ART_ID_RX.test(String(art))) return json(env, { error: "битый art-id" }, 400);
    // url-unification: источник docs/art/<art>.zml → единый рендер docs/art/<art>.html
    // (тот же render.js, что build_views.mjs → паритет). Прежний .view.html →
    // редирект-заглушка. NB: браузерный рендер БЕЗ ctx.legacyBody → у правленой через
    // веб статьи опция «old» временно скрыта до следующей полной build_views.
    files = [
      { path: `docs/art/${art}.zml`, content: zml },
      { path: `docs/art/${art}.html`, content: html },
      { path: `docs/art/${art}.view.html`, content: redirectStub(`${art}.html`) },
    ];
    // Ф8(b) опц. иллюстрация: бинарная картинка в docs/img/<name>. content —
    // ЧИСТЫЙ base64 байтов (флаг binary → commitFiles кладёт в blob без utf8-обёртки).
    // Файл картинки НЕ удаляем при «отвязке» (image: убирают из frontmatter ZML —
    // «рукописи не горят»); сюда приходит только при загрузке/замене.
    if (body.image != null) {
      const img = body.image;
      const name = img && typeof img.name === "string" ? img.name.trim() : "";
      if (!IMG_NAME_RX.test(name)) {
        return json(env, { error: "имя картинки: буквы/цифры/_-, расширение jpg|jpeg|png|gif|webp" }, 400);
      }
      if (!img || typeof img.content !== "string" || !img.content) {
        return json(env, { error: "пустое содержимое картинки" }, 400);
      }
      files.push({ path: `docs/img/${name}`, content: img.content, binary: true });
    }
    message = `cms: edit ${art} — ${payload.nick}`;
  }
  const branch = body.branch || "main";
  try {
    const sha = await commitFiles(env, { branch, author: payload.nick, message, files });
    return json(env, { ok: true, sha });
  } catch (e) {
    return json(env, { error: String(e.message || e) }, 502);
  }
}

// Ф10: общий мультифайловый коммит структуры (ТОЛЬКО admin). Принимает
// files:[{path,content}] — structure.json + перегенерённые index/section-страницы
// (+ опц. manifest.json при перемещении). Пути ограничены docs/ и manifest.json.
async function handleCommit(env, who, body) {
  if (who.role !== "admin") {
    return json(env, { error: "структуру правит только admin (роль: " + who.role + ")" }, 403);
  }
  const files = Array.isArray(body.files) ? body.files : null;
  if (!files || !files.length) return json(env, { error: "нужен files:[{path,content}]" }, 400);
  if (files.length > 500) return json(env, { error: "слишком много файлов (>500)" }, 400);
  for (const f of files) {
    if (!f || typeof f.path !== "string" || typeof f.content !== "string") {
      return json(env, { error: "битый files[]" }, 400);
    }
    if (!(f.path.startsWith("docs/") || f.path === "manifest.json")) {
      return json(env, { error: "запрещённый путь: " + f.path }, 400);
    }
  }
  const message = (typeof body.message === "string" && body.message.trim())
    ? body.message.trim().slice(0, 200) : `cms: структура — ${who.nick}`;
  try {
    const sha = await commitFiles(env, { branch: body.branch || "main", author: who.nick, message, files });
    return json(env, { ok: true, sha });
  } catch (e) {
    return json(env, { error: String(e.message || e) }, 502);
  }
}

// ── Ф8′ display settings ─────────────────────────────────────────────────────
// Персональные настройки вида (global + rules) у каждого юзера.
//   • editor → личные в KV `settings:<nick>`;
//   • admin  → ГЛОБАЛЬНЫЕ = коммит docs/config/display.json (видят анонимы).
// GET у незаведённого editor отдаёт глобаль (стартовая точка = «как у анонима»).
// url-unification: «old» — 6-й дизайн (не отдельная «версия»); default_view упразднён.
const F8_THEMES = ["A_editorial", "B_manuscript", "cyberpunk", "swiss", "ar_deco", "old"];
const F8_WIDTHS = ["narrow", "wide"];
const F8_DEFAULT = { version: 1, global: { design: "A_editorial", width: "wide" }, rules: [] };

function sanitizeSettings(o) {
  o = o && typeof o === "object" ? o : {};
  const g = o.global && typeof o.global === "object" ? o.global : {};
  const rules = Array.isArray(o.rules) ? o.rules.slice(0, 100).map((r) => {
    if (!r || typeof r !== "object" || !r.match || typeof r.match !== "object") return null;
    const kind = r.match.kind === "type" ? "type" : (r.match.kind === "section" ? "section" : null);
    const value = typeof r.match.value === "string" ? r.match.value.trim().slice(0, 40) : "";
    if (!kind || !value) return null;
    return {
      match: { kind, value },
      design: F8_THEMES.includes(r.design) ? r.design : "A_editorial",
      width: F8_WIDTHS.includes(r.width) ? r.width : "wide",
    };
  }).filter(Boolean) : [];
  return {
    version: 1,
    global: {
      design: F8_THEMES.includes(g.design) ? g.design : "A_editorial",
      width: F8_WIDTHS.includes(g.width) ? g.width : "wide",
    },
    rules,
  };
}

async function ghReadFileText(env, path, branch) {
  try {
    const r = await gh(env, `contents/${path}?ref=${encodeURIComponent(branch || "main")}`);
    if (r && r.content) return new TextDecoder().decode(b64ToBytes(r.content.replace(/\s/g, "")));
  } catch (e) { /* 404 → нет файла */ }
  return "";
}
async function readGlobalSettings(env) {
  const txt = await ghReadFileText(env, "docs/config/display.json", "main");
  if (txt) { try { return sanitizeSettings(JSON.parse(txt)); } catch (e) { /* битый */ } }
  return F8_DEFAULT;
}

// Ф8′: ГЛОБАЛЬНЫЕ умолчания (их видят анонимы) задаёт ТОЛЬКО мастер-аккаунт «Admin»
// — гейт по НИКУ, не по роли. Прочие admin'ы (Nipna/Anibe) и editor'ы пишут ЛИЧНЫЕ
// настройки (видят только себя залогиненными). Так повышение их до admin даёт права
// на структуру/правку/юзеров, но НЕ на публичный дефолт показа.
const isMasterAdmin = (u) => (u.nick || "").trim().toLowerCase() === "admin";

async function handleGetSettings(env, u) {
  if (isMasterAdmin(u)) return json(env, await readGlobalSettings(env));
  const raw = await env.USERS.get(`settings:${u.nick.toLowerCase()}`);
  if (raw) { try { return json(env, sanitizeSettings(JSON.parse(raw))); } catch (e) { /* битый */ } }
  return json(env, await readGlobalSettings(env)); // не настроен → глобаль как старт
}

async function handlePutSettings(env, u, body) {
  const s = sanitizeSettings(body);
  if (isMasterAdmin(u)) {
    try {
      const sha = await commitFiles(env, {
        branch: "main", author: u.nick,
        message: `cms: display settings (global) — ${u.nick}`,
        files: [{ path: "docs/config/display.json", content: JSON.stringify(s, null, 2) + "\n" }],
      });
      return json(env, { ok: true, scope: "global", sha });
    } catch (e) { return json(env, { error: String(e.message || e) }, 502); }
  }
  if (u.role !== "editor" && u.role !== "admin") return json(env, { error: "нет прав (роль: " + u.role + ")" }, 403);
  await env.USERS.put(`settings:${u.nick.toLowerCase()}`, JSON.stringify(s));
  return json(env, { ok: true, scope: "personal" });
}

async function handleAdminUsers(env) {
  const list = await env.USERS.list({ prefix: "user:" });
  const users = [];
  for (const k of list.keys) {
    const u = JSON.parse(await env.USERS.get(k.name));
    users.push({ nick: u.nick, role: u.role, createdAt: u.createdAt });
  }
  users.sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
  return json(env, { ok: true, users });
}

async function handleAdminPromote(env, body) {
  const role = body.role;
  if (!["pending", "editor", "admin"].includes(role)) return json(env, { error: "роль: pending|editor|admin" }, 400);
  const user = await getUser(env, body.nick || "");
  if (!user) return json(env, { error: "нет такого ника" }, 404);
  user.role = role;
  await putUser(env, user);
  return json(env, { ok: true, nick: user.nick, role });
}

// ── router ──────────────────────────────────────────────────────────────────
// CORS-origin на КАЖДЫЙ ответ: боевой сайт (ALLOW_ORIGIN, можно список через запятую)
// ИЛИ любой localhost/127.0.0.1 (для локального теста). Иначе — первый из ALLOW_ORIGIN.
function corsAllowOrigin(env, origin) {
  const allowed = (env.ALLOW_ORIGIN || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (origin && allowed.includes(origin)) return origin;
  if (/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin || "")) return origin;
  return allowed[0] || "*";
}

export default {
  async fetch(req, env) {
    const res = await route(req, env);
    res.headers.set("Access-Control-Allow-Origin", corsAllowOrigin(env, req.headers.get("Origin") || ""));
    res.headers.set("Vary", "Origin");
    return res;
  },
};

async function route(req, env) {
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(env) });
    const url = new URL(req.url);
    const p = url.pathname;
    try {
      if (req.method === "GET" && p === "/api/health") return json(env, { ok: true });

      if (req.method === "POST" && p === "/api/register") return handleRegister(env, await req.json());
      if (req.method === "POST" && p === "/api/login") return handleLogin(env, await req.json());

      if (req.method === "GET" && p === "/api/me") {
        const pl = await authedPayload(env, req);
        if (!pl) return json(env, { error: "не авторизован" }, 401);
        // re-read role + display nick from KV (canonical) so promotions and
        // nick-capitalization take effect without re-login.
        const u = await getUser(env, pl.nick);
        return json(env, { ok: true, nick: u ? u.nick : pl.nick, role: u ? u.role : pl.role });
      }

      if (req.method === "POST" && p === "/api/save") {
        const pl = await authedPayload(env, req);
        if (!pl) return json(env, { error: "не авторизован" }, 401);
        const u = await getUser(env, pl.nick);                // fresh role + canonical nick
        return handleSave(env, { nick: u ? u.nick : pl.nick, role: u ? u.role : pl.role }, await req.json());
      }

      if (req.method === "POST" && p === "/api/commit") {
        const pl = await authedPayload(env, req);
        if (!pl) return json(env, { error: "не авторизован" }, 401);
        const u = await getUser(env, pl.nick);
        return handleCommit(env, { nick: u ? u.nick : pl.nick, role: u ? u.role : pl.role }, await req.json());
      }

      if (p === "/api/settings" && (req.method === "GET" || req.method === "PUT")) {
        const pl = await authedPayload(env, req);
        if (!pl) return json(env, { error: "не авторизован" }, 401);
        const u = await getUser(env, pl.nick);
        const who = { nick: u ? u.nick : pl.nick, role: u ? u.role : pl.role };
        if (req.method === "GET") return handleGetSettings(env, who);
        return handlePutSettings(env, who, await req.json());
      }

      if (p.startsWith("/api/admin/")) {
        const pl = await authedPayload(env, req);
        if (!pl) return json(env, { error: "не авторизован" }, 401);
        const u = await getUser(env, pl.nick);
        if (!u || u.role !== "admin") return json(env, { error: "только админ" }, 403);
        if (req.method === "GET" && p === "/api/admin/users") return handleAdminUsers(env);
        if (req.method === "POST" && p === "/api/admin/promote") return handleAdminPromote(env, await req.json());
      }

      return json(env, { error: "not found" }, 404);
    } catch (e) {
      return json(env, { error: "worker: " + String(e.message || e) }, 500);
    }
}

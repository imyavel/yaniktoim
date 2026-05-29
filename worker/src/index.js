// yaniktoim auth + commit-proxy Worker (Этап 8).
//
// Зачем: друзья без своего GitHub правят сайт «под общим аккаунтом», логинятся
// каждый под своим ником. GitHub-токен живёт ТОЛЬКО здесь (секрет Worker'а), к
// клиенту не попадает → «править можно только через сайт». Роль на Worker'е —
// граница безопасности (самой регистрацией прав к репо не получить).
//
// Хранилище: KV namespace USERS. Ключи:
//   user:<nick>  → { nick, role, salt, hash, createdAt }
// Роли: "pending" (вошёл, писать нельзя) → "editor" (пишет) / "admin" (+управляет).
//
// Секреты (wrangler secret put …): GH_TOKEN, SESSION_SECRET, ADMIN_BOOTSTRAP.
// Vars (wrangler.toml): ALLOW_ORIGIN, REPO ("imyavel/yaniktoim"), [INVITE_CODE].
//
// Эндпоинты (JSON): POST /api/register, /api/login, GET /api/me,
//   POST /api/save, GET /api/admin/users, POST /api/admin/promote.

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
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
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
    sha: (await gh(env, "git/blobs", { method: "POST", body: JSON.stringify({ content: b64utf8(f.content), encoding: "base64" }) })).sha,
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

async function handleSave(env, payload, body) {
  if (payload.role !== "editor" && payload.role !== "admin") {
    return json(env, { error: "нет прав на запись (роль: " + payload.role + ")" }, 403);
  }
  const { art, section, zml, html } = body;
  if (!art || !section || typeof zml !== "string" || typeof html !== "string") {
    return json(env, { error: "нужны art, section, zml, html" }, 400);
  }
  const branch = body.branch || "main";
  try {
    const sha = await commitFiles(env, {
      branch, author: payload.nick,
      message: `cms: edit ${art} — ${payload.nick}`,
      files: [
        { path: `zml/${art}.zml`, content: zml },
        { path: `docs/${section}/${art}.html`, content: html },
      ],
    });
    return json(env, { ok: true, sha });
  } catch (e) {
    return json(env, { error: String(e.message || e) }, 502);
  }
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
export default {
  async fetch(req, env) {
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
  },
};

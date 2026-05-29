// In-page (wiki-style) editor + login control.
// In Worker mode the page always shows a discreet "Вход" button; once a writer
// logs in it becomes ✎ (enter edit). Editing turns <article> into a ZML editor
// with a live preview rendered by the SAME render.js that builds the site.
//
// render.js is heavy (full ZML renderer) — loaded LAZILY so guests/readers who
// only need the login control don't pull it. enterEdit awaits it before editing.
let RENDER = null;
async function ensureRender() { if (!RENDER) RENDER = await import("./render.js"); return RENDER; }

const dataURL = (p) => new URL("data/" + p, import.meta.url).href;
const art = document.body.dataset.art;
const articleEl = document.querySelector("article");
const fab = document.getElementById("edit-fab");

let base = null;       // { manifest, manifestByArt, zoharIndex, properNouns, template, users }
let rec = null;
let originalZml = null; // last-saved source
let savedArticleHTML = null;
let savedH1 = "", savedDocTitle = "";
let ui = null;          // { bar, ta, prev, status, signer }
let previewing = false;

// ── config (GitHub) ────────────────────────────────────────────────────────
const CFG_KEY = "yanik_gh";
const GH_DEFAULTS = { owner: "imyavel", repo: "yaniktoim", branch: "main" };
const loadCfg = () => { try { return { ...GH_DEFAULTS, ...(JSON.parse(localStorage.getItem(CFG_KEY)) || {}) }; } catch { return { ...GH_DEFAULTS }; } };
const saveCfg = (c) => localStorage.setItem(CFG_KEY, JSON.stringify(c));

// Who the edit is signed as ("подписываюсь как…"). Persisted across sessions.
const SIGNER_KEY = "yanik_signer";
const loadSigner = () => { try { return localStorage.getItem(SIGNER_KEY) || ""; } catch { return ""; } };
const saveSigner = (n) => { try { localStorage.setItem(SIGNER_KEY, n); } catch {} };

// ── Worker mode (Этап 8) ─────────────────────────────────────────────────────
// If config/site.json → docs/editor/data/site.json carries a non-empty workerUrl,
// the editor logs in by nick (session, no PAT in the browser) and saves via the
// Worker (which holds the GitHub token). Empty workerUrl → interim PAT mode below.
const SESSION_KEY = "yanik_session";
let session = null;   // { token, nick, role }
let siteCfg = null;   // { workerUrl } — loaded at boot, before ensureData
const loadSession = () => { try { return JSON.parse(localStorage.getItem(SESSION_KEY)) || null; } catch { return null; } };
const saveSession = (s) => { try { s ? localStorage.setItem(SESSION_KEY, JSON.stringify(s)) : localStorage.removeItem(SESSION_KEY); } catch {} };
function workerUrl() { const c = siteCfg || (base && base.site); return c && c.workerUrl ? String(c.workerUrl).replace(/\/+$/, "") : ""; }
const roleRu = (r) => ({ admin: "админ", editor: "редактор", pending: "ожидает прав" }[r] || r || "—");
const canWrite = (r) => r === "editor" || r === "admin";

async function wapi(path, { method = "GET", body = null, auth = false } = {}) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (auth && session) headers["Authorization"] = `Bearer ${session.token}`;
  const res = await fetch(workerUrl() + path, { method, headers, body: body ? JSON.stringify(body) : null });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

// today as YYYY-MM-DD (local) for the `edited:` frontmatter stamp.
function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// Set/replace a frontmatter scalar (editor/edited) in the ZML source. Adds the
// field (and a frontmatter block, if somehow missing) when absent.
function setFrontmatter(zml, key, value) {
  const v = `${key}: "${String(value).replace(/"/g, '\\"')}"`;
  const m = /^---\n([\s\S]*?)\n---\n?/.exec(zml);
  if (!m) return `---\n${v}\n---\n\n${zml.replace(/^\n+/, "")}`;
  let fm = m[1];
  const rx = new RegExp(`^${key}:\\s*.*$`, "m");
  fm = rx.test(fm) ? fm.replace(rx, v) : `${fm}\n${v}`;
  return `---\n${fm}\n---\n` + zml.slice(m[0].length);
}

function b64utf8(s) {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}
function setStatus(t, cls) { if (ui) { ui.status.textContent = t; ui.status.className = "yanik-status " + (cls || ""); } }
function el(tag, cls, html) { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }

// ── data ─────────────────────────────────────────────────────────────────────
async function ensureData() {
  if (base) return;
  const [manifest, zoharIndex, properNouns, template, users, site] = await Promise.all([
    fetch(dataURL("manifest.json")).then((r) => r.json()),
    fetch(dataURL("zohar_index.json")).then((r) => r.json()).catch(() => ({ chapters: {}, articles: {} })),
    fetch(dataURL("proper-nouns.txt")).then((r) => (r.ok ? r.text() : "")).catch(() => ""),
    fetch(dataURL("template.html")).then((r) => (r.ok ? r.text() : "")).catch(() => ""),
    fetch(dataURL("users.json")).then((r) => (r.ok ? r.json() : [])).catch(() => []),
    fetch(dataURL("site.json")).then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
  ]);
  const manifestByArt = {};
  for (const r of manifest) if (r.art) manifestByArt[r.art] = r;
  base = { manifest, manifestByArt, zoharIndex, properNouns, template, users, site };
  siteCfg = site;
  rec = manifestByArt[art];
  session = loadSession();
}

// Editors selectable in "подписываюсь как…" — everyone except the auto/AI
// signature ("Иван Иванович"), which is only set by the pipeline.
function signerOptions() {
  const users = (base && base.users) || [];
  return users.filter((u) => u && u.role !== "auto" && u.name).map((u) => u.name);
}

async function fetchZml() {
  if (originalZml != null) return originalZml;
  originalZml = await fetch(dataURL("zml/" + art + ".zml")).then((r) => {
    if (!r.ok) throw new Error("zml " + r.status);
    return r.text();
  });
  return originalZml;
}

// ── enter / exit ───────────────────────────────────────────────────────────────
async function enterEdit() {
  try {
    // In Worker mode editing requires a writer session.
    if (workerUrl() && !(session && canWrite(session.role))) { openAuth(); return; }
    await ensureData();
    await ensureRender();
    if (!rec) { alert("Статья " + art + " не найдена в manifest."); return; }
    const zml = await fetchZml();

    savedArticleHTML = articleEl.innerHTML;
    savedH1 = (document.getElementById("article-title") || {}).textContent || "";
    savedDocTitle = document.title;
    fab.hidden = true;

    const bar = el("div", "yanik-editbar");
    const status = el("span", "yanik-status", "правка");
    const mk = (label, cls) => { const b = el("button", cls); b.type = "button"; b.textContent = label; return b; };
    const bSave = mk("Сохранить", "primary");
    const bPrev = mk("Предпросмотр");
    const bCancel = mk("Отмена");
    const bDl = mk("↓ zml");
    const bCfg = mk("⚙");

    const worker = !!workerUrl();
    let signer = null, chip = null;
    if (worker) {
      // Worker mode: sign as the logged-in nick; "Аккаунт" opens login/register.
      chip = el("span", "yanik-signchip");
      const bAuth = mk("Аккаунт");
      bAuth.addEventListener("click", openAuth);
      bar.append(bSave, bPrev, bCancel, el("span", "yanik-grow"), chip, bAuth, status, bDl);
    } else {
      // Interim PAT mode: pick a signature from config/users.json + ⚙ for token.
      signer = el("select", "yanik-signer");
      signer.title = "Подписываюсь как…";
      const names = signerOptions();
      const prev0 = loadSigner();
      for (const n of names) {
        const o = document.createElement("option");
        o.value = n; o.textContent = n;
        if (n === prev0) o.selected = true;
        signer.append(o);
      }
      if (!names.length) { const o = document.createElement("option"); o.textContent = "(нет пользователей)"; o.value = ""; signer.append(o); }
      signer.addEventListener("change", () => saveSigner(signer.value));
      bar.append(bSave, bPrev, bCancel, el("span", "yanik-grow"),
                 el("span", "yanik-signlabel", "как:"), signer, status, bDl, bCfg);
    }

    const ta = el("textarea", "yanik-ta"); ta.spellcheck = false; ta.value = zml;
    const prev = el("article", "yanik-preview"); prev.hidden = true;

    articleEl.innerHTML = "";
    articleEl.append(bar, ta, prev);
    ui = { bar, ta, prev, status, signer, chip, worker };
    previewing = false;

    bSave.addEventListener("click", save);
    bPrev.addEventListener("click", () => togglePreview(bPrev));
    bCancel.addEventListener("click", cancel);
    bDl.addEventListener("click", download);
    if (!worker) bCfg.addEventListener("click", openSettings);
    ta.addEventListener("input", () => { if (ta.value !== originalZml) setStatus("● изменено", "dirty"); else setStatus("правка"); });
    ta.focus();
    window.addEventListener("beforeunload", beforeUnload);

    if (worker) { renderChip(); refreshMe(); }
  } catch (e) {
    alert("Ошибка входа в правку: " + e.message);
    console.error(e);
  }
}

function beforeUnload(e) {
  if (ui && ui.ta && ui.ta.value !== originalZml) { e.preventDefault(); e.returnValue = ""; }
}

function exitEdit() {
  window.removeEventListener("beforeunload", beforeUnload);
  ui = null; previewing = false;
  fab.hidden = false;
}

function cancel() {
  if (ui.ta.value !== originalZml && !confirm("Отменить несохранённые изменения?")) return;
  articleEl.innerHTML = savedArticleHTML;
  const h1 = document.getElementById("article-title");
  if (h1) h1.textContent = savedH1;
  document.title = savedDocTitle;
  window.yanikBindArticle && window.yanikBindArticle();
  exitEdit();
}

// ── preview ──────────────────────────────────────────────────────────────────
function renderInner(zml) {
  const parts = RENDER.renderArticleParts({ zml, rec, ...base });
  const inner = (parts.tocHtml ? parts.tocHtml + "\n" : "") + parts.articleInner;
  return { inner, parts };
}

function togglePreview(btn) {
  if (!previewing) {
    let r;
    try { r = renderInner(ui.ta.value); }
    catch (e) { setStatus("✗ render: " + e.message, "err"); console.error(e); return; }
    ui.prev.innerHTML = r.inner;
    ui.ta.hidden = true; ui.prev.hidden = false;
    btn.textContent = "← Править";
    previewing = true;
    // keep title/byline faithful, rebind footnote/music behaviours
    const h1 = document.getElementById("article-title");
    if (h1 && r.parts.title) h1.textContent = r.parts.title;
    if (r.parts.title) document.title = r.parts.title + " — Путь Восходящей Звезды";
    window.yanikBindArticle && window.yanikBindArticle();
  } else {
    ui.prev.hidden = true; ui.ta.hidden = false;
    btn.textContent = "Предпросмотр";
    previewing = false;
    ui.ta.focus();
  }
}

// ── save ──────────────────────────────────────────────────────────────────────
// One logical commit (§0.5): stamp attribution into the zml, render the FULL
// page with the same render.js the build uses, then write zml/<art>.zml AND
// docs/<section>/<art>.html together via the GitHub Git Data API (blobs → tree
// → commit → ref) so source + generated html never diverge.
async function ghApi(cfg, path, opts = {}) {
  const url = `https://api.github.com/repos/${cfg.owner}/${cfg.repo}/${path}`;
  const res = await fetch(url, {
    ...opts,
    headers: {
      Authorization: `Bearer ${cfg.token}`,
      Accept: "application/vnd.github+json",
      ...(opts.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${(await res.text()).slice(0, 200)}`);
  return res.json();
}

// Worker-mode account chip + role refresh.
function renderChip() {
  if (!ui || !ui.chip) return;
  if (session) {
    ui.chip.textContent = `${session.nick} · ${roleRu(session.role)}`;
    ui.chip.className = "yanik-signchip " + (canWrite(session.role) ? "ok" : "warn");
  } else {
    ui.chip.textContent = "не вошёл";
    ui.chip.className = "yanik-signchip warn";
  }
}
async function refreshMe() {
  if (!session) { renderChip(); return; }
  try {
    const me = await wapi("/api/me", { auth: true });
    session = { ...session, nick: me.nick, role: me.role };
    saveSession(session);
  } catch {
    session = null; saveSession(null); // expired/invalid token
  }
  renderChip();
}

// Stamp attribution + render full page (shared by PAT and Worker save paths).
// Normalize to LF first — source .zml may be CRLF (Windows); committed form is LF.
function prepareSave(signerName) {
  const lf = ui.ta.value.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  let zml = setFrontmatter(lf, "editor", signerName);
  zml = setFrontmatter(zml, "edited", todayISO());
  if (!base.template) throw new Error("нет template.html в data/");
  const html = RENDER.renderArticleHtml({ zml, rec, ...base });
  const section = rec.section || "_unsorted";
  return { zml, html, section };
}

async function save() {
  if (ui && ui.worker) return saveViaWorker();
  return saveViaPat();
}

// Worker-mode: token lives on the Worker; we send the rendered files + session.
async function saveViaWorker() {
  if (!session) { setStatus("войдите, чтобы сохранять", "err"); openAuth(); return; }
  if (!canWrite(session.role)) { setStatus(`нет прав (роль: ${roleRu(session.role)})`, "err"); return; }
  let prep;
  try { prep = prepareSave(session.nick); }
  catch (e) { setStatus("✗ render: " + e.message, "err"); console.error(e); return; }
  setStatus("⏳ сохраняю…", "wait");
  try {
    const r = await wapi("/api/save", { method: "POST", auth: true, body: {
      art, section: prep.section, zml: prep.zml, html: prep.html,
    } });
    originalZml = prep.zml; ui.ta.value = prep.zml;
    setStatus(`✓ закоммичено (${(r.sha || "").slice(0, 7)}, обновится ~30-60 c)`, "ok");
  } catch (e) {
    if (/401|не авторизован/i.test(e.message)) { session = null; saveSession(null); renderChip(); openAuth(); }
    setStatus("✗ " + e.message, "err"); console.error(e);
  }
}

// Interim PAT-mode: commit straight to GitHub Git Data API with a personal token.
async function saveViaPat() {
  const cfg = loadCfg();
  if (!cfg.token || !cfg.owner || !cfg.repo) { setStatus("нет настроек GitHub", "err"); openSettings(); return; }
  const signerName = (ui.signer && ui.signer.value) || loadSigner();
  if (!signerName) { setStatus("выбери, как подписать", "err"); return; }
  const branch = cfg.branch || "main";
  let prep;
  try { prep = prepareSave(signerName); }
  catch (e) { setStatus("✗ render: " + e.message, "err"); console.error(e); return; }
  setStatus("⏳ сохраняю…", "wait");
  try {
    const refObj = await ghApi(cfg, `git/ref/heads/${encodeURIComponent(branch)}`);
    const headSha = refObj.object.sha;
    const headCommit = await ghApi(cfg, `git/commits/${headSha}`);
    const [zmlBlob, htmlBlob] = await Promise.all([
      ghApi(cfg, "git/blobs", { method: "POST", body: JSON.stringify({ content: b64utf8(prep.zml), encoding: "base64" }) }),
      ghApi(cfg, "git/blobs", { method: "POST", body: JSON.stringify({ content: b64utf8(prep.html), encoding: "base64" }) }),
    ]);
    const tree = await ghApi(cfg, "git/trees", { method: "POST", body: JSON.stringify({
      base_tree: headCommit.tree.sha,
      tree: [
        { path: `zml/${art}.zml`, mode: "100644", type: "blob", sha: zmlBlob.sha },
        { path: `docs/${prep.section}/${art}.html`, mode: "100644", type: "blob", sha: htmlBlob.sha },
      ],
    }) });
    const commit = await ghApi(cfg, "git/commits", { method: "POST", body: JSON.stringify({
      message: `cms: edit ${art} — ${signerName}`, tree: tree.sha, parents: [headSha],
    }) });
    await ghApi(cfg, `git/refs/heads/${encodeURIComponent(branch)}`, { method: "PATCH", body: JSON.stringify({ sha: commit.sha }) });
    originalZml = prep.zml; ui.ta.value = prep.zml;
    setStatus("✓ закоммичено (обновится ~30-60 c)", "ok");
  } catch (e) {
    setStatus("✗ " + e.message, "err"); console.error(e);
  }
}

function download() {
  const blob = new Blob([ui.ta.value], { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = `${art}.zml`;
  a.click(); URL.revokeObjectURL(a.href);
}

// ── settings dialog ────────────────────────────────────────────────────────────
let dlg = null;
function buildDialog() {
  if (dlg) return dlg;
  dlg = el("dialog", "yanik-settings");
  dlg.innerHTML = `
    <h3 style="margin:0 0 .6rem">GitHub — сохранение</h3>
    <label>owner</label><input id="yk-owner" placeholder="imyavel" autocomplete="off">
    <label>repo</label><input id="yk-repo" placeholder="yaniktoim" autocomplete="off">
    <label>branch</label><input id="yk-branch" placeholder="main" autocomplete="off">
    <label>token (PAT, contents:write)</label>
    <input id="yk-token" type="password" placeholder="ghp_… (хранится только в этом браузере)" autocomplete="off">
    <p class="hint">Локально (без репозитория) commit недоступен — пользуйся «↓ zml» и клади файл в <code>zml/</code> вручную.</p>
    <div class="row"><button type="button" id="yk-clear">Очистить</button><button type="button" id="yk-ok" class="primary">OK</button></div>`;
  document.body.appendChild(dlg);
  dlg.querySelector("#yk-ok").addEventListener("click", () => {
    saveCfg({
      owner: dlg.querySelector("#yk-owner").value.trim(),
      repo: dlg.querySelector("#yk-repo").value.trim(),
      branch: dlg.querySelector("#yk-branch").value.trim() || "main",
      token: dlg.querySelector("#yk-token").value.trim(),
    });
    dlg.close(); setStatus("настройки сохранены", "ok");
  });
  dlg.querySelector("#yk-clear").addEventListener("click", () => { localStorage.removeItem(CFG_KEY); dlg.close(); });
  return dlg;
}
function openSettings() {
  const d = buildDialog();
  const c = loadCfg();
  d.querySelector("#yk-owner").value = c.owner || "";
  d.querySelector("#yk-repo").value = c.repo || "";
  d.querySelector("#yk-branch").value = c.branch || "main";
  d.querySelector("#yk-token").value = c.token || "";
  d.showModal();
}

// ── account dialog (Worker mode) ────────────────────────────────────────────
let authDlg = null;
function buildAuthDialog() {
  if (authDlg) return authDlg;
  authDlg = el("dialog", "yanik-settings yanik-auth");
  authDlg.innerHTML = `
    <h3 style="margin:0 0 .6rem">Аккаунт yaniktoim</h3>
    <div id="yk-astate" class="yanik-astate"></div>
    <div id="yk-aforms">
      <label>ник</label><input id="yk-anick" autocomplete="off">
      <label>пароль</label><input id="yk-apass" type="password" autocomplete="off">
      <label>инвайт-код <span class="hint">(если нужен)</span></label>
      <input id="yk-ainvite" autocomplete="off" placeholder="оставь пустым, если без кода">
      <div class="row"><button type="button" id="yk-aregister">Регистрация</button><button type="button" id="yk-alogin" class="primary">Войти</button></div>
    </div>
    <p class="hint" id="yk-amsg"></p>
    <div id="yk-admin" hidden><h4 style="margin:.6rem 0 .3rem">Пользователи</h4><div id="yk-users" class="yanik-users"></div></div>
    <div class="row"><button type="button" id="yk-alogout" hidden>Выйти</button><button type="button" id="yk-aclose" class="primary">Закрыть</button></div>`;
  document.body.appendChild(authDlg);
  const $ = (s) => authDlg.querySelector(s);
  const msg = (t, ok) => { const m = $("#yk-amsg"); m.textContent = t || ""; m.style.color = ok ? "var(--done)" : "#b00020"; };

  $("#yk-alogin").addEventListener("click", async () => {
    try {
      const r = await wapi("/api/login", { method: "POST", body: { nick: $("#yk-anick").value.trim(), password: $("#yk-apass").value } });
      session = { token: r.token, nick: r.nick, role: r.role }; saveSession(session);
      $("#yk-apass").value = ""; renderChip(); refreshFab(); msg("Вошёл: " + r.nick, true); refreshAuthDialog();
    } catch (e) { msg(e.message); }
  });
  $("#yk-aregister").addEventListener("click", async () => {
    try {
      const body = { nick: $("#yk-anick").value.trim(), password: $("#yk-apass").value };
      const inv = $("#yk-ainvite").value.trim(); if (inv) body.invite = inv;
      const r = await wapi("/api/register", { method: "POST", body });
      msg(r.message || "Заявка создана. Жди прав от админа.", true);
    } catch (e) { msg(e.message); }
  });
  $("#yk-alogout").addEventListener("click", () => { session = null; saveSession(null); renderChip(); refreshFab(); msg("Вышел", true); refreshAuthDialog(); });
  $("#yk-aclose").addEventListener("click", () => authDlg.close());
  return authDlg;
}

async function refreshAuthDialog() {
  const d = buildAuthDialog();
  const $ = (s) => d.querySelector(s);
  await refreshMe();
  const logged = !!session;
  $("#yk-astate").textContent = logged ? `Вы вошли как ${session.nick} · ${roleRu(session.role)}` : "Вы не вошли.";
  $("#yk-aforms").hidden = logged;
  $("#yk-alogout").hidden = !logged;
  const isAdmin = logged && session.role === "admin";
  $("#yk-admin").hidden = !isAdmin;
  if (isAdmin) {
    try {
      const { users } = await wapi("/api/admin/users", { auth: true });
      const box = $("#yk-users"); box.innerHTML = "";
      for (const u of users) {
        const row = el("div", "yanik-userrow");
        const sel = el("select"); for (const r of ["pending", "editor", "admin"]) { const o = document.createElement("option"); o.value = o.textContent = r; if (r === u.role) o.selected = true; sel.append(o); }
        const apply = el("button"); apply.type = "button"; apply.textContent = "⤴";
        apply.addEventListener("click", async () => {
          try { await wapi("/api/admin/promote", { method: "POST", auth: true, body: { nick: u.nick, role: sel.value } }); apply.textContent = "✓"; }
          catch (e) { alert(e.message); }
        });
        row.append(el("span", "yanik-unick", u.nick), sel, apply);
        box.append(row);
      }
    } catch (e) { $("#yk-users").textContent = e.message; }
  }
}

function openAuth() {
  const d = buildAuthDialog();
  refreshAuthDialog();
  d.showModal();
}

// ── fab state ────────────────────────────────────────────────────────────────
// One floating button. Worker mode: "Вход" for guests → ✎ once a writer logs in.
// PAT mode (no workerUrl): ✎ only when ?edit=1 set the yanik_edit flag.
function refreshFab() {
  if (!fab || !art || !articleEl) return;
  if (workerUrl()) {
    if (session && canWrite(session.role)) {
      fab.textContent = "✎"; fab.classList.remove("login");
      fab.title = "Редактировать"; fab.onclick = enterEdit; fab.hidden = false;
    } else {
      fab.textContent = "Вход"; fab.classList.add("login");
      fab.title = "Войти / регистрация"; fab.onclick = openAuth; fab.hidden = false;
    }
  } else {
    // interim PAT mode
    if (localStorage.getItem("yanik_edit") === "1") {
      fab.textContent = "✎"; fab.classList.remove("login");
      fab.title = "Редактировать"; fab.onclick = enterEdit; fab.hidden = false;
    } else {
      fab.hidden = true;
    }
  }
}

// ── boot ──────────────────────────────────────────────────────────────────────
if (fab && art && articleEl) {
  fetch(dataURL("site.json")).then((r) => (r.ok ? r.json() : {})).catch(() => ({})).then((cfg) => {
    siteCfg = cfg || {};
    session = loadSession();
    refreshFab();
  });
  // Ctrl+S inside the editor → save
  window.addEventListener("keydown", (e) => {
    if (ui && (e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); }
  });
}

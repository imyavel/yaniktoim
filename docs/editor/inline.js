// In-page (wiki-style) editor. Loaded only in edit mode by the article page.
// Clicking ✎ turns the <article> area into a ZML editor with a live preview
// rendered by the SAME render.js that builds the site — no separate page/form.
import { renderArticleParts, renderArticleHtml } from "./render.js";

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
  const [manifest, zoharIndex, properNouns, template, users] = await Promise.all([
    fetch(dataURL("manifest.json")).then((r) => r.json()),
    fetch(dataURL("zohar_index.json")).then((r) => r.json()).catch(() => ({ chapters: {}, articles: {} })),
    fetch(dataURL("proper-nouns.txt")).then((r) => (r.ok ? r.text() : "")).catch(() => ""),
    fetch(dataURL("template.html")).then((r) => (r.ok ? r.text() : "")).catch(() => ""),
    fetch(dataURL("users.json")).then((r) => (r.ok ? r.json() : [])).catch(() => []),
  ]);
  const manifestByArt = {};
  for (const r of manifest) if (r.art) manifestByArt[r.art] = r;
  base = { manifest, manifestByArt, zoharIndex, properNouns, template, users };
  rec = manifestByArt[art];
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
    await ensureData();
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

    // "подписываюсь как…" — who this edit is attributed to.
    const signer = el("select", "yanik-signer");
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

    const ta = el("textarea", "yanik-ta"); ta.spellcheck = false; ta.value = zml;
    const prev = el("article", "yanik-preview"); prev.hidden = true;

    articleEl.innerHTML = "";
    articleEl.append(bar, ta, prev);
    ui = { bar, ta, prev, status, signer };
    previewing = false;

    bSave.addEventListener("click", save);
    bPrev.addEventListener("click", () => togglePreview(bPrev));
    bCancel.addEventListener("click", cancel);
    bDl.addEventListener("click", download);
    bCfg.addEventListener("click", openSettings);
    ta.addEventListener("input", () => { if (ta.value !== originalZml) setStatus("● изменено", "dirty"); else setStatus("правка"); });
    ta.focus();
    window.addEventListener("beforeunload", beforeUnload);
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
  const parts = renderArticleParts({ zml, rec, ...base });
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

async function save() {
  const cfg = loadCfg();
  if (!cfg.token || !cfg.owner || !cfg.repo) {
    setStatus("нет настроек GitHub", "err");
    openSettings();
    return;
  }
  const signerName = (ui.signer && ui.signer.value) || loadSigner();
  if (!signerName) { setStatus("выбери, как подписать", "err"); return; }
  const branch = cfg.branch || "main";

  // 1. Stamp attribution into the source. Normalize to LF first — source .zml
  // may be CRLF (Windows), and setFrontmatter's regex + the committed form are
  // LF (matches render.js normalization and the LF html the build writes).
  const lf = ui.ta.value.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  let zml = setFrontmatter(lf, "editor", signerName);
  zml = setFrontmatter(zml, "edited", todayISO());

  // 2. Render the full page (same renderer + template as the build).
  let html;
  try {
    if (!base.template) throw new Error("нет template.html в data/");
    html = renderArticleHtml({ zml, rec, ...base });
  } catch (e) {
    setStatus("✗ render: " + e.message, "err"); console.error(e); return;
  }

  const section = rec.section || "_unsorted";
  const zmlPath = `zml/${art}.zml`;
  const htmlPath = `docs/${section}/${art}.html`;

  setStatus("⏳ сохраняю…", "wait");
  try {
    // 3. Current branch head + base tree.
    const refObj = await ghApi(cfg, `git/ref/heads/${encodeURIComponent(branch)}`);
    const headSha = refObj.object.sha;
    const headCommit = await ghApi(cfg, `git/commits/${headSha}`);
    const baseTree = headCommit.tree.sha;

    // 4. Blobs for both files.
    const [zmlBlob, htmlBlob] = await Promise.all([
      ghApi(cfg, "git/blobs", { method: "POST", body: JSON.stringify({ content: b64utf8(zml), encoding: "base64" }) }),
      ghApi(cfg, "git/blobs", { method: "POST", body: JSON.stringify({ content: b64utf8(html), encoding: "base64" }) }),
    ]);

    // 5. Tree → commit → move ref.
    const tree = await ghApi(cfg, "git/trees", { method: "POST", body: JSON.stringify({
      base_tree: baseTree,
      tree: [
        { path: zmlPath, mode: "100644", type: "blob", sha: zmlBlob.sha },
        { path: htmlPath, mode: "100644", type: "blob", sha: htmlBlob.sha },
      ],
    }) });
    const commit = await ghApi(cfg, "git/commits", { method: "POST", body: JSON.stringify({
      message: `cms: edit ${art} — ${signerName}`,
      tree: tree.sha,
      parents: [headSha],
    }) });
    await ghApi(cfg, `git/refs/heads/${encodeURIComponent(branch)}`, {
      method: "PATCH", body: JSON.stringify({ sha: commit.sha }),
    });

    originalZml = zml;
    ui.ta.value = zml; // reflect stamped frontmatter back into the textarea
    setStatus("✓ закоммичено (обновится ~30-60 c)", "ok");
  } catch (e) {
    setStatus("✗ " + e.message, "err");
    console.error(e);
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

// ── boot ──────────────────────────────────────────────────────────────────────
if (fab && art && articleEl) {
  fab.hidden = false;
  fab.addEventListener("click", enterEdit);
  // Ctrl+S inside the editor → save
  window.addEventListener("keydown", (e) => {
    if (ui && (e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); }
  });
}

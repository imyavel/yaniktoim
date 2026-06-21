// Локальный end-to-end тест Worker'а /api/commit БЕЗ GitHub и БЕЗ живого сайта.
//   node test_commit.mjs
// Импортирует НАСТОЯЩИЙ src/index.js (через временную .mjs-копию, т.к. worker/
// package.json — CJS), фейковый KV (сеет тест-admin через ADMIN_BOOTSTRAP),
// мок-GitHub (Git Data API в память). Прогоняет реальный 6-файловый payload фазы
// E (создание статьи; файлы строятся теми же render.js-функциями, что и
// браузерный ya-struct.commitNewArticle) + негативы. Самоочищается.
import { readFileSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { renderArticleHtml, renderIndexHtml, renderSectionIndexHtml } from "../editor/render.js";

const data = "../editor/data", docs = "../../docs";
const J = (p) => JSON.parse(readFileSync(p, "utf8"));
const T = (p) => readFileSync(p, "utf8");

// src/index.js — ESM с расширением .js в CJS-пакете → копируем в .mjs и импортим.
const tmp = "./_wtmp_test.mjs";
writeFileSync(tmp, readFileSync("./src/index.js", "utf8"));
const worker = (await import(pathToFileURL(tmp).href)).default;

const REPO = "test/test";
const ghStore = { blobs: {}, trees: [], commits: [], refPatched: null, n: 0, files: {} };
const realFetch = globalThis.fetch;
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url);
  if (!u.startsWith(`https://api.github.com/repos/${REPO}/`)) return realFetch(url, opts);
  const path = u.slice(`https://api.github.com/repos/${REPO}/`.length).split("?")[0];
  const body = opts.body ? JSON.parse(opts.body) : null;
  const ok = (o) => new Response(JSON.stringify(o), { status: 200, headers: { "Content-Type": "application/json" } });
  if (opts.method === undefined || opts.method === "GET") {
    if (path === "git/ref/heads/main") return ok({ object: { sha: "BASESHA" } });
    if (path === "git/commits/BASESHA") return ok({ tree: { sha: "BASETREE" } });
    if (path.startsWith("contents/")) {           // ghReadFileText (Ф8(d) forced_views.json)
      const fp = decodeURIComponent(path.slice("contents/".length));
      if (ghStore.files[fp] != null) return ok({ content: Buffer.from(ghStore.files[fp], "utf8").toString("base64") });
      return new Response("not found", { status: 404 });
    }
  }
  if (opts.method === "POST" && path === "git/blobs") { const sha = "blob" + (++ghStore.n); ghStore.blobs[sha] = body; return ok({ sha }); }
  if (opts.method === "POST" && path === "git/trees") { ghStore.trees.push(body); return ok({ sha: "NEWTREE" }); }
  if (opts.method === "POST" && path === "git/commits") { ghStore.commits.push(body); return ok({ sha: "NEWCOMMIT" }); }
  if (opts.method === "PATCH" && path === "git/refs/heads/main") { ghStore.refPatched = body; return ok({}); }
  return new Response("unexpected " + opts.method + " " + path, { status: 500 });
};

const kv = new Map();
const USERS = {
  get: async (k) => (kv.has(k) ? kv.get(k) : null),
  put: async (k, v) => { kv.set(k, v); },
  list: async ({ prefix } = {}) => ({ keys: [...kv.keys()].filter((k) => !prefix || k.startsWith(prefix)).map((name) => ({ name })) }),
};
const env = { USERS, SESSION_SECRET: "devsecret", GH_TOKEN: "dummy", REPO, ALLOW_ORIGIN: "http://localhost", ADMIN_BOOTSTRAP: "Admin:test123" };
const call = (method, path, { token, body } = {}) => {
  const headers = { "Content-Type": "application/json", Origin: "http://localhost" };
  if (token) headers.Authorization = "Bearer " + token;
  return worker.fetch(new Request("https://w.dev" + path, { method, headers, body: body ? JSON.stringify(body) : undefined }), env);
};

function buildPayload() {
  const today = "2026-06-18", art = "66I", slug = "best", title = "Новая статья";
  const manifest = J(join(docs, "..", "manifest.json"));
  const manifestByArt = Object.fromEntries(manifest.map((r) => [r.art, r]));
  const zoharIndex = J(join(data, "zohar_index.json"));
  const properNouns = T(join(data, "proper-nouns.txt"));
  const tplView = T(join(data, "template_view.html"));
  const tplIndex = T(join(data, "template_index.html"));
  const tplSection = T(join(data, "template_section.html"));
  const displayConfig = J(join(docs, "config", "display.json"));
  const siteConfig = J(join(data, "site.json"));
  const zml = ["---", "title: " + title, 'art: "' + art + '"', "date: " + today, "type: prose", "view: zml", "---",
    "[epi kind=prose]", "Эпиграф.", "[/epi]", "", "Текст.[^1]", "", "[^1]: сноска.", ""].join("\n");
  const view = renderArticleHtml({ zml, rec: { art, section: slug, title, date_chosen: today, url: "" },
    manifest, manifestByArt, zoharIndex, template: tplView, properNouns, displayConfig, siteConfig });
  const st = J(join(docs, "config", "structure.json"));
  const maxO = st.articles.filter((a) => a.section === slug && a.status !== "archived").reduce((m, a) => Math.max(m, a.order), -1);
  st.articles.push({ art, section: slug, order: maxO + 1, status: "published", title, date: today });
  const fc = J(join(docs, "config", "forced_views.json")); fc[art] = "zml";
  return [
    { path: "docs/config/structure.json", content: JSON.stringify(st, null, 2) + "\n" },
    { path: "docs/config/forced_views.json", content: JSON.stringify(fc) + "\n" },
    { path: "docs/art/" + art + ".zml", content: zml },
    { path: "docs/art/" + art + ".view.html", content: view },
    { path: "docs/index.html", content: renderIndexHtml({ structure: st, manifestByArt, template: tplIndex, buildDate: today }) },
    { path: "docs/" + slug + "/index.html", content: renderSectionIndexHtml({ slug, structure: st, manifestByArt, template: tplSection, buildDate: today, forced: fc, defaultView: "old" }) },
  ];
}

let pass = 0, fail = 0;
const ok = (n, c) => { console.log((c ? "  OK  " : "  FAIL ") + n); c ? pass++ : fail++; };
const dec = (b64) => Buffer.from(b64, "base64").toString("utf8");

try {
  let r = await call("POST", "/api/login", { body: { nick: "Admin", password: "test123" } });
  let d = await r.json();
  ok("login admin → token", r.status === 200 && !!d.token && d.role === "admin");
  const token = d.token;

  const files = buildPayload();
  ok("payload = 6 файлов", files.length === 6);
  r = await call("POST", "/api/commit", { token, body: { files, message: "cms: новая статья 66I (best) — Admin" } });
  d = await r.json();
  ok("/api/commit admin → ok+sha", r.status === 200 && d.ok === true && d.sha === "NEWCOMMIT");

  ok("создано 6 blob'ов", Object.keys(ghStore.blobs).length === 6);
  const tree = ghStore.trees[ghStore.trees.length - 1];
  ok("tree.base_tree = BASETREE", tree && tree.base_tree === "BASETREE");
  ok("пути дерева == 6 путей payload", JSON.stringify((tree.tree || []).map((t) => t.path).sort()) === JSON.stringify(files.map((f) => f.path).sort()));
  ok("все mode=100644 type=blob", (tree.tree || []).every((t) => t.mode === "100644" && t.type === "blob"));
  let contentOk = true;
  for (const t of tree.tree) if (dec(ghStore.blobs[t.sha].content) !== files.find((f) => f.path === t.path).content) { contentOk = false; console.log("    разошлось:", t.path); }
  ok("содержимое всех 6 blob'ов == payload", contentOk);
  ok("ref heads/main → NEWCOMMIT", ghStore.refPatched && ghStore.refPatched.sha === "NEWCOMMIT");
  ok("commit-message сохранён", ghStore.commits[0].message.includes("новая статья 66I"));
  ok("author = ник Admin", ghStore.commits[0].author && ghStore.commits[0].author.name === "Admin");

  r = await call("POST", "/api/commit", { token, body: { files: [{ path: "evil.txt", content: "x" }] } });
  d = await r.json();
  ok("admin + путь вне docs/ → 400", r.status === 400 && /запрещённый путь/.test(d.error || ""));
  r = await call("POST", "/api/commit", { body: { files } });
  ok("без токена → 401", r.status === 401);
  r = await call("POST", "/api/commit", { token, body: { files: [] } });
  ok("пустой files[] → 400", r.status === 400);

  // ── Ф8(b): /api/save с бинарной иллюстрацией (editor, не только admin) ────────
  // image.content — ЧИСТЫЙ base64 байтов → в blob БЕЗ utf8-обёртки (binary);
  // zml/html — текст (b64utf8). Проверяем точное восстановление байтов картинки.
  r = await call("POST", "/api/register", { body: { nick: "Edi", password: "test123" } });
  ok("register Edi → pending", (await r.json()).role === "pending");
  r = await call("POST", "/api/admin/promote", { token, body: { nick: "Edi", role: "editor" } });
  ok("promote Edi → editor", (await r.json()).role === "editor");
  r = await call("POST", "/api/login", { body: { nick: "Edi", password: "test123" } });
  const etoken = (await r.json()).token;

  const imgBytes = Buffer.from([0xFF, 0xD8, 0xFF, 0xE0, 0, 16, 1, 2, 3, 250, 128, 7]); // «байты картинки»
  const imgB64 = imgBytes.toString("base64");
  const zmlText = "---\ntitle: T\nimage: 03H.jpg\n---\nтекст";
  const htmlText = "<html>вью</html>";
  let before = Object.keys(ghStore.blobs).length;
  r = await call("POST", "/api/save", { token: etoken, body: { art: "03H", zml: zmlText, html: htmlText, image: { name: "03H.jpg", content: imgB64 }, branch: "main" } });
  d = await r.json();
  ok("editor /api/save+image → ok+sha", r.status === 200 && d.ok === true && d.sha === "NEWCOMMIT");
  ok("создано 3 blob'а (zml+view+img)", Object.keys(ghStore.blobs).length - before === 3);
  const stree = ghStore.trees[ghStore.trees.length - 1];
  ok("дерево = 3 пути", JSON.stringify((stree.tree || []).map((t) => t.path).sort()) ===
    JSON.stringify(["docs/art/03H.view.html", "docs/art/03H.zml", "docs/img/03H.jpg"]));
  const imgBlob = ghStore.blobs[stree.tree.find((t) => t.path === "docs/img/03H.jpg").sha];
  ok("img blob: encoding base64", imgBlob.encoding === "base64");
  ok("img blob: ЧИСТЫЙ base64 (НЕ двойное кодирование)",
    imgBlob.content === imgB64 && imgBlob.content !== Buffer.from(imgB64, "utf8").toString("base64"));
  ok("img blob: байты восстановлены точно", Buffer.from(imgBlob.content, "base64").equals(imgBytes));
  ok("zml blob: текст через utf8-обёртку", dec(ghStore.blobs[stree.tree.find((t) => t.path === "docs/art/03H.zml").sha].content) === zmlText);

  r = await call("POST", "/api/save", { token: etoken, body: { art: "03H", zml: zmlText, html: htmlText, image: { name: "../evil.jpg", content: imgB64 } } });
  ok("image имя с .. → 400", r.status === 400);
  r = await call("POST", "/api/save", { token: etoken, body: { art: "03H", zml: zmlText, html: htmlText, image: { name: "x.exe", content: imgB64 } } });
  ok("image расширение .exe → 400", r.status === 400);
  r = await call("POST", "/api/save", { token: etoken, body: { art: "03H", zml: zmlText, html: htmlText, image: { name: "03H.jpg", content: "" } } });
  ok("image пустой контент → 400", r.status === 400);
  before = Object.keys(ghStore.blobs).length;
  r = await call("POST", "/api/save", { token: etoken, body: { art: "03H", zml: zmlText, html: htmlText } });
  d = await r.json();
  ok("/api/save без image → 2 blob'а (совместимость)", r.status === 200 && d.ok && Object.keys(ghStore.blobs).length - before === 2);
  r = await call("POST", "/api/save", { token: etoken, body: { art: "../../etc/x", zml: zmlText, html: htmlText } });
  ok("битый art-id → 400", r.status === 400);

  // ── Ф8(c): /api/save page:"songs" — фикс. пути спец-страницы (editor) ────────
  const sZml = "---\ntitle: Песнь Ступеней\n---\n[shir cols=3]\nID | Трек | Автор | 03H";
  const sHtml = "<html>songs-вью</html>";
  before = Object.keys(ghStore.blobs).length;
  r = await call("POST", "/api/save", { token: etoken, body: { page: "songs", zml: sZml, html: sHtml, branch: "main" } });
  d = await r.json();
  ok("editor /api/save page:songs → ok+sha", r.status === 200 && d.ok === true && d.sha === "NEWCOMMIT");
  ok("songs: создано 2 blob'а", Object.keys(ghStore.blobs).length - before === 2);
  const songsTree = ghStore.trees[ghStore.trees.length - 1];
  ok("songs: пути = index.zml + index.view.html", JSON.stringify((songsTree.tree || []).map((t) => t.path).sort()) ===
    JSON.stringify(["docs/songs/index.view.html", "docs/songs/index.zml"]));
  ok("songs: zml-blob == payload", dec(ghStore.blobs[songsTree.tree.find((t) => t.path === "docs/songs/index.zml").sha].content) === sZml);
  ok("songs: art-id НЕ требуется (нет docs/art/)", !(songsTree.tree || []).some((t) => t.path.startsWith("docs/art/")));
  ok("songs: commit-message про songs", ghStore.commits[ghStore.commits.length - 1].message.includes("edit songs"));
  r = await call("POST", "/api/save", { token: etoken, body: { page: "songs", zml: sZml } });
  ok("songs без html → 400", r.status === 400);
  r = await call("POST", "/api/save", { body: { page: "songs", zml: sZml, html: sHtml } });
  ok("songs без токена → 401", r.status === 401);

  // ── Ф8(d): /api/save отражает frontmatter `view:` в forced_views.json ────────
  const FV = "docs/config/forced_views.json";
  const lastTree = () => ghStore.trees[ghStore.trees.length - 1];
  const fvBlob = () => { const t = (lastTree().tree || []).find((x) => x.path === FV); return t ? JSON.parse(dec(ghStore.blobs[t.sha].content)) : null; };
  const hasFv = () => (lastTree().tree || []).some((x) => x.path === FV);

  // (1) view: zml, файла ещё нет → forced_views.json в коммите = {03H:"zml"}
  ghStore.files = {};
  r = await call("POST", "/api/save", { token: etoken, body: { art: "03H", zml: "---\ntitle: T\nview: zml\n---\nтекст", html: htmlText, branch: "main" } });
  d = await r.json();
  ok("save view:zml → ok", r.status === 200 && d.ok === true);
  ok("save view:zml → forced_views.json {03H:zml}", hasFv() && fvBlob()["03H"] === "zml");

  // (2) view: html → forced_views.json {03H:"html"}
  ghStore.files = {};
  await (await call("POST", "/api/save", { token: etoken, body: { art: "03H", zml: "---\ntitle: T\nview: html\n---\nтекст", html: htmlText } })).json();
  ok("save view:html → forced_views.json {03H:html}", hasFv() && fvBlob()["03H"] === "html");

  // (3) нет view:, но 03H БЫЛ в карте → запись убирается, чужие остаются
  ghStore.files = { [FV]: JSON.stringify({ "03H": "zml", "OTH": "zml" }) };
  await (await call("POST", "/api/save", { token: etoken, body: { art: "03H", zml: "---\ntitle: T\n---\nтекст", html: htmlText } })).json();
  ok("save без view: убирает 03H, чужой OTH цел", hasFv() && !("03H" in fvBlob()) && fvBlob()["OTH"] === "zml");

  // (4) нет view: и 03H НЕ в карте → forced_views.json НЕ коммитим (нет изменений)
  ghStore.files = { [FV]: JSON.stringify({ "OTH": "zml" }) };
  before = Object.keys(ghStore.blobs).length;
  await (await call("POST", "/api/save", { token: etoken, body: { art: "03H", zml: "---\ntitle: T\n---\nтекст", html: htmlText } })).json();
  ok("save без изменения карты → forced_views.json НЕ в коммите", !hasFv());
  ok("save без изменения карты → только 2 blob'а (zml+view)", Object.keys(ghStore.blobs).length - before === 2);

  // (5) page:"songs" тоже отражает view: в forced_views.json под ключом "songs"
  ghStore.files = {};
  r = await call("POST", "/api/save", { token: etoken, body: { page: "songs", zml: "---\ntitle: Песнь\nview: zml\n---\n[shir]\n[/shir]", html: "<x>", branch: "main" } });
  d = await r.json();
  ok("songs save view:zml → ok", r.status === 200 && d.ok === true);
  ok("songs save view:zml → forced_views.json {songs:zml}", hasFv() && fvBlob().songs === "zml");
  ghStore.files = { [FV]: JSON.stringify({ "OTH": "zml" }) };
  before = Object.keys(ghStore.blobs).length;
  await (await call("POST", "/api/save", { token: etoken, body: { page: "songs", zml: "---\ntitle: Песнь\n---\n[shir]\n[/shir]", html: "<x>" } })).json();
  ok("songs save без view: → forced_views.json НЕ в коммите", !hasFv());
  ok("songs save без изменения карты → 2 blob'а (zml+view)", Object.keys(ghStore.blobs).length - before === 2);
  ghStore.files = {};

  // ── Ф8′: глобальные умолчания (анонимам) задаёт ТОЛЬКО ник Admin, не роль ─────
  let before2 = Object.keys(ghStore.blobs).length;
  r = await call("PUT", "/api/settings", { token, body: { default_view: "new", global: { design: "swiss", width: "narrow" }, rules: [] } });
  d = await r.json();
  ok("Admin (мастер-ник) PUT settings → scope global", r.status === 200 && d.ok === true && d.scope === "global");
  ok("global → коммит display.json (blob +1)", Object.keys(ghStore.blobs).length - before2 === 1);

  // Boss — admin по РОЛИ, но ник не Admin → ЛИЧНЫЕ (не глобаль)
  await call("POST", "/api/register", { body: { nick: "Boss", password: "test123" } });
  await call("POST", "/api/admin/promote", { token, body: { nick: "Boss", role: "admin" } });
  const bossTok = (await (await call("POST", "/api/login", { body: { nick: "Boss", password: "test123" } })).json()).token;
  before2 = Object.keys(ghStore.blobs).length;
  r = await call("PUT", "/api/settings", { token: bossTok, body: { global: { design: "swiss" } } });
  d = await r.json();
  ok("admin-роль, НЕ-Admin ник (Boss) PUT → scope personal", r.status === 200 && d.ok === true && d.scope === "personal");
  ok("personal → БЕЗ коммита (blob +0)", Object.keys(ghStore.blobs).length - before2 === 0);
  r = await call("PUT", "/api/settings", { token: etoken, body: { global: { design: "swiss" } } });
  ok("editor (Edi) PUT → scope personal", (await r.json()).scope === "personal");

  console.log(`\n${fail === 0 ? "ВСЁ ЗЕЛЁНОЕ" : "ЕСТЬ ПРОВАЛЫ"}: pass=${pass} fail=${fail}`);
} finally {
  rmSync(tmp, { force: true });
}
process.exit(fail === 0 ? 0 : 1);

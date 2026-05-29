// Site build — JS-canonical. Renders every zml/*.zml → docs/<section>/<art>.html
// via the single renderer (docs/editor/render.js), and emits the data bundle the
// in-browser editor needs (manifest subset + zohar index + page template + zml
// sources). NO CI: the same render.js runs here (local batch) and in the editor's
// browser at Save — docs/ is committed and served by legacy Pages (main /docs).
//
//   node tools/build.mjs            # all arts present in zml/
//   node tools/build.mjs 237 654    # subset

import {
  readdirSync, readFileSync, writeFileSync, mkdirSync, copyFileSync, existsSync,
} from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { renderArticleHtml } from "../docs/editor/render.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SITE = join(ROOT, "docs");
const ZML = join(ROOT, "zml");
const DATA = join(SITE, "editor", "data");

function loadCtx() {
  const manifest = JSON.parse(readFileSync(join(ROOT, "manifest.json"), "utf-8"));
  const manifestByArt = {};
  for (const r of manifest) if (r.art) manifestByArt[r.art] = r;
  let zoharIndex = { chapters: {}, articles: {} };
  const zi = join(ROOT, "_logs/zohar_index.json");
  if (existsSync(zi)) zoharIndex = JSON.parse(readFileSync(zi, "utf-8"));
  const template = readFileSync(join(ROOT, "templates/article.html"), "utf-8");
  const pnPath = join(ROOT, "config/proper-nouns.txt");
  const properNouns = existsSync(pnPath) ? readFileSync(pnPath, "utf-8") : "";
  const usersPath = join(ROOT, "config/users.json");
  const users = existsSync(usersPath) ? readFileSync(usersPath, "utf-8") : "[]";
  const sitePath = join(ROOT, "config/site.json");
  const site = existsSync(sitePath) ? readFileSync(sitePath, "utf-8") : '{"workerUrl":""}';
  return { manifest, manifestByArt, zoharIndex, template, properNouns, users, site };
}

function discoverArts() {
  return readdirSync(ZML).filter((f) => f.endsWith(".zml")).map((f) => f.slice(0, -4));
}

// Fields render.js actually reads from a manifest record.
function trimRec(r) {
  return {
    art: r.art, section: r.section, title: r.title,
    section_order: r.section_order, url: r.url, date_chosen: r.date_chosen,
  };
}

function emitEditorData(base, arts) {
  mkdirSync(DATA, { recursive: true });
  mkdirSync(join(DATA, "zml"), { recursive: true });
  // The in-page editor needs: cross-link/sibling data (manifest subset),
  // zohar index, zml sources, AND the page template (it renders the FULL page
  // via renderArticleHtml at Save, so it must have the same template as the build).
  const trimmed = base.manifest.filter((r) => r.art).map(trimRec);
  writeFileSync(join(DATA, "manifest.json"), JSON.stringify(trimmed), "utf-8");
  // Editable proper-noun list → editor copy (so in-page preview folds CAPS
  // identically to the build).
  writeFileSync(join(DATA, "proper-nouns.txt"), base.properNouns || "", "utf-8");
  writeFileSync(join(DATA, "zohar_index.json"), JSON.stringify(base.zoharIndex), "utf-8");
  // Page template — editor renders the full page at Save with the same template.
  writeFileSync(join(DATA, "template.html"), base.template, "utf-8");
  // User list for the "подписываюсь как…" selector + attribution.
  writeFileSync(join(DATA, "users.json"), base.users || "[]", "utf-8");
  // Site config (workerUrl): empty → editor uses interim PAT mode; set → Worker login.
  writeFileSync(join(DATA, "site.json"), base.site || '{"workerUrl":""}', "utf-8");
  for (const art of arts) copyFileSync(join(ZML, `${art}.zml`), join(DATA, "zml", `${art}.zml`));
}

function main(argv) {
  const arts = argv.length ? argv : discoverArts();
  const base = loadCtx();
  let ok = 0;
  for (const art of arts) {
    const rec = base.manifestByArt[art];
    if (!rec) { console.error(`  ! ${art}: not in manifest`); continue; }
    const zmlPath = join(ZML, `${art}.zml`);
    if (!existsSync(zmlPath)) { console.error(`  ! ${art}: no zml`); continue; }
    const zml = readFileSync(zmlPath, "utf-8");
    // Flat layout: every article at docs/art/<art>.html, independent of section
    // (section is metadata only → moving between sections never changes the URL).
    const outDir = join(SITE, "art");
    mkdirSync(outDir, { recursive: true });
    const html = renderArticleHtml({ zml, rec, ...base });
    writeFileSync(join(outDir, `${art}.html`), html, "utf-8"); // LF
    console.log(`  ✓ ${art} → docs/art/${art}.html`);
    ok++;
  }
  emitEditorData(base, arts.filter((a) => base.manifestByArt[a] && existsSync(join(ZML, `${a}.zml`))));
  console.log(`\nbuilt ${ok}/${arts.length} · editor data → docs/editor/data/`);
  // Non-zero exit if any requested art failed — the batch pipeline (run_batch.py)
  // checks rc to decide whether to push.
  if (ok < arts.length) process.exitCode = 1;
}

main(process.argv.slice(2));

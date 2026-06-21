// Build the «Песнь Ступеней» special page (ZML3 §6.8): docs/songs/index.zml →
// docs/songs/index.view.html via template_songs.html. NOT an art-id article →
// own template (no byline/prev-next/TOC), art-links get base "../art/".
// Live docs/songs/index.html is NOT touched (cutover at Ф9). Reuses render.js.
// Usage: node build_songs.mjs

import { readFileSync, writeFileSync, readdirSync, copyFileSync, mkdirSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { renderSongsHtml } from "./render.js";

const here = dirname(fileURLToPath(import.meta.url)); // editor/
const data = join(here, "data");
const root = dirname(here);                            // cms-revival
const docsSongs = join(root, "..", "docs", "songs");

// Sync themes (source→docs) — same contract as build_views.mjs (idempotent).
const themesSrc = join(root, "themes");
const themesDst = join(root, "..", "docs", "themes");
mkdirSync(themesDst, { recursive: true });
for (const f of readdirSync(themesSrc).filter((f) => f.endsWith(".css"))) {
  copyFileSync(join(themesSrc, f), join(themesDst, f));
}

const manifest = JSON.parse(readFileSync(join(root, "..", "manifest.json"), "utf8"));
const zoharIndex = JSON.parse(readFileSync(join(data, "zohar_index.json"), "utf8"));
const properNouns = readFileSync(join(data, "proper-nouns.txt"), "utf8");
const template = readFileSync(join(data, "template_songs.html"), "utf8");
const siteConfig = JSON.parse(readFileSync(join(data, "site.json"), "utf8")); // workerUrl → data-worker
// Ф8′: запекаем АНОН-вид по правилам display.json (раздел "songs"); как build_views.
let displayConfig = null;
try { displayConfig = JSON.parse(readFileSync(join(docsSongs, "..", "config", "display.json"), "utf8")); }
catch (e) { /* нет конфига → дефолты A_editorial/wide */ }
const manifestByArt = Object.fromEntries(manifest.map((r) => [r.art, r]));

// node build_songs.mjs [inZml] [outHtml] — по умолчанию index.zml → index.view.html.
const argIn = process.argv[2];
const argOut = process.argv[3];
const zmlPath = argIn ? join(process.cwd(), argIn) : join(docsSongs, "index.zml");
if (!existsSync(zmlPath)) {
  console.error("НЕТ", zmlPath, "— сначала: python convert/gen_songs_zml.py");
  process.exit(1);
}
const zml = readFileSync(zmlPath, "utf8");
// songs — спец-страница: синтетический rec (нет section/url → byline-полей нет).
// Рендер вынесен в render.js::renderSongsHtml — ОБЩИЙ код с браузерным docs/ya-songs.js.
const rec = { art: "songs", section: "", title: "Песнь Ступеней", url: "" };
const html = renderSongsHtml({
  zml, rec, manifest, manifestByArt, zoharIndex, properNouns,
  template, artHrefBase: "../art/", siteConfig, displayConfig, // docs/songs/ → docs/art/<id>.view.html
});

const out = argOut ? join(process.cwd(), argOut) : join(docsSongs, "index.view.html");
writeFileSync(out, html);
console.log("OK songs ->", out, html.length, "B");

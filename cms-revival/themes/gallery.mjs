// Ф2 gallery harness — render a .zml through a chosen theme CSS.
// Usage: node gallery.mjs <theme-stem> [zmlPath]
//   theme-stem -> themes/<stem>.css ; default zml = ../zml1/demo.zml
// Reuses the production renderer + template; only swaps the stylesheet href.
// Output: themes/gallery/<stem>__<zmlname>.html  (open / screenshot to review)

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, basename } from "node:path";
import { renderArticleHtml } from "../editor/render.js";

const here = dirname(fileURLToPath(import.meta.url)); // themes/
const root = dirname(here);                            // cms-revival
const data = join(root, "editor", "data");

const theme = process.argv[2];
if (!theme) { console.error("usage: node gallery.mjs <theme-stem> [zml]"); process.exit(1); }
const zmlPath = process.argv[3] || join(root, "zml1", "demo.zml");

const zml = readFileSync(zmlPath, "utf8");
// LIVE manifest (yaniktoim/manifest.json, 352) — NOT the stale editor/data copy
// (350; diverged ~30 each way) so internal [[art]] links resolve to real corpus.
const manifest = JSON.parse(readFileSync(join(root, "..", "manifest.json"), "utf8"));
const zoharIndex = JSON.parse(readFileSync(join(data, "zohar_index.json"), "utf8"));
const template = readFileSync(join(data, "template.html"), "utf8");
const properNouns = readFileSync(join(data, "proper-nouns.txt"), "utf8");
const manifestByArt = Object.fromEntries(manifest.map((r) => [r.art, r]));

const fmArt = (/(?:^|\n)art:\s*"?([^"\n]+)"?/.exec(zml.split("\n---")[0]) || [])[1];
const art = (fmArt || basename(zmlPath).replace(/\.zml$/, "")).trim();
const rec = manifestByArt[art] || { art, section: "other", title: "", url: "" };

let html = renderArticleHtml({ zml, rec, manifest, manifestByArt, zoharIndex, template, properNouns });
// swap the production stylesheet for this theme; drop favicon links that 404 here
html = html.replace(/<link rel="stylesheet" href="[^"]*">/, `<link rel="stylesheet" href="../${theme}.css">`);
html = html.replace(/<link rel="(icon|apple-touch-icon)"[^>]*>\n?/g, "");

const outdir = join(here, "gallery");
mkdirSync(outdir, { recursive: true });
const outname = `${theme}__${basename(zmlPath).replace(/\.zml$/, "")}.html`;
writeFileSync(join(outdir, outname), html);
console.log("wrote", `gallery/${outname}`, html.length, "B");

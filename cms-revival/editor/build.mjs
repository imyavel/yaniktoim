// Ф0 stand driver — runs the ZML1 renderer (render.js) in Node, locally.
// Usage: node build.mjs [path/to/article.zml]   (default: ../zml1/demo.zml)
// Writes next to the input: <name>.out.html (full page via template) and
// <name>.article.html (just the <article> inner — toc+body+notes) for diffing.
// SINGLE SOURCE OF TRUTH for rendering stays render.js; this only feeds it data.

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, basename } from "node:path";
import { renderArticleHtml, renderArticleParts } from "./render.js";

const here = dirname(fileURLToPath(import.meta.url));
const data = join(here, "data");
const root = dirname(here); // cms-revival

const zmlPath = process.argv[2] || join(root, "zml1", "demo.zml");
const zml = readFileSync(zmlPath, "utf8");

const manifest = JSON.parse(readFileSync(join(root, "..", "manifest.json"), "utf8"));
const zoharIndex = JSON.parse(readFileSync(join(data, "zohar_index.json"), "utf8"));
const template = readFileSync(join(data, "template.html"), "utf8");
const properNouns = readFileSync(join(data, "proper-nouns.txt"), "utf8");

const manifestByArt = Object.fromEntries(manifest.map((r) => [r.art, r]));

// art id from frontmatter; synthesize a minimal rec if absent (e.g. demo "65S").
const fmBlock = zml.split("\n---")[0];
const fmArt = (/(?:^|\n)art:\s*"?([^"\n]+)"?/.exec(fmBlock) || [])[1];
const art = (fmArt || basename(zmlPath).replace(/\.zml$/, "")).trim();
const rec = manifestByArt[art] || { art, section: "other", title: "", url: "" };

const ctx = { zml, rec, manifest, manifestByArt, zoharIndex, template, properNouns };

const full = renderArticleHtml(ctx);
const parts = renderArticleParts(ctx);
const articleInner =
  (parts.tocHtml ? parts.tocHtml + "\n\n" : "") + parts.articleInner;

const outBase = zmlPath.replace(/\.zml$/, "");
writeFileSync(outBase + ".out.html", full);
writeFileSync(outBase + ".article.html", articleInner);

console.log(
  `OK  art=${art}  full=${full.length}B  article=${articleInner.length}B  toc=${parts ? parts.tocHtml.length : 0}B`,
);

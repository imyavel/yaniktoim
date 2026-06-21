// Разовый тест CAPS:ON — рендерит docs/art/<id>.view.html с инжектом `caps: on`
// в frontmatter (не трогая канонический .zml). После осмотра восстановить вью:
//   node editor/build_views.mjs <id>
// Usage: node editor/caps_test.mjs <art-id>
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { renderArticleHtml } from "./render.js";

const here = dirname(fileURLToPath(import.meta.url));
const data = join(here, "data");
const root = dirname(here);
const docsArt = join(root, "..", "docs", "art");
const manifest = JSON.parse(readFileSync(join(root, "..", "manifest.json"), "utf8"));
const zoharIndex = JSON.parse(readFileSync(join(data, "zohar_index.json"), "utf8"));
const template = readFileSync(join(data, "template_view.html"), "utf8");
const properNouns = readFileSync(join(data, "proper-nouns.txt"), "utf8");
const manifestByArt = Object.fromEntries(manifest.map((r) => [r.art, r]));

const art = process.argv[2];
let zml = readFileSync(join(docsArt, `${art}.zml`), "utf8");
zml = zml.replace(/^---\r?\n/, (m) => m + "caps: on\n");  // .zml — CRLF
const rec = manifestByArt[art] || { art, section: "other", title: "", url: "" };
const html = renderArticleHtml({ zml, rec, manifest, manifestByArt, zoharIndex, template, properNouns });
writeFileSync(join(docsArt, `${art}.view.html`), html);
console.log("caps:on view written for", art, "(restore: node editor/build_views.mjs " + art + ")");

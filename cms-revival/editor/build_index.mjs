// Ф10: собрать главную (docs/index.html) и страницы разделов
// (docs/<slug>/index.html) из docs/config/structure.json (+ manifest для
// заголовков/дат). Тот же render.js, что и в браузерном редакторе структуры.
// Usage: node build_index.mjs [YYYY-MM-DD]   (дата сборки; по умолч. — сегодня)
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { renderIndexHtml, renderSectionIndexHtml } from "./render.js";

const here = dirname(fileURLToPath(import.meta.url));
const data = join(here, "data");
const yan = join(dirname(here), "..");
const docs = join(yan, "docs");

const structure = JSON.parse(readFileSync(join(docs, "config", "structure.json"), "utf8"));
const manifest = JSON.parse(readFileSync(join(yan, "manifest.json"), "utf8"));
const manifestByArt = Object.fromEntries(manifest.map((r) => [r.art, r]));
const tplIndex = readFileSync(join(data, "template_index.html"), "utf8");
const tplSection = readFileSync(join(data, "template_section.html"), "utf8");
const buildDate = process.argv[2] || new Date().toISOString().slice(0, 10);
// url-unification: forced_views/default_view упразднены — ссылки списков всегда NNN.html.

writeFileSync(join(docs, "index.html"),
  renderIndexHtml({ structure, manifestByArt, template: tplIndex, buildDate }));
console.log("OK index.html");

for (const s of structure.sections.filter((x) => !x.archived)) {
  const html = renderSectionIndexHtml({ slug: s.slug, structure, manifestByArt, template: tplSection, buildDate });
  mkdirSync(join(docs, s.slug), { recursive: true });
  writeFileSync(join(docs, s.slug, "index.html"), html);
  console.log("OK", s.slug + "/index.html");
}

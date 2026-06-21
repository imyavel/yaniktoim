// Тест-стенд ZML3: рендерит zml3test.zml в zml3test.<theme>.view.html для
// КАЖДОЙ из 5 тем (override frontmatter `theme:`). Файлы лежат здесь же:
// ../../themes/<theme>.css резолвится в ИСХОДНЫЕ темы cms-revival/themes —
// видно живые правки CSS без синка в docs/. Запуск: node build_test.mjs [тема...]
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { renderArticleHtml } from "../../editor/render.js";

const here = dirname(fileURLToPath(import.meta.url));     // zml3/teststand
const root = join(here, "..", "..");                       // cms-revival
const data = join(root, "editor", "data");

const THEMES = process.argv.slice(2).length
  ? process.argv.slice(2)
  : ["A_editorial", "B_manuscript", "cyberpunk", "swiss", "ar_deco"];

const manifest = JSON.parse(readFileSync(join(root, "..", "manifest.json"), "utf8"));
const zoharIndex = JSON.parse(readFileSync(join(data, "zohar_index.json"), "utf8"));
const properNouns = readFileSync(join(data, "proper-nouns.txt"), "utf8");
// шаблон вью, но CSS-путь ../themes/ → ../../themes/ (исходники тем)
const template = readFileSync(join(data, "template_view.html"), "utf8")
  .split("../themes/").join("../../themes/");
const manifestByArt = Object.fromEntries(manifest.map((r) => [r.art, r]));

const zmlSrc = readFileSync(join(here, "zml3test.zml"), "utf8");
const rec = { art: "zml3test", section: "best", title: "ZML3 тест", url: "https://example.org", date_chosen: "2026-06-11" };

for (const theme of THEMES) {
  const zml = zmlSrc.replace(/^theme:.*$/m, `theme: ${theme}`);
  const html = renderArticleHtml({ zml, rec, manifest, manifestByArt, zoharIndex, template, properNouns });
  const out = join(here, `zml3test.${theme}.view.html`);
  writeFileSync(out, html);
  console.log("OK", theme, "->", out);
}

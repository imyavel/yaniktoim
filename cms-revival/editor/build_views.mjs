// Build read-only ZML preview pages for the public site.
// Renders docs/art/<id>.zml -> docs/art/<id>.view.html via template_view.html
// (theme/width switcher, no editor). Reuses the production renderer (render.js).
// Usage: node build_views.mjs [<art-id> ...]   (default: all docs/art/*.zml)

import { readFileSync, writeFileSync, readdirSync, copyFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { renderArticleHtml } from "./render.js";

const here = dirname(fileURLToPath(import.meta.url)); // editor/
const data = join(here, "data");
const root = dirname(here);                            // cms-revival
const docsArt = join(root, "..", "docs", "art");

// ЕДИНСТВЕННЫЙ источник истины тем — cms-revival/themes/. docs/themes/ —
// ПРОИЗВОДНЫЙ артефакт: пересобирается здесь на каждый build (НЕ редактировать
// руками в docs!). Так стили не дрейфуют между двумя копиями.
const themesSrc = join(root, "themes");
const themesDst = join(root, "..", "docs", "themes");
mkdirSync(themesDst, { recursive: true });
const themeFiles = readdirSync(themesSrc).filter((f) => f.endsWith(".css"));
for (const f of themeFiles) copyFileSync(join(themesSrc, f), join(themesDst, f));
console.log("themes synced (source→docs):", themeFiles.join(", "));

// ── Ф8: отдать ZML-редактору движок + данные в docs/editor/ (публично, served) ──
// Браузерный редактор (docs/ya-edit.js) грузит ровно ЭТИ ЖЕ входы и зовёт тот же
// renderArticleHtml → Просмотр и сохраняемый .view.html байт-в-байт совпадают с
// этой сборкой (один код, один источник данных, без дрейфа). docs/editor/ —
// ПРОИЗВОДНЫЙ артефакт (как docs/themes/): не редактировать руками в docs.
const editorDst = join(root, "..", "docs", "editor");
const editorDataDst = join(editorDst, "data");
mkdirSync(editorDataDst, { recursive: true });
copyFileSync(join(here, "render.js"), join(editorDst, "render.js"));
copyFileSync(join(here, "verse_split.js"), join(editorDst, "verse_split.js")); // [faw]: счёт слогов
copyFileSync(join(here, "faw_markup.js"), join(editorDst, "faw_markup.js"));   // [faw]: авто-разметка на «Сохранить»
copyFileSync(join(root, "..", "manifest.json"), join(editorDataDst, "manifest.json"));
copyFileSync(join(here, "data", "zohar_index.json"), join(editorDataDst, "zohar_index.json"));
copyFileSync(join(here, "data", "proper-nouns.txt"), join(editorDataDst, "proper-nouns.txt"));
copyFileSync(join(here, "data", "template_view.html"), join(editorDataDst, "template_view.html"));
copyFileSync(join(here, "data", "template_songs.html"), join(editorDataDst, "template_songs.html")); // Ф8(c): браузерный ya-songs
// index/section шаблоны отдаём как .tpl — у них НЕТ data-pagefind-ignore (он бы
// протёк в генерируемые страницы), а Pagefind индексирует только *.html → .tpl
// безопасно. Браузерный редактор тянет их как текст (расширение неважно).
copyFileSync(join(here, "data", "template_index.html"), join(editorDataDst, "template_index.tpl"));
copyFileSync(join(here, "data", "template_section.html"), join(editorDataDst, "template_section.tpl"));
copyFileSync(join(here, "data", "site.json"), join(editorDataDst, "site.json"));
console.log("editor assets synced → docs/editor/ (render.js + data)");

const manifest = JSON.parse(readFileSync(join(root, "..", "manifest.json"), "utf8"));
const zoharIndex = JSON.parse(readFileSync(join(data, "zohar_index.json"), "utf8"));
const template = readFileSync(join(data, "template_view.html"), "utf8");
const properNouns = readFileSync(join(data, "proper-nouns.txt"), "utf8");
const manifestByArt = Object.fromEntries(manifest.map((r) => [r.art, r]));
// Ф8′: центральный конфиг вида (Admin/анон-дефолт) запекается в вью → ноль FOUC
// для анонимов; worker-URL — для клиентского ре-резолвинга у залогиненных.
const docsRoot = join(root, "..", "docs");
const displayConfig = JSON.parse(readFileSync(join(docsRoot, "config", "display.json"), "utf8"));
const siteConfig = JSON.parse(readFileSync(join(data, "site.json"), "utf8"));

// ── «old» (6-й дизайн): тело архивного старого html → ctx.legacyBody ──────────
// Вынимаем то, что покажем в Shadow DOM: все <style> из <head> + тело <body>.
// Селекторы :root/body/html в шадоу не матчатся (нет этих элементов и :root) →
// ремапим: :root→:host (CSS-переменные старого дизайна), body/html→.ya-old (обёртка
// тела). Инлайн-<script> оставляем — boot исполнит их scoped к shadow root (lazy-YT,
// сноски). <script src=ya-switch> (если затесался в тело) вырезаем — он не нужен.
const legacyDir = join(root, "legacy_html");
function extractLegacy(oldHtml) {
  const styles = [];
  oldHtml.replace(/<style\b[^>]*>([\s\S]*?)<\/style>/gi, (m, css) => { styles.push(css); return m; });
  const bm = /<body\b([^>]*)>([\s\S]*?)<\/body>/i.exec(oldHtml);
  if (!bm) return "";
  const bodyInner = bm[2].replace(/<script\b[^>]*\bya-switch[^>]*><\/script>\s*/gi, "");
  const remap = (css) => css
    .replace(/:root\b/g, ":host")
    .replace(/(^|[\s,{}>+~()])body\b/g, "$1.ya-old")
    .replace(/(^|[\s,{}>+~()])html\b/g, "$1.ya-old");
  const styleBlock = styles.map((c) => `<style>${remap(c)}</style>`).join("\n");
  const schemeM = /\bdata-scheme\s*=\s*("[^"]*"|'[^']*')/i.exec(bm[1]);
  const schemeAttr = schemeM ? ` data-scheme=${schemeM[1]}` : "";
  return `${styleBlock}\n<div class="ya-old"${schemeAttr}>${bodyInner}</div>`;
}

// Редирект-заглушка вместо прежнего .view.html: уже расшаренные …/NNN.view.html
// (Telegram/закладки) не ломаем — мгновенный refresh на NNN.html. noindex +
// data-pagefind-ignore, чтобы заглушки не конкурировали в выдаче/поиске. В sitemap
// их нет (он исключает *.view.html). Идемпотентна — перезаписывается на каждый build.
function redirectStub(target) {
  return '<!doctype html><html lang="ru"><head><meta charset="utf-8">\n' +
    '<meta name="robots" content="noindex"><link rel="canonical" href="' + target + '">\n' +
    '<meta http-equiv="refresh" content="0; url=' + target + '"></head>\n' +
    '<body data-pagefind-ignore="all"><a href="' + target + '">→ Перейти к статье</a></body></html>\n';
}

let ids = process.argv.slice(2);
if (!ids.length) {
  ids = readdirSync(docsArt)
    .filter((f) => f.endsWith(".zml"))
    .map((f) => f.replace(/\.zml$/, ""));
}

for (const art of ids) {
  try {
    const zml = readFileSync(join(docsArt, `${art}.zml`), "utf8");
    const rec = manifestByArt[art] || { art, section: "other", title: "", url: "" };
    let legacyBody = "";
    try { legacyBody = extractLegacy(readFileSync(join(legacyDir, `${art}.html`), "utf8")); }
    catch (e) { legacyBody = ""; } // нет архива (zml-only статья) → опция «old» скрыта
    const html = renderArticleHtml({ zml, rec, manifest, manifestByArt, zoharIndex, template, properNouns, displayConfig, siteConfig, legacyBody });
    // url-unification: единственный публичный адрес — NNN.html (перезаписывает бывший
    // старый html, он уже в архиве legacy_html). Прежний NNN.view.html → редирект-заглушка.
    writeFileSync(join(docsArt, `${art}.html`), html);
    writeFileSync(join(docsArt, `${art}.view.html`), redirectStub(`${art}.html`));
    console.log("OK", art, "->", `art/${art}.html`, html.length, "B");
  } catch (e) {
    console.log("ERR", art, e.message);
  }
}

// ── Ссылки статей в индексах разделов → единый NNN.html ───────────────────────
// forced_views.json и default_view упразднены (url-unification): один адрес статьи,
// вид (5 тем + «old») резолвится в рантайме. Регэксп схлопывает и старые .view-хвосты.
const targetFor = (art) => `../art/${art}.html`;
const sections = [...new Set(manifest.map((r) => r.section).filter(Boolean))];
let touched = 0;
for (const sec of sections) {
  const idxPath = join(docsRoot, sec, "index.html");
  let html;
  try { html = readFileSync(idxPath, "utf8"); } catch (e) { continue; }
  const out = html.replace(/href="\.\.\/art\/([A-Za-z0-9_]+)(?:\.view)?\.html"/g,
    (m, art) => `href="${targetFor(art)}"`);
  if (out !== html) { writeFileSync(idxPath, out); touched++; }
}
console.log("section indexes переписаны:", touched, "из", sections.length);

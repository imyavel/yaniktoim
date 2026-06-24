// Рендер списка Зоар-тегов в текст анкора + href (для отчёта-«было→стало»).
// stdin: JSON-массив строк-тегов (или строк, содержащих теги — резолвим как есть).
// stdout: JSON { "<input>": {"text": "...", "href": "...", "broken": bool} }
import { resolveInline } from "../cms-revival/editor/render.js";
import fs from "node:fs";

const zi = JSON.parse(fs.readFileSync(
  new URL("../cms-revival/editor/data/zohar_index.json", import.meta.url), "utf8"));
const inline = { zoharIndex: zi };

let buf = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (d) => (buf += d));
process.stdin.on("end", () => {
  const items = JSON.parse(buf);
  const out = {};
  for (const s of items) {
    const html = resolveInline(s, inline);
    const broken = /class="broken"/.test(html);
    const href = (html.match(/href="([^"]*)"/) || [])[1] || "";
    // собрать видимый текст всех анкоров в строке
    const text = html.replace(/<a[^>]*>/g, "").replace(/<\/a>/g, "");
    out[s] = { text, href, broken };
  }
  process.stdout.write(JSON.stringify(out, null, 1));
});

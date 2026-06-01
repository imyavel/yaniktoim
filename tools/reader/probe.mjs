import { readFileSync } from 'fs';
import { parseHTML } from 'linkedom';
import { Readability } from '@mozilla/readability';
const path = process.argv[2];
const html = readFileSync(path, 'utf-8');
const { document } = parseHTML(html);
const reader = new Readability(document, { charThreshold: 50 });
const art = reader.parse();
const text = (art?.textContent || '').replace(/\s+/g,' ').trim();
console.log("TITLE:", art?.title);
console.log("LEN:", text.length);
console.log("FIRST 400:", text.slice(0,400));
console.log("---- markers present? ----");
for (const m of ['ПРЕДВАРЯЮЩАЯ','СТИХ ПЕРВЫЙ','СТИХ ВТОРОЙ','СТИХ ТРЕТИЙ','ЭКРАН','НАСТРОЙКА','ЗАМЫКАЯ']) {
  console.log(`  ${m}: ${text.includes(m) ? 'YES' : 'NO — DROPPED'}`);
}

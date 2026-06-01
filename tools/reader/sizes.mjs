import { readFileSync } from 'fs';
import { parseHTML } from 'linkedom';
const { document } = parseHTML(readFileSync(process.argv[2],'utf-8'));
const main = document.querySelector('main') || document.body;
for (const sec of document.querySelectorAll('section, header, div.epis, nav.toc')) {
  const t = (sec.textContent||'').replace(/\s+/g,' ').trim();
  const ps = sec.querySelectorAll('p').length;
  console.log(`${(sec.id||sec.className||sec.tagName).padEnd(14)} len=${String(t.length).padStart(5)}  <p>=${ps}  :: ${t.slice(0,40)}`);
}

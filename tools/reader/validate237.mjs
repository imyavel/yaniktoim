import { readFileSync } from 'fs';
import { parseHTML } from 'linkedom';
const { document } = parseHTML(readFileSync('../../docs/art/237.html','utf-8'));
const art = document.querySelector('article');
console.log('article children:', [...art.children].map(c=>c.tagName.toLowerCase()+(c.id?'#'+c.id:'')+(c.className?'.'+String(c.className).split(' ')[0]:'')).join(', '));
console.log('h1 in article:', !!art.querySelector('h1'), '| h2 count:', art.querySelectorAll('h2').length);
// TOC anchors resolve?
let ok=true;
for (const a of document.querySelectorAll('nav.toc a[href^="#"]')) {
  const id=a.getAttribute('href').slice(1);
  if(!document.getElementById(id)){ ok=false; console.log('  BROKEN anchor #'+id);}
}
console.log('TOC anchors resolve:', ok);
// readability still gets everything
const { Readability } = await import('@mozilla/readability');
const r=new Readability(document,{charThreshold:50}).parse();
const t=(r.textContent||'').replace(/\s+/g,' ');
console.log('Readability sees prayer/verse1/verse2:', t.includes('ПРЕДВАРЯЮЩАЯ'),t.includes('СТИХ ПЕРВЫЙ'),t.includes('СТИХ ВТОРОЙ'));

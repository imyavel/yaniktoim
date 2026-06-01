import { readFileSync } from 'fs';
import { parseHTML } from 'linkedom';
const { document } = parseHTML(readFileSync(process.argv[2],'utf-8'));
for (const id of ['prayer','verse1','verse2','notes']) {
  let el = document.getElementById(id);
  if (!el) { console.log(id,'= MISSING'); continue; }
  let chain=[];
  for (let p=el; p && p.tagName; p=p.parentElement) chain.push(p.tagName.toLowerCase()+(p.id?'#'+p.id:'')+(p.className?'.'+String(p.className).split(' ')[0]:''));
  console.log(id,'->', chain.join(' < '));
}
// also: list direct children tagNames of the main content container
const wrap = document.getElementById('top') || document.body;
console.log('\nwrap children:', [...wrap.children].map(c=>c.tagName.toLowerCase()+(c.id?'#'+c.id:'')+(c.className?'.'+String(c.className).split(' ')[0]:'')).join(', '));

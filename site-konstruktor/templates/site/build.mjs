import { readFileSync, writeFileSync } from 'node:fs';
const [src, out] = process.argv.slice(2);
let n = 0;
const html = readFileSync(src, 'utf8').replace(/\[\[([\s\S]+?)\|\|([\s\S]+?)\]\](?!\])/g, (_, ru, en) => { n++; return `<span class="ru">${ru}</span><span class="en" lang="en">${en}</span>`; });
if (/\[\[|\]\]/.test(html.replace(/<script[\s\S]*?<\/script>/g, ''))) console.warn('leftover brackets');
writeFileSync(out, html); console.log('pairs:', n);

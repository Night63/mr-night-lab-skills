"""Страница документа из docs/*.txt по шаблону готовой страницы сайта (берутся шапка и подвал).
Запуск: python3 doc.py docs/offer.txt index.html offer.html "Licence agreement" "{{PRODUCT}}" "{{DOMAIN}}"
Разметка txt: "# " заголовок, "@" строка-подзаголовок, "## " раздел, "— " пункт списка, "1.2. " номер пункта."""
import sys, re, html
src, tpl, out, title_en, BRAND, DOMAIN = sys.argv[1:7]
t = open(tpl).read()
head = t[:t.index('<main')].replace('href="#', 'href="index.html#')
foot = t[t.index('<footer'):].replace('href="#', 'href="index.html#')
if 'data-title-ru' not in head: head = head.replace('<html lang="ru">', '<html lang="ru" data-title-ru="" data-title-en="">')
head = head.replace('<body>', '<body class="page-doc">')
lines = open(src).read().split('\n')
body = []; title = ''; ul = False
def link(s):
    s = html.escape(s, quote=False)
    s = re.sub(r'(https://[^\s)«»,;]+[^\s)«»,;.])', r'<a href="\1">\1</a>', s)
    s = re.sub(r'([\w.+-]+@[\w.-]+\.[a-z]{2,})', r'<a href="mailto:\1">\1</a>', s)
    return s
for l in lines:
    l = l.rstrip()
    if not l.startswith('— ') and ul: body.append('</ul>'); ul = False
    if not l: continue
    if l.startswith('# '): title = l[2:]; body.append(f'<h1 class="doc__title">{html.escape(title)}</h1>')
    elif l.startswith('@'): body.append(f'<p class="doc__meta">{link(l[1:])}</p>')
    elif l.startswith('## '): body.append(f'<h2>{html.escape(l[3:])}</h2>')
    elif l.startswith('— '):
        if not ul: body.append('<ul>'); ul = True
        body.append(f'<li>{link(l[2:])}</li>')
    else:
        m = re.match(r'^(\d+\.\d+\.)\s', l)
        body.append(f'<p><b class="num">{m.group(1)}</b> {link(l[len(m.group(0)):])}</p>' if m else f'<p>{link(l)}</p>')
if ul: body.append('</ul>')
tt = title.capitalize() if title.isupper() else title
head = re.sub(r'<title>.*?</title>', f'<title>{tt} — {BRAND}</title>', head)
head = re.sub(r'data-title-ru="[^"]*" data-title-en="[^"]*"', f'data-title-ru="{tt} — {BRAND}" data-title-en="{title_en} — {BRAND}"', head)
head = re.sub(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{tt} — {BRAND}, {DOMAIN}">', head)
head = head.replace('class="page-news"', 'class="page-doc"')
main = f'''<main id="top" class="doc">
  <div class="box doc__in">
    <p class="doc__en" lang="en"><span class="en">This document is available in Russian only for now. An English version will follow.</span></p>
    <article lang="ru">
{chr(10).join("      "+b for b in body)}
    </article>
    <p class="doc__back"><a href="index.html">← <span class="ru">На главную</span><span class="en" lang="en">Home</span></a></p>
  </div>
</main>

'''
open(out, 'w').write(head + main + foot)
print('ok', len(body))

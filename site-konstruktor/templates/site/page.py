"""Служебная страница (thanks/fail) из фрагмента <main> и шапки/подвала готовой страницы. noindex.
Запуск: python3 page.py index.html t.html thanks.html "Спасибо за покупку" "Thank you" "{{PRODUCT}}" """
import sys, re
tpl, mainf, out, title_ru, title_en, BRAND = sys.argv[1:7]
t = open(tpl).read()
head = t[:t.index('<main')].replace('href="#', 'href="index.html#')
foot = t[t.index('<footer'):].replace('href="#', 'href="index.html#')
head = re.sub(r'<title>.*?</title>', f'<title>{title_ru} — {BRAND}</title>', head)
head = head.replace('<html lang="ru">', f'<html lang="ru" data-title-ru="{title_ru} — {BRAND}" data-title-en="{title_en} — {BRAND}">')
head = head.replace('<body>', '<body class="page-doc">')
head = head.replace('<meta name="description"', '<meta name="robots" content="noindex">\n<meta name="referrer" content="no-referrer">\n<meta name="description"')
m = open(mainf).read()
if 'data-api=' in m: foot = foot.replace('<script src="assets/site.js"></script>', '<script src="assets/site.js"></script>\n<script src="assets/pay.js"></script>')
open(out, 'w').write(head + m + '\n' + foot)
print('ok')

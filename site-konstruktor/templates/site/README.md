# Сайт (шаблон)

Статический сайт в бакете Object Storage. Стили и вёрстку делает дизайн-скилл под проект; здесь — механика.

- `build.mjs` — `node build.mjs src/index.src.html index.html`: пары `[[русский||English]]` → `span.ru` / `span.en`. Переключатель языка и запоминание выбора (localStorage, не cookie) — в своём `site.js`: класс на `<html>` и `lang`.
- `doc.py` — `python3 doc.py docs/offer.txt index.html offer.html "Licence agreement" "Бренд" "домен"`: страница документа с шапкой и подвалом главной.
- `page.py` — служебные страницы `thanks.html` / `fail.html` (noindex, no-referrer).
- `buy-form.html` + `assets/buy.js` — форма покупки. `data-pay="on"` — только через `scripts/_claude_pay.cmd`.
- `thanks.main.html` + `assets/pay.js` — страница «Спасибо»: опрос `/order`, показ товара, очистка адресной строки.
- `docs/offer.txt`, `privacy.txt`, `consent.txt` — тексты документов с плейсхолдерами.

Шрифты — файлами на сайте, не Google Fonts. Видео — VK Видео или Rutube. Счётчиков и cookies нет, пока нет плашки с реальным выбором.

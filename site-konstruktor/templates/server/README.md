# Сервер продажи (шаблон)

Python 3.12, Yandex Cloud Functions, YDB serverless, API Gateway, Postbox, Object Storage для копий. Без Telegram (связь с ним из Yandex Cloud нестабильна, и это трансграничная передача ПД).

## Файлы
- `index.py` — точка входа `index.handler`, маршруты и таймер.
- `service.py` — заказ, Result, выдача, возврат, чистка. Здесь весь обязательный список безопасности.
- `robokassa.py` — подписи SHA256, `Receipt`.
- `delivery.py` — **что выдаём**. Заменить под свой товар.
- `mailer.py` — Postbox (SES v2 JSON + SigV4), письмо покупателю и уведомления владельцу.
- `storage.py` — схема, YDB и память для тестов.
- `backup.py`, `s3.py`, `tools/decrypt_backup.py` — шифрованные копии.
- `tests/test_shop.py` — `python3 -I tests/test_shop.py`.

## Развёртывание (кратко; подробно — references/02, 03, 04, 09)
1. Сервисный аккаунт функции: `ydb.editor` на каталог (или на базу). Для таймера — `functions.functionInvoker`.
2. YDB serverless → `YDB_DATABASE` (путь вида `/ru-central1/b1…/etn…`).
3. Функция: Python 3.12, точка входа `index.handler`, таймаут 60 с, память 256 МБ, zip с этими файлами (без `tests/`).
4. Переменные: из `config.py`. Секреты вводит владелец. **Каждый раз при правке переменных прикреплять zip заново** — иначе версия создастся без кода.
5. `?r=setup&k=ADMIN_KEY` на прямом URL функции → «Таблицы: OK», «Не заданы переменные: нет».
6. API Gateway со спецификацией: `/buy` (POST), `/order` (GET), `/rk/result` (POST), `OPTIONS` → функция; домен `api.<домен>` с сертификатом.
7. Таймер и бакет копий — `scripts/_claude_infra.cmd`.
8. Тестовая оплата (RK_TEST=1), затем боевой порядок из references/12.

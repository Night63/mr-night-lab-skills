# Почта: Yandex Cloud Postbox

## Настройка домена
1. **[C/П]** Postbox → «Адреса» → добавить домен (адрес вида `noreply@домен`). DKIM «Простая» → 2 CNAME → создать в Cloud DNS.
2. **SPF** (TXT на корне, в кавычках): `"v=spf1 include:spf.postbox.yandexcloud.net ~all"` — по документации Postbox (`_spf.yandex.ru` — это для Яндекс 360, не путать). Если почта поддержки на Яндекс 360 — оба include в одной записи.
3. **DMARC** (TXT `_dmarc`): `"v=DMARC1; p=quarantine; adkim=r; aspf=r"`.
4. Ужесточение: через ~2 недели без проблем SPF `~all` → `-all`; через ~месяц DMARC `p=quarantine` → `p=reject`. Поставить напоминания.

## Ключ отправки
**[П]** Сервисный аккаунт с ролью `postbox.sender` → статический ключ → `POSTBOX_KEY_ID` / `POSTBOX_SECRET` в функцию и в менеджер паролей (секрет показывается один раз).

## API
- **SES v2 JSON:** `POST https://postbox.cloud.yandex.net/v2/email/outbound-emails`, подпись SigV4, сервис `ses`, регион `ru-central1`. Старый Query API v1 (`Action=SendEmail`) не работает — в опыте давал «письмо: error».
- Подпись сверять с botocore в автотесте (`templates/server/tests`).
- Пока ключей нет — «сухой прогон» (письмо пишется в журнал).
- Тестовая отправка в консоли: в поле «Отправитель» — только имя (`noreply`), домен подставляется справа.

## Почта поддержки
Отдельный ящик (Яндекс 360 / Яндекс Почта) с 2FA. Её адрес — в документах, письмах и Reply-To.

## Признак готовности
Тестовое письмо пришло во «Входящие» (не в спам) на Яндекс и Gmail; в заголовках `dkim=pass`, `spf=pass`, `dmarc=pass`.

"""Настройки — из переменных окружения функции Yandex Cloud.
Секреты (пароли платёжки, ключи Postbox и бакета копий, ADMIN_KEY, BACKUP_PASSWORD) задаются ТОЛЬКО там
и хранятся в менеджере паролей владельца. В код и в репозиторий их не класть."""
import os


def env(name, default=""):
    return (os.environ.get(name) or default).strip()


def flag(name, default="0"):
    return env(name, default).lower() in ("1", "true", "yes", "on")


# --- Служебное ---
ADMIN_KEY = env("ADMIN_KEY")                  # длинный случайный пароль для ?r=setup / backup / cleanup / resend / refund

# --- Товар ---
PRODUCT_NAME = env("PRODUCT_NAME", "{{PRODUCT}}")
PRODUCT_TITLE = env("PRODUCT_TITLE", "{{Название товара для страницы оплаты}}")
RECEIPT_ITEM = env("RECEIPT_ITEM", "{{Наименование в чеке, например: Лицензия на программу X (бессрочная)}}")
PRICE = int(env("PRICE", "990"))
ORDER_PREFIX = env("ORDER_PREFIX", "OR")       # номер заказа: префикс + 12 цифр
SALES_OPEN = flag("SALES_OPEN", "1")          # 0 — приём заказов выключен (503)
OFFER_VERSION = env("OFFER_VERSION", "{{ГГГГ-ММ-ДД}}")   # редакция оферты, пишется в заказ

# --- Робокасса ---
RK_LOGIN = env("RK_LOGIN")
RK_PASS1 = env("RK_PASS1")                    # боевой пароль №1 (подпись ссылки)
RK_PASS2 = env("RK_PASS2")                    # боевой пароль №2 (проверка уведомления)
RK_TEST_PASS1 = env("RK_TEST_PASS1")
RK_TEST_PASS2 = env("RK_TEST_PASS2")
RK_TEST = flag("RK_TEST", "1")                # 1 — тест (IsTest=1, тестовые пароли). Боевой режим — только явным 0
RK_URL = env("RK_URL", "https://auth.robokassa.ru/Merchant/Index.aspx")
RK_RECEIPT = flag("RK_RECEIPT", "1")          # 1 — передавать Receipt. Без него Робочек самозанятого НЕ формируется

# --- Почта (Yandex Cloud Postbox, API SES v2) ---
POSTBOX_KEY_ID = env("POSTBOX_KEY_ID")
POSTBOX_SECRET = env("POSTBOX_SECRET")
POSTBOX_ENDPOINT = env("POSTBOX_ENDPOINT", "https://postbox.cloud.yandex.net")
POSTBOX_REGION = env("POSTBOX_REGION", "ru-central1")
MAIL_FROM = env("MAIL_FROM", "{{PRODUCT}} <noreply@{{DOMAIN}}>")
MAIL_REPLY_TO = env("MAIL_REPLY_TO", "{{SUPPORT_EMAIL}}")
ADMIN_EMAIL = env("ADMIN_EMAIL")              # куда слать уведомления владельцу (без ПД покупателей)
SELLER_LINE = env("SELLER_LINE", "{{Продавец: самозанятый Фамилия И. О., ИНН ...}}")

# --- Адреса ---
SITE_URL = env("SITE_URL", "https://{{DOMAIN}}")
ALLOWED_ORIGIN = env("ALLOWED_ORIGIN", "https://{{DOMAIN}}")
DOWNLOAD_URL = env("DOWNLOAD_URL", "")        # ссылка на файл/программу для письма (если есть)

# --- База YDB ---
YDB_ENDPOINT = env("YDB_ENDPOINT", "grpcs://ydb.serverless.yandexcloud.net:2135")
YDB_DATABASE = env("YDB_DATABASE")

# --- Лимиты ---
RATE_IP_PER_HOUR = int(env("RATE_IP_PER_HOUR", "5"))
RATE_EMAIL_PER_DAY = int(env("RATE_EMAIL_PER_DAY", "5"))

# --- Резервное копирование ---
BACKUP_BUCKET = env("BACKUP_BUCKET")
BACKUP_KEY_ID = env("BACKUP_KEY_ID")
BACKUP_SECRET = env("BACKUP_SECRET")
BACKUP_PASSWORD = env("BACKUP_PASSWORD")
BACKUP_ENDPOINT = env("BACKUP_ENDPOINT", "https://storage.yandexcloud.net")
BACKUP_REGION = env("BACKUP_REGION", "ru-central1")

# --- Сроки хранения ПД (должны совпадать с Политикой) ---
KEEP_UNPAID_DAYS = int(env("KEEP_UNPAID_DAYS", "365"))
KEEP_PAID_DAYS = int(env("KEEP_PAID_DAYS", str(5 * 365)))


def rk_pass1():
    return RK_TEST_PASS1 if RK_TEST else RK_PASS1


def rk_pass2(is_test):
    """Вызывать только после проверки, что IsTest уведомления == RK_TEST == режим заказа (service.rk_result)."""
    return RK_TEST_PASS2 if is_test else RK_PASS2

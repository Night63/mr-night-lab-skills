"""Выдача товара после оплаты. Заменить под свой товар.

По умолчанию — случайный ключ XXXX-XXXX-XXXX-XXXX (80 бит, алфавит без I, O, 0, 1).
Варианты:
- ключ к программе с проверкой на сервере (см. references/09-backend.md: лицензия-сертификат RSA, отпечаток ПК);
- подписанная временная ссылка на файл в закрытом бакете;
- доступ к закрытому разделу/курсу.
Функция должна быть детерминированно-безопасной: вызывается ровно один раз на заказ (идемпотентность — в service).
"""
import os

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # 32 символа, 5 бит на символ


def new_key(groups=4, size=4):
    raw = os.urandom(groups * size)
    chars = [ALPHABET[b % 32] for b in raw]
    return "-".join("".join(chars[i * size:(i + 1) * size]) for i in range(groups))


def issue(order):
    """Возвращает (goods_value, goods_text_for_letter_ru, goods_text_for_letter_en)."""
    key = new_key()
    return key, "Ваш ключ: %s" % key, "Your key: %s" % key

"""Робокасса: ссылка оплаты и проверка уведомления Result. Алгоритм подписи — SHA256 (hex).

Ссылка:  sha256("MerchantLogin:OutSum:InvId[:Receipt]:Password1:Shp_token=<token>")
Result:  sha256("OutSum:InvId:Password2:Shp_token=<token>") == SignatureValue (без учёта регистра)

Shp-параметры — в конце, по алфавиту. Receipt входит в подпись в URL-кодированном виде,
а в ссылке кодируется ещё раз (urlencode). Без Receipt Робочек самозанятого не формируется.
Перед использованием сверить формат с актуальной документацией Робокассы.
"""
import hashlib
import hmac
import json
import urllib.parse

import config


def _sha256_hex(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def fmt_sum(amount):
    return "%.2f" % float(amount)


def receipt_encoded():
    receipt = {"items": [{
        "name": config.RECEIPT_ITEM[:128],
        "quantity": 1,
        "sum": config.PRICE,
        "tax": "none",                     # НПД — без НДС
        "payment_method": "full_payment",
        "payment_object": "service",       # для лицензии/цифрового товара; сверить с бухгалтерской логикой
    }]}
    raw = json.dumps(receipt, ensure_ascii=True, separators=(",", ":"))
    return urllib.parse.quote(raw, safe="")


def build_pay_link(inv_id, out_sum, token, email, lang):
    """(url, signature). Пароль №1 — боевой или тестовый по config.RK_TEST."""
    out_sum = fmt_sum(out_sum)
    parts = [config.RK_LOGIN, out_sum, str(inv_id)]
    params = {
        "MerchantLogin": config.RK_LOGIN, "OutSum": out_sum, "InvId": str(inv_id),
        "Description": config.PRODUCT_TITLE[:100], "Email": email,
        "Culture": "en" if lang == "en" else "ru", "Encoding": "utf-8", "Shp_token": token,
    }
    if config.RK_RECEIPT:
        enc = receipt_encoded()
        parts.append(enc)
        params["Receipt"] = enc
    parts += [config.rk_pass1() or "", "Shp_token=%s" % token]
    sig = _sha256_hex(":".join(parts))
    params["SignatureValue"] = sig
    if config.RK_TEST:
        params["IsTest"] = "1"
    return config.RK_URL + "?" + urllib.parse.urlencode(params, safe=""), sig


def verify_result(out_sum, inv_id, token, signature_value, is_test):
    password = config.rk_pass2(is_test)
    if not signature_value or not password:
        return False
    expected = _sha256_hex(":".join([str(out_sum), str(inv_id), password, "Shp_token=%s" % token]))
    return hmac.compare_digest(expected.lower(), signature_value.strip().lower())

"""Письма через Yandex Cloud Postbox: API SES v2 (JSON, POST /v2/email/outbound-emails), подпись AWS SigV4,
сервис 'ses', регион ru-central1. Старый Query API v1 (Action=SendEmail) Postbox не принимает.

Без POSTBOX_KEY_ID/SECRET — «сухой прогон»: письмо пишется в журнал, возвращается 'dryrun'.
Ошибка письма не должна ломать ответ платёжке: вызывающий код смотрит на статус и не падает.
"""
import datetime
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

import config

log = logging.getLogger("shop")
SERVICE = "ses"
PATH = "/v2/email/outbound-emails"


def _sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret, datestamp, region):
    k = _sign(("AWS4" + secret).encode("utf-8"), datestamp)
    k = _sign(k, region)
    k = _sign(k, SERVICE)
    return _sign(k, "aws4_request")


def build_request(body, now=None):
    """(url, headers) для POST в Postbox. Вынесено отдельно, чтобы сверить подпись с botocore в тестах."""
    parsed = urllib.parse.urlparse(config.POSTBOX_ENDPOINT)
    host = parsed.netloc
    now = now or datetime.datetime.now(datetime.timezone.utc)
    amzdate, datestamp = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    canonical_headers = "content-type:application/json\nhost:%s\nx-amz-date:%s\n" % (host, amzdate)
    signed = "content-type;host;x-amz-date"
    creq = "POST\n%s\n\n%s\n%s\n%s" % (PATH, canonical_headers, signed, payload_hash)
    scope = "%s/%s/%s/aws4_request" % (datestamp, config.POSTBOX_REGION, SERVICE)
    sts = "AWS4-HMAC-SHA256\n%s\n%s\n%s" % (amzdate, scope, hashlib.sha256(creq.encode("utf-8")).hexdigest())
    sig = hmac.new(signing_key(config.POSTBOX_SECRET, datestamp, config.POSTBOX_REGION),
                   sts.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Amz-Date": amzdate, "Host": host,
               "Authorization": "AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s"
                                % (config.POSTBOX_KEY_ID, scope, signed, sig)}
    return "%s://%s%s" % (parsed.scheme or "https", host, PATH), headers


def send(to, subject, text):
    """'sent' | 'dryrun' | 'error'. Простой текст + тот же текст в HTML без картинок."""
    if not (config.POSTBOX_KEY_ID and config.POSTBOX_SECRET):
        log.info("MAIL dryrun: «%s» не отправлено (нет ключей Postbox)", subject)
        return "dryrun"
    html = "<html><body><pre style=\"font:14px/1.5 Arial,sans-serif\">%s</pre></body></html>" % (
        text.replace("&", "&amp;").replace("<", "&lt;"))
    payload = {"FromEmailAddress": config.MAIL_FROM, "Destination": {"ToAddresses": [to]},
               "ReplyToAddresses": [config.MAIL_REPLY_TO] if config.MAIL_REPLY_TO else [],
               "Content": {"Simple": {"Subject": {"Data": subject, "Charset": "UTF-8"},
                                      "Body": {"Text": {"Data": text, "Charset": "UTF-8"},
                                               "Html": {"Data": html, "Charset": "UTF-8"}}}}}
    body = json.dumps(payload, ensure_ascii=False)
    url, headers = build_request(body)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body.encode("utf-8"), method="POST",
                                                           headers=headers), timeout=12) as r:
            r.read()
            return "sent"
    except urllib.error.HTTPError as ex:
        try:
            detail = ex.read().decode("utf-8", "replace")[:300]
        except Exception:
            detail = ""
        log.warning("MAIL error: HTTP %s %s", ex.code, detail)
    except Exception as ex:
        log.warning("MAIL error: %s: %s", type(ex).__name__, ex)
    return "error"


def goods_letter(order_id, goods, when, lang):
    """(subject, text) письма покупателю. Тексты — под свой товар."""
    if lang == "en":
        return ("Your %s purchase" % config.PRODUCT_NAME,
                "Thank you for your purchase! Order %s dated %s.\n\n%s\n\nSupport: %s\n%s"
                % (order_id, when, goods, config.MAIL_REPLY_TO, config.SELLER_LINE))
    return ("Ваша покупка %s" % config.PRODUCT_NAME,
            "Спасибо за покупку! Заказ %s от %s.\n\n%s\n\nПоддержка: %s\n%s"
            % (order_id, when, goods, config.MAIL_REPLY_TO, config.SELLER_LINE))


def notify_admin(text):
    """Уведомление владельцу. Без персональных данных покупателей (почта — только маской)."""
    if config.ADMIN_EMAIL:
        return send(config.ADMIN_EMAIL, "[%s] %s" % (config.PRODUCT_NAME, text.split("\n")[0][:80]), text)
    log.info("ADMIN: %s", text)
    return "log"

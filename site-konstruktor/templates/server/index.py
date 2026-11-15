"""Точка входа Cloud Function: index.handler (Python 3.12, таймаут 60 с).

Сайт — через API Gateway (api.<домен>), по пути:
  POST /buy        — создать заказ, вернуть ссылку оплаты
  GET  /order      — статус заказа для страницы «Спасибо» (Cache-Control: no-store)
  POST /rk/result  — уведомление Робокассы (Result URL)
Служебное — на прямом URL функции, ?r=...&k=ADMIN_KEY:
  setup   — создать таблицы, показать незаданные переменные и состояние копий
  backup  — копия базы сейчас;  backups — список копий
  restore — ?r=restore&obj=<объект>&yes=1 — восстановление (перед ним страховочная копия)
  cleanup — чистка ПД вручную
  resend  — ?r=resend&o=<номер заказа>;  refund — ?r=refund&o=<номер заказа>
Таймер (раз в сутки): чистка ПД, затем копия базы. payload «cleanup» или «backup» — только это действие.
"""
import base64
import hmac
import json
import logging
import urllib.parse

import backup as backupmod
import config
from service import Service

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("shop")
_svc = None


def get_service(store=None):
    global _svc
    if store is not None:
        _svc = Service(store)
    if _svc is None:
        from storage import YdbStorage
        _svc = Service(YdbStorage(config.YDB_ENDPOINT, config.YDB_DATABASE))
    return _svc


def resp(code, body, headers=None):
    ctype = "text/plain; charset=utf-8"
    if not isinstance(body, str):
        body, ctype = json.dumps(body, ensure_ascii=False), "application/json; charset=utf-8"
    h = {"Content-Type": ctype}
    h.update(headers or {})
    return {"statusCode": code, "headers": h, "body": body}


def _cors():
    return {"Access-Control-Allow-Origin": config.ALLOWED_ORIGIN, "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "86400"}


def _client_ip(event, headers):
    """IP — от API Gateway (sourceIp). X-Forwarded-For может подделать сам клиент."""
    ip = ((event.get("requestContext") or {}).get("identity") or {}).get("sourceIp") or ""
    if ip:
        return ip
    xff = headers.get("x-forwarded-for", "")
    return xff.split(",")[-1].strip() if xff else ""


def _admin_ok(q):
    return bool(config.ADMIN_KEY) and hmac.compare_digest(q.get("k", ""), config.ADMIN_KEY)


def timer(event):
    try:
        payload = str(((event.get("messages") or [{}])[0].get("details") or {}).get("payload") or "").strip().lower()
    except Exception:
        payload = ""
    svc, out, code = get_service(), [], 200
    if payload in ("", "cleanup"):
        try:
            out.append(svc.cleanup())
        except Exception:
            log.exception("cleanup")
            out.append("cleanup: ошибка")
            code = 500
    if payload in ("", "backup"):
        rep = svc.backup.run("daily")
        out.append(rep)
        code = 500 if rep.startswith("⚠️") else code
    return {"statusCode": code, "body": "\n".join(out)}


def handler(event, context):
    if isinstance(event, dict) and event.get("messages") and not event.get("httpMethod"):
        return timer(event)
    q = event.get("queryStringParameters") or {}
    headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
    method = (event.get("httpMethod") or "").upper()
    path = (event.get("path") or "").rstrip("/")
    body = event.get("body") or ""
    if event.get("isBase64Encoded") and body:
        body = base64.b64decode(body).decode("utf-8")
    try:
        if method == "OPTIONS":
            return {"statusCode": 204, "headers": _cors(), "body": ""}
        if path.endswith("/buy"):
            try:
                data = json.loads(body or "{}")
            except ValueError:
                return resp(400, {"error": "bad_request"}, _cors())
            code, out = get_service().buy(data, _client_ip(event, headers))
            return resp(code, out, _cors())
        if path.endswith("/order"):
            code, out = get_service().order_status(q.get("inv"), q.get("t"))
            h = _cors()
            h["Cache-Control"] = "no-store"
            return resp(code, out, h)
        if path.endswith("/rk/result"):
            form = {k: v[0] for k, v in urllib.parse.parse_qs(body, keep_blank_values=True).items()}
            code, text = get_service().rk_result(form)
            return resp(code, text)

        r = q.get("r", "")
        if r and not _admin_ok(q):
            return resp(403, "forbidden")
        svc = get_service() if r else None
        if r == "setup":
            svc.store.init_schema()
            need = [("ADMIN_KEY", config.ADMIN_KEY), ("RK_LOGIN", config.RK_LOGIN), ("YDB_DATABASE", config.YDB_DATABASE),
                    ("POSTBOX_KEY_ID", config.POSTBOX_KEY_ID), ("POSTBOX_SECRET", config.POSTBOX_SECRET)]
            need += [("RK_TEST_PASS1", config.RK_TEST_PASS1), ("RK_TEST_PASS2", config.RK_TEST_PASS2)] if config.RK_TEST \
                else [("RK_PASS1", config.RK_PASS1), ("RK_PASS2", config.RK_PASS2)]
            miss = [n for n, v in need if not v]
            mb = backupmod.missing_config()
            return resp(200, "Таблицы: OK\nРежим оплаты: %s\nReceipt: %s\nНе заданы переменные: %s\n"
                             "Резервное копирование: %s" % (
                                 "ТЕСТ (RK_TEST=1)" if config.RK_TEST else "БОЕВОЙ", "да" if config.RK_RECEIPT else "НЕТ",
                                 ", ".join(miss) or "нет", "настроено" if not mb else "НЕ настроено (нет %s)" % ", ".join(mb)))
        if r == "backup":
            return resp(200, svc.backup.run("manual"))
        if r == "backups":
            return resp(200, svc.backup.status())
        if r == "restore":
            if q.get("yes") != "1":
                return resp(200, "Добавь &yes=1, чтобы восстановить %s" % q.get("obj", "<объект>"))
            return resp(200, svc.backup.restore(q.get("obj", "")))
        if r == "cleanup":
            return resp(200, svc.cleanup())
        if r == "resend":
            return resp(200, svc.resend(q.get("o")))
        if r == "refund":
            return resp(200, svc.refund(q.get("o")))
        return resp(200, "%s shop server" % config.PRODUCT_NAME)
    except Exception:
        log.exception("handler error")
        return resp(500, "error")

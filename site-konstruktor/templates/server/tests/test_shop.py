"""Автотест шаблона сервера: python -I tests/test_shop.py (из папки server). Нужны cryptography; botocore — по желанию.
Проверяет покупку, все отказы Result, идемпотентность, /order, возврат, чистку, копию и восстановление,
маршруты handler и подписи SigV4 (Postbox, Object Storage) против botocore."""
import hashlib
import json
import os
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.update({"RK_LOGIN": "shop-test", "RK_TEST": "1", "RK_TEST_PASS1": "tp1", "RK_TEST_PASS2": "tp2",
                   "RK_PASS1": "p1", "RK_PASS2": "p2", "ADMIN_KEY": "adm", "PRICE": "990", "RK_RECEIPT": "1",
                   "BACKUP_BUCKET": "b", "BACKUP_KEY_ID": "id", "BACKUP_SECRET": "s", "BACKUP_PASSWORD": "pw",
                   "POSTBOX_KEY_ID": "", "POSTBOX_SECRET": ""})
import config  # noqa: E402
import index  # noqa: E402
import robokassa  # noqa: E402
import storage  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print("FAIL:", name)


class FakeS3:
    def __init__(self):
        self.objs = {}

    def put(self, k, data, content_type=None):
        self.objs[k] = data

    def get(self, k):
        return self.objs[k]

    def list(self, prefix=""):
        return [(k, len(v), "2026-01-01T00:00:00Z") for k, v in self.objs.items() if k.startswith(prefix)]


notes = []
store = storage.MemoryStorage()
svc = index.get_service(store)
svc.notify = notes.append
svc.backup.notify = notes.append
svc.backup._client = FakeS3()


def ev(path, method="POST", body="", q=None, ip="1.2.3.4"):
    return {"httpMethod": method, "path": path, "body": body, "queryStringParameters": q or {},
            "headers": {"X-Forwarded-For": "9.9.9.9"}, "requestContext": {"identity": {"sourceIp": ip}}}


def buy(email="a@b.ru", ip="1.2.3.4", **kw):
    p = {"email": email, "offer": True, "consent": True}
    p.update(kw)
    r = index.handler(ev("/buy", body=json.dumps(p), ip=ip), None)
    return r["statusCode"], json.loads(r["body"])


def result(inv, token, out_sum="990.00", is_test="1", pw="tp2", sig=None):
    s = sig or hashlib.sha256(("%s:%s:%s:Shp_token=%s" % (out_sum, inv, pw, token)).encode()).hexdigest().upper()
    form = {"OutSum": out_sum, "InvId": str(inv), "SignatureValue": s, "Shp_token": token, "IsTest": is_test}
    r = index.handler(ev("/rk/result", body=urllib.parse.urlencode(form)), None)
    return r["statusCode"], r["body"]


# --- покупка ---
c, d = buy()
check("buy 200", c == 200 and d["pay_url"].startswith(config.RK_URL))
qs = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(d["pay_url"]).query))
inv = int(qs["InvId"])
order = store.get(inv)
check("IP от шлюза, а не XFF", order["ip_hash"] == hashlib.sha256(b"ip:1.2.3.4").hexdigest())
check("IsTest=1 в ссылке", qs.get("IsTest") == "1")
rec = qs["Receipt"]   # после разбора ссылки остаётся один слой кодирования — он и входит в подпись
exp = hashlib.sha256(("shop-test:990.00:%d:%s:tp1:Shp_token=%s" % (inv, rec, order["token"])).encode()).hexdigest()
check("подпись ссылки с Receipt", qs["SignatureValue"] == exp)
check("Receipt: tax none, full_payment", json.loads(urllib.parse.unquote(qs["Receipt"]))["items"][0]["tax"] == "none")
check("токен 256 бит", len(order["token"]) >= 43)
check("buy без согласия", buy(consent=False)[0] == 400)
check("buy без оферты", buy(offer="yes")[0] == 400)
check("buy плохая почта", buy(email="x@")[0] == 400)
check("OPTIONS CORS", index.handler(ev("/buy", method="OPTIONS"), None)["headers"]["Access-Control-Allow-Origin"] == config.ALLOWED_ORIGIN)

# --- Result: отказы ---
tok = order["token"]
check("неверный режим (боевое уведомление на тестовом сервере)", result(inv, tok, is_test="0", pw="p2")[0] == 400)
check("чужой токен", result(inv, "x" * 43)[0] == 400)
check("неверная подпись", result(inv, tok, pw="bad")[0] == 400)
check("недоплата", result(inv, tok, out_sum="1.00")[0] == 400)
check("нет заказа", result(999999, tok)[0] == 400)
config.RK_TEST_PASS2 = ""
c, _ = result(inv, tok, pw="")
check("пустой пароль №2 → 500 и сообщение", c == 500 and any("пароль №2" in n for n in notes))
config.RK_TEST_PASS2 = "tp2"
check("до оплаты /order pending",
      json.loads(index.handler(ev("/order", "GET", q={"inv": str(inv), "t": tok}), None)["body"])["status"] == "pending")

# --- Result: успех и идемпотентность ---
c, b = result(inv, tok)
check("оплата OK<InvId>", c == 200 and b == "OK%d" % inv)
goods = store.get(inv)["goods"]
check("товар выдан", store.get(inv)["status"] == "paid" and len(goods) == 19)
c, b = result(inv, tok)
check("повтор без второй выдачи", c == 200 and store.get(inv)["goods"] == goods)
r = index.handler(ev("/order", "GET", q={"inv": str(inv), "t": tok}), None)
d = json.loads(r["body"])
check("/order отдаёт ключ", d["status"] == "paid" and d["key"] == goods and "***" in d["email"])
check("/order no-store", r["headers"]["Cache-Control"] == "no-store")
check("/order чужой токен 404", index.handler(ev("/order", "GET", q={"inv": str(inv), "t": "z"}), None)["statusCode"] == 404)
check("уведомление владельцу без почты", any("Оплата" in n and "a@b.ru" not in n for n in notes))

# --- служебные маршруты ---
check("setup без ключа 403", index.handler(ev("", "GET", q={"r": "setup"}), None)["statusCode"] == 403)
s = index.handler(ev("", "GET", q={"r": "setup", "k": "adm"}), None)["body"]
check("setup пишет режим ТЕСТ и копии", "ТЕСТ" in s and "Резервное копирование: настроено" in s)
oid = store.get(inv)["order_id"]
check("refund", "возвращённым" in index.handler(ev("", "GET", q={"r": "refund", "k": "adm", "o": oid}), None)["body"])
check("после возврата повторное уведомление не выдаёт товар", result(inv, tok)[0] == 200 and store.get(inv)["status"] == "refunded")

# --- лимиты ---
for i in range(5):
    buy(email="r%d@b.ru" % i, ip="5.5.5.5")
check("лимит IP в час", buy(email="z@b.ru", ip="5.5.5.5")[0] == 429)

# --- копия и восстановление ---
rep = index.handler(ev("", "GET", q={"r": "backup", "k": "adm"}), None)["body"]
check("копия создана", rep.startswith("📦"))
objs = svc.backup._client.objs
name = [k for k in objs if k.startswith("manual/")][0]
check("копия зашифрована", b"a@b.ru" not in objs[name] and objs[name].startswith(b"SKBK1"))
store.set_field(inv, "status", "broken")
rr = index.handler(ev("", "GET", q={"r": "restore", "k": "adm", "obj": name, "yes": "1"}), None)["body"]
check("восстановление", rr.startswith("♻️") and store.get(inv)["status"] == "refunded")
check("страховочная копия", any(k.startswith("pre-restore/") for k in objs))
t = index.handler({"messages": [{"details": {"payload": ""}}]}, None)
check("таймер: чистка + копия", t["statusCode"] == 200 and "cleanup" in t["body"] and "📦" in t["body"])

# --- чистка ---
store.orders[inv]["created"] = store.orders[inv]["paid_at"] = int(time.time()) - 6 * 365 * 86400
check("чистка старых оплаченных", "удалено 1" in svc.cleanup() and store.get(inv) is None)

# --- SigV4 против botocore ---
try:
    import datetime
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest, HTTPHeaders
    from botocore.credentials import Credentials
    import mailer
    import s3

    def boto_sig(service, method, url, body, h, names):
        class A(SigV4Auth):
            def _modify_request_before_signing(self, request):
                pass

            def headers_to_sign(self, request):
                hh = HTTPHeaders()
                for k in names:
                    hh[k] = h[[x for x in h if x.lower() == k][0]]
                return hh
        req = AWSRequest(method=method, url=url, data=body, headers=dict(h))
        req.context["timestamp"] = h["X-Amz-Date"]
        a = A(Credentials("AKID", "SECRET"), service, "ru-central1")
        return a.signature(a.string_to_sign(req, a.canonical_request(req)), req)

    now = datetime.datetime(2026, 1, 5, 12, 0, 0, tzinfo=datetime.timezone.utc)
    config.POSTBOX_KEY_ID, config.POSTBOX_SECRET = "AKID", "SECRET"
    body = '{"a":1}'
    url, h = mailer.build_request(body, now)
    check("Postbox SigV4 == botocore", h["Authorization"].endswith(
        boto_sig("ses", "POST", url, body.encode(), h, ("content-type", "host", "x-amz-date"))))
    for method, path, query, payload in (("PUT", "/b/daily/x.bk", None, b"\x00data"),
                                         ("GET", "/b", {"list-type": "2", "prefix": "weekly/"}, b"")):
        url, h = s3.sign_headers(method, "https://storage.yandexcloud.net", path, query, payload,
                                 "AKID", "SECRET", "ru-central1", now)
        check("S3 SigV4 == botocore " + method, h["Authorization"].endswith(
            boto_sig("s3", method, url, payload, h, ("host", "x-amz-content-sha256", "x-amz-date"))))
except ImportError:
    print("botocore не установлен — сверка SigV4 пропущена")

print("OK: %d, FAIL: %d" % (ok, fail))
sys.exit(1 if fail else 0)

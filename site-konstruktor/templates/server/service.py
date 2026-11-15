"""Бизнес-логика продажи: заказ, оплата (Робокасса), выдача, возврат, чистка ПД. Не зависит от HTTP.

Обязательная безопасность (из внешнего аудита; её отсутствие давало товар без оплаты):
- режим уведомления IsTest == режим сервера RK_TEST == режим заказа, иначе 400;
- пустой пароль №2 — 500 и сообщение владельцу, а не «подпись совпала с пустой строкой»;
- подпись через hmac.compare_digest; сумма — из базы, а не из уведомления;
- идемпотентность: повторное уведомление не выдаёт товар второй раз;
- токен заказа 256 бит; /order отдаёт товар только при совпадении токена;
- лимиты: заказов с IP в час и на почту в сутки.
"""
import base64
import hashlib
import logging
import os
import re
import time

import config
import delivery
import mailer
import robokassa

log = logging.getLogger("shop")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def norm_email(s):
    return (s or "").strip().lower()


def mask_email(s):
    s = s or ""
    if "@" not in s:
        return "***"
    local, _, domain = s.partition("@")
    head, _, tld = domain.partition(".")
    return "%s***@%s***%s" % (local[:2], head[:2], ("." + tld) if tld else "")


class Service:
    def __init__(self, store, notify=None):
        self.store = store
        self.notify = notify or mailer.notify_admin
        import backup as backupmod
        self.backup = backupmod.Backup(store, notify=self.notify)

    def _new_inv_id(self):
        for _ in range(8):
            inv = int.from_bytes(os.urandom(4), "big") % 2147483647 + 1
            if not self.store.get(inv):
                return inv
        raise RuntimeError("inv_id collision")

    def buy(self, payload, ip):
        """POST /buy {email, offer:true, consent:true, lang} → (код, json)."""
        payload = payload if isinstance(payload, dict) else {}
        if not config.SALES_OPEN:
            return 503, {"error": "closed"}
        email = norm_email(payload.get("email"))
        lang = "en" if payload.get("lang") == "en" else "ru"
        if not email or len(email) > 254 or not EMAIL_RE.match(email):
            return 400, {"error": "email"}
        if not (payload.get("offer") is True and payload.get("consent") is True):
            return 400, {"error": "consent"}
        now = int(time.time())
        ip_hash = hashlib.sha256(("ip:" + (ip or "")).encode()).hexdigest()
        recent = self.store.recent(now - 86400)
        ip_hour = sum(1 for o in recent if o.get("ip_hash") == ip_hash and int(o["created"]) >= now - 3600)
        email_day = sum(1 for o in recent if norm_email(o.get("email")) == email)
        if ip_hour >= config.RATE_IP_PER_HOUR or email_day >= config.RATE_EMAIL_PER_DAY:
            return 429, {"error": "rate"}
        inv_id = self._new_inv_id()
        order_id = config.ORDER_PREFIX + "".join(str(b % 10) for b in os.urandom(12))
        token = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
        self.store.create_order({
            "inv_id": inv_id, "order_id": order_id, "email": email, "lang": lang, "token": token,
            "amount": robokassa.fmt_sum(config.PRICE), "status": "created", "consent_at": now,
            "offer_version": config.OFFER_VERSION, "created": now, "is_test": config.RK_TEST, "ip_hash": ip_hash})
        url, _ = robokassa.build_pay_link(inv_id, config.PRICE, token, email, lang)
        return 200, {"pay_url": url, "order": order_id}

    def rk_result(self, form):
        """POST /rk/result → (код, текст). Успех: OK<InvId>."""
        try:
            inv_id = int(form.get("InvId") or 0)
        except ValueError:
            inv_id = 0
        out_sum = (form.get("OutSum") or "").strip()
        sig = form.get("SignatureValue") or ""
        token = form.get("Shp_token") or ""
        is_test = str(form.get("IsTest") or "") == "1"
        if is_test != bool(config.RK_TEST):
            log.warning("RK: IsTest=%s, а RK_TEST=%s, inv=%s", is_test, config.RK_TEST, inv_id)
            return 400, "bad mode"
        if not config.rk_pass2(is_test):
            self.notify("⚠️ Не задан пароль №2 Робокассы (%s): оплаты не подтверждаются."
                        % ("тестовый" if is_test else "боевой"))
            return 500, "no password"
        order = self.store.get(inv_id) if inv_id else None
        if order and bool(order.get("is_test")) != is_test:
            return 400, "bad mode"
        if not order or not token or token != order["token"]:
            return 400, "bad order"
        if not robokassa.verify_result(out_sum, inv_id, token, sig, is_test):
            return 400, "bad sign"
        try:
            if float(out_sum.replace(",", ".")) + 0.01 < float(order["amount"]):
                self.notify("⚠️ Заказ %s оплачен не полностью: %s (нужно %s)." % (order["order_id"], out_sum, order["amount"]))
                return 400, "bad sum"
        except ValueError:
            return 400, "bad sum"
        if order["status"] in ("paid", "refunded"):
            return 200, "OK%d" % inv_id                     # повторное уведомление: товар второй раз не выдаём
        goods, text_ru, text_en = delivery.issue(order)
        now = int(time.time())
        self.store.mark_paid(inv_id, goods, now)
        st = self._send_goods(order, text_ru, text_en, now)
        self.notify("💰 Оплата %s, %s ₽%s%s" % (order["order_id"], order["amount"], " (ТЕСТ)" if is_test else "",
                                              "" if st == "sent" else " — письмо: %s" % st))
        return 200, "OK%d" % inv_id

    def _send_goods(self, order, text_ru, text_en, when_ts):
        when = time.strftime("%d.%m.%Y", time.gmtime(when_ts))
        subj, text = mailer.goods_letter(order["order_id"], text_en if order["lang"] == "en" else text_ru,
                                         when, order["lang"])
        st = mailer.send(norm_email(order["email"]), subj, text)
        if st == "sent":
            self.store.set_field(int(order["inv_id"]), "mail_sent", True)
        return st

    def order_status(self, inv_id, token):
        """GET /order?inv=&t= — страница «Спасибо» опрашивает товар."""
        try:
            inv_id = int(inv_id or 0)
        except ValueError:
            inv_id = 0
        order = self.store.get(inv_id) if inv_id else None
        if not order or not token or token != order["token"]:
            return 404, {"status": "not_found"}
        if order["status"] == "paid" and order.get("goods"):
            return 200, {"status": "paid", "order": order["order_id"], "key": order["goods"],
                         "email": mask_email(order["email"])}
        return 200, {"status": "pending", "order": order["order_id"]}

    def resend(self, order_id):
        order = self.store.find_by_order((order_id or "").strip())
        if not order:
            return "Заказ не найден."
        if order["status"] != "paid":
            return "Заказ %s не оплачен (статус %s)." % (order["order_id"], order["status"])
        g = order["goods"]
        st = self._send_goods(order, "Ваш ключ: %s" % g, "Your key: %s" % g, int(order["paid_at"] or time.time()))
        return "Письмо по заказу %s: %s (%s)." % (order["order_id"], st, mask_email(order["email"]))

    def refund(self, order_id):
        """Пометить заказ возвращённым. Деньги возвращает владелец в кабинете платёжки (с баланса магазина),
        чек аннулирует в «Мой налог». Если товар — ключ, его отзыв делается здесь же (под свою логику)."""
        order = self.store.find_by_order((order_id or "").strip())
        if not order:
            return "Заказ не найден."
        self.store.set_field(int(order["inv_id"]), "status", "refunded")
        return "Заказ %s помечен возвращённым. Не забудь: возврат в кабинете платёжки и аннулирование чека." % order["order_id"]

    def cleanup(self):
        """Суточная чистка ПД по срокам Политики."""
        now = int(time.time())
        unpaid_cut, paid_cut = now - config.KEEP_UNPAID_DAYS * 86400, now - config.KEEP_PAID_DAYS * 86400
        a = b = 0
        for o in self.store.all():
            if o["status"] != "paid" and o["status"] != "refunded" and int(o["created"]) < unpaid_cut:
                self.store.delete(int(o["inv_id"])); a += 1
            elif o["status"] in ("paid", "refunded") and int(o["paid_at"] or o["created"]) < paid_cut:
                self.store.delete(int(o["inv_id"])); b += 1
        return "cleanup: неоплаченных удалено %d, старых оплаченных удалено %d" % (a, b)

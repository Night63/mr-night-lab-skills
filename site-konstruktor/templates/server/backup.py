"""Резервное копирование базы.

Каждый день (по таймеру, после чистки ПД) — выгрузка всех таблиц в JSON → gzip → шифрование AES-256-GCM
паролем BACKUP_PASSWORD → объект daily/ГГГГ-ММ-ДД.bk в закрытом бакете BACKUP_BUCKET.
По понедельникам (UTC) та же копия дополнительно кладётся в weekly/ГГГГ-Wнн.bk, и владельцу приходит
напоминание скачать её на ПК. Срок хранения задаётся правилами жизненного цикла бакета (daily — 30 дней).
Восстановление — только UPSERT (существующие строки перезаписываются копией, лишние не удаляются);
перед восстановлением автоматически делается копия pre-restore/…, чтобы шаг можно было откатить.

Формат .bk: b"SKBK1" + соль(16) + nonce(12) + AESGCM(ключ = scrypt(пароль, соль), gzip(JSON), aad=b"SKBK1").
Расшифровать на ПК: python decrypt_backup.py файл.bk (нужен пакет cryptography).
"""
import datetime
import gzip
import hashlib
import json
import logging
import os
import time

import config

log = logging.getLogger("shop")

MAGIC = b"SKBK1"
FORMAT_VERSION = 1
from storage import TABLES


# ---------- шифрование ----------
def _kdf(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def encrypt(data, password):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, nonce = os.urandom(16), os.urandom(12)
    return MAGIC + salt + nonce + AESGCM(_kdf(password, salt)).encrypt(nonce, data, MAGIC)


def decrypt(blob, password):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 28:
        raise ValueError("не файл резервной копии")
    salt = blob[len(MAGIC):len(MAGIC) + 16]
    nonce = blob[len(MAGIC) + 16:len(MAGIC) + 28]
    return AESGCM(_kdf(password, salt)).decrypt(nonce, blob[len(MAGIC) + 28:], MAGIC)


def pack(snapshot, password):
    raw = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return encrypt(gzip.compress(raw, 9), password)


def unpack(blob, password):
    return json.loads(gzip.decompress(decrypt(blob, password)).decode("utf-8"))


# ---------- снимок ----------
def make_snapshot(store, now=None):
    now = int(now or time.time())
    tables, counts = {}, {}
    for t in TABLES:
        rows = store.dump_table(t)
        expected = store.count_table(t)
        if len(rows) != expected:
            raise RuntimeError("таблица %s: выгружено %d строк, а в базе %d" % (t, len(rows), expected))
        tables[t], counts[t] = rows, len(rows)
    return {"format": FORMAT_VERSION, "product": config.PRODUCT_NAME,
            "created": now, "counts": counts, "tables": tables}


def summary(counts):
    return ", ".join("%s %d" % (t, n) for t, n in sorted(counts.items()))


# ---------- хранилище копий ----------
def missing_config():
    return [n for n, v in (("BACKUP_BUCKET", config.BACKUP_BUCKET), ("BACKUP_KEY_ID", config.BACKUP_KEY_ID),
                           ("BACKUP_SECRET", config.BACKUP_SECRET), ("BACKUP_PASSWORD", config.BACKUP_PASSWORD))
            if not v]


def default_client():
    import s3
    return s3.S3(config.BACKUP_ENDPOINT, config.BACKUP_REGION, config.BACKUP_KEY_ID,
                 config.BACKUP_SECRET, config.BACKUP_BUCKET)


def object_names(now):
    d = datetime.datetime.fromtimestamp(int(now), datetime.timezone.utc)
    iso = d.isocalendar()
    daily = "daily/%s.bk" % d.strftime("%Y-%m-%d")
    weekly = "weekly/%04d-W%02d.bk" % (iso[0], iso[1]) if d.weekday() == 0 else None
    return daily, weekly


class Backup:
    def __init__(self, store, client=None, notify=None):
        self.store = store
        self._client = client
        self.notify = notify or (lambda text: None)    # текст админу в бот

    @property
    def client(self):
        if self._client is None:
            self._client = default_client()
        return self._client

    def run(self, reason="daily", now=None):
        """Сделать копию. reason: daily (по таймеру), manual (?r=backup), pre-restore. Возвращает отчёт."""
        now = int(now or time.time())
        miss = missing_config()
        if miss:
            msg = "⚠️ Резервное копирование НЕ настроено — не заданы: %s." % ", ".join(miss)
            if reason == "daily":
                self.notify(msg)
            return msg
        try:
            snap = make_snapshot(self.store, now)
            blob = pack(snap, config.BACKUP_PASSWORD)
            daily, weekly = object_names(now)
            if reason == "daily":
                names = [daily] + ([weekly] if weekly else [])
            elif reason == "pre-restore":
                names = ["pre-restore/%s.bk" % time.strftime("%Y-%m-%d_%H%M%S", time.gmtime(now))]
            else:
                names = ["manual/%s.bk" % time.strftime("%Y-%m-%d_%H%M%S", time.gmtime(now))]
            for n in names:
                self.client.put(n, blob)
            self.store.set_setting("backup_last_ok_ts", str(now))
            self.store.set_setting("backup_last_obj", names[0])
            text = "📦 Копия базы: %s (%d КБ; %s)." % (", ".join(names), max(1, len(blob) // 1024),
                                                       summary(snap["counts"]))
            log.info("backup ok: %s", text)
            if reason == "daily" and weekly:
                self.notify(text + "\nНедельная копия готова — скачай на ПК/флешку:\n"
                                   "yc storage s3 cp s3://%s/%s ." % (config.BACKUP_BUCKET, weekly))
            return text
        except Exception as ex:
            log.exception("backup error")
            msg = "⚠️ Резервное копирование НЕ удалось (%s): %s: %s" % (reason, type(ex).__name__, ex)
            self.notify(msg)
            return msg

    def status(self):
        ts = self.store.get_setting("backup_last_ok_ts")
        obj = self.store.get_setting("backup_last_obj") or "—"
        if not ts:
            last = "успешных копий ещё не было"
        else:
            age = int(time.time()) - int(ts)
            last = "последняя успешная: %s UTC (%s), %s" % (
                time.strftime("%d.%m %H:%M", time.gmtime(int(ts))),
                "%d ч назад" % (age // 3600) if age < 172800 else "%d дн назад" % (age // 86400), obj)
        miss = missing_config()
        lines = ["Резервное копирование: " + ("НЕ настроено (нет %s)" % ", ".join(miss) if miss else "настроено"),
                 last]
        if not miss:
            try:
                objs = sorted(self.client.list(""), key=lambda o: o[0])
                lines.append("В бакете %s копий: %d. Последние:" % (config.BACKUP_BUCKET, len(objs)))
                for k, size, _ in sorted(objs, key=lambda o: o[2])[-8:]:
                    lines.append("  %s · %d КБ" % (k, max(1, size // 1024)))
            except Exception as ex:
                lines.append("Список копий не получен: %s" % ex)
        return "\n".join(lines)

    def restore(self, name, now=None):
        """UPSERT всех строк из копии. Перед этим — свежая копия pre-restore/…"""
        miss = missing_config()
        if miss:
            return "Восстановление невозможно — не заданы: %s." % ", ".join(miss)
        name = (name or "").strip().lstrip("/")
        if not name.endswith(".bk") or ".." in name:
            return "Укажите объект копии, например: ?r=restore&obj=daily/2026-01-05.bk&yes=1"
        try:
            snap = unpack(self.client.get(name), config.BACKUP_PASSWORD)
        except Exception as ex:
            return "Копию %s прочитать не удалось: %s: %s" % (name, type(ex).__name__, ex)
        if snap.get("format") != FORMAT_VERSION:
            return "Неизвестный формат копии: %s" % snap.get("format")
        pre = self.run("pre-restore", now)
        if pre.startswith("⚠️"):
            return "Восстановление отменено: не удалось сделать страховочную копию.\n" + pre
        done = {}
        for t in TABLES:
            rows = snap["tables"].get(t) or []
            if t == "settings":     # отметки о копиях не откатываем — они описывают сами копии, а не данные
                rows = [r for r in rows if not str(r.get("k", "")).startswith("backup_")]
            self.store.restore_rows(t, rows)
            done[t] = len(rows)
        text = "♻️ Восстановлено из %s (копия от %s UTC): %s.\nСтраховочная копия до восстановления: %s" % (
            name, time.strftime("%d.%m.%Y %H:%M", time.gmtime(int(snap["created"]))), summary(done),
            pre.split(": ", 1)[1].split(" (")[0] if ": " in pre else pre)
        log.info(text)
        return text

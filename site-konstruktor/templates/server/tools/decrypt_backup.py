"""Расшифровка резервной копии базы (.bk) на своём ПК.

Нужен Python 3.8+ и пакет cryptography:   pip install cryptography
Запуск:   python decrypt_backup.py 2026-W46.bk
Пароль (BACKUP_PASSWORD) спрашивается без отображения. Рядом появится 2026-W46.json — в нём
персональные данные покупателей: посмотрели — удалите, не пересылайте и не кладите в облако.
"""
import getpass
import gzip
import hashlib
import json
import os
import sys

MAGIC = b"SKBK1"


def decrypt(blob, password):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 28:
        raise ValueError("это не файл резервной копии")
    salt = blob[len(MAGIC):len(MAGIC) + 16]
    nonce = blob[len(MAGIC) + 16:len(MAGIC) + 28]
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return AESGCM(key).decrypt(nonce, blob[len(MAGIC) + 28:], MAGIC)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    password = os.environ.get("BK_PASSWORD") or getpass.getpass("Пароль копии (BACKUP_PASSWORD): ")
    with open(src, "rb") as f:
        blob = f.read()
    try:
        snap = json.loads(gzip.decompress(decrypt(blob, password)).decode("utf-8"))
    except Exception as ex:
        print("Не удалось расшифровать: неверный пароль или повреждённый файл (%s)" % type(ex).__name__)
        return 1
    dst = os.path.splitext(src)[0] + ".json"
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    print("Готово: %s" % dst)
    print("Копия от (unix): %s, строк: %s" % (snap.get("created"), snap.get("counts")))
    return 0


if __name__ == "__main__":
    sys.exit(main())

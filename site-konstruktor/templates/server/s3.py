"""Минимальный клиент Yandex Object Storage (S3-совместимый API, подпись AWS SigV4, сервис s3).
Без сторонних библиотек. Доступ — статический ключ сервисного аккаунта (BACKUP_KEY_ID / BACKUP_SECRET).
Нужны только три операции: положить объект, получить объект, список объектов по префиксу."""
import datetime
import hashlib
import hmac
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SERVICE = "s3"


class S3Error(Exception):
    pass


def _hmac(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret, datestamp, region):
    k = _hmac(("AWS4" + secret).encode("utf-8"), datestamp)
    k = _hmac(k, region)
    k = _hmac(k, SERVICE)
    return _hmac(k, "aws4_request")


def _q(s, safe="-_.~"):
    return urllib.parse.quote(s, safe=safe)


def sign_headers(method, endpoint, path, query, payload, key_id, secret, region, now=None):
    """Возвращает (url, headers). path — уже вида /bucket/key (без кодирования), query — dict."""
    parsed = urllib.parse.urlparse(endpoint)
    host = parsed.netloc
    now = now or datetime.datetime.now(datetime.timezone.utc)
    amzdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    canon_path = _q(path, safe="/-_.~")
    canon_query = "&".join("%s=%s" % (_q(k), _q(str(v))) for k, v in sorted((query or {}).items()))
    payload_hash = hashlib.sha256(payload or b"").hexdigest()
    canonical_headers = "host:%s\nx-amz-content-sha256:%s\nx-amz-date:%s\n" % (host, payload_hash, amzdate)
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join([method, canon_path, canon_query, canonical_headers, signed_headers, payload_hash])
    scope = "%s/%s/%s/aws4_request" % (datestamp, region, SERVICE)
    string_to_sign = "AWS4-HMAC-SHA256\n%s\n%s\n%s" % (
        amzdate, scope, hashlib.sha256(canonical_request.encode("utf-8")).hexdigest())
    signature = hmac.new(signing_key(secret, datestamp, region), string_to_sign.encode("utf-8"),
                         hashlib.sha256).hexdigest()
    headers = {
        "Host": host,
        "X-Amz-Date": amzdate,
        "X-Amz-Content-Sha256": payload_hash,
        "Authorization": "AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s"
                         % (key_id, scope, signed_headers, signature),
    }
    url = "%s://%s%s" % (parsed.scheme or "https", host, canon_path)
    if canon_query:
        url += "?" + canon_query
    return url, headers


class S3:
    def __init__(self, endpoint, region, key_id, secret, bucket):
        self.endpoint, self.region = endpoint.rstrip("/"), region
        self.key_id, self.secret, self.bucket = key_id, secret, bucket

    def _call(self, method, key="", query=None, payload=b"", extra_headers=None, timeout=20):
        path = "/%s/%s" % (self.bucket, key) if key else "/%s" % self.bucket
        url, headers = sign_headers(method, self.endpoint, path, query, payload,
                                    self.key_id, self.secret, self.region)
        if extra_headers:
            headers.update(extra_headers)       # не подписываются (Content-Type)
        req = urllib.request.Request(url, data=payload if method == "PUT" else None, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as ex:
            detail = ""
            try:
                detail = ex.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            raise S3Error("HTTP %s %s" % (ex.code, detail))
        except Exception as ex:
            raise S3Error("%s: %s" % (type(ex).__name__, ex))

    def put(self, key, data, content_type="application/octet-stream"):
        self._call("PUT", key, payload=data, extra_headers={"Content-Type": content_type}, timeout=60)

    def get(self, key):
        return self._call("GET", key, timeout=60)

    def list(self, prefix=""):
        """[(key, size, last_modified_iso)] по префиксу, все страницы."""
        out, token = [], None
        for _ in range(50):
            q = {"list-type": "2", "prefix": prefix}
            if token:
                q["continuation-token"] = token
            xml = self._call("GET", "", query=q)
            root = ET.fromstring(xml)
            ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
            for c in root.findall(ns + "Contents"):
                out.append((c.findtext(ns + "Key"), int(c.findtext(ns + "Size") or 0),
                            c.findtext(ns + "LastModified") or ""))
            if (root.findtext(ns + "IsTruncated") or "").lower() != "true":
                break
            token = root.findtext(ns + "NextContinuationToken")
        return out

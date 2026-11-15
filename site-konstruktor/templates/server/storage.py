"""Хранилище заказов: YdbStorage (облако) и MemoryStorage (тесты). Время — Unix-секунды (Int64).
Схема одна (SCHEMA) — из неё же берутся колонки для резервной копии и восстановления."""
import re
import time

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS orders (
        inv_id Int64, order_id Utf8, email Utf8, lang Utf8, token Utf8, amount Utf8, status Utf8,
        goods Utf8, consent_at Int64, offer_version Utf8, created Int64, paid_at Int64,
        is_test Bool, ip_hash Utf8, mail_sent Bool, PRIMARY KEY (inv_id))""",
    """CREATE TABLE IF NOT EXISTS settings (k Utf8, v Utf8, PRIMARY KEY (k))""",
]
FIELDS_UPDATABLE = {"status": "Utf8", "mail_sent": "Bool", "email": "Utf8", "goods": "Utf8"}


def columns():
    out = {}
    for q in SCHEMA:
        name = re.search(r"CREATE TABLE IF NOT EXISTS (\w+)", q).group(1)
        body = q.split("(", 1)[1].rsplit("PRIMARY KEY", 1)[0]
        out[name] = re.findall(r"(\w+) (Utf8|Int64|Bool)", body)
    return out


TABLES = list(columns())


class MemoryStorage:
    def __init__(self):
        self.orders, self.settings = {}, {}

    def init_schema(self):
        pass

    def create_order(self, o):
        row = {c: None for c, _ in columns()["orders"]}
        row.update(o)
        row.setdefault("goods", "")
        row["paid_at"], row["mail_sent"] = 0, False
        self.orders[int(o["inv_id"])] = row

    def get(self, inv_id):
        o = self.orders.get(int(inv_id))
        return dict(o) if o else None

    def find_by_order(self, order_id):
        for o in self.orders.values():
            if o["order_id"] == order_id:
                return dict(o)
        return None

    def mark_paid(self, inv_id, goods, paid_at):
        o = self.orders.get(int(inv_id))
        if o:
            o.update(status="paid", goods=goods, paid_at=int(paid_at))

    def set_field(self, inv_id, field, value):
        if field not in FIELDS_UPDATABLE:
            raise ValueError(field)
        o = self.orders.get(int(inv_id))
        if o:
            o[field] = value

    def recent(self, cutoff):
        return [{"email": o["email"], "ip_hash": o["ip_hash"], "created": o["created"]}
                for o in self.orders.values() if int(o["created"]) >= cutoff]

    def all(self):
        return [dict(o) for o in self.orders.values()]

    def delete(self, inv_id):
        self.orders.pop(int(inv_id), None)

    def set_setting(self, k, v):
        self.settings[k] = str(v)

    def get_setting(self, k):
        return self.settings.get(k)

    # резервное копирование
    def dump_table(self, table):
        if table == "orders":
            return [dict(o) for o in self.orders.values()]
        if table == "settings":
            return [{"k": k, "v": v} for k, v in self.settings.items()]
        raise ValueError(table)

    def count_table(self, table):
        return len(self.dump_table(table))

    def restore_rows(self, table, rows):
        cols = [c for c, _ in columns()[table]]
        for r in rows:
            r = {c: r.get(c) for c in cols}
            if table == "orders":
                self.orders[int(r["inv_id"])] = r
            else:
                self.settings[r["k"]] = r["v"]


class YdbStorage:
    def __init__(self, endpoint, database):
        import ydb
        import ydb.iam
        self.ydb = ydb
        self.driver = ydb.Driver(endpoint=endpoint, database=database,
                                 credentials=ydb.iam.MetadataUrlCredentials())
        self.driver.wait(timeout=10, fail_fast=True)
        self.pool = ydb.QuerySessionPool(self.driver)

    def _u(self, v):
        return ("" if v is None else str(v), self.ydb.PrimitiveType.Utf8)

    def _i(self, v):
        return (int(v or 0), self.ydb.PrimitiveType.Int64)

    def _b(self, v):
        return (bool(v), self.ydb.PrimitiveType.Bool)

    def _exec(self, query, params=None):
        return self.pool.execute_with_retries(query, params or {})

    def _rows(self, query, params=None):
        out = []
        for rs in self._exec(query, params):
            cols = [c.name for c in rs.columns]
            for row in rs.rows:
                out.append({c: row[c] for c in cols})
        return out

    def init_schema(self):
        for q in SCHEMA:
            self._exec(q)

    def create_order(self, o):
        self._exec("""DECLARE $inv AS Int64; DECLARE $oid AS Utf8; DECLARE $em AS Utf8; DECLARE $lang AS Utf8;
            DECLARE $tok AS Utf8; DECLARE $amt AS Utf8; DECLARE $st AS Utf8; DECLARE $cons AS Int64;
            DECLARE $ov AS Utf8; DECLARE $cr AS Int64; DECLARE $test AS Bool; DECLARE $ip AS Utf8;
            UPSERT INTO orders (inv_id, order_id, email, lang, token, amount, status, goods, consent_at,
                offer_version, created, paid_at, is_test, ip_hash, mail_sent)
            VALUES ($inv, $oid, $em, $lang, $tok, $amt, $st, '', $cons, $ov, $cr, 0, $test, $ip, false);""",
                   {"$inv": self._i(o["inv_id"]), "$oid": self._u(o["order_id"]), "$em": self._u(o["email"]),
                    "$lang": self._u(o["lang"]), "$tok": self._u(o["token"]), "$amt": self._u(o["amount"]),
                    "$st": self._u(o["status"]), "$cons": self._i(o["consent_at"]),
                    "$ov": self._u(o["offer_version"]), "$cr": self._i(o["created"]),
                    "$test": self._b(o["is_test"]), "$ip": self._u(o["ip_hash"])})

    def get(self, inv_id):
        r = self._rows("DECLARE $inv AS Int64; SELECT * FROM orders WHERE inv_id = $inv;", {"$inv": self._i(inv_id)})
        return r[0] if r else None

    def find_by_order(self, order_id):
        r = self._rows("DECLARE $o AS Utf8; SELECT * FROM orders WHERE order_id = $o;", {"$o": self._u(order_id)})
        return r[0] if r else None

    def mark_paid(self, inv_id, goods, paid_at):
        self._exec("""DECLARE $inv AS Int64; DECLARE $g AS Utf8; DECLARE $p AS Int64; DECLARE $st AS Utf8;
            UPDATE orders SET status = $st, goods = $g, paid_at = $p WHERE inv_id = $inv;""",
                   {"$inv": self._i(inv_id), "$g": self._u(goods), "$p": self._i(paid_at), "$st": self._u("paid")})

    def set_field(self, inv_id, field, value):
        typ = FIELDS_UPDATABLE.get(field)
        if not typ:
            raise ValueError(field)
        val = self._b(value) if typ == "Bool" else self._u(value)
        self._exec("DECLARE $inv AS Int64; DECLARE $v AS %s; UPDATE orders SET %s = $v WHERE inv_id = $inv;"
                   % (typ, field), {"$inv": self._i(inv_id), "$v": val})

    def recent(self, cutoff):
        return self._rows("DECLARE $c AS Int64; SELECT email, ip_hash, created FROM orders WHERE created >= $c;",
                          {"$c": self._i(cutoff)})

    def all(self):
        return self._rows("SELECT * FROM orders;")

    def delete(self, inv_id):
        self._exec("DECLARE $inv AS Int64; DELETE FROM orders WHERE inv_id = $inv;", {"$inv": self._i(inv_id)})

    def set_setting(self, k, v):
        self._exec("DECLARE $k AS Utf8; DECLARE $v AS Utf8; UPSERT INTO settings (k, v) VALUES ($k, $v);",
                   {"$k": self._u(k), "$v": self._u(v)})

    def get_setting(self, k):
        r = self._rows("DECLARE $k AS Utf8; SELECT v FROM settings WHERE k = $k;", {"$k": self._u(k)})
        return r[0]["v"] if r else None

    def dump_table(self, table):
        if table not in TABLES:
            raise ValueError(table)
        return self._rows("SELECT * FROM %s;" % table)

    def count_table(self, table):
        if table not in TABLES:
            raise ValueError(table)
        r = self._rows("SELECT COUNT(*) AS c FROM %s;" % table)
        return int(r[0]["c"]) if r else 0

    def restore_rows(self, table, rows, chunk=200):
        cols = columns().get(table)
        if not cols:
            raise ValueError(table)
        ydb = self.ydb
        prim = {"Utf8": ydb.PrimitiveType.Utf8, "Int64": ydb.PrimitiveType.Int64, "Bool": ydb.PrimitiveType.Bool}
        conv = {"Utf8": lambda v: None if v is None else str(v),
                "Int64": lambda v: None if v is None else int(v),
                "Bool": lambda v: None if v is None else bool(v)}
        struct = ydb.StructType()
        for c, t in cols:
            struct.add_member(c, ydb.OptionalType(prim[t]))
        decl = "DECLARE $rows AS List<Struct<%s>>;" % ", ".join("%s: %s?" % (c, t) for c, t in cols)
        query = "%s UPSERT INTO %s SELECT * FROM AS_TABLE($rows);" % (decl, table)
        for i in range(0, len(rows), chunk):
            batch = [{c: conv[t](r.get(c)) for c, t in cols} for r in rows[i:i + chunk]]
            self._exec(query, {"$rows": (batch, ydb.ListType(struct))})

"""In-memory PostgREST stand-in for tests (no network): upsert by the 0002 keys, filters, order, paging."""
import urllib.parse

# primary / unique keys of supabase/migrations/0002_market_and_app_tables.sql
KEYS = {"conflict": {"bars_30m": ("market", "symbol", "bar_start"), "signals": ("market", "asof", "symbol"),
                     "snapshot_meta": ("market", "slot_start"), "quotes_latest": ("market", "symbol"),
                     "heartbeat": ("market", "job")}}


class FakeDB:
    """Records every violation of the 0002 contract (wrong on_conflict, row without market).

    Without an `order` parameter, rows come back in an arbitrary order that changes between pages, the way
    PostgREST may behave without ORDER BY: code that pages without an explicit order loses or repeats rows."""

    def __init__(self, fail_tables=()):
        self.tables = {}
        self.fail = set(fail_tables)
        self.writes = []
        self.violations = []
        self.reads = []

    def rows(self, t):
        return list(self.tables.get(t, {}).values())

    def put(self, t, row):
        key = tuple(row[c] for c in KEYS["conflict"][t])
        self.tables.setdefault(t, {})[key] = row

    def __call__(self, method, path, headers, body):
        u = urllib.parse.urlparse(path)
        table = u.path.rsplit("/", 1)[-1]
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if method == "POST":
            if table in self.fail:
                return 500, {}
            self.writes.append(table)
            want = ",".join(KEYS["conflict"][table])
            if q.get("on_conflict") != want:
                self.violations.append(f"{table}: on_conflict {q.get('on_conflict')} != {want}")
            if not all(r.get("market") in ("VN", "US") for r in body):
                self.violations.append(f"{table}: row without market")
            if self.violations:
                return 400, {"violations": self.violations}
            ignore = "ignore-duplicates" in headers.get("prefer", headers.get("Prefer", ""))
            for r in body:
                key = tuple(r[c] for c in KEYS["conflict"][table])
                if ignore and key in self.tables.get(table, {}):
                    continue
                self.put(table, r)
            return 201, None
        out = self.rows(table)
        self.reads.append((table, q))
        for k, v in q.items():
            if k in ("select", "limit", "offset", "on_conflict", "order"):
                continue
            op, _, val = v.partition(".")
            if op == "eq":
                out = [r for r in out if str(r.get(k)) == val]
            elif op == "in":
                out = [r for r in out if r.get(k) in val.strip("()").split(",")]
            elif op == "gte":
                out = [r for r in out if str(r.get(k)) >= val]
            elif op == "lt":
                out = [r for r in out if str(r.get(k)) < val]
        off, lim = int(q.get("offset", 0)), int(q.get("limit", 1000))
        if "order" in q:
            for part in reversed(q["order"].split(",")):
                col, _, direction = part.partition(".")
                out.sort(key=lambda r, c=col: str(r.get(c)), reverse=direction == "desc")
        elif off % 2 == 0:  # no order: even pages come back reversed, odd pages as stored
            out.reverse()
        return 200, out[off:off + lim]

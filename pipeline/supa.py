"""Minimal Supabase REST (PostgREST) client over urllib. The secret key comes from the environment only."""
import urllib.parse

from pipeline.sources.http import request_json

BATCH = 500


def from_env(env):
    """Build a client from SUPABASE_URL and SUPABASE_SECRET_KEY; no defaults, no key in the message."""
    missing = [k for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY") if not (env.get(k) or "").strip()]
    if missing:
        raise RuntimeError("missing environment variable(s): " + ", ".join(missing))
    return Supabase(env["SUPABASE_URL"].strip(), env["SUPABASE_SECRET_KEY"].strip())


class Supabase:
    def __init__(self, url, key, sleep=None):
        self.base = url.rstrip("/") + "/rest/v1"
        # Not the browser User-Agent of request_json: Supabase answers 401 to a secret key sent with one.
        self.headers = {"apikey": key, "Authorization": f"Bearer {key}", "User-Agent": "agent-chung-khoan-bot"}
        self.sleep = sleep

    def _call(self, path, payload=None, method=None, prefer=None):
        headers = {**self.headers, **({"Prefer": prefer} if prefer else {})}
        return request_json(self.base + path, payload, headers=headers, method=method, sleep=self.sleep)

    def select(self, table, params=None):
        q = urllib.parse.urlencode(params or {})
        return self._call(f"/{table}?{q}", method="GET")

    def select_all(self, table, params=None, page=1000, order=None):
        """select() across pages (PostgREST caps one response); stops at the first short page.

        `order` is required (e.g. "market.asc,symbol.asc"): without a stable order the pages can overlap or skip rows."""
        if not order:
            raise ValueError("select_all needs an explicit order (the primary key columns)")
        out = []
        while True:
            rows = self.select(table, {**(params or {}), "order": order, "limit": page, "offset": len(out)})
            out.extend(rows)
            if len(rows) < page:
                return out

    def upsert(self, table, rows, on_conflict, merge=True):
        """merge=False keeps the row that is already there (first writer wins), so a rerun cannot overwrite it."""
        if "market" in on_conflict.split(","):
            # every market table is keyed by market; a row without it would land in the default market
            bad = [r for r in rows if r.get("market") not in ("VN", "US")]
            if bad:
                raise ValueError(f"{table}: {len(bad)} row(s) without a valid market")
        q = urllib.parse.urlencode({"on_conflict": on_conflict})
        mode = "merge-duplicates" if merge else "ignore-duplicates"
        for i in range(0, len(rows), BATCH):
            self._call(f"/{table}?{q}", rows[i:i + BATCH], prefer=f"resolution={mode},return=minimal")

    def delete(self, table, params):
        self._call(f"/{table}?{urllib.parse.urlencode(params)}", method="DELETE", prefer="return=minimal")

    def rpc(self, fn, args=None):
        return self._call(f"/rpc/{fn}", args or {})

import json
import os
import unittest
import urllib.parse
from datetime import datetime, time, timedelta, timezone

from pipeline.banned import find_banned
from pipeline.run import closed, main, slot_start, window_minutes
from tests.fakehttp import FakeServer

UTC = timezone.utc
NOW = datetime(2026, 10, 30, 2, 50, tzinfo=UTC)  # Friday 09:50 in Ho Chi Minh -> slot 09:30
SLOT = "2026-10-30T02:30:00+00:00"
PREV_ASOF = "2026-10-30T02:20:00+00:00"
SYMS = ["AAA", "BBB"]
KEYS = {"conflict": {"bars_30m": ("symbol", "bar_start"), "signals": ("asof", "symbol"),
                     "snapshot_meta": ("market", "asof"), "quotes_latest": ("symbol",),
                     "heartbeat": ("market",)}}


class FakeDB:
    """In-memory PostgREST stand-in: upsert by conflict key, eq/gte/lt filters, limit/offset."""

    def __init__(self, fail_tables=()):
        self.tables = {}
        self.fail = set(fail_tables)
        self.writes = []

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
            ignore = "ignore-duplicates" in headers.get("prefer", headers.get("Prefer", ""))
            for r in body:
                key = tuple(r[c] for c in KEYS["conflict"][table])
                if ignore and key in self.tables.get(table, {}):
                    continue
                self.put(table, r)
            return 201, None
        out = self.rows(table)
        for k, v in q.items():
            if k in ("select", "limit", "offset", "on_conflict"):
                continue
            op, _, val = v.partition(".")
            if op == "eq":
                out = [r for r in out if str(r.get(k)) == val]
            elif op == "gte":
                out = [r for r in out if str(r.get(k)) >= val]
            elif op == "lt":
                out = [r for r in out if str(r.get(k)) < val]
        off, lim = int(q.get("offset", 0)), int(q.get("limit", 1000))
        return 200, out[off:off + lim]


def board(**over):
    row = {"EX": "HOSE", "CP": 10_000, "RE": 10_000, "CL": 10_700, "FL": 9_300,
           "TT": 200_000, "TV": 2_000_000_000, "FB": 1000, "FS": 1000, "FR": 0, "PTQ": 0, "PTV": 0}
    return {**row, **over}


def quote(sym, **over):
    base = {"symbol": sym, "exchange": "HOSE", "price": 10_000, "ref_price": 10_000, "ceil_price": 10_700,
            "floor_price": 9_300, "vol": 100_000, "val": 1_000_000_000, "f_buy": 500, "f_sell": 500,
            "f_room": 0, "pt_vol": 0, "pt_val": 0, "asof": PREV_ASOF}
    return {**base, **over}


def env_for(url, **extra):
    return {"SUPABASE_URL": url, "SUPABASE_SECRET_KEY": "test-key", **extra}


def run(db, rows, now=NOW, market="VN", env_extra=None):
    with FakeServer(db) as s:
        fetch = lambda symbols: {k: {"SB": k, **v} for k, v in rows.items()}
        code = main(["--market", market], env_for(s.url, **(env_extra or {})), now=now, fetch=fetch, symbols=SYMS,
                    sleep=lambda x: None)
        return code, s.requests


class HelpersTest(unittest.TestCase):
    def test_slot_is_the_local_half_hour_in_utc(self):
        self.assertEqual(slot_start("VN", NOW), datetime(2026, 10, 30, 2, 30, tzinfo=UTC))
        us = datetime(2026, 10, 30, 14, 5, tzinfo=UTC)  # 10:05 New York (EDT)
        self.assertEqual(slot_start("US", us), datetime(2026, 10, 30, 14, 0, tzinfo=UTC))

    def test_lunch_time_runs_get_distinct_slots(self):
        a = slot_start("VN", datetime(2026, 10, 30, 4, 40, tzinfo=UTC))  # 11:40
        b = slot_start("VN", datetime(2026, 10, 30, 6, 20, tzinfo=UTC))  # 13:20
        self.assertEqual((a.hour, a.minute, b.hour, b.minute), (4, 30, 6, 0))

    def test_window_minutes_skip_the_lunch_break(self):
        self.assertEqual(window_minutes("VN", time(9, 20)), 20)  # first run of the day counts from the open
        self.assertEqual(window_minutes("VN", time(9, 50)), 30)
        self.assertEqual(window_minutes("VN", time(11, 40)), 10)
        self.assertEqual(window_minutes("VN", time(13, 20)), 20)
        self.assertEqual(window_minutes("VN", time(15, 5)), 0)

    def test_us_window_minutes(self):
        self.assertEqual(window_minutes("US", time(10, 5)), 35)
        self.assertEqual(window_minutes("US", time(15, 35)), 30)
        self.assertEqual(window_minutes("US", time(16, 20)), 25)
        self.assertEqual(window_minutes("US", time(16, 50)), 0)

    def test_closed_when_95_percent_of_volumes_did_not_move(self):
        prev = {f"S{i}": {"TT": 100} for i in range(20)}
        curr = {f"S{i}": {"TT": 100 if i else 101} for i in range(20)}  # 19 of 20 flat = 95%
        self.assertTrue(closed(prev, curr))
        curr["S1"]["TT"] = 150  # 18 of 20 = 90%
        self.assertFalse(closed(prev, curr))

    def test_not_closed_without_anything_to_compare(self):
        self.assertFalse(closed({}, {"A": {"TT": 1}}))
        self.assertFalse(closed({"A": {"TT": 1}}, {}))


class GateTest(unittest.TestCase):
    def test_missing_secrets_are_reported_before_any_work(self):
        called = []
        code = main(["--market", "VN"], {}, now=NOW, fetch=lambda s: called.append(1), symbols=SYMS)
        self.assertEqual((code, called), (2, []))

    def test_us_needs_alpaca_keys_by_name(self):
        with FakeServer(FakeDB()) as s:
            with self.assertLogs("pipeline.run", level="ERROR") as cm:
                code = main(["--market", "US"], env_for(s.url), now=datetime(2026, 10, 30, 14, 5, tzinfo=UTC),
                            symbols=SYMS)
        self.assertEqual(code, 2)
        self.assertIn("APCA_API_KEY_ID", "".join(cm.output))
        self.assertNotIn("test-key", "".join(cm.output))

    def test_outside_the_run_window_nothing_is_fetched_or_written(self):
        db = FakeDB()
        night = datetime(2026, 10, 30, 18, 0, tzinfo=UTC)
        with self.assertLogs("pipeline.run", level="INFO") as cm:
            code, reqs = run(db, {"AAA": board()}, now=night)
        self.assertEqual((code, reqs), (0, []))
        self.assertTrue(any("outside" in line for line in cm.output))

    def test_weekend_is_outside_the_window(self):
        sat = datetime(2026, 10, 31, 2, 50, tzinfo=UTC)
        with self.assertLogs("pipeline.run", level="INFO"):
            code, reqs = run(FakeDB(), {"AAA": board()}, now=sat)
        self.assertEqual((code, reqs), (0, []))

    def test_unknown_market_is_rejected(self):
        with self.assertRaises(SystemExit):
            main(["--market", "JP"], {}, now=NOW)


class ClosedMarketTest(unittest.TestCase):
    def test_flat_volumes_mean_closed_so_nothing_is_written(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s, vol=200_000))
        with self.assertLogs("pipeline.run", level="INFO") as cm:
            code, reqs = run(db, {s: board() for s in SYMS})
        self.assertEqual(code, 0)
        self.assertTrue(any("closed" in line for line in cm.output))
        self.assertEqual(db.writes, [])
        self.assertEqual([r for r in reqs if r["method"] == "POST"], [])


class NormalRunTest(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        for s in SYMS:
            self.db.put("quotes_latest", quote(s))
        # AAA: foreign net buy of 60k in a 100k window -> S2; BBB: quiet
        self.rows = {"AAA": board(FB=60_500), "BBB": board(TT=200_000, TV=2_000_000_000)}

    def go(self, **kw):
        with self.assertLogs("pipeline.run", level="INFO"):
            return run(self.db, self.rows, **kw)

    def test_writes_bars_quotes_snapshot_and_heartbeat(self):
        code, _ = self.go()
        self.assertEqual(code, 0)
        bars = {r["symbol"]: r for r in self.db.rows("bars_30m")}
        self.assertEqual(set(bars), {"AAA", "BBB"})
        self.assertEqual(bars["AAA"]["bar_start"], SLOT)
        self.assertEqual((bars["AAA"]["vol"], bars["AAA"]["fnet"]), (100_000, 59_500))
        meta = self.db.rows("snapshot_meta")
        self.assertEqual([(m["market"], m["asof"], m["symbols"], m["signals"]) for m in meta], [("VN", SLOT, 2, 1)])
        self.assertEqual(len(self.db.rows("heartbeat")), 1)
        q = {r["symbol"]: r for r in self.db.rows("quotes_latest")}
        self.assertEqual(q["AAA"]["vol"], 200_000)
        self.assertEqual(q["AAA"]["asof"], NOW.isoformat())

    def test_signals_are_written_only_when_level_is_above_zero(self):
        self.go()
        sig = self.db.rows("signals")
        self.assertEqual([(r["symbol"], r["level"], r["learning"]) for r in sig], [("AAA", 1, True)])
        self.assertEqual(sig[0]["items"][0]["id"], "S2")
        self.assertEqual(sig[0]["asof"], SLOT)

    def test_running_the_same_slot_twice_leaves_one_row_each(self):
        self.go()
        first = {t: len(self.db.rows(t)) for t in ("bars_30m", "signals", "snapshot_meta")}
        with self.assertLogs("pipeline.run", level="INFO") as cm:
            code, _ = run(self.db, self.rows)
        self.assertEqual(code, 0)
        self.assertTrue(any("already" in line for line in cm.output))
        self.assertEqual({t: len(self.db.rows(t)) for t in first}, first)

    def test_rerun_after_a_crash_cannot_overwrite_bars_with_zeros(self):
        self.db.fail = {"snapshot_meta"}
        with self.assertRaises(Exception):
            run(self.db, self.rows)
        self.db.fail = set()
        # quotes_latest already moved on, so the rerun sees only a tiny window
        later = {s: {**r, "TT": r["TT"] + 10} for s, r in self.rows.items()}
        with self.assertLogs("pipeline.run", level="INFO"):
            run(self.db, later, now=datetime(2026, 10, 30, 2, 55, tzinfo=UTC))
        bars = {r["symbol"]: r for r in self.db.rows("bars_30m")}
        self.assertEqual(bars["AAA"]["vol"], 100_000)

    def test_new_session_where_cumulative_numbers_dropped_gives_no_bar_for_that_symbol(self):
        self.db.put("quotes_latest", quote("BBB", vol=900_000_000))
        self.go()
        self.assertEqual([r["symbol"] for r in self.db.rows("bars_30m")], ["AAA"])

    def test_symbol_never_seen_before_gets_no_window(self):
        self.rows["CCC"] = board()
        self.go()
        self.assertNotIn("CCC", [r["symbol"] for r in self.db.rows("bars_30m")])
        self.assertIn("CCC", [r["symbol"] for r in self.db.rows("quotes_latest")])

    def test_heartbeat_failure_is_logged_not_fatal(self):
        self.db.fail = {"heartbeat"}
        with self.assertLogs("pipeline.run", level="WARNING") as cm:
            code, _ = run(self.db, self.rows)
        self.assertEqual(code, 0)
        self.assertTrue(any("heartbeat" in line for line in cm.output))

    def test_enough_history_turns_learning_off_and_flags_a_volume_spike(self):
        for day in range(1, 21):
            ts = datetime(2026, 10, 30, 2, 30, tzinfo=UTC) - timedelta(days=day)
            for sym in SYMS:
                vol = 10_000 + 200 * (day % 5)
                self.db.put("bars_30m", {"symbol": sym, "bar_start": ts.isoformat(), "vol": vol,
                                         "val": 1, "fnet": 0, "pt_val": 0})
        self.rows["BBB"] = board(TT=100_000 + 100_000)  # +100k in the window against ~10k usual
        self.go()
        sig = {r["symbol"]: r for r in self.db.rows("signals")}
        self.assertFalse(sig["BBB"]["learning"])
        self.assertIn("S1", [i["id"] for i in sig["BBB"]["items"]])

    def test_every_written_text_field_passes_the_banned_scanner(self):
        self.go()
        blob = json.dumps({t: self.db.rows(t) for t in ("signals", "snapshot_meta", "heartbeat")}, ensure_ascii=False)
        self.assertEqual(find_banned(blob), [])


if __name__ == "__main__":
    unittest.main()

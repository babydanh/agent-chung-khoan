import json
import os
import unittest
import urllib.parse
from datetime import datetime, time, timedelta, timezone

from pipeline.banned import find_banned
from pipeline.run import closed, main, slot_start, window_minutes
from tests.fakedb import FakeDB, KEYS
from tests.fakehttp import FakeServer

UTC = timezone.utc
NOW = datetime(2026, 10, 30, 2, 50, tzinfo=UTC)  # Friday 09:50 in Ho Chi Minh -> slot 09:30
SLOT = "2026-10-30T02:30:00+00:00"
PREV_ASOF = "2026-10-30T02:20:00+00:00"
SYMS = ["AAA", "BBB"]
def board(**over):
    row = {"EX": "HOSE", "CP": 10_000, "RE": 10_000, "CL": 10_700, "FL": 9_300,
           "TT": 200_000, "TV": 2_000_000_000, "FB": 1000, "FS": 1000, "FR": 0, "PTQ": 0, "PTV": 0}
    return {**row, **over}


def quote(sym, **over):
    base = {"market": "VN", "symbol": sym, "exchange": "HOSE", "price": 10_000, "ref_price": 10_000, "ceil_price": 10_700,
            "floor_price": 9_300, "vol": 100_000, "val": 1_000_000_000, "f_buy": 500, "f_sell": 500,
            "f_room": 0, "pt_vol": 0, "pt_val": 0, "asof": PREV_ASOF}
    return {**base, **over}


def env_for(url, **extra):
    return {"SUPABASE_URL": url, "SUPABASE_SECRET_KEY": "test-key", **extra}


def run(db, rows, now=NOW, market="VN", env_extra=None):
    with FakeServer(db) as s:
        fetch = lambda symbols: {k: {"SB": k, "SRC": "KBS", **v} for k, v in rows.items()}
        code = main(["--market", market], env_for(s.url, **(env_extra or {})), now=now, fetch=fetch, symbols=SYMS,
                    sleep=lambda x: None)
        assert not db.violations, db.violations
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
        self.assertEqual(code, 1)  # a weekday outside the holiday list that looks closed is an alarm, see ClosedGateTest
        self.assertTrue(any("closed" in line for line in cm.output))
        self.assertEqual(db.writes, ["heartbeat"])  # only the "closed" heartbeat, no bars, quotes or snapshot
        self.assertEqual(db.rows("snapshot_meta"), [])


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
        self.assertEqual([(m["market"], m["slot_start"], m["asof"], m["symbols"], m["signals"]) for m in meta],
                         [("VN", SLOT, NOW.isoformat(), 2, 1)])
        hb = self.db.rows("heartbeat")
        self.assertEqual([(h["market"], h["job"], h["last_seen"]) for h in hb], [("VN", "snapshot", NOW.isoformat())])
        self.assertEqual((hb[0]["detail"]["status"], hb[0]["detail"]["source"]), ("ok", "KBS"))
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
        self.db.fail = {"quotes_latest"}  # crash after the slot was recorded
        with self.assertRaises(Exception):
            run(self.db, self.rows)
        self.db.fail = set()
        later = {s: {**r, "TT": r["TT"] + 10} for s, r in self.rows.items()}
        with self.assertLogs("pipeline.run", level="INFO") as cm:
            run(self.db, later, now=datetime(2026, 10, 30, 2, 55, tzinfo=UTC))
        self.assertTrue(any("finishing" in line for line in cm.output))  # the slot is completed, not skipped
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

    def test_heartbeat_failure_fails_the_run(self):
        self.db.fail = {"heartbeat"}
        with self.assertLogs("pipeline.run", level="ERROR") as cm:
            code, _ = run(self.db, self.rows)
        self.assertEqual(code, 1)
        self.assertTrue(any("heartbeat" in line for line in cm.output))

    def test_enough_history_turns_learning_off_and_flags_a_volume_spike(self):
        for day in range(1, 21):
            ts = datetime(2026, 10, 30, 2, 30, tzinfo=UTC) - timedelta(days=day)
            for sym in SYMS:
                vol = 10_000 + 200 * (day % 5)
                self.db.put("bars_30m", {"market": "VN", "symbol": sym, "bar_start": ts.isoformat(), "vol": vol,
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


# ---------------------------------------------------------------- review fixes (group B)
from pipeline.run import actual_minutes, late_minutes, process, _history
from pipeline import config as _config
from pipeline.supa import Supabase

TH_VN = _config.load(os.path.join(os.path.dirname(__file__), "..", "config", "thresholds.json"), "VN")


class MarketKeyTest(unittest.TestCase):
    def test_every_written_row_carries_the_market_and_uses_the_0002_keys(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s))
        with self.assertLogs("pipeline.run", level="INFO"):
            run(db, {"AAA": board(FB=60_500), "BBB": board()})  # FakeDB records any violation and run() asserts none
        for t in ("bars_30m", "signals", "snapshot_meta", "quotes_latest", "heartbeat"):
            self.assertTrue(db.rows(t), t)
            self.assertTrue(all(r["market"] == "VN" for r in db.rows(t)), t)

    def test_us_run_writes_us_rows_without_touching_vn_quotes(self):
        db = FakeDB()
        db.put("quotes_latest", quote("AAA", market="VN", vol=7))
        us_now = datetime(2026, 10, 30, 14, 5, tzinfo=UTC)
        db.put("quotes_latest", quote("AAA", market="US", asof="2026-10-30T13:50:00+00:00"))
        with self.assertLogs("pipeline.run", level="INFO"):
            run(db, {"AAA": board(TT=250_000)}, now=us_now, market="US",
                env_extra={"APCA_API_KEY_ID": "a", "APCA_API_SECRET_KEY": "b"})
        vn = [r for r in db.rows("quotes_latest") if r["market"] == "VN"]
        self.assertEqual(vn[0]["vol"], 7)
        self.assertEqual({r["market"] for r in db.rows("snapshot_meta")}, {"US"})


class FeedHealthTest(unittest.TestCase):
    def test_too_few_symbols_is_an_error_and_writes_nothing(self):
        db = FakeDB()
        for s in ("AAA", "BBB", "CCC", "DDD"):
            db.put("quotes_latest", quote(s))
        with FakeServer(db) as srv:
            fetch = lambda syms: {"AAA": {"SB": "AAA", "SRC": "KBS", **board()}}
            with self.assertLogs("pipeline.run", level="ERROR"):
                code = main(["--market", "VN"], env_for(srv.url), now=NOW, fetch=fetch,
                            symbols=["AAA", "BBB", "CCC", "DDD"], sleep=lambda x: None)
        self.assertEqual(code, 1)
        self.assertEqual(db.writes, [])

    def test_empty_feed_is_an_error_without_snapshot_or_heartbeat(self):
        db = FakeDB()
        with FakeServer(db) as srv:
            with self.assertLogs("pipeline.run", level="ERROR"):
                code = main(["--market", "VN"], env_for(srv.url), now=NOW, fetch=lambda syms: {}, symbols=SYMS,
                            sleep=lambda x: None)
        self.assertEqual(code, 1)
        self.assertEqual((db.rows("snapshot_meta"), db.rows("heartbeat")), ([], []))

    def test_half_of_the_symbols_is_enough(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s))
        with FakeServer(db) as srv:
            fetch = lambda syms: {"AAA": {"SB": "AAA", "SRC": "KBS", **board()}}
            with self.assertLogs("pipeline.run", level="INFO"):
                code = main(["--market", "VN"], env_for(srv.url), now=NOW, fetch=fetch, symbols=SYMS,
                            sleep=lambda x: None)
        self.assertEqual(code, 0)


class ClosedGateTest(unittest.TestCase):
    def test_a_few_matching_symbols_do_not_prove_the_market_is_closed(self):
        prev = {"A": {"TT": 5, "PTQ": 0, "PTV": 0}}
        curr = {s: {"TT": 5, "PTQ": 0, "PTV": 0} for s in "ABCDEFGHIJ"}  # only 1 of 10 comparable
        self.assertFalse(closed(prev, curr))

    def test_negotiated_deals_count_as_movement(self):
        prev = {f"S{i}": {"TT": 100, "PTQ": 0, "PTV": 0} for i in range(20)}
        curr = {f"S{i}": {"TT": 100, "PTQ": 10, "PTV": 5} for i in range(20)}
        self.assertFalse(closed(prev, curr))

    def test_closed_run_records_a_closed_heartbeat_and_fails_on_an_unlisted_weekday(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s, vol=200_000))
        with self.assertLogs("pipeline.run", level="WARNING") as cm:
            code, _ = run(db, {s: board() for s in SYMS})
        self.assertEqual(code, 1)
        self.assertTrue(any("closed" in line for line in cm.output))
        self.assertEqual(db.rows("heartbeat")[0]["detail"]["status"], "closed")
        self.assertEqual(db.rows("snapshot_meta"), [])

    def test_the_run_after_the_close_still_records_negotiated_deals(self):
        db = FakeDB()
        now = datetime(2026, 10, 30, 8, 5, tzinfo=UTC)  # 15:05 in Ho Chi Minh, volumes frozen since 14:45
        for s in SYMS:
            db.put("quotes_latest", quote(s, vol=200_000, asof="2026-10-30T07:50:00+00:00"))
        rows = {s: board(PTQ=40_000, PTV=1_000_000_000) for s in SYMS}
        with self.assertLogs("pipeline.run", level="INFO"):
            code, _ = run(db, rows, now=now)
        self.assertEqual(code, 0)
        bars = db.rows("bars_30m")
        self.assertEqual({b["pt_val"] for b in bars}, {1_000_000_000})
        self.assertEqual(len(db.rows("snapshot_meta")), 1)


class HistoryLocalTimeTest(unittest.TestCase):
    def test_us_history_matches_across_the_november_1_time_change(self):
        db = FakeDB()
        # 10:00 New York was 14:00 UTC under EDT and is 15:00 UTC under EST
        for day in (28, 29, 30):
            db.put("bars_30m", {"market": "US", "symbol": "AAA", "bar_start": f"2026-10-{day}T14:00:00+00:00",
                                "vol": 1000 + day, "val": 1, "fnet": 0, "pt_val": 0})
        now = datetime(2026, 11, 2, 15, 5, tzinfo=UTC)  # Monday 10:05 EST
        slot = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
        hist = _history(db_client(db), "US", slot, now)
        self.assertEqual(sorted(hist["AAA"]), [1028, 1029, 1030])

    def test_bars_of_other_half_hours_and_other_markets_are_ignored(self):
        db = FakeDB()
        db.put("bars_30m", {"market": "US", "symbol": "AAA", "bar_start": "2026-10-29T14:30:00+00:00",
                            "vol": 5, "val": 1, "fnet": 0, "pt_val": 0})
        db.put("bars_30m", {"market": "VN", "symbol": "AAA", "bar_start": "2026-10-29T14:00:00+00:00",
                            "vol": 6, "val": 1, "fnet": 0, "pt_val": 0})
        now = datetime(2026, 10, 30, 14, 5, tzinfo=UTC)
        hist = _history(db_client(db), "US", datetime(2026, 10, 30, 14, 0, tzinfo=UTC), now)
        self.assertEqual(hist, {})


def db_client(fake):
    srv = FakeServer(fake).__enter__()
    db_client.servers.append(srv)
    return Supabase(srv.url, "K", sleep=lambda x: None)


db_client.servers = []


def tearDownModule():
    for srv in db_client.servers:
        srv.__exit__(None, None, None)


class WindowMinutesTest(unittest.TestCase):
    def test_minutes_come_from_the_real_previous_snapshot(self):
        prev = datetime(2026, 10, 30, 2, 20, tzinfo=UTC)  # 09:20
        self.assertEqual(actual_minutes("VN", prev, NOW), 30)
        self.assertEqual(actual_minutes("VN", datetime(2026, 10, 30, 2, 40, tzinfo=UTC), NOW), 10)

    def test_a_window_over_one_and_a_half_slots_drops_s1_with_a_warning(self):
        prev = datetime(2026, 10, 30, 2, 0, tzinfo=UTC)  # 09:00 -> 09:50 is 50 minutes
        with self.assertLogs("pipeline.run", level="WARNING") as cm:
            self.assertEqual(actual_minutes("VN", prev, NOW), 0)
        self.assertTrue(any("S1" in line for line in cm.output))

    def test_first_run_of_the_day_counts_from_the_open(self):
        yesterday = datetime(2026, 10, 29, 8, 5, tzinfo=UTC)
        self.assertEqual(actual_minutes("VN", yesterday, datetime(2026, 10, 30, 2, 20, tzinfo=UTC)), 20)

    def test_no_previous_snapshot_counts_from_the_open(self):
        self.assertEqual(actual_minutes("VN", None, datetime(2026, 10, 30, 2, 20, tzinfo=UTC)), 20)

    def test_late_runs_are_measured_against_the_scheduled_time(self):
        self.assertEqual(late_minutes("VN", NOW), 0)
        self.assertEqual(late_minutes("VN", datetime(2026, 10, 30, 3, 10, tzinfo=UTC)), 20)


class FirstRunOfDayTest(unittest.TestCase):
    def test_yesterdays_quote_is_treated_as_zero_so_the_first_window_runs_from_the_open(self):
        prev = [quote("AAA", vol=900_000_000, asof="2026-10-29T08:05:00+00:00")]
        now = datetime(2026, 10, 30, 2, 20, tzinfo=UTC)
        bars, _, _ = process("VN", now, {"AAA": {"SB": "AAA", **board(TT=50_000)}}, prev, {}, TH_VN)
        self.assertEqual(bars[0]["vol"], 50_000)


class DeltaDropLogTest(unittest.TestCase):
    def test_dropped_symbols_are_counted_in_a_warning(self):
        from pipeline.compare import delta_all
        prev = {"A": {"TT": 10, "TV": 0, "FB": 0, "FS": 0, "PTQ": 0, "PTV": 0}}
        curr = {"A": {"TT": 5, "TV": 0, "FB": 0, "FS": 0, "PTQ": 0, "PTV": 0}}
        with self.assertLogs("pipeline.compare", level="WARNING") as cm:
            self.assertEqual(delta_all(prev, curr), {})
        self.assertIn("1", cm.output[0])


class SourceSwitchTest(unittest.TestCase):
    def test_vci_rows_without_negotiated_data_keep_the_previous_values_and_do_not_drop_the_symbol(self):
        prev = [quote("AAA", pt_vol=900, pt_val=500_000)]
        row = {"SB": "AAA", "SRC": "VCI", "PT": False, **board(PTQ=0, PTV=0)}
        bars, _, quotes = process("VN", NOW, {"AAA": row}, prev, {}, TH_VN)
        self.assertEqual([b["symbol"] for b in bars], ["AAA"])
        self.assertEqual(bars[0]["pt_val"], 0)
        self.assertEqual((quotes[0]["pt_vol"], quotes[0]["pt_val"]), (900, 500_000))

    def test_heartbeat_names_the_source_and_flags_missing_negotiated_data(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s))
        with FakeServer(db) as srv:
            fetch = lambda syms: {k: {"SB": k, "SRC": "VCI", "PT": False, **board()} for k in SYMS}
            with self.assertLogs("pipeline.run", level="INFO"):
                main(["--market", "VN"], env_for(srv.url), now=NOW, fetch=fetch, symbols=SYMS, sleep=lambda x: None)
        detail = db.rows("heartbeat")[0]["detail"]
        self.assertEqual((detail["source"], detail["pt"]), ("VCI", False))

    def test_many_symbols_without_a_window_trigger_a_warning(self):
        db = FakeDB()
        db.put("quotes_latest", quote("AAA"))
        with FakeServer(db) as srv:
            fetch = lambda syms: {k: {"SB": k, "SRC": "KBS", **board()} for k in ("AAA", "BBB", "CCC")}
            with self.assertLogs("pipeline.run", level="WARNING") as cm:
                main(["--market", "VN"], env_for(srv.url), now=NOW, fetch=fetch, symbols=["AAA", "BBB", "CCC"],
                     sleep=lambda x: None)
        self.assertTrue(any("have a window" in line for line in cm.output))


class WriteOrderTest(unittest.TestCase):
    def test_the_slot_is_recorded_before_the_quotes_move_on(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s))
        with self.assertLogs("pipeline.run", level="INFO"):
            run(db, {"AAA": board(FB=60_500), "BBB": board()})
        self.assertLess(db.writes.index("snapshot_meta"), db.writes.index("quotes_latest"))


class LateRunTest(unittest.TestCase):
    LATE = datetime(2026, 10, 30, 3, 12, tzinfo=UTC)  # 10:12: the 09:50 run, delayed by 22 minutes

    def test_late_minutes_are_counted_from_the_latest_scheduled_run(self):
        self.assertEqual(late_minutes("VN", self.LATE), 22)

    def test_a_delayed_run_keeps_the_slot_it_was_scheduled_for(self):
        self.assertEqual(slot_start("VN", self.LATE), datetime(2026, 10, 30, 2, 30, tzinfo=UTC))

    def test_a_delayed_run_does_not_block_the_next_scheduled_one(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s))
        with self.assertLogs("pipeline.run", level="INFO"):
            run(db, {"AAA": board(TT=250_000), "BBB": board(TT=250_000)}, now=self.LATE)
        next_run = datetime(2026, 10, 30, 3, 21, tzinfo=UTC)  # 10:21, the 10:20 run
        with self.assertLogs("pipeline.run", level="INFO") as cm:
            run(db, {"AAA": board(TT=300_000), "BBB": board(TT=300_000)}, now=next_run)
        self.assertFalse(any("already" in line for line in cm.output))
        self.assertEqual(len(db.rows("snapshot_meta")), 2)

    def test_the_run_logs_a_warning_when_it_is_late(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s))
        with self.assertLogs("pipeline.run", level="WARNING") as cm:
            run(db, {"AAA": board(TT=250_000), "BBB": board(TT=250_000)}, now=self.LATE)
        self.assertTrue(any("late" in line for line in cm.output))

    def test_a_run_on_time_does_not_warn(self):
        self.assertLessEqual(late_minutes("VN", NOW), 10)


if __name__ == "__main__":
    unittest.main()


SUNDAY = datetime(2026, 11, 8, 7, 0, tzinfo=UTC)  # 14:00 Sunday in Ho Chi Minh
MONDAY_OPEN = datetime(2026, 11, 9, 2, 20, tzinfo=UTC)  # 09:20 Monday: the first run of the week


def refresh(db, rows, now=SUNDAY, symbols=SYMS):
    """Run `--refresh-quotes` with a fake feed; returns (exit code, how many times the feed was asked)."""
    asked = []

    def fetch(syms):
        asked.append(1)
        return {k: {"SB": k, "SRC": "KBS", **v} for k, v in rows.items()}
    with FakeServer(db) as s:
        code = main(["--market", "VN", "--refresh-quotes"], env_for(s.url), now=now, fetch=fetch, symbols=symbols,
                    sleep=lambda x: None)
    assert not db.violations, db.violations
    return code, len(asked)


class RefreshQuotesTest(unittest.TestCase):
    """TC-REFRESH: outside the run window the last close can be put into quotes_latest so the app has prices to show."""

    def test_the_weekend_close_is_written_to_quotes_and_nothing_else(self):  # TC-REFRESH-01
        db = FakeDB()
        code, asked = refresh(db, {s: board() for s in SYMS})
        self.assertEqual((code, asked), (0, 1))
        self.assertEqual(sorted(q["symbol"] for q in db.rows("quotes_latest")), SYMS)
        self.assertEqual(db.rows("quotes_latest")[0]["asof"], SUNDAY.isoformat())
        for table in ("snapshot_meta", "bars_30m", "signals", "heartbeat"):
            self.assertEqual(db.rows(table), [], table)

    def test_inside_the_run_window_it_does_nothing(self):  # TC-REFRESH-02
        db = FakeDB()
        code, asked = refresh(db, {s: board() for s in SYMS}, now=NOW)
        self.assertEqual((code, asked, db.rows("quotes_latest")), (0, 0, []))

    def test_a_feed_with_too_few_live_symbols_writes_nothing(self):  # TC-REFRESH-03
        db = FakeDB()
        code, _ = refresh(db, {"AAA": board()}, symbols=["AAA", "BBB", "CCC", "DDD"])  # 1 of 4 is below half
        self.assertEqual((code, db.rows("quotes_latest")), (1, []))

    def test_no_source_answering_is_an_error(self):
        from pipeline.sources.http import SourceError
        db = FakeDB()

        def down(syms):
            raise SourceError("down")
        with FakeServer(db) as s:
            code = main(["--market", "VN", "--refresh-quotes"], env_for(s.url), now=SUNDAY, fetch=down, symbols=SYMS,
                        sleep=lambda x: None)
        self.assertEqual((code, db.rows("quotes_latest")), (1, []))

    def test_the_first_run_after_a_refresh_still_counts_from_the_open(self):  # TC-REFRESH-04
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s, vol=900_000_000, asof=SUNDAY.isoformat()))
        code, _ = run(db, {s: board(TT=50_000) for s in SYMS}, now=MONDAY_OPEN)
        self.assertEqual(code, 0)
        self.assertEqual({b["vol"] for b in db.rows("bars_30m")}, {50_000})

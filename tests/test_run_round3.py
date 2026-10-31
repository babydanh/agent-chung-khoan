"""Round 3 review fixes for pipeline.run / supa (B1-B9)."""
import logging
import unittest
from datetime import datetime, timedelta, timezone

from pipeline import calendar, config
from pipeline.run import actual_minutes, closed, main, process, slot_start
from pipeline.supa import Supabase
from tests.fakedb import FakeDB
from tests.fakehttp import FakeServer
from tests.test_run import SYMS, board, env_for, quote

UTC = timezone.utc
NOW = datetime(2026, 10, 30, 2, 50, tzinfo=UTC)  # Friday 09:50 Ho Chi Minh
TH_VN = config.load("config/thresholds.json", "VN")
US_ENV = {"APCA_API_KEY_ID": "a", "APCA_API_SECRET_KEY": "b"}


def go(db, rows, now=NOW, market="VN", symbols=None, extra_env=None):
    with FakeServer(db) as srv:
        fetch = lambda syms: {k: {"SB": k, "SRC": "KBS", **v} for k, v in rows.items()}
        code = main(["--market", market], env_for(srv.url, **(extra_env or {})), now=now, fetch=fetch,
                    symbols=symbols or list(rows), sleep=lambda x: None)
        assert not db.violations, db.violations
        return code


def vci(**over):
    return {"SRC": "VCI", "PT": False, **board(**over)}


class NegotiatedCarryTest(unittest.TestCase):  # B1
    def setUp(self):
        self.yesterday = "2026-10-29T08:05:00+00:00"
        self.prev = [quote(s, vol=900_000, pt_vol=5_000, pt_val=9_000_000_000, asof=self.yesterday) for s in SYMS]

    def test_negotiated_totals_of_a_previous_day_are_never_carried_into_today(self):
        now = datetime(2026, 10, 30, 2, 20, tzinfo=UTC)  # first run of the day, 09:20
        rows = {s: {"SB": s, **vci(TT=50_000)} for s in SYMS}
        bars, sigs, quotes = process("VN", now, rows, self.prev, {}, TH_VN)
        self.assertEqual({b["pt_val"] for b in bars}, {0})
        self.assertNotIn("S3", [i["id"] for r in sigs for i in r["items"]])
        self.assertEqual({(q["pt_vol"], q["pt_val"]) for q in quotes}, {(0, 0)})

    def test_the_same_day_still_carries_the_previous_values(self):
        prev = [quote(s, pt_vol=900, pt_val=500_000, asof="2026-10-30T02:20:00+00:00") for s in SYMS]
        rows = {s: {"SB": s, **vci()} for s in SYMS}
        bars, _, quotes = process("VN", NOW, rows, prev, {}, TH_VN)
        self.assertEqual({q["pt_val"] for q in quotes}, {500_000})
        self.assertEqual({b["pt_val"] for b in bars}, {0})

    def test_end_to_end_no_s3_and_clean_quotes_after_a_vci_first_run(self):
        db = FakeDB()
        for q in self.prev:
            db.put("quotes_latest", q)
        go(db, {s: vci(TT=50_000) for s in SYMS}, now=datetime(2026, 10, 30, 2, 20, tzinfo=UTC))
        self.assertEqual({r["pt_val"] for r in db.rows("bars_30m")}, {0})
        self.assertEqual({r["pt_val"] for r in db.rows("quotes_latest")}, {0})
        self.assertEqual(db.rows("signals"), [])


class ClosedWithoutNegotiatedDataTest(unittest.TestCase):  # B2
    def feed(self, n=29):
        syms = [f"S{i:02d}" for i in range(n)]
        prev = {s: {"TT": 100, "PTQ": 500 if i < 2 else 0, "PTV": 1 if i < 2 else 0} for i, s in enumerate(syms)}
        curr = {s: {"TT": 100, "PTQ": 0, "PTV": 0, "PT": False} for s in syms}
        return syms, prev, curr

    def test_negotiated_fields_are_ignored_when_the_source_has_none(self):
        _, prev, curr = self.feed()
        self.assertTrue(closed(prev, curr))

    def test_with_negotiated_data_a_change_still_counts_as_movement(self):
        _, prev, curr = self.feed()
        for r in curr.values():
            r["PT"] = True
        self.assertFalse(closed(prev, curr))

    def test_stuck_vci_feed_is_reported_not_ok(self):
        syms, _, curr = self.feed()
        db = FakeDB()
        for i, s in enumerate(syms):
            db.put("quotes_latest", quote(s, vol=100, pt_vol=500 if i < 2 else 0, pt_val=1 if i < 2 else 0))
        rows = {s: {"SB": s, **vci(TT=100)} for s in syms}
        with self.assertLogs("pipeline.run", level="WARNING"):
            code = go(db, rows, symbols=syms)
        self.assertEqual(code, 1)
        self.assertEqual(db.rows("heartbeat")[0]["detail"]["status"], "closed")
        self.assertEqual(db.rows("snapshot_meta"), [])


class EarlyCloseTest(unittest.TestCase):  # B3
    EARLY_DAY = datetime(2026, 11, 27, 18, 35, tzinfo=UTC)  # 13:35 EST, market closed since 13:00

    def test_minutes_use_the_early_session(self):
        prev = datetime(2026, 11, 27, 18, 5, tzinfo=UTC)
        from pipeline.signals import US_EARLY_SESSIONS, US_SESSIONS
        self.assertEqual(actual_minutes("US", prev, self.EARLY_DAY, sessions=US_SESSIONS), 30)
        self.assertEqual(actual_minutes("US", prev, self.EARLY_DAY, sessions=US_EARLY_SESSIONS), 0)

    def run_us(self, now):
        db = FakeDB()
        prev_at = (now - timedelta(minutes=30)).isoformat()
        for s in SYMS:
            db.put("quotes_latest", quote(s, market="US", vol=200_000, asof=prev_at))
        with self.assertLogs("pipeline.run", level="INFO"):
            code = go(db, {s: board() for s in SYMS}, now=now, market="US", extra_env=US_ENV)
        return code, db

    def test_after_an_early_close_the_flat_runs_are_not_flagged_as_closed(self):
        for now in (self.EARLY_DAY, datetime(2026, 11, 27, 19, 5, tzinfo=UTC)):  # 13:35 and 14:05 ET
            code, db = self.run_us(now)
            self.assertEqual(code, 0, now)
            self.assertEqual(len(db.rows("snapshot_meta")), 1)

    def test_a_regular_day_flat_run_at_the_same_clock_time_is_still_closed(self):
        code, _ = self.run_us(datetime(2026, 11, 25, 18, 35, tzinfo=UTC))  # Wednesday, 13:35 EST, market open
        self.assertEqual(code, 1)


class NoWindowsTest(unittest.TestCase):  # B4
    def test_a_feed_reset_on_a_later_run_is_an_error_without_a_snapshot(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s, vol=900_000_000, asof="2026-10-30T02:20:00+00:00"))
        with self.assertLogs("pipeline.run", level="ERROR"):
            code = go(db, {s: board(TT=200_000) for s in SYMS})
        self.assertEqual(code, 1)
        self.assertEqual((db.rows("snapshot_meta"), db.rows("bars_30m")), ([], []))
        hb = db.rows("heartbeat")[0]["detail"]
        self.assertEqual((hb["status"], hb["deltas"]), ("no_windows", 0))
        # the baseline moves on, so the next run is not stuck behind the reset
        self.assertEqual({q["vol"] for q in db.rows("quotes_latest")}, {200_000})

    def test_the_first_run_of_a_day_never_trips_it(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s, vol=900_000_000, asof="2026-10-29T08:05:00+00:00"))
        code = go(db, {s: board(TT=50_000) for s in SYMS}, now=datetime(2026, 10, 30, 2, 20, tzinfo=UTC))
        self.assertEqual(code, 0)

    def test_half_of_the_symbols_with_a_window_is_enough(self):
        db = FakeDB()
        db.put("quotes_latest", quote("AAA", asof="2026-10-30T02:20:00+00:00"))
        db.put("quotes_latest", quote("BBB", vol=900_000_000, asof="2026-10-30T02:20:00+00:00"))
        self.assertEqual(go(db, {s: board() for s in SYMS}), 0)


class ResumeTest(unittest.TestCase):  # B5
    def setUp(self):
        self.db = FakeDB()
        for s in SYMS:
            self.db.put("quotes_latest", quote(s))
        self.rows = {s: board(TT=250_000) for s in SYMS}

    def test_a_crash_between_snapshot_and_quotes_is_finished_by_the_rerun(self):
        self.db.fail = {"quotes_latest"}
        with self.assertRaises(Exception):
            go(self.db, self.rows)
        self.assertEqual(len(self.db.rows("snapshot_meta")), 1)
        self.db.fail = set()
        later = NOW + timedelta(minutes=3)
        with self.assertLogs("pipeline.run", level="WARNING") as cm:
            code = go(self.db, self.rows, now=later)
        self.assertEqual(code, 0)
        self.assertTrue(any("finishing" in line for line in cm.output))
        self.assertEqual({q["asof"] for q in self.db.rows("quotes_latest")}, {later.isoformat()})
        self.assertEqual(self.db.rows("heartbeat")[0]["last_seen"], later.isoformat())
        self.assertEqual(len(self.db.rows("bars_30m")), 2)  # untouched

    def test_a_missing_heartbeat_alone_is_also_finished(self):
        self.db.fail = {"heartbeat"}
        self.assertEqual(go(self.db, self.rows), 1)  # the first run reports the heartbeat failure
        self.db.fail = set()
        with self.assertLogs("pipeline.run", level="WARNING"):
            code = go(self.db, self.rows, now=NOW + timedelta(minutes=2))
        self.assertEqual(code, 0)
        self.assertEqual(len(self.db.rows("heartbeat")), 1)

    def test_a_completed_slot_is_skipped_quietly(self):
        go(self.db, self.rows)
        writes = len(self.db.writes)
        with self.assertLogs("pipeline.run", level="INFO") as cm:
            self.assertEqual(go(self.db, self.rows, now=NOW + timedelta(minutes=2)), 0)
        self.assertTrue(any("already" in line for line in cm.output))
        self.assertEqual(len(self.db.writes), writes)


class MissedSlotTest(unittest.TestCase):  # B6
    def test_a_run_delayed_past_the_next_schedule_reports_the_slot_it_missed(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s, asof="2026-10-30T01:50:00+00:00"))
        late = datetime(2026, 10, 30, 2, 55, tzinfo=UTC)  # the 09:20 run, executing at 09:55
        self.assertEqual(slot_start("VN", late), datetime(2026, 10, 30, 2, 30, tzinfo=UTC))
        with self.assertLogs("pipeline.run", level="WARNING") as cm:
            code = go(db, {s: board(TT=250_000) for s in SYMS}, now=late)
        self.assertEqual(code, 0)
        self.assertEqual(db.rows("heartbeat")[0]["detail"]["missed_slots"], ["2026-10-30T02:00:00+00:00"])
        self.assertTrue(any("missed" in line for line in cm.output))

    def test_the_lunch_gap_case(self):
        db = FakeDB()
        done = ["02:00", "02:30", "03:00", "03:30"]  # 09:00 .. 10:30 recorded, 11:00 is not
        for hm in done:
            db.put("snapshot_meta", {"market": "VN", "slot_start": f"2026-10-30T{hm}:00+00:00",
                                     "asof": f"2026-10-30T{hm}:00+00:00", "symbols": 2, "signals": 0})
        for s in SYMS:
            db.put("quotes_latest", quote(s, asof="2026-10-30T03:35:00+00:00"))
        late = datetime(2026, 10, 30, 4, 45, tzinfo=UTC)  # the 11:20 run, executing at 11:45 (after the 11:40 time)
        code = go(db, {s: board(TT=250_000) for s in SYMS}, now=late)
        self.assertEqual(code, 0)
        self.assertEqual(db.rows("heartbeat")[0]["detail"]["missed_slots"], ["2026-10-30T04:00:00+00:00"])

    def test_nothing_missed_when_every_earlier_slot_is_recorded(self):
        db = FakeDB()
        db.put("snapshot_meta", {"market": "VN", "slot_start": "2026-10-30T02:00:00+00:00",
                                 "asof": "2026-10-30T02:00:00+00:00", "symbols": 2, "signals": 0})
        for s in SYMS:
            db.put("quotes_latest", quote(s))
        go(db, {s: board(TT=250_000) for s in SYMS})
        self.assertEqual(db.rows("heartbeat")[0]["detail"]["missed_slots"], [])


class LongWindowTest(unittest.TestCase):  # B7
    def test_a_bar_over_forty_five_minutes_is_not_written_into_the_baseline(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s, asof="2026-10-30T02:00:00+00:00"))  # 09:00 -> 09:50 is 50 minutes
        with self.assertLogs("pipeline.run", level="WARNING"):
            code = go(db, {s: board(TT=250_000) for s in SYMS})
        self.assertEqual(code, 0)
        self.assertEqual(db.rows("bars_30m"), [])
        detail = db.rows("heartbeat")[0]["detail"]
        self.assertEqual(detail["s1_skipped"], "window_too_long")
        self.assertEqual(len(db.rows("snapshot_meta")), 1)

    def test_a_normal_window_still_writes_its_bar(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s))
        go(db, {s: board(TT=250_000) for s in SYMS})
        self.assertEqual(len(db.rows("bars_30m")), 2)


class OrderedPagingTest(unittest.TestCase):  # B8
    def test_select_all_needs_an_explicit_order(self):
        with FakeServer(FakeDB()) as s:
            with self.assertRaises(ValueError):
                Supabase(s.url, "K", sleep=lambda x: None).select_all("bars_30m", {"select": "*"})

    def test_pages_come_back_complete_when_the_server_orders_them(self):
        db = FakeDB()
        for i in range(2500):
            db.put("bars_30m", {"market": "VN", "symbol": f"S{i:04d}", "bar_start": "2026-10-29T02:30:00+00:00",
                                "vol": i, "val": 1, "fnet": 0, "pt_val": 0})
        with FakeServer(db) as s:
            rows = Supabase(s.url, "K", sleep=lambda x: None).select_all(
                "bars_30m", {"select": "symbol,vol"}, order="market.asc,symbol.asc,bar_start.asc")
        self.assertEqual(sorted(r["vol"] for r in rows), list(range(2500)))

    def test_history_sees_every_symbol_when_there_are_more_than_one_page_of_bars(self):
        from pipeline.run import _history
        db = FakeDB()
        base = datetime(2026, 10, 30, 2, 30, tzinfo=UTC)
        for sym in range(60):
            for day in range(1, 26):
                db.put("bars_30m", {"market": "VN", "symbol": f"S{sym:02d}",
                                    "bar_start": (base - timedelta(days=day)).isoformat(),
                                    "vol": 1000 + day, "val": 1, "fnet": 0, "pt_val": 0})
        with FakeServer(db) as s:
            hist = _history(Supabase(s.url, "K", sleep=lambda x: None), "VN", base, NOW)
        self.assertEqual({len(v) for v in hist.values()}, {20})
        self.assertEqual(len(hist), 60)

    def test_cleanup_and_run_reads_all_carry_an_order(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s))
        go(db, {s: board(TT=250_000) for s in SYMS})
        paged = [(t, q) for t, q in db.reads if t in ("bars_30m", "quotes_latest") and "offset" in q]
        self.assertTrue(paged)
        for t, q in paged:
            self.assertIn("order", q, t)


class HeartbeatDetailTest(unittest.TestCase):  # B9
    def test_detail_names_every_health_number(self):
        db = FakeDB()
        db.put("snapshot_meta", {"market": "VN", "slot_start": "2026-10-30T02:00:00+00:00",
                                 "asof": "2026-10-30T02:00:00+00:00", "symbols": 2, "signals": 0})
        for s in SYMS:
            db.put("quotes_latest", quote(s))
        go(db, {s: board(TT=250_000) for s in SYMS}, symbols=SYMS + ["CCC", "DDD"])
        d = db.rows("heartbeat")[0]["detail"]
        self.assertEqual((d["status"], d["source"], d["pt"]), ("ok", "KBS", True))
        self.assertEqual((d["symbols"], d["requested"], d["missing"], d["deltas"]), (2, 4, 2, 2))
        self.assertEqual((d["late_minutes"], d["s1_skipped"]), (0, None))
        self.assertEqual(d["missed_slots"], [])

    def test_post_close_run_says_why_s1_was_skipped(self):
        db = FakeDB()
        now = datetime(2026, 10, 30, 8, 5, tzinfo=UTC)  # 15:05
        for s in SYMS:
            db.put("quotes_latest", quote(s, asof="2026-10-30T07:50:00+00:00"))
        go(db, {s: board(TT=250_000) for s in SYMS}, now=now)
        self.assertEqual(db.rows("heartbeat")[0]["detail"]["s1_skipped"], "no_trading_minutes")

    def test_late_minutes_are_recorded(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s))
        go(db, {s: board(TT=250_000) for s in SYMS}, now=datetime(2026, 10, 30, 3, 12, tzinfo=UTC))
        self.assertEqual(db.rows("heartbeat")[0]["detail"]["late_minutes"], 22)

    def test_pt_flag_is_false_for_a_vci_run(self):
        db = FakeDB()
        for s in SYMS:
            db.put("quotes_latest", quote(s))
        go(db, {s: vci(TT=250_000) for s in SYMS})
        d = db.rows("heartbeat")[0]["detail"]
        self.assertEqual((d["source"], d["pt"]), ("VCI", False))


if __name__ == "__main__":
    unittest.main()

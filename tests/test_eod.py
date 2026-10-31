import json
import unittest
from datetime import date, datetime, timedelta, timezone

from pipeline import calendar
from pipeline.eod import check_market, main
from pipeline.run import expected_runs, expected_slots
from tests.fakedb import FakeDB
from tests.fakehttp import FakeServer
from pipeline.supa import Supabase

UTC = timezone.utc
CAL = {"VN": {"holidays": ["2026-11-02"]},
       "US": {"holidays": ["2026-11-26"], "early_close": ["2026-11-27"]}}
FRI = date(2026, 10, 30)  # a VN trading day, US still on daylight time


def meta(db, market, slots):
    for s in slots:
        db.put("snapshot_meta", {"market": market, "slot_start": s.isoformat(), "asof": s.isoformat(),
                                 "symbols": 1, "signals": 0})


def beat(db, market, at):
    db.put("heartbeat", {"market": market, "job": "snapshot", "last_seen": at.isoformat(), "detail": {}})


def client(db):
    srv = FakeServer(db).__enter__()
    client.servers.append(srv)
    return Supabase(srv.url, "K", sleep=lambda x: None)


client.servers = []


def tearDownModule():
    for s in client.servers:
        s.__exit__(None, None, None)


class ExpectedSlotsTest(unittest.TestCase):
    def test_vn_has_eleven_slots_on_a_trading_day(self):
        slots = expected_slots("VN", FRI, CAL)
        self.assertEqual(len(slots), 11)
        self.assertEqual(len(set(slots)), 11)
        self.assertEqual(slots[0], datetime(2026, 10, 30, 2, 0, tzinfo=UTC))  # 09:00 Ho Chi Minh

    def test_us_has_fourteen_slots_on_a_regular_day(self):
        self.assertEqual(len(expected_slots("US", FRI, CAL)), 14)

    def test_weekend_and_holidays_expect_nothing(self):
        self.assertEqual(expected_slots("VN", date(2026, 10, 31), CAL), [])  # Saturday
        self.assertEqual(expected_slots("VN", date(2026, 11, 2), CAL), [])   # listed holiday
        self.assertEqual(expected_slots("US", date(2026, 11, 26), CAL), [])

    def test_early_close_day_expects_only_runs_inside_the_shorter_window(self):
        early = expected_runs("US", date(2026, 11, 27), CAL)
        regular = expected_runs("US", date(2026, 11, 25), CAL)
        self.assertLess(len(early), len(regular))
        self.assertTrue(all(r.astimezone(calendar.TZ["US"]).time() <= datetime(2000, 1, 1, 14, 20).time()
                            for r, _ in early))


class CheckMarketTest(unittest.TestCase):
    NOW = datetime(2026, 10, 30, 11, 0, tzinfo=UTC)  # 18:00 Ho Chi Minh, after the last VN run

    def test_a_complete_day_has_no_problems(self):
        db = FakeDB()
        slots = expected_slots("VN", FRI, CAL)
        meta(db, "VN", slots)
        beat(db, "VN", datetime(2026, 10, 30, 8, 5, tzinfo=UTC))
        problems, summary = check_market(client(db), "VN", self.NOW, CAL)
        self.assertEqual(problems, [])
        self.assertIn("11/11", summary)

    def test_missing_slots_are_listed(self):
        db = FakeDB()
        slots = expected_slots("VN", FRI, CAL)
        meta(db, "VN", slots[:4] + slots[6:])
        beat(db, "VN", datetime(2026, 10, 30, 8, 5, tzinfo=UTC))
        problems, summary = check_market(client(db), "VN", self.NOW, CAL)
        self.assertEqual(len(problems), 1)
        self.assertIn("2 slot", problems[0])
        self.assertIn("9/11", summary)

    def test_a_dead_heartbeat_is_reported_even_when_the_slots_exist(self):
        db = FakeDB()
        meta(db, "VN", expected_slots("VN", FRI, CAL))
        beat(db, "VN", datetime(2026, 10, 29, 8, 5, tzinfo=UTC))  # yesterday's last run
        problems, _ = check_market(client(db), "VN", self.NOW, CAL)
        self.assertTrue(any("heartbeat" in p for p in problems))

    def test_no_heartbeat_row_at_all_is_a_problem(self):
        db = FakeDB()
        meta(db, "VN", expected_slots("VN", FRI, CAL))
        problems, _ = check_market(client(db), "VN", self.NOW, CAL)
        self.assertTrue(any("heartbeat" in p for p in problems))

    def test_a_day_that_is_not_over_yet_is_not_judged(self):
        db = FakeDB()
        midday = datetime(2026, 10, 30, 5, 0, tzinfo=UTC)  # 12:00 in Ho Chi Minh: the afternoon runs are still to come
        # the previous trading day (Thursday) is judged instead
        meta(db, "VN", expected_slots("VN", date(2026, 10, 29), CAL))
        beat(db, "VN", datetime(2026, 10, 29, 8, 5, tzinfo=UTC))
        problems, summary = check_market(client(db), "VN", midday, CAL)
        self.assertEqual(problems, [])
        self.assertIn("2026-10-29", summary)

    def test_holiday_is_skipped_back_to_the_last_trading_day(self):
        db = FakeDB()
        monday_evening = datetime(2026, 11, 2, 11, 0, tzinfo=UTC)  # Monday, a listed VN holiday
        meta(db, "VN", expected_slots("VN", FRI, CAL))
        beat(db, "VN", datetime(2026, 10, 30, 8, 5, tzinfo=UTC))
        problems, summary = check_market(client(db), "VN", monday_evening, CAL)
        self.assertEqual(problems, [])
        self.assertIn("2026-10-30", summary)

    def test_other_markets_rows_do_not_count(self):
        db = FakeDB()
        meta(db, "US", expected_slots("VN", FRI, CAL))  # wrong market
        beat(db, "VN", datetime(2026, 10, 30, 8, 5, tzinfo=UTC))
        problems, _ = check_market(client(db), "VN", self.NOW, CAL)
        self.assertTrue(problems)

    def test_more_than_a_page_of_rows_is_counted_completely(self):
        db = FakeDB()
        slots = expected_slots("VN", FRI, CAL)
        meta(db, "VN", slots)
        for i in range(1200):  # old days push the table past one page
            db.put("snapshot_meta", {"market": "VN", "slot_start": (datetime(2026, 1, 1, tzinfo=UTC)
                                     + timedelta(minutes=30 * i)).isoformat(), "asof": "x", "symbols": 1, "signals": 0})
        beat(db, "VN", datetime(2026, 10, 30, 8, 5, tzinfo=UTC))
        problems, _ = check_market(client(db), "VN", self.NOW, CAL)
        self.assertEqual(problems, [])


class MainTest(unittest.TestCase):
    def test_exit_status_and_detail_file(self):
        import tempfile, os
        db = FakeDB()
        slots = expected_slots("VN", FRI, CAL)
        meta(db, "VN", slots[:3])
        beat(db, "VN", datetime(2026, 10, 30, 8, 5, tzinfo=UTC))
        meta(db, "US", expected_slots("US", FRI, CAL))
        beat(db, "US", datetime(2026, 10, 30, 21, 0, tzinfo=UTC))
        path = os.path.join(tempfile.mkdtemp(), "alert.txt")
        with FakeServer(db) as s:
            with self.assertLogs("pipeline.eod", level="WARNING"):
                code = main({"SUPABASE_URL": s.url, "SUPABASE_SECRET_KEY": "k", "ALERT_DETAIL_FILE": path},
                            now=datetime(2026, 10, 30, 11, 0, tzinfo=UTC), cal=CAL)
        self.assertEqual(code, 1)
        text = open(path, encoding="utf-8").read()
        self.assertIn("VN", text)
        os.unlink(path)

    def test_clean_day_exits_zero_and_writes_no_detail(self):
        import tempfile, os
        db = FakeDB()
        for m in ("VN", "US"):
            meta(db, m, expected_slots(m, FRI, CAL))
        beat(db, "VN", datetime(2026, 10, 30, 8, 5, tzinfo=UTC))
        beat(db, "US", datetime(2026, 10, 30, 21, 0, tzinfo=UTC))
        path = os.path.join(tempfile.mkdtemp(), "alert.txt")
        with FakeServer(db) as s:
            code = main({"SUPABASE_URL": s.url, "SUPABASE_SECRET_KEY": "k", "ALERT_DETAIL_FILE": path},
                        now=datetime(2026, 10, 30, 23, 0, tzinfo=UTC), cal=CAL)
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(path))

    def test_missing_secrets_exit_two(self):
        self.assertEqual(main({}, now=datetime(2026, 10, 30, 11, 0, tzinfo=UTC), cal=CAL), 2)


if __name__ == "__main__":
    unittest.main()

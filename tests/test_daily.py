import unittest
from datetime import datetime, timezone

from pipeline import daily
from pipeline.sources.http import SourceError
from pipeline.supa import Supabase
from tests.fakedb import FakeDB
from tests.fakehttp import FakeServer

NOW = datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc)
# VCI answers one symbol as parallel arrays; t is epoch seconds at 00:00 UTC = 07:00 in Ho Chi Minh City
VCI = {"symbol": "FPT", "o": [52400, 50300], "h": [52500, 51700], "l": [50100, 49550], "c": [50200, 50400],
       "v": [12293400, 9249300], "t": ["1793577600", "1793664000"], "accumulatedValue": [625753.86, 465686.92]}
KBS = {"symbol": "FPT", "data_day": [
    {"t": "2026-11-03 07:00", "o": 50300, "h": 51700, "l": 49550, "c": 50400, "v": 9249300, "va": 465686920000},
    {"t": "2026-11-02 07:00", "o": 52400, "h": 52500, "l": 50100, "c": 50200, "v": 12293400, "va": 625753860000}]}


def row(symbol, date, close):
    return {"market": "VN", "symbol": symbol, "trade_date": date, "open": close, "high": close, "low": close,
            "close": close, "vol": 1, "val": 1}


class ParseTest(unittest.TestCase):
    def test_vci_arrays_become_one_row_per_day(self):  # TC-DAILY-01
        rows = daily.parse_vci(VCI)
        self.assertEqual([r["trade_date"] for r in rows], ["2026-11-02", "2026-11-03"])
        self.assertEqual(rows[0], {"market": "VN", "symbol": "FPT", "trade_date": "2026-11-02", "open": 52400,
                                   "high": 52500, "low": 50100, "close": 50200, "vol": 12293400, "val": 625753860000})

    def test_vci_skips_days_without_a_close_and_ignores_ragged_arrays(self):  # TC-DAILY-02
        bad = {**VCI, "c": [None, 50400]}
        self.assertEqual([r["trade_date"] for r in daily.parse_vci(bad)], ["2026-11-03"])
        self.assertEqual(daily.parse_vci({**VCI, "c": [1]}), [])

    def test_kbs_rows_become_the_same_shape_oldest_first(self):  # TC-DAILY-03
        rows = daily.parse_kbs(KBS)
        self.assertEqual([r["trade_date"] for r in rows], ["2026-11-02", "2026-11-03"])
        self.assertEqual(rows, daily.parse_vci(VCI))


class FetchTest(unittest.TestCase):
    def fetch(self, handler):
        with FakeServer(handler) as s:
            return daily.fetch_symbol("FPT", 90, NOW, vci_url=s.url + "/vci", kbs_url=s.url + "/kbs", sleep=lambda x: None), s.requests

    def test_vci_is_asked_for_one_symbol_and_the_day_count(self):  # TC-DAILY-04
        rows, reqs = self.fetch(lambda m, p, h, b: (200, [VCI]))
        self.assertEqual(len(rows), 2)
        self.assertEqual(reqs[0]["body"]["symbols"], ["FPT"])
        self.assertEqual(reqs[0]["body"]["countBack"], 90)
        self.assertEqual(reqs[0]["body"]["timeFrame"], "ONE_DAY")
        self.assertEqual(len(reqs), 1)

    def test_kbs_answers_when_vci_is_empty_or_down(self):  # TC-DAILY-05
        for vci in ((200, []), (500, {})):
            rows, reqs = self.fetch(lambda m, p, h, b, v=vci: v if p.startswith("/vci") else (200, KBS))
            self.assertEqual(len(rows), 2, vci)
            self.assertTrue(any(r["path"].startswith("/kbs/FPT/data_day?sdate=") for r in reqs))

    def test_both_sources_empty_is_an_error_not_an_empty_success(self):  # TC-DAILY-06
        with FakeServer(lambda m, p, h, b: (200, [] if p.startswith("/vci") else {"data_day": []})) as s:
            with self.assertRaises(SourceError):
                daily.fetch_symbol("FPT", 90, NOW, vci_url=s.url + "/vci", kbs_url=s.url + "/kbs", sleep=lambda x: None)


class RunTest(unittest.TestCase):
    def db(self, fake, s):
        return Supabase(s.url, "K", sleep=lambda x: None)

    def test_symbols_are_the_three_character_vn_codes_in_quotes_latest(self):  # TC-DAILY-07
        fake = FakeDB()
        for sym, mk in (("FPT", "VN"), ("VCB", "VN"), ("CFPT2401", "VN"), ("AAPL", "US"), ("HPG", "VN")):
            fake.put("quotes_latest", {"market": mk, "symbol": sym})
        with FakeServer(fake) as s:
            self.assertEqual(daily.vn_symbols(Supabase(s.url, "K", sleep=lambda x: None)), ["FPT", "HPG", "VCB"])

    def test_rows_are_stored_under_the_table_key_and_a_rerun_adds_nothing(self):  # TC-DAILY-08
        fake = FakeDB()
        fetch = lambda sym, days, now, **kw: [row(sym, "2026-11-06", 10), row(sym, "2026-11-09", 11)]
        with FakeServer(fake) as s:
            self.assertEqual(daily.run(self.db(fake, s), ["FPT", "VCB"], 90, NOW, fetch=fetch), 0)
            self.assertEqual(daily.run(self.db(fake, s), ["FPT", "VCB"], 90, NOW, fetch=fetch), 0)
        self.assertEqual(len(fake.rows("bars_1d")), 4)
        self.assertEqual(fake.violations, [])

    def test_a_rerun_overwrites_a_day_that_was_still_open(self):  # TC-DAILY-09
        fake = FakeDB()
        fake.put("bars_1d", row("FPT", "2026-11-09", 10))
        with FakeServer(fake) as s:
            daily.run(self.db(fake, s), ["FPT"], 5, NOW, fetch=lambda *a, **k: [row("FPT", "2026-11-09", 12)])
        self.assertEqual([r["close"] for r in fake.rows("bars_1d")], [12])

    def test_one_broken_symbol_does_not_stop_the_rest(self):  # TC-DAILY-10
        fake = FakeDB()

        def fetch(sym, days, now, **kw):
            if sym == "BAD":
                raise SourceError("down")
            return [row(sym, "2026-11-06", 10)]

        syms = [f"A{i:02d}" for i in range(40)] + ["BAD"]
        with FakeServer(fake) as s:
            with self.assertLogs("pipeline.daily", level="WARNING"):
                self.assertEqual(daily.run(self.db(fake, s), syms, 90, NOW, fetch=fetch), 0)
        self.assertEqual(len(fake.rows("bars_1d")), 40)

    def test_many_failures_fail_the_job(self):  # TC-DAILY-11
        fake = FakeDB()
        fetch = lambda sym, days, now, **kw: (_ for _ in ()).throw(SourceError("down"))
        with FakeServer(fake) as s:
            with self.assertLogs("pipeline.daily", level="WARNING"):
                self.assertEqual(daily.run(self.db(fake, s), ["FPT", "VCB"], 90, NOW, fetch=fetch), 1)
        self.assertEqual(fake.rows("bars_1d"), [])

    def test_no_symbols_is_a_failure_not_a_quiet_success(self):  # TC-DAILY-12
        fake = FakeDB()
        with FakeServer(fake) as s:
            with self.assertLogs("pipeline.daily", level="ERROR"):
                self.assertEqual(daily.run(self.db(fake, s), [], 90, NOW, fetch=lambda *a, **k: []), 1)

    def test_main_needs_the_database_environment(self):  # TC-DAILY-13
        self.assertEqual(daily.main({}), 2)

    def test_days_come_from_the_environment_and_are_bounded(self):  # TC-DAILY-14
        self.assertEqual(daily.days_from({}), 7)
        self.assertEqual(daily.days_from({"DAILY_DAYS": "90"}), 90)
        for bad in ("0", "-3", "x", "5000", ""):
            self.assertEqual(daily.days_from({"DAILY_DAYS": bad}), 7, bad)


if __name__ == "__main__":
    unittest.main()

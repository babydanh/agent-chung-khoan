import logging
import unittest
from datetime import datetime, timedelta, timezone

from pipeline.cleanup import bars_cutoff, db_report, run, signals_cutoff
from pipeline.supa import Supabase
from tests.fakehttp import FakeServer

UTC = timezone.utc
NOW = datetime(2026, 10, 30, 8, 0, tzinfo=UTC)


def days(n):
    """n distinct session days, newest first, two bars each."""
    out = []
    for i in range(n):
        d = NOW - timedelta(days=i)
        out += [d.replace(hour=3).isoformat(), d.replace(hour=4).isoformat()]
    return out


class CutoffTest(unittest.TestCase):
    def test_nothing_to_delete_up_to_forty_sessions(self):
        self.assertIsNone(bars_cutoff(days(40)))
        self.assertIsNone(bars_cutoff([]))

    def test_cutoff_is_the_start_of_the_oldest_kept_session(self):
        cut = bars_cutoff(days(45))
        self.assertEqual(cut, (NOW - timedelta(days=39)).replace(hour=0, minute=0, second=0, microsecond=0))

    def test_two_bars_on_one_day_count_as_one_session(self):
        self.assertIsNone(bars_cutoff(days(40) + days(1)))

    def test_keep_is_adjustable(self):
        self.assertIsNotNone(bars_cutoff(days(5), keep=3))

    def test_signals_cutoff_is_thirty_days_back(self):
        self.assertEqual(signals_cutoff(NOW), NOW - timedelta(days=30))


class ReportTest(unittest.TestCase):
    def test_under_limit_is_info(self):
        self.assertEqual(db_report(120.5)[0], "info")

    def test_over_400_mb_is_a_warning(self):
        level, msg = db_report(401)
        self.assertEqual(level, "warning")
        self.assertIn("db_mb=401", msg)

    def test_exactly_400_is_still_fine(self):
        self.assertEqual(db_report(400)[0], "info")

    def test_unknown_size_is_a_warning_not_a_crash(self):
        self.assertEqual(db_report(None)[0], "warning")


class RunTest(unittest.TestCase):
    def handler(self, bar_rows, size=12.0):
        def h(method, path, headers, body):
            if method == "GET" and "/bars_30m" in path:
                return 200, bar_rows if "offset=0" in path else []
            if "/rpc/db_size_mb" in path:
                return 200, size
            return 200, None
        return h

    def test_deletes_old_bars_and_signals_and_logs_db_mb(self):
        rows = [{"bar_start": s} for s in days(45)]
        with FakeServer(self.handler(rows)) as s:
            with self.assertLogs("pipeline.cleanup", level="INFO") as cm:
                run(Supabase(s.url, "K", sleep=lambda x: None), NOW)
            deletes = [r["path"] for r in s.requests if r["method"] == "DELETE"]
        self.assertEqual(len(deletes), 2)
        self.assertTrue(any(p.startswith("/rest/v1/bars_30m?bar_start=lt.") for p in deletes))
        self.assertTrue(any(p.startswith("/rest/v1/signals?asof=lt.") for p in deletes))
        self.assertTrue(any("db_mb=12.0" in line for line in cm.output))

    def test_exit_status_is_zero_when_the_size_is_known_and_small(self):
        with FakeServer(self.handler([], size=12.0)) as s:
            with self.assertLogs("pipeline.cleanup", level="INFO"):
                self.assertEqual(run(Supabase(s.url, "K", sleep=lambda x: None), NOW), 0)

    def test_over_400_mb_fails_the_run(self):
        with FakeServer(self.handler([], size=450.0)) as s:
            with self.assertLogs("pipeline.cleanup", level="WARNING"):
                self.assertEqual(run(Supabase(s.url, "K", sleep=lambda x: None), NOW), 1)

    def test_unavailable_size_fails_the_run(self):
        def h(method, path, headers, body):
            return (404, {}) if "/rpc/db_size_mb" in path else (200, [] if method == "GET" else None)

        with FakeServer(h) as s:
            with self.assertLogs("pipeline.cleanup", level="WARNING"):
                self.assertEqual(run(Supabase(s.url, "K", sleep=lambda x: None), NOW), 1)

    def test_main_returns_the_run_status(self):
        import pipeline.cleanup as c
        with FakeServer(self.handler([], size=999.0)) as s:
            with self.assertLogs("pipeline.cleanup", level="WARNING"):
                code = c.main({"SUPABASE_URL": s.url, "SUPABASE_SECRET_KEY": "k"}, now=NOW)
        self.assertEqual(code, 1)

    def test_short_history_skips_the_bars_delete(self):
        with FakeServer(self.handler([{"bar_start": s} for s in days(10)])) as s:
            with self.assertLogs("pipeline.cleanup", level="INFO"):
                run(Supabase(s.url, "K", sleep=lambda x: None), NOW)
            deletes = [r["path"] for r in s.requests if r["method"] == "DELETE"]
        self.assertEqual(len(deletes), 1)
        self.assertIn("/signals", deletes[0])


if __name__ == "__main__":
    unittest.main()

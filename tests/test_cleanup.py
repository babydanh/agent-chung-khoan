import unittest
from datetime import datetime, timezone

from pipeline.cleanup import db_report, run
from pipeline.supa import Supabase
from tests.fakehttp import FakeServer

NOW = datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc)
DELETED = {"signals": 1, "bars_30m": 2, "snapshot_meta": 0, "snapshot_compact": 3, "zones": 4, "news": 5, "digests": 6, "heartbeat": 7}


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
    """Retention lives in SQL (cleanup_old_data, see docs/schema.md); the job only calls it and reports the size."""

    def handler(self, size=12.0, cleanup=(200, DELETED)):
        def h(method, path, headers, body):
            if "/rpc/db_size_mb" in path:
                return 200, size
            if "/rpc/cleanup_old_data" in path:
                return cleanup
            return 200, None
        return h

    def db(self, s):
        return Supabase(s.url, "K", sleep=lambda x: None)

    def test_calls_the_sql_retention_function_and_never_deletes_by_itself(self):
        with FakeServer(self.handler()) as s:
            with self.assertLogs("pipeline.cleanup", level="INFO") as cm:
                self.assertEqual(run(self.db(s), NOW), 0)
            reqs = [(r["method"], r["path"]) for r in s.requests]
        self.assertIn(("POST", "/rest/v1/rpc/cleanup_old_data"), reqs)
        self.assertFalse([r for r in reqs if r[0] == "DELETE"])
        self.assertTrue(any("zones" in line and "news" in line for line in cm.output))
        self.assertTrue(any("db_mb=12.0" in line for line in cm.output))

    def test_over_400_mb_fails_the_run(self):
        with FakeServer(self.handler(size=450.0)) as s:
            with self.assertLogs("pipeline.cleanup", level="WARNING"):
                self.assertEqual(run(self.db(s), NOW), 1)

    def test_unavailable_size_fails_the_run(self):
        def h(method, path, headers, body):
            return (404, {}) if "/rpc/db_size_mb" in path else (200, DELETED)

        with FakeServer(h) as s:
            with self.assertLogs("pipeline.cleanup", level="WARNING"):
                self.assertEqual(run(self.db(s), NOW), 1)

    def test_failed_retention_call_fails_the_run_but_still_reports_the_size(self):
        with FakeServer(self.handler(cleanup=(500, {}))) as s:
            with self.assertLogs("pipeline.cleanup", level="INFO") as cm:
                self.assertEqual(run(self.db(s), NOW), 1)
        self.assertTrue(any("cleanup_old_data" in line for line in cm.output))
        self.assertTrue(any("db_mb=12.0" in line for line in cm.output))

    def test_main_returns_the_run_status(self):
        import pipeline.cleanup as c
        with FakeServer(self.handler(size=999.0)) as s:
            with self.assertLogs("pipeline.cleanup", level="WARNING"):
                code = c.main({"SUPABASE_URL": s.url, "SUPABASE_SECRET_KEY": "k"}, now=NOW)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()

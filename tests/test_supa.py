import unittest

from pipeline.supa import Supabase, from_env
from tests.fakehttp import FakeServer

NO_SLEEP = lambda s: None


class FromEnvTest(unittest.TestCase):
    def test_missing_variables_are_named_and_there_is_no_fallback(self):
        with self.assertRaisesRegex(RuntimeError, "SUPABASE_URL.*SUPABASE_SECRET_KEY"):
            from_env({})
        with self.assertRaisesRegex(RuntimeError, "SUPABASE_SECRET_KEY"):
            from_env({"SUPABASE_URL": "https://x.supabase.co"})

    def test_blank_values_count_as_missing(self):
        with self.assertRaisesRegex(RuntimeError, "SUPABASE_URL"):
            from_env({"SUPABASE_URL": " ", "SUPABASE_SECRET_KEY": "k"})

    def test_builds_a_client(self):
        self.assertIsInstance(from_env({"SUPABASE_URL": "https://x.supabase.co/", "SUPABASE_SECRET_KEY": "k"}), Supabase)

    def test_error_message_never_contains_a_key_value(self):
        try:
            from_env({"SUPABASE_URL": "", "SUPABASE_SECRET_KEY": "topsecretvalue"})
        except RuntimeError as e:
            self.assertNotIn("topsecretvalue", str(e))


class ClientTest(unittest.TestCase):
    def test_select_sends_filters_and_key_headers(self):
        with FakeServer(lambda *a: (200, [{"symbol": "FPT"}])) as s:
            rows = Supabase(s.url, "KEY", sleep=NO_SLEEP).select("quotes_latest", {"select": "symbol", "symbol": "eq.FPT"})
            req = s.requests[0]
        self.assertEqual(rows, [{"symbol": "FPT"}])
        self.assertTrue(req["path"].startswith("/rest/v1/quotes_latest?"))
        self.assertIn("symbol=eq.FPT", req["path"])
        self.assertEqual(req["headers"]["apikey"], "KEY")
        self.assertEqual(req["headers"]["authorization"], "Bearer KEY")

    def test_select_all_follows_pages_until_a_short_one(self):
        def handler(m, path, h, b):
            off = int(path.split("offset=")[1].split("&")[0])
            return 200, [{"i": i} for i in range(off, min(off + 3, 7))]

        with FakeServer(handler) as s:
            rows = Supabase(s.url, "K", sleep=NO_SLEEP).select_all("bars_30m", {"select": "*"}, page=3)
        self.assertEqual([r["i"] for r in rows], list(range(7)))

    def test_upsert_merges_on_the_conflict_columns(self):
        with FakeServer(lambda *a: (201, None)) as s:
            Supabase(s.url, "K", sleep=NO_SLEEP).upsert("signals", [{"a": 1}], "asof,symbol")
            req = s.requests[0]
        self.assertEqual((req["method"], req["body"]), ("POST", [{"a": 1}]))
        self.assertIn("on_conflict=asof%2Csymbol", req["path"])
        self.assertIn("merge-duplicates", req["headers"]["prefer"])

    def test_upsert_splits_big_batches_and_skips_empty_ones(self):
        with FakeServer(lambda *a: (201, None)) as s:
            db = Supabase(s.url, "K", sleep=NO_SLEEP)
            db.upsert("bars_30m", [{"i": i} for i in range(1200)], "symbol,bar_start")
            db.upsert("bars_30m", [], "symbol,bar_start")
            sizes = [len(r["body"]) for r in s.requests]
        self.assertEqual(sizes, [500, 500, 200])

    def test_delete_uses_filters(self):
        with FakeServer(lambda *a: (204, None)) as s:
            Supabase(s.url, "K", sleep=NO_SLEEP).delete("signals", {"asof": "lt.2026-01-01"})
            req = s.requests[0]
        self.assertEqual(req["method"], "DELETE")
        self.assertIn("asof=lt.2026-01-01", req["path"])

    def test_rpc_posts_arguments(self):
        with FakeServer(lambda *a: (200, 123.4)) as s:
            out = Supabase(s.url, "K", sleep=NO_SLEEP).rpc("db_size_mb", {})
            req = s.requests[0]
        self.assertEqual(out, 123.4)
        self.assertEqual(req["path"], "/rest/v1/rpc/db_size_mb")


if __name__ == "__main__":
    unittest.main()

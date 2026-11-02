import logging
import unittest

from pipeline.sources import SourceError, alpaca, fetch_vn, kbs, vci
from pipeline.sources.http import request_json
from tests.fakehttp import FakeServer

KBS_ROW = {"SB": "FPT", "EX": "HOSE", "CP": 53100, "RE": 52700, "CL": 56000, "FL": 49000, "TT": 3107400,
           "TV": 165_000_000_000, "FB": 285610, "FS": 367500, "FR": 1000, "PTQ": 10, "PTV": 500, "IT": "12:48:18"}
KBS_UNLISTED = {"SB": "ZZZ", "IT": "12:00:00"}  # no TT: not a live symbol
VCI_ROW = {"listingInfo": {"symbol": "HPG", "board": "HOSE", "refPrice": 21200, "ceiling": 22600, "floor": 19800},
           "matchPrice": {"matchPrice": 21300, "accumulatedVolume": 11951100, "accumulatedValue": 254_677_695_000,
                          "foreignBuyVolume": 3096629, "foreignSellVolume": 2560300, "currentRoom": 5},
           "bidAsk": {}}
ALPACA = {"AAPL": {"dailyBar": {"o": 101.0, "h": 103, "l": 99, "c": 102, "v": 5000, "vw": 100.5},
                   "prevDailyBar": {"c": 100.0}, "latestTrade": {"p": 102.5}}}
NO_SLEEP = {"sleep": lambda s: None}


class RequestJsonTest(unittest.TestCase):
    def test_retries_server_errors_with_2_4_8_second_waits_then_succeeds(self):
        calls, waits = [], []

        def handler(*a):
            calls.append(1)
            return (500, {}) if len(calls) < 4 else (200, {"ok": True})

        with FakeServer(handler) as s:
            out = request_json(s.url, {"x": 1}, sleep=waits.append)
        self.assertEqual(out, {"ok": True})
        self.assertEqual(waits, [2, 4, 8])

    def test_gives_up_after_three_retries(self):
        waits = []
        with FakeServer(lambda *a: (503, {})) as s:
            with self.assertRaises(SourceError):
                request_json(s.url, sleep=waits.append)
            self.assertEqual(len(s.requests), 4)
        self.assertEqual(waits, [2, 4, 8])

    def test_client_error_is_not_retried(self):
        waits = []
        with FakeServer(lambda *a: (401, {})) as s:
            with self.assertRaises(SourceError):
                request_json(s.url, sleep=waits.append)
            self.assertEqual(len(s.requests), 1)
        self.assertEqual(waits, [])

    def test_unreachable_host_is_a_source_error(self):
        with self.assertRaises(SourceError):
            request_json("http://127.0.0.1:1/", retries=0, **NO_SLEEP)


class KbsTest(unittest.TestCase):
    def test_keeps_only_live_rows_and_normalises_fields(self):
        with FakeServer(lambda *a: (200, [KBS_ROW, KBS_UNLISTED])) as s:
            rows = kbs.fetch(["FPT", "ZZZ"], url=s.url, **NO_SLEEP)
            self.assertEqual(s.requests[0]["body"], {"code": "FPT,ZZZ"})
        self.assertEqual(set(rows), {"FPT"})
        self.assertEqual(rows["FPT"]["TT"], 3107400)
        self.assertEqual(rows["FPT"]["CP"], 53100)
        self.assertEqual(rows["FPT"]["EX"], "HOSE")

    def test_large_symbol_lists_are_split_in_chunks(self):
        codes = [f"A{i:03d}" for i in range(3200)]
        with FakeServer(lambda *a: (200, [KBS_ROW])) as s:
            kbs.fetch(codes, url=s.url, **NO_SLEEP)
            sizes = [len(r["body"]["code"].split(",")) for r in s.requests]
        self.assertEqual(sizes, [1500, 1500, 200])

    def test_missing_optional_numbers_default_to_zero(self):
        row = {k: v for k, v in KBS_ROW.items() if k not in ("PTQ", "PTV", "FR")}
        with FakeServer(lambda *a: (200, [row])) as s:
            out = kbs.fetch(["FPT"], url=s.url, **NO_SLEEP)
        self.assertEqual((out["FPT"]["PTQ"], out["FPT"]["PTV"], out["FPT"]["FR"]), (0, 0, 0))


class VciTest(unittest.TestCase):
    def test_nested_rows_map_to_the_same_shape_as_kbs(self):
        with FakeServer(lambda *a: (200, [VCI_ROW])) as s:
            rows = vci.fetch(["HPG"], url=s.url, **NO_SLEEP)
            self.assertEqual(s.requests[0]["body"], {"symbols": ["HPG"]})
            self.assertIn("vietcap", s.requests[0]["headers"]["origin"])
        r = rows["HPG"]
        self.assertEqual((r["TT"], r["TV"], r["FB"], r["FS"], r["CP"], r["RE"]),
                         (11951100, 254_677_695_000, 3096629, 2560300, 21300, 21200))

    def test_rows_without_live_volume_are_dropped(self):
        dead = {"listingInfo": {"symbol": "XYZ"}, "matchPrice": {}, "bidAsk": {}}
        live = {**VCI_ROW}
        with FakeServer(lambda *a: (200, [dead, live])) as s:
            self.assertEqual(set(vci.fetch(["XYZ", "HPG"], url=s.url, **NO_SLEEP)), {"HPG"})


class AlpacaTest(unittest.TestCase):
    def test_snapshot_maps_to_board_shape_and_sends_key_headers(self):
        with FakeServer(lambda *a: (200, ALPACA)) as s:
            rows = alpaca.fetch(["AAPL"], "KEYID", "SECRET", url=s.url, **NO_SLEEP)
            req = s.requests[0]
        self.assertIn("symbols=AAPL", req["path"])
        self.assertEqual(req["headers"]["apca-api-key-id"], "KEYID")
        self.assertEqual(req["headers"]["apca-api-secret-key"], "SECRET")
        r = rows["AAPL"]
        self.assertEqual((r["TT"], r["CP"], r["RE"], r["OP"]), (5000, 102.5, 100.0, 101.0))
        self.assertAlmostEqual(r["TV"], 5000 * 100.5)
        self.assertEqual((r["FB"], r["FS"], r["PTQ"], r["PTV"]), (0, 0, 0, 0))

    def test_symbol_without_a_daily_bar_is_skipped(self):
        body = {"NEW": {"latestTrade": {"p": 1}}, **ALPACA}
        with FakeServer(lambda *a: (200, body)) as s:
            self.assertEqual(set(alpaca.fetch(["NEW", "AAPL"], "k", "s", url=s.url, **NO_SLEEP)), {"AAPL"})

    def test_missing_credentials_fail_loudly(self):
        with self.assertRaises(SourceError):
            alpaca.fetch(["AAPL"], "", "", url="http://127.0.0.1:1")


class EmptyFeedTest(unittest.TestCase):
    BAD_BODIES = (None, {}, "oops", 7, [], [KBS_UNLISTED], [None, 3])

    def test_kbs_rejects_empty_or_malformed_bodies(self):
        for body in self.BAD_BODIES:
            with FakeServer(lambda *a, b=body: (200, b)) as s:
                with self.assertRaises(SourceError, msg=repr(body)):
                    kbs.fetch(["FPT"], url=s.url, **NO_SLEEP)

    def test_vci_rejects_empty_or_malformed_bodies(self):
        for body in (None, {}, "oops", [], [{"listingInfo": {}, "matchPrice": {}}], [None]):
            with FakeServer(lambda *a, b=body: (200, b)) as s:
                with self.assertRaises(SourceError, msg=repr(body)):
                    vci.fetch(["HPG"], url=s.url, **NO_SLEEP)

    def test_alpaca_rejects_empty_or_malformed_bodies(self):
        for body in (None, [], "oops", {}, {"NEW": {"latestTrade": {"p": 1}}}):
            with FakeServer(lambda *a, b=body: (200, b)) as s:
                with self.assertRaises(SourceError, msg=repr(body)):
                    alpaca.fetch(["AAPL"], "k", "s", url=s.url, **NO_SLEEP)

    def test_kbs_returning_nothing_live_falls_back_to_vci(self):
        with FakeServer(lambda *a: (200, [])) as bad, FakeServer(lambda *a: (200, [VCI_ROW])) as good:
            with self.assertLogs("pipeline.sources", level="INFO") as cm:
                rows = fetch_vn(["HPG"], kbs_url=bad.url, vci_url=good.url, **NO_SLEEP)
        self.assertIn("HPG", rows)
        self.assertTrue(any("source=VCI" in line for line in cm.output))

    def test_both_sources_empty_is_an_error(self):
        with FakeServer(lambda *a: (200, [])) as a, FakeServer(lambda *a: (200, None)) as b:
            with self.assertRaises(SourceError):
                fetch_vn(["HPG"], kbs_url=a.url, vci_url=b.url, **NO_SLEEP)

    def test_rows_say_where_they_came_from_and_whether_they_carry_negotiated_data(self):
        with FakeServer(lambda *a: (200, [KBS_ROW])) as s:
            self.assertEqual(kbs.fetch(["FPT"], url=s.url, **NO_SLEEP)["FPT"]["SRC"], "KBS")
        with FakeServer(lambda *a: (200, [VCI_ROW])) as s:
            r = vci.fetch(["HPG"], url=s.url, **NO_SLEEP)["HPG"]
        self.assertEqual((r["SRC"], r["PT"]), ("VCI", False))
        with FakeServer(lambda *a: (200, ALPACA)) as s:
            a = alpaca.fetch(["AAPL"], "k", "s", url=s.url, **NO_SLEEP)["AAPL"]
        self.assertEqual(a["SRC"], "Alpaca")


class HttpLimitsTest(unittest.TestCase):
    def test_huge_response_is_refused(self):
        with FakeServer(lambda *a: (200, {"x": "y" * 5000})) as s:
            with self.assertRaises(SourceError):
                request_json(s.url, max_bytes=1000, **NO_SLEEP)

    def test_response_within_the_limit_is_fine(self):
        with FakeServer(lambda *a: (200, {"x": 1})) as s:
            self.assertEqual(request_json(s.url, max_bytes=1000, **NO_SLEEP), {"x": 1})

    def test_gzip_bomb_is_refused(self):
        import gzip, json, threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        bomb = gzip.compress(json.dumps({"x": "0" * 200_000}).encode())

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(bomb)))
                self.end_headers()
                self.wfile.write(bomb)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        try:
            with self.assertRaises(SourceError):
                request_json(f"http://127.0.0.1:{srv.server_address[1]}/", max_bytes=10_000, **NO_SLEEP)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_client_error_keeps_the_start_of_the_body_in_the_message(self):
        with FakeServer(lambda *a: (403, {"message": "bad key for this feed"})) as s:
            with self.assertRaises(SourceError) as cm:
                request_json(s.url, **NO_SLEEP)
        self.assertIn("bad key for this feed", str(cm.exception))

    def test_error_body_in_the_message_is_cut_to_200_bytes(self):
        with FakeServer(lambda *a: (400, {"m": "z" * 1000})) as s:
            with self.assertRaises(SourceError) as cm:
                request_json(s.url, **NO_SLEEP)
        self.assertLess(len(str(cm.exception)), 400)


class FallbackTest(unittest.TestCase):
    def test_kbs_failure_falls_back_to_vci_and_logs_the_source(self):
        with FakeServer(lambda m, p, h, b: (500, {})) as bad, FakeServer(lambda *a: (200, [VCI_ROW])) as good:
            with self.assertLogs("pipeline.sources", level="INFO") as cm:
                rows = fetch_vn(["HPG"], kbs_url=bad.url, vci_url=good.url, **NO_SLEEP)
        self.assertIn("HPG", rows)
        self.assertTrue(any("source=VCI" in line for line in cm.output))

    def test_kbs_success_never_touches_vci(self):
        with FakeServer(lambda *a: (200, [KBS_ROW])) as good, FakeServer(lambda *a: (200, [])) as other:
            with self.assertLogs("pipeline.sources", level="INFO") as cm:
                fetch_vn(["FPT"], kbs_url=good.url, vci_url=other.url, **NO_SLEEP)
            self.assertEqual(other.requests, [])
        self.assertTrue(any("source=KBS" in line for line in cm.output))

    def test_both_failing_raises(self):
        with FakeServer(lambda *a: (500, {})) as a, FakeServer(lambda *a: (500, {})) as b:
            with self.assertRaises(SourceError):
                fetch_vn(["X"], kbs_url=a.url, vci_url=b.url, **NO_SLEEP)


if __name__ == "__main__":
    logging.disable(logging.NOTSET)
    unittest.main()

import os
import tempfile
import unittest

from pipeline.alert import build_message, main, send
from tests.fakehttp import FakeServer

ENV = {"TELEGRAM_BOT_TOKEN": "123:TOKENVALUE", "TELEGRAM_CHAT_ID": "-1001", "WORKFLOW_NAME": "snap-vn",
       "RUN_URL": "https://github.com/o/r/actions/runs/42"}


def ok_handler(*a):
    return 200, {"ok": True, "result": {}}


class MessageTest(unittest.TestCase):
    def test_message_has_workflow_run_url_and_detail_only(self):
        text = build_message("snap-vn", "https://github.com/o/r/actions/runs/42", "VN: 1 slot missing")
        self.assertIn("snap-vn", text)
        self.assertIn("https://github.com/o/r/actions/runs/42", text)
        self.assertIn("VN: 1 slot missing", text)

    def test_detail_is_cut_to_a_reasonable_length(self):
        self.assertLess(len(build_message("w", "https://x", "d" * 5000)), 1500)


class SendTest(unittest.TestCase):
    def test_posts_to_the_bot_endpoint_with_chat_id_and_text(self):
        with FakeServer(ok_handler) as s:
            send("123:TOKEN", "-1001", "hello", base=s.url, sleep=lambda x: None)
            req = s.requests[0]
        self.assertEqual(req["path"], "/bot123:TOKEN/sendMessage")
        self.assertEqual((req["body"]["chat_id"], req["body"]["text"]), ("-1001", "hello"))

    def test_telegram_saying_not_ok_is_an_error(self):
        with FakeServer(lambda *a: (200, {"ok": False, "description": "chat not found"})) as s:
            with self.assertRaises(RuntimeError):
                send("t", "c", "x", base=s.url, sleep=lambda x: None)


class MainTest(unittest.TestCase):
    def test_sends_the_failure_message_and_never_puts_the_token_in_it(self):
        with FakeServer(ok_handler) as s:
            code = main(ENV, base=s.url, sleep=lambda x: None)
            body = s.requests[0]["body"]
        self.assertEqual(code, 0)
        self.assertIn("snap-vn", body["text"])
        self.assertNotIn("TOKENVALUE", body["text"])

    def test_a_missing_secret_fails_loudly_and_names_the_variable(self):
        for drop in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "RUN_URL", "WORKFLOW_NAME"):
            env = {k: v for k, v in ENV.items() if k != drop}
            with self.assertLogs("pipeline.alert", level="ERROR") as cm:
                code = main(env, base="http://127.0.0.1:1", sleep=lambda x: None)
            self.assertEqual(code, 2, drop)
            self.assertIn(drop, "".join(cm.output))
            self.assertNotIn("TOKENVALUE", "".join(cm.output))

    def test_blank_secret_counts_as_missing(self):
        with self.assertLogs("pipeline.alert", level="ERROR"):
            self.assertEqual(main({**ENV, "TELEGRAM_CHAT_ID": "  "}, base="http://127.0.0.1:1"), 2)

    def test_a_send_failure_exits_non_zero_without_leaking_the_token(self):
        with FakeServer(lambda *a: (401, {"ok": False})) as s:
            with self.assertLogs("pipeline.alert", level="ERROR") as cm:
                code = main(ENV, base=s.url, sleep=lambda x: None)
        self.assertEqual(code, 1)
        self.assertNotIn("TOKENVALUE", "".join(cm.output))

    def test_detail_file_is_appended_when_present(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("VN 2026-10-30: 10/11 slots (missing 11:00)")
        try:
            with FakeServer(ok_handler) as s:
                main({**ENV, "ALERT_DETAIL_FILE": f.name}, base=s.url, sleep=lambda x: None)
                self.assertIn("10/11 slots", s.requests[0]["body"]["text"])
        finally:
            os.unlink(f.name)

    def test_a_missing_detail_file_is_fine(self):
        with FakeServer(ok_handler) as s:
            self.assertEqual(main({**ENV, "ALERT_DETAIL_FILE": "/nonexistent/x.txt"}, base=s.url,
                                  sleep=lambda x: None), 0)


if __name__ == "__main__":
    unittest.main()

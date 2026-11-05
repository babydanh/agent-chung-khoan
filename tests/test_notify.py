import json
import unittest
from datetime import datetime, timedelta, timezone

from pipeline import notify
from pipeline.banned import find_banned
from tests.fakehttp import FakeServer

NOW = datetime(2026, 11, 5, 3, 0, tzinfo=timezone.utc)  # Thursday 10:00 in Vietnam
ASOF = "2026-11-05T02:30:00+00:00"
CFG = {"hot": 60, "max_per_hour": 6, "signal_level": 3, "flow_level": 2, "watch": {"VN": [], "US": []}}


def rss(*items):
    body = "".join(f"<item><title>{t}</title><link>https://example.com/{i}</link><pubDate>{d}</pubDate>"
                   f"<description>x</description></item>" for i, (t, d) in enumerate(items))
    return f"<rss><channel>{body}</channel></rss>"


def gmt(minutes_ago):
    return (NOW - timedelta(minutes=minutes_ago)).strftime("%a, %d %b %Y %H:%M:%S GMT")


SIGNALS = [
    {"market": "VN", "asof": ASOF, "symbol": "HPG", "level": 3, "learning": False,
     "items": [{"id": "S1", "dir": None}, {"id": "S2", "dir": "buy"}]},
    {"market": "VN", "asof": ASOF, "symbol": "FPT", "level": 2, "learning": False, "items": [{"id": "S3", "dir": None}]},
]


class World:
    """A fake Supabase (signals + the notify state row) and a fake Telegram on one server."""

    def __init__(self, signals=SIGNALS, telegram_status=200):
        self.signals, self.telegram_status, self.state, self.asof = signals, telegram_status, None, ASOF
        self.sent = []

    def handler(self, method, path, headers, body):
        if "/bot" in path and path.endswith("/sendMessage"):
            if self.telegram_status != 200:
                return self.telegram_status, {"ok": False}
            self.sent.append(body)
            return 200, {"ok": True}
        if method == "GET" and "/signals" in path:
            if path.endswith("limit=1") or "limit=1&" in path:  # not limit=1000 of the paged read
                return 200, [{"asof": self.asof}] if self.signals else []
            return 200, [{**r, "asof": self.asof} for r in self.signals]
        if method == "GET" and "/heartbeat" in path:
            return 200, [{"detail": self.state}] if self.state is not None else []
        if method == "POST" and "/heartbeat" in path:
            row = body[0]
            if row["job"] == "notify":
                self.state = row["detail"]
            return 201, None
        return 404, None

    def run(self, feed=None, cfg=None, now=NOW, market="VN", env=None, text=None):
        calls = []

        def get_text(url):
            calls.append(url)
            if feed is None:
                raise OSError("no feed")
            return feed

        with FakeServer(self.handler) as s:
            e = {"SUPABASE_URL": s.url, "SUPABASE_SECRET_KEY": "k", "TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "42"}
            e.update(env or {})
            code = notify.main(["--market", market], e, now=now, get_text=text or get_text, sleep=lambda x: None,
                               config=cfg or CFG, telegram_base=s.url)
        self.calls = calls
        return code

    def texts(self):
        return [m["text"] for m in self.sent]


class NotifyTest(unittest.TestCase):
    def assertClean(self, w):
        for t in w.texts():
            self.assertEqual(find_banned(t), [], t)

    def test_a_new_level_three_symbol_is_sent_once_with_its_signals(self):
        w = World()
        self.assertEqual(w.run(), 0)
        (t,) = w.texts()
        self.assertIn("HPG", t)
        self.assertIn("Mức 3", t)
        self.assertIn("KL tăng đột biến", t)
        self.assertIn("NN ròng dương", t)
        self.assertNotIn("FPT", t, "level 2 is below the configured level")
        self.assertEqual(w.sent[0]["chat_id"], "42")
        self.assertClean(w)
        self.assertEqual(w.run(), 0)
        self.assertEqual(len(w.sent), 1, "the same symbol at the same level is not sent again")

    def test_a_hot_story_is_sent_and_a_cold_one_is_not(self):
        w = World(signals=[])
        feed = rss(("HPG báo lãi quý 3 tăng 20% so với cùng kỳ", gmt(10)), ("Phan Đình Dự nhận giải thưởng", gmt(10)))
        w.run(feed=feed, cfg={**CFG, "watch": {"VN": ["HPG"], "US": []}})
        (t,) = w.texts()
        self.assertIn("HPG · Kết quả kinh doanh", t)
        self.assertIn("báo lãi quý 3", t)
        self.assertIn("https://example.com/0", t)
        self.assertClean(w)

    def test_the_same_story_is_not_sent_twice_across_runs(self):
        w = World(signals=[])
        feed = rss(("HPG báo lãi quý 3 tăng 20% so với cùng kỳ", gmt(10)))
        cfg = {**CFG, "watch": {"VN": ["HPG"], "US": []}}
        w.run(feed=feed, cfg=cfg)
        w.run(feed=feed, cfg=cfg, now=NOW + timedelta(minutes=30))
        self.assertEqual(len(w.sent), 1)

    def test_a_story_that_matches_a_money_flow_signal_says_so(self):
        w = World()  # HPG is level 3 with S1 + S2
        w.run(feed=rss(("HPG ký hợp đồng cung cấp thép cho dự án lớn", gmt(10))))
        news = [t for t in w.texts() if "hợp đồng" in t]
        self.assertEqual(len(news), 1)
        self.assertIn("Khớp dòng tiền", news[0])
        self.assertIn("Mức 3", news[0])

    def test_a_story_below_the_threshold_stays_quiet_until_it_is_watched(self):
        feed = rss(("FPT ký hợp đồng chuyển đổi số mới", gmt(400)))
        w = World(signals=[])
        w.run(feed=feed)
        self.assertEqual(w.sent, [])
        w2 = World(signals=[])
        w2.run(feed=feed, cfg={**CFG, "hot": 40, "watch": {"VN": ["FPT"], "US": []}})
        self.assertEqual(len(w2.sent), 1)

    def test_nothing_goes_out_in_quiet_hours_and_the_queue_is_sent_after_seven(self):
        w = World()
        night = datetime(2026, 11, 5, 16, 0, tzinfo=timezone.utc)  # 23:00 in Vietnam
        w.asof = (night - timedelta(minutes=5)).isoformat()
        self.assertEqual(w.run(now=night), 0)
        self.assertEqual(w.sent, [])
        self.assertEqual(len(w.state["queue"]), 1)
        morning = datetime(2026, 11, 6, 0, 5, tzinfo=timezone.utc)  # 07:05
        w.run(now=morning)
        self.assertEqual(len(w.sent), 1)
        self.assertEqual(w.state["queue"], [])

    def test_a_us_run_flushes_the_vietnam_queue_too(self):
        w = World()
        night = datetime(2026, 11, 5, 16, 0, tzinfo=timezone.utc)
        w.asof = (night - timedelta(minutes=5)).isoformat()
        w.run(now=night)
        w.signals = []
        w.run(market="US", now=datetime(2026, 11, 6, 0, 30, tzinfo=timezone.utc))
        self.assertEqual(len(w.sent), 1)

    def test_over_the_hourly_limit_the_rest_is_one_summary(self):
        signals = [{"market": "VN", "asof": ASOF, "symbol": s, "level": 3, "learning": False, "items": [{"id": "S1", "dir": None}]}
                   for s in ("AAA", "BBB", "CCC", "DDD")]
        w = World(signals=signals)
        w.run(cfg={**CFG, "max_per_hour": 2})
        self.assertEqual(len(w.sent), 2)
        self.assertIn("Còn 3 tin nóng", w.texts()[1])
        self.assertClean(w)
        w.run(cfg={**CFG, "max_per_hour": 2}, now=NOW + timedelta(minutes=5))
        self.assertEqual(len(w.sent), 2, "the summarised stories are not sent again later")

    def test_a_telegram_failure_exits_one_and_keeps_the_message_for_the_next_run(self):
        w = World(telegram_status=500)
        self.assertEqual(w.run(), 1)
        self.assertEqual(w.sent, [])
        w.telegram_status = 200
        self.assertEqual(w.run(now=NOW + timedelta(minutes=30)), 0)
        self.assertEqual(len(w.sent), 1)

    def test_missing_telegram_secrets_fail_before_anything_is_read_or_sent(self):
        w = World()
        self.assertEqual(w.run(env={"TELEGRAM_BOT_TOKEN": ""}), 2)
        self.assertEqual(w.sent, [])

    def test_a_headline_with_advice_wording_is_never_sent(self):
        w = World(signals=[])
        w.run(feed=rss(("HPG báo lãi quý 3: nên mua ngay trước khi tăng", gmt(5))), cfg={**CFG, "watch": {"VN": ["HPG"], "US": []}})
        self.assertEqual(w.sent, [])

    def test_a_us_run_sends_signal_notices_and_never_reads_the_feeds(self):
        w = World(signals=[{"market": "US", "asof": ASOF, "symbol": "NVDA", "level": 3, "learning": False, "items": [{"id": "S1", "dir": None}]}])
        w.run(market="US")
        self.assertEqual(w.calls, [])
        self.assertIn("NVDA", w.texts()[0])

    def test_broken_feeds_do_not_stop_the_signal_notices(self):
        w = World()
        self.assertEqual(w.run(feed=None), 0)
        self.assertEqual(len(w.sent), 1)

    def test_old_sent_records_are_dropped_from_the_state(self):
        w = World()
        w.run()
        w.state["sent"]["lv:VN:OLD:2026-10-01:3"] = (NOW - timedelta(days=5)).isoformat()
        w.run(now=NOW + timedelta(minutes=30))
        self.assertNotIn("lv:VN:OLD:2026-10-01:3", w.state["sent"])
        self.assertTrue(any(k.startswith("lv:VN:HPG") for k in w.state["sent"]))

    def test_the_state_is_stored_under_the_vietnam_notify_heartbeat(self):
        w = World()
        w.run()
        self.assertEqual(set(w.state), {"sent", "queue", "recent"})
        json.dumps(w.state)


class ConfigTest(unittest.TestCase):
    def test_the_shipped_config_loads_and_is_valid(self):
        cfg = notify.load_config(notify.CONFIG_PATH)
        self.assertEqual(set(cfg["watch"]), {"VN", "US"})
        self.assertTrue(0 < cfg["hot"] <= 100)

    def test_a_missing_key_is_reported(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "n.json")
            with open(p, "w") as f:
                json.dump({"hot": 60}, f)
            with self.assertRaises(ValueError):
                notify.load_config(p)


if __name__ == "__main__":
    unittest.main()

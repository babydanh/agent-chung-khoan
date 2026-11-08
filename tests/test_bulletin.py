import unittest
from datetime import datetime, timezone

from pipeline import bulletin
from tests.fakehttp import FakeServer

NOW = datetime(2026, 10, 30, 8, 5, tzinfo=timezone.utc)  # 15:05 in Vietnam
ASOF = "2026-10-30T08:05:00+00:00"
RSS = ('<rss><channel><item><title>HPG tăng sản lượng</title><link>https://example.com/a</link>'
       '<pubDate>Fri, 30 Oct 2026 07:00:00 GMT</pubDate><description>x</description></item></channel></rss>')
ITEMS = [{"signals": [{"id": "S1", "dir": None}]}]


def fake_make(items, news, api_key, time_text, **kw):
    fake_make.calls.append({"items": items, "news": news, "key": api_key, "time": time_text,
                            "cli_token": kw.get("cli_token")})
    return {"source": "ai", "reason": None, "fatal": False, "paragraphs": ["Dòng một.", "Dòng hai."],
            "news": [{k: n[k] for k in ("id", "title", "link", "source")} for n in news[:1]],  # same shape as the real agent
            "dropped": []}


fake_make.calls = []


def no_notes(headlines, seen, key, token):
    return []


def handler(signal_rows, noted=()):
    def h(method, path, headers, body):
        if method == "GET" and "/news_notes" in path:
            return 200, [{"url": u} for u in noted]
        if method == "GET" and "/signals" in path:
            if path.endswith("limit=1") or "limit=1&" in path:
                return 200, [{"asof": ASOF}] if signal_rows else []
            return 200, signal_rows
        return 201, None
    return h


def run(rows, env=None, make=fake_make, text=lambda url: RSS, argv=("--market", "VN"), annotate=no_notes, noted=()):
    with FakeServer(handler(rows, noted)) as s:
        env = {"SUPABASE_URL": s.url, "SUPABASE_SECRET_KEY": "k", "ANTHROPIC_API_KEY": "a", **(env or {})}
        code = bulletin.main(list(argv), env, now=NOW, get_text=text, make=make, annotate=annotate, sleep=lambda x: None)
        return code, s.requests


def posts(reqs, table):
    return [r for r in reqs if r["method"] == "POST" and r["path"].startswith(f"/rest/v1/{table}?")]


class BulletinTest(unittest.TestCase):
    def setUp(self):
        fake_make.calls.clear()
        self.rows = [{"market": "VN", "asof": ASOF, "symbol": "HPG", "level": 2, "learning": False, "items": ITEMS[0]["signals"]}]

    def test_writes_one_digest_for_the_slot_with_the_paragraphs(self):
        code, reqs = run(self.rows)
        self.assertEqual(code, 0)
        (d,) = posts(reqs, "digests")
        self.assertIn("on_conflict=market%2Cdigest_date%2Ckind", d["path"])
        self.assertEqual(d["body"][0]["market"], "VN")
        self.assertEqual(d["body"][0]["digest_date"], "2026-10-30")
        self.assertEqual(d["body"][0]["body"], "Dòng một.\nDòng hai.")
        self.assertIn("ignore-duplicates", d["headers"]["prefer"])  # a rerun keeps the first bulletin

    def test_the_agent_gets_items_in_its_shape_and_local_time(self):
        run(self.rows)
        call = fake_make.calls[0]
        self.assertEqual(call["items"], [{"symbol": "HPG", "level": 2, "signals": [{"id": "S1", "dir": None}]}])
        self.assertEqual(call["time"], "15:05")
        self.assertEqual(call["key"], "a")

    def test_cli_token_from_the_environment_is_passed_to_the_agent(self):  # TC-BULLETIN-CLI-11
        run(self.rows, env={"CLAUDE_CODE_OAUTH_TOKEN": "tok"})
        self.assertEqual(fake_make.calls[0]["cli_token"], "tok")

    def test_news_used_by_the_bulletin_is_stored_with_the_market(self):
        _, reqs = run(self.rows)
        (n,) = posts(reqs, "news")
        self.assertEqual(n["body"][0]["url"], "https://example.com/a")
        self.assertEqual(n["body"][0]["market"], "VN")
        self.assertEqual(n["body"][0]["published_at"], "2026-10-30T07:00:00+00:00")

    def test_heartbeat_records_how_the_bulletin_was_made_and_the_push_decision(self):
        _, reqs = run(self.rows)
        (h,) = posts(reqs, "heartbeat")
        row = h["body"][0]
        self.assertEqual((row["market"], row["job"]), ("VN", "bulletin"))
        self.assertEqual(row["detail"]["bulletin_source"], "ai")
        self.assertEqual(row["detail"]["push"]["status"], "send")

    def test_a_fatal_agent_result_turns_the_run_red_but_still_stores_the_fallback(self):
        def bad(items, news, key, t, **kw):
            return {"source": "fallback", "reason": "no_key", "fatal": True, "paragraphs": ["Bản tin."], "news": [], "dropped": []}
        code, reqs = run(self.rows, make=bad)
        self.assertEqual(code, 1)
        self.assertEqual(len(posts(reqs, "digests")), 1)

    def test_no_signal_rows_still_make_a_bulletin_through_the_agent(self):
        code, reqs = run([])
        self.assertEqual(code, 0)
        self.assertEqual(fake_make.calls[0]["items"], [])

    def test_a_dead_news_feed_does_not_stop_the_bulletin(self):
        def boom(url):
            raise OSError("down")
        code, reqs = run(self.rows, text=boom)
        self.assertEqual(code, 0)
        self.assertEqual(fake_make.calls[0]["news"], [])
        self.assertEqual(len(posts(reqs, "digests")), 1)

    def test_us_bulletins_use_no_vietnamese_feeds(self):
        called = []
        run(self.rows, text=lambda u: called.append(u) or RSS, argv=("--market", "US"))
        self.assertEqual(called, [])

    def test_missing_supabase_env_exits_2(self):
        self.assertEqual(bulletin.main(["--market", "VN"], {}, now=NOW), 2)


if __name__ == "__main__":
    unittest.main()


class HeadlineNotesTest(unittest.TestCase):
    """TC-NOTE-15..20: the bulletin job also notes the new headlines; the notes never decide whether the run is green."""

    def setUp(self):
        fake_make.calls.clear()
        self.rows = [{"market": "VN", "asof": ASOF, "symbol": "HPG", "level": 2, "learning": False, "items": ITEMS[0]["signals"]}]
        self.asked = []

    def annotate(self, headlines, seen, key, token):
        self.asked.append({"links": [h["link"] for h in headlines], "seen": set(seen), "key": key, "token": token})
        return [{"url": h["link"], "kind": "earnings", "outlook": "pos", "aspect": "A.", "note": "Lý do."} for h in headlines]

    def test_note_15_new_notes_are_stored_with_the_market_and_never_overwrite_older_ones(self):
        code, reqs = run(self.rows, annotate=self.annotate, env={"CLAUDE_CODE_OAUTH_TOKEN": "tok"})
        self.assertEqual(code, 0)
        (n,) = posts(reqs, "news_notes")
        self.assertIn("on_conflict=url", n["path"])
        self.assertIn("ignore-duplicates", n["headers"]["prefer"])
        self.assertEqual(n["body"], [{"url": "https://example.com/a", "kind": "earnings", "outlook": "pos", "aspect": "A.",
                                      "note": "Lý do.", "market": "VN"}])
        self.assertEqual((self.asked[0]["key"], self.asked[0]["token"]), ("a", "tok"))

    def test_note_16_headlines_noted_in_the_last_days_are_not_sent_again(self):
        _, reqs = run(self.rows, annotate=self.annotate, noted=["https://example.com/a"])
        self.assertEqual(self.asked[0]["seen"], {"https://example.com/a"})
        (q,) = [r for r in reqs if r["method"] == "GET" and "/news_notes" in r["path"]]
        self.assertIn("market=eq.VN", q["path"])
        self.assertIn("created_at=gte.2026-10-26T08%3A05%3A00%2B00%3A00", q["path"])  # four days back

    def test_note_17_a_failing_annotator_does_not_fail_the_run_or_lose_the_bulletin(self):
        def boom(*a):
            raise RuntimeError("model down")
        code, reqs = run(self.rows, annotate=boom)
        self.assertEqual(code, 0)
        self.assertEqual(len(posts(reqs, "digests")), 1)
        self.assertEqual(posts(reqs, "heartbeat")[0]["body"][0]["detail"]["notes"], 0)

    def test_note_18_the_heartbeat_counts_the_notes_stored(self):
        _, reqs = run(self.rows, annotate=self.annotate)
        self.assertEqual(posts(reqs, "heartbeat")[0]["body"][0]["detail"]["notes"], 1)

    def test_note_19_no_headlines_means_no_annotator_call_and_no_note_rows(self):
        def boom(url):
            raise OSError("down")
        _, reqs = run(self.rows, annotate=self.annotate, text=boom)
        self.assertEqual((self.asked, posts(reqs, "news_notes")), ([], []))

    def test_note_20_a_stored_headline_carries_the_ticker_it_names(self):
        _, reqs = run(self.rows)
        (n,) = posts(reqs, "news")
        self.assertEqual(n["body"][0]["symbol"], "HPG")  # the detail screen filters headlines by symbol

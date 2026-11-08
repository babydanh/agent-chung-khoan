import re
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pipeline import bulletin, weekend
from pipeline.banned import find_banned
from tests.fakehttp import FakeServer

ROOT = Path(__file__).resolve().parent.parent
SUNDAY = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)  # 19:00 Sunday in Vietnam
FRIDAY_CLOSE = "2026-11-06T08:05:00+00:00"


def head(title, symbols=(), source="CafeF", published="2026-11-06T07:00:00+00:00", summary=""):
    return {"id": title[:6], "title": title, "link": "https://example.com/" + title[:6], "source": source,
            "published": published, "summary": summary, "symbols": list(symbols)}


ITEMS = [{"symbol": "HPG", "level": 3, "signals": []}, {"symbol": "FPT", "level": 1, "signals": []},
         {"symbol": "VNM", "level": 2, "signals": []}]
HEADS = [head("HPG báo lãi quý 3 tăng so với cùng kỳ", ["HPG"]),
         head("Thanh tra một doanh nghiệp bất động sản", [], "Vietstock"),
         head("Cổ tức tiền mặt của VCB", ["VCB"]),
         head("Thị trường đi ngang", [])]


class ClassifyTest(unittest.TestCase):
    def test_the_event_rules_are_the_same_as_the_apps(self):  # TC-WEEKEND-01
        src = (ROOT / "app" / "lib" / "news" / "rank.dart").read_text(encoding="utf-8")
        found = re.findall(r"\('(\w+)', '([^']+)', ([\d.]+), \[([^\]]*)\]\)", src)
        app = [(k, label, float(w), tuple(re.findall(r"'([^']+)'", kws))) for k, label, w, kws in found]
        self.assertEqual(len(app), 10)
        self.assertEqual([(k, label, w, tuple(kws)) for k, label, w, kws in weekend.RULES], app)

    def test_first_matching_event_wins_and_unknown_is_other(self):
        self.assertEqual(weekend.classify("Lãi suất tăng, doanh nghiệp báo lãi")[0], "macro")
        self.assertEqual(weekend.classify("HPG báo lãi quý 3")[0], "earnings")
        self.assertEqual(weekend.classify("Khởi tố vụ án")[0], "legal")
        self.assertEqual(weekend.classify("Thị trường đi ngang")[0], "other")


class BuildTest(unittest.TestCase):
    def text(self, items=ITEMS, heads=HEADS):
        return "\n".join(weekend.build(items, heads))

    def test_signals_line_names_the_count_and_the_strongest_first(self):  # TC-WEEKEND-02
        first = weekend.build(ITEMS, HEADS)[0]
        self.assertIn("3 mã", first)
        self.assertLess(first.index("HPG (mức 3)"), first.index("VNM (mức 2)"))

    def test_news_are_counted_by_topic_and_headlines_are_listed_word_for_word(self):
        t = self.text()
        self.assertIn("4 tin", t)
        self.assertIn("Kết quả kinh doanh (1)", t)
        self.assertIn("HPG báo lãi quý 3 tăng so với cùng kỳ", t)
        self.assertIn("(Vietstock)", t)
        self.assertNotIn("Thị trường đi ngang", t, "'other' headlines are only counted, never listed")

    def test_a_symbol_with_news_and_a_signal_is_a_watch_point_with_only_known_facts(self):  # TC-WEEKEND-03
        t = self.text()
        self.assertIn("HPG: có tin về kết quả kinh doanh và có dấu hiệu dòng tiền mức 3 ở phiên gần nhất", t)
        self.assertNotIn("VCB: có tin", t, "VCB has news but no signal")

    def test_topics_with_weight_get_a_fixed_watch_line(self):
        t = self.text()
        self.assertIn("Có 1 tin về pháp lý", t)
        self.assertIn("Có 1 tin về cổ tức", t)

    def test_nothing_in_the_bulletin_reads_as_advice_or_a_forecast(self):  # TC-WEEKEND-04
        self.assertEqual(find_banned(self.text()), [])
        bad = HEADS + [head("Nên mua HPG ngay hôm nay", ["HPG"])]
        t = self.text(heads=bad)
        self.assertNotIn("Nên mua", t)
        self.assertEqual(find_banned(t), [])

    def test_it_ends_with_the_not_advice_note(self):
        self.assertEqual(weekend.build(ITEMS, HEADS)[-1], "Tham khảo, không phải khuyến nghị đầu tư.")

    def test_no_data_says_so_instead_of_inventing_anything(self):  # TC-WEEKEND-05
        t = self.text(items=[], heads=[])
        self.assertIn("chưa ghi nhận mã nào", t)
        self.assertIn("chưa đọc được tin nào", t)
        self.assertIn("Chưa có điểm đặc biệt", t)
        self.assertEqual(find_banned(t), [])

    def test_at_most_five_symbols_and_five_headlines(self):
        items = [{"symbol": f"S{i:02d}", "level": 1, "signals": []} for i in range(9)]
        heads = [head(f"Báo lãi số {i}", [], published=f"2026-11-06T0{i}:00:00+00:00") for i in range(9)]
        out = weekend.build(items, heads)
        self.assertEqual(out[0].count("(mức"), 5)
        self.assertEqual(sum(1 for l in out if l.startswith("- [")), 5)


def handler(signal_rows, asof=FRIDAY_CLOSE):
    def h(method, path, headers, body):
        if method == "GET" and "/signals" in path:
            if path.endswith("limit=1") or "limit=1&" in path:
                return 200, [{"asof": asof}] if signal_rows else []
            return 200, signal_rows
        return 201, None
    return h


RSS = ('<rss><channel><item><title>HPG báo lãi quý 3</title><link>https://example.com/a</link>'
       '<pubDate>Fri, 06 Nov 2026 07:00:00 GMT</pubDate><description>x</description></item></channel></rss>')


def run(rows, argv=("--market", "VN", "--weekend"), calls=None, asof=FRIDAY_CLOSE):
    def make(*a, **kw):
        if calls is not None:
            calls.append(1)
        raise AssertionError("the weekend bulletin must not call the model")
    with FakeServer(handler(rows, asof)) as s:
        env = {"SUPABASE_URL": s.url, "SUPABASE_SECRET_KEY": "k", "ANTHROPIC_API_KEY": "a", "CLAUDE_CODE_OAUTH_TOKEN": "t"}
        code = bulletin.main(list(argv), env, now=SUNDAY, get_text=lambda url: RSS, make=make, sleep=lambda x: None)
        return code, s.requests


def posts(reqs, table):
    return [r for r in reqs if r["method"] == "POST" and r["path"].startswith(f"/rest/v1/{table}?")]


class WeekendJobTest(unittest.TestCase):
    rows = [{"market": "VN", "asof": FRIDAY_CLOSE, "symbol": "HPG", "level": 2, "learning": False, "items": []}]

    def test_it_writes_one_weekend_digest_from_friday_signals_without_the_model(self):  # TC-WEEKEND-06
        calls = []
        code, reqs = run(self.rows, calls=calls)
        self.assertEqual((code, calls), (0, []))
        (d,) = posts(reqs, "digests")
        row = d["body"][0]
        self.assertEqual((row["market"], row["kind"], row["digest_date"]), ("VN", "weekend", "2026-11-08"))
        self.assertIn("HPG (mức 2)", row["body"])
        self.assertIn("HPG báo lãi quý 3", row["body"])
        self.assertIn("ignore-duplicates", d["headers"]["prefer"])

    def test_signals_older_than_five_days_are_not_reported(self):  # TC-WEEKEND-07
        old = "2026-11-01T08:05:00+00:00"
        code, reqs = run([{**self.rows[0], "asof": old}], asof=old)
        self.assertEqual(code, 0)
        (d,) = posts(reqs, "digests")
        self.assertIn("chưa ghi nhận mã nào", d["body"][0]["body"])

    def test_the_us_market_has_no_weekend_bulletin(self):  # TC-WEEKEND-08
        code, reqs = run(self.rows, argv=("--market", "US", "--weekend"))
        self.assertEqual(code, 0)
        self.assertEqual(posts(reqs, "digests"), [])


if __name__ == "__main__":
    unittest.main()

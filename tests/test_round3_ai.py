"""Round 3 review fixes for guard / banned / news / agent / push (G1-G7)."""
import json
import unittest
from datetime import datetime, timedelta, timezone

from pipeline import agent, news
from pipeline.agent import MODEL, build_table, exit_code, heartbeat_detail, make_bulletin, request_body
from pipeline.banned import find_banned
from pipeline.guard import check_paragraph, clean
from pipeline.news import NewsError, fetch_all, parse_rss, strip_html
from pipeline.push import build
from tests.fakehttp import FakeServer

ALLOWED = {"SYM1", "LVL1", "SIG1", "COUNT", "TIME"}
TABLE = {"SYM1": "HPG", "LVL1": "2", "SIG1": "khối lượng tăng mạnh bất thường", "COUNT": "1", "TIME": "09:50"}
IDS = {"n1", "n2"}


def ok(text, refs=()):
    return check_paragraph(text, ALLOWED, IDS, refs)[0]


class NumericVariableTest(unittest.TestCase):  # G1
    def test_adjacent_numeric_variables_are_rejected(self):
        for bad in ("{SYM1} mức {LVL1}{COUNT}", "{SYM1} mức {LVL1}.{COUNT}", "{SYM1} mức {LVL1}{LVL1}",
                    "{SYM1} mức {LVL1} {COUNT}", "{SYM1} mức {LVL1}, {COUNT}", "{SYM1} mức {LVL1} - {TIME}",
                    "{SYM1} có {COUNT}{TIME} mã"):
            self.assertFalse(ok(bad), bad)

    def test_a_numeric_variable_needs_its_fixed_label(self):
        self.assertFalse(ok("{SYM1} nổi bật {LVL1}"))
        self.assertFalse(ok("{SYM1} xếp hạng {LVL1}"))
        self.assertFalse(ok("Bản tin {TIME} nổi bật {COUNT}"))

    def test_labelled_numeric_variables_are_fine(self):
        self.assertTrue(ok("{SYM1} nổi bật ở mức {LVL1}."))
        self.assertTrue(ok("Hiện có {COUNT} mã nổi bật."))
        self.assertTrue(ok("Bản tin lúc {TIME}: {SYM1} nổi bật."))
        self.assertTrue(ok("{SYM1} mức {LVL1}; {SYM1} mức {LVL1} khác"))

    def test_text_variables_may_sit_next_to_each_other(self):
        self.assertTrue(ok("{SYM1} {SIG1}"))


class NumberWordTest(unittest.TestCase):  # G2
    def test_invisible_characters_cannot_split_a_number_word(self):
        for bad in ("h\u200bai tr\u200băm", "mư\u00adời", "tr\u2060iệu", "h\u200dai", "phần\u200b trăm", "ba mươ\ufeffi"):
            self.assertFalse(ok("{SYM1} " + bad), repr(bad))

    def test_combining_marks_do_not_hide_a_word(self):
        self.assertFalse(ok("{SYM1} trăm"))  # decomposed "trăm"
        self.assertFalse(ok("{SYM1} nghìn"))

    def test_numeric_characters_of_any_script_are_rejected(self):
        for bad in ("三百", "一", "½ số lệnh", "٣", "²", "Ⅻ", "٥ mã"):
            self.assertFalse(ok("{SYM1} " + bad), bad)

    def test_english_number_words_are_rejected(self):
        for bad in ("one hundred", "twenty", "doubled", "triple the volume", "half of orders", "a dozen",
                    "thirty percent", "million shares", "billion", "two", "ninety"):
            self.assertFalse(ok("{SYM1} " + bad.replace("doubled", "double")), bad)

    def test_vietnamese_number_words_with_and_without_accents(self):
        for bad in ("không", "một", "mười", "chục", "trăm", "nghìn", "ngàn", "triệu", "tỷ", "phần trăm", "rưỡi",
                    "khong", "mot", "muoi", "chuc", "tram", "nghin", "ngan", "trieu", "ty", "phan tram", "ruoi"):
            self.assertFalse(ok("{SYM1} " + bad), bad)

    def test_homoglyphs_from_other_alphabets_are_rejected(self):
        self.assertFalse(ok("{SYM1} nổi bật hоm nay"))  # Cyrillic o
        self.assertFalse(ok("{SYM1} nổi bật аnd"))      # Cyrillic a
        self.assertFalse(ok("{SYM1} nổi bật ζ"))
        self.assertFalse(ok("{SYM1} nổi bật 😀"))

    def test_plain_vietnamese_with_all_its_letters_is_accepted(self):
        self.assertTrue(ok("{SYM1} nổi bật, khối ngoại đáng chú ý: ơ ư đ ă â ê ô."))

    def test_everyday_words_next_to_number_words_are_not_collateral(self):
        self.assertTrue(ok("{SYM1} có dấu hiệu từ khối ngoại, sau phiên sáng"))


class AdviceWordingTest(unittest.TestCase):  # G3
    BAD = ["Hãy mua HPG", "hãy bán cổ phiếu này", "Nên cân nhắc mua HPG", "nên cân nhắc bán FPT",
           "Nên xuống tiền", "nên giải ngân ngay", "Nên chốt lời", "nên cắt lỗ", "Nên gom thêm", "nên canh mua", "nên canh bán",
           "Cơ hội mua hấp dẫn", "cơ hội bán", "Đáng mua", "đáng bán",
           "hay mua", "hay ban", "nen can nhac mua", "nen xuong tien", "nen giai ngan", "nen chot loi", "nen cat lo",
           "nen gom", "nen canh mua", "co hoi mua", "co hoi ban", "dang mua", "dang ban",
           "This is a good time to buy", "good time to sell", "You may consider buying HPG", "consider selling",
           "It is time to buy", "time to sell now",
           "Dự kiến tăng mạnh", "Kỳ vọng giảm", "Nhiều khả năng tăng", "Có thể tăng", "có thể giảm",
           "du kien tang", "ky vong giam", "nhieu kha nang tang", "co the giam", "Dự kiến sẽ tăng", "Có thể sẽ giảm"]

    def test_every_listed_advice_or_forecast_is_flagged(self):
        for text in self.BAD:
            self.assertTrue(find_banned(text), text)

    def test_old_patterns_still_work(self):
        for text in ["Nên mua HPG", "Khuyến nghị nắm giữ", "Mua ngay", "Giá mục tiêu", "Tín hiệu bán"]:
            self.assertTrue(find_banned(text), text)

    def test_flow_reporting_and_disclaimers_stay_allowed(self):
        for text in ["Khối ngoại mua vào 2 triệu cổ phiếu", "Khối ngoại bán ra", "Khối ngoại mua ròng lớn",
                     "Không phải khuyến nghị đầu tư.",
                     "Nội dung chỉ mang tính thông tin tham khảo, không phải tư vấn đầu tư, khuyến nghị mua/bán hay lời mời giao dịch."]:
            self.assertEqual(find_banned(text), [], text)

    def test_sentences_produced_by_the_templates_are_not_flagged(self):
        table = build_table([{"symbol": s, "level": 2, "signals": [{"id": i, "dir": d} for i, d in
                              (("S1", None), ("S2", "buy"), ("S2", "sell"), ("S3", None), ("S4", "up"),
                               ("S4", "down"), ("S5", "up"), ("S5", "down"))]} for s in ("HPG",)], "09:50")
        self.assertEqual(find_banned(" ".join(table.values())), [])
        self.assertEqual(find_banned("\n".join(agent.fallback_bulletin(table))), [])


class KnownSymbolTest(unittest.TestCase):  # G4
    def test_known_tickers_are_rejected_in_any_case(self):
        for bad in ("HPG nổi bật", "hpg nổi bật", "Hpg nổi bật", "{SYM1} và fpt", "{SYM1} và Vcb", "AAPL tăng",
                    "aapl", "nvda", "{SYM1} và V", "{SYM1} và v"):
            self.assertFalse(ok(bad), bad)

    def test_unknown_ticker_shaped_words_are_rejected(self):
        for bad in ("ABC nổi bật", "{SYM1} và XYZ", "{SYM1} và AB", "{SYM1} và HOSE", "{SYM1} và ABCDE"):
            self.assertFalse(ok(bad), bad)

    def test_placeholders_market_names_and_ordinary_words_pass(self):
        self.assertTrue(ok("{SYM1} nổi bật"))
        self.assertTrue(ok("VN và US cùng nổi bật, {SYM1}"))
        self.assertTrue(ok("Dòng tiền lan tỏa, {SYM1} dẫn đầu"))

    def test_a_given_symbol_list_overrides_the_file(self):
        self.assertFalse(check_paragraph("{SYM1} và qqq", ALLOWED, IDS, symbols={"QQQ"})[0])
        self.assertTrue(check_paragraph("{SYM1} và hpg", ALLOWED, IDS, symbols={"QQQ"})[0])


class LinkTest(unittest.TestCase):  # G5
    def test_links_of_every_shape_are_rejected(self):
        for bad in ("xem t.me/kenh", "vào zalo.me/abc", "bit.ly/x", "liên hệ a@b.com", "{SYM1}/ngày", "xem t.me",
                    "mở example.com", "đọc \\tại đây", "tại www.x.vn", "http://x"):
            self.assertFalse(ok(bad), bad)

    def test_ordinary_punctuation_is_fine(self):
        self.assertTrue(ok("{SYM1} nổi bật. Khối ngoại chú ý, phiên sáng sôi động!"))


class StripHtmlTest(unittest.TestCase):  # G5
    def test_escaped_tags_are_removed_too(self):
        self.assertEqual(strip_html("&lt;b&gt;đậm&lt;/b&gt; và &lt;script&gt;x()&lt;/script&gt;"), "đậm và")

    def test_double_encoded_markup_does_not_survive(self):
        out = strip_html("&amp;lt;script&amp;gt;alert(1)&amp;lt;/script&amp;gt;chữ")
        self.assertNotIn("<", out)
        self.assertNotIn("script", out)

    def test_plain_text_and_ampersands_are_unchanged(self):
        self.assertEqual(strip_html("Hòa Phát &amp; Hoa Sen"), "Hòa Phát & Hoa Sen")

    def test_titles_are_capped(self):
        xml = f"<rss><channel><item><title>{'t' * 500}</title><link>https://e.com/1</link></item></channel></rss>"
        self.assertEqual(len(parse_rss(xml, "S", set())[0]["title"]), 200)


class NewsIdsTest(unittest.TestCase):  # G5
    def test_malformed_news_ids_drop_the_paragraph_without_crashing(self):
        for refs in ("n1", 5, [["n1"]], [1], [None], [{"a": 1}], {"n1": 1}, [["x"], "n1"]):
            good, dropped = clean([{"text": "{SYM1} nổi bật.", "news_ids": refs}], TABLE, IDS)
            self.assertEqual(good, [], refs)
            self.assertEqual(len(dropped), 1, refs)

    def test_missing_or_empty_ids_are_fine(self):
        good, _ = clean([{"text": "{SYM1} nổi bật."}, {"text": "{SYM1} nổi bật.", "news_ids": []}], TABLE, IDS)
        self.assertEqual(len(good), 2)


class ModelTest(unittest.TestCase):  # G6
    def test_model_is_haiku_5_5(self):
        self.assertEqual(MODEL, "claude-haiku-5-5")

    def test_request_asks_for_thinking_off_effort_low_and_a_json_schema(self):
        body = request_body(MODEL, build_table([], "09:50"), [])
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertEqual(body["output_config"]["effort"], "low")
        self.assertEqual(body["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(body["model"], "claude-haiku-5-5")

    def test_the_same_parameters_go_to_every_model_id(self):
        a = request_body("claude-haiku-5-5", {"COUNT": "0", "TIME": "x"}, [])
        b = request_body("some-other-id", {"COUNT": "0", "TIME": "x"}, [])
        self.assertEqual(a["output_config"], b["output_config"])
        self.assertEqual(a["thinking"], b["thinking"])


ITEMS = [{"symbol": "HPG", "level": 2, "signals": [{"id": "S1", "dir": None}]}]
NEWS = [{"id": "n1", "title": "Hòa Phát công bố kết quả", "link": "https://example.com/1"}]


def run_agent(handler, key="k", items=ITEMS):
    with FakeServer(handler) as s:
        return make_bulletin(items, NEWS, key, "09:50", url=s.url + "/v1/messages", sleep=lambda x: None)


class FatalReasonTest(unittest.TestCase):  # G6 / G7
    def test_config_errors_turn_the_run_red_and_say_why(self):
        for status in (400, 401, 403, 404):
            out = run_agent(lambda *a, st=status: (st, {"error": {"message": "nope"}}))
            self.assertEqual(out["source"], "fallback")
            self.assertTrue(out["fatal"], status)
            self.assertEqual(exit_code(out), 1)
            self.assertTrue(out["reason"].startswith("config_error:"), out["reason"])
            self.assertIn(str(status), out["reason"])

    def test_a_missing_key_is_fatal(self):
        out = run_agent(lambda *a: (200, {}), key="")
        self.assertEqual((out["reason"], out["fatal"], exit_code(out)), ("no_key", True, 1))

    def test_transient_trouble_uses_the_template_quietly_but_records_it(self):
        for handler in (lambda *a: (500, {}), lambda *a: (503, {}), lambda *a: (429, {}),
                        lambda *a: (200, {"stop_reason": "refusal", "content": []}),
                        lambda *a: (200, {"stop_reason": "end_turn", "content": [{"type": "text", "text": "x"}]})):
            out = run_agent(handler)
            self.assertEqual(out["source"], "fallback")
            self.assertFalse(out["fatal"])
            self.assertEqual(exit_code(out), 0)
            self.assertTrue(out["reason"].startswith("model_error:"), out["reason"])

    def test_no_items_is_not_an_error(self):
        out = run_agent(lambda *a: (200, {}), items=[])
        self.assertEqual((out["reason"], out["fatal"]), ("no_items", False))

    def test_an_unreachable_host_is_transient(self):
        out = make_bulletin(ITEMS, NEWS, "k", "09:50", url="http://127.0.0.1:1/v1/messages", sleep=lambda x: None)
        self.assertFalse(out["fatal"])

    def test_heartbeat_detail_and_alert_line_carry_the_reason(self):
        out = run_agent(lambda *a: (401, {}))
        detail = heartbeat_detail(out)
        self.assertEqual(detail["bulletin_source"], "fallback")
        self.assertIn("config_error", detail["bulletin_reason"])
        ai = run_agent(lambda *a: (200, {"stop_reason": "end_turn", "content": [
            {"type": "text", "text": json.dumps({"paragraphs": [{"text": "{SYM1} nổi bật.", "news_ids": []}]})}]}))
        self.assertEqual(heartbeat_detail(ai), {"bulletin_source": "ai", "bulletin_reason": None})

    def test_the_key_never_leaks_through_the_reason(self):
        out = run_agent(lambda *a: (401, {"echo": "fake-key-LEAK"}), key="fake-key-LEAK")
        self.assertNotIn("fake-key-LEAK", json.dumps(out))


XML = ('<rss><channel><item><title>Tin A</title><link>https://e.com/a</link>'
       '<pubDate>Fri, 30 Oct 2026 02:00:00 +0000</pubDate></item></channel></rss>')
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


class FeedReportTest(unittest.TestCase):  # G7
    def test_result_names_the_failed_and_the_empty_sources(self):
        feeds = {"Good": "https://g/", "Bad": "https://b/", "Empty": "https://e/"}

        def get(url):
            if "b/" in url:
                raise OSError("down")
            return XML if "g/" in url else "<rss><channel></channel></rss>"

        with self.assertLogs("pipeline.news", level="WARNING") as cm:
            res = fetch_all(feeds, set(), get, now=NOW)
        self.assertEqual([i["title"] for i in res.items], ["Tin A"])
        self.assertEqual(set(res.failed), {"Bad"})
        self.assertEqual(res.empty, ["Empty"])
        self.assertTrue(any("Empty" in line and "no headlines" in line for line in cm.output))

    def test_all_feeds_failing_raises(self):
        def get(url):
            raise OSError("down")

        with self.assertRaises(NewsError):
            fetch_all({"A": "https://a/", "B": "https://b/"}, set(), get, now=NOW)

    def test_a_source_whose_items_are_all_old_is_reported_empty_not_failed(self):
        later = NOW + timedelta(days=10)
        res = fetch_all({"A": "https://a/"}, set(), lambda u: XML, now=later)
        self.assertEqual((res.items, res.failed, res.empty), ([], {}, ["A"]))


class PushPromiseTest(unittest.TestCase):  # G7
    def test_the_docstring_does_not_promise_storage(self):
        from pipeline import push
        self.assertNotIn("never dropped", push.build.__doc__)
        self.assertIn("caller", push.build.__doc__)

    def test_defer_still_carries_the_send_time(self):
        n = build("US", datetime(2026, 10, 30, 16, 0, tzinfo=timezone.utc), datetime(2026, 10, 30, 16, 0, tzinfo=timezone.utc))
        self.assertEqual(n["status"], "defer")  # 23:00 in Ho Chi Minh
        self.assertIn("send_at", n)


if __name__ == "__main__":
    unittest.main()

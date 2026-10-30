import unittest
from pathlib import Path

from pipeline.news import FEEDS, extract_symbols, fetch_all, parse_rss, strip_html, summarize
from tests.fakehttp import FakeServer

XML = (Path(__file__).parent / "fixtures" / "feed.xml").read_text(encoding="utf-8")
KNOWN = {"HPG", "FPT", "VCB", "USD", "GDP", "CEO"}  # even if the list contained them, they must not count


class StripHtmlTest(unittest.TestCase):
    def test_tags_scripts_and_entities_are_removed(self):
        self.assertEqual(strip_html("<p>A <b>B</b>&nbsp;C &amp; D</p><script>x()</script>"), "A B C & D")

    def test_whitespace_is_collapsed(self):
        self.assertEqual(strip_html("a \n\t b   c"), "a b c")

    def test_plain_text_is_unchanged(self):
        self.assertEqual(strip_html("Giá tăng 5%"), "Giá tăng 5%")


class SummarizeTest(unittest.TestCase):
    def test_short_text_is_kept(self):
        self.assertEqual(summarize("ngắn"), "ngắn")

    def test_long_text_is_cut_to_200_characters_including_the_ellipsis(self):
        out = summarize("x" * 500)
        self.assertEqual(len(out), 200)
        self.assertTrue(out.endswith("…"))

    def test_exactly_200_is_not_cut(self):
        self.assertEqual(summarize("y" * 200), "y" * 200)


class SymbolsTest(unittest.TestCase):
    def test_known_ticker_in_text_becomes_a_symbol(self):
        self.assertEqual(extract_symbols("Hòa Phát (HPG) và FPT", KNOWN), ["FPT", "HPG"])

    def test_common_acronyms_are_never_symbols(self):
        self.assertEqual(extract_symbols("USD tăng, GDP quý, CEO phát biểu", KNOWN), [])

    def test_unknown_three_letter_words_and_lowercase_are_ignored(self):
        self.assertEqual(extract_symbols("ABC hpg Vcb", KNOWN), [])

    def test_symbol_inside_a_longer_word_does_not_count(self):
        self.assertEqual(extract_symbols("HPGX và XHPG", KNOWN), [])

    def test_each_symbol_once(self):
        self.assertEqual(extract_symbols("HPG HPG HPG", KNOWN), ["HPG"])


class ParseRssTest(unittest.TestCase):
    def setUp(self):
        self.items = parse_rss(XML, "Demo", KNOWN)

    def test_items_without_title_are_dropped(self):
        self.assertEqual([i["link"] for i in self.items],
                         ["https://example.com/a1", "https://example.com/a2", "https://example.com/a3"])

    def test_fields_are_title_link_source_time_and_summary_only(self):
        first = self.items[0]
        self.assertEqual(set(first), {"id", "title", "link", "source", "published", "summary", "symbols"})
        self.assertEqual(first["source"], "Demo")
        self.assertEqual(first["published"], "2026-10-30T02:15:00+00:00")

    def test_summary_has_no_html_and_is_capped(self):
        self.assertEqual(self.items[0]["summary"], "Cổ phiếu HPG được chú ý. Xem thêm tại đây.")
        self.assertNotIn("alert", self.items[0]["summary"])
        self.assertLessEqual(len(self.items[2]["summary"]), 200)

    def test_missing_description_gives_empty_summary_and_bad_date_gives_none(self):
        self.assertEqual(self.items[1]["summary"], "")
        self.assertIsNone(self.items[1]["published"])

    def test_timezone_offset_is_converted_to_utc(self):
        self.assertEqual(self.items[2]["published"], "2026-10-29T20:00:00+00:00")

    def test_symbols_come_from_title_and_summary_with_acronyms_excluded(self):
        self.assertEqual(self.items[0]["symbols"], ["FPT", "HPG"])

    def test_ids_are_stable_and_unique(self):
        self.assertEqual(len({i["id"] for i in self.items}), 3)
        self.assertEqual(self.items[0]["id"], parse_rss(XML, "Other", KNOWN)[0]["id"])

    def test_broken_xml_gives_empty_list(self):
        self.assertEqual(parse_rss("<rss><channel><item>", "Demo", KNOWN), [])


class FetchAllTest(unittest.TestCase):
    def test_feeds_are_the_three_expected_sources(self):
        self.assertEqual(set(FEEDS), {"CafeF", "Vietstock", "VnExpress Kinh doanh"})

    def test_failing_feed_is_skipped_and_results_are_newest_first_without_duplicates(self):
        def handler(m, path, h, b):
            return (500, {}) if "bad" in path else (200, None)

        with FakeServer(handler) as s:
            def get(url):
                if "bad" in url:
                    raise OSError("down")
                return XML

            feeds = {"A": s.url + "/a", "B": s.url + "/bad", "C": s.url + "/c"}
            with self.assertLogs("pipeline.news", level="WARNING"):
                items = fetch_all(feeds, KNOWN, get)
        links = [i["link"] for i in items]
        self.assertEqual(len(links), len(set(links)))
        self.assertEqual(links[0], "https://example.com/a1")  # 02:15Z beats 20:00Z of the day before
        self.assertEqual(items[-1]["published"], None)


if __name__ == "__main__":
    unittest.main()

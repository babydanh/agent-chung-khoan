import unittest
from datetime import datetime, timedelta, timezone

from pipeline import newsrank
from pipeline.banned import find_banned

NOW = datetime(2026, 11, 5, 3, 0, tzinfo=timezone.utc)
TH = {"hot": 60}


def item(title, source="CafeF", age_min=0, symbols=(), link=None):
    pub = (NOW - timedelta(minutes=age_min)).isoformat()
    return {"id": title[:8], "title": title, "link": link or f"https://x.test/{abs(hash(title))}", "source": source,
            "published": pub, "summary": "", "symbols": list(symbols)}


class FoldTest(unittest.TestCase):
    def test_accents_case_and_d_with_stroke_are_removed(self):
        self.assertEqual(newsrank.fold("Cổ tức TIỀN mặt, Đầu tư"), "co tuc tien mat, dau tu")


class ClassifyTest(unittest.TestCase):
    def key(self, text):
        return newsrank.classify(text)[0]

    def test_common_headlines_map_to_their_event(self):
        cases = {
            "Vinamilk công bố lịch chia cổ tức tiền mặt": "dividend",
            "HPG báo lãi quý 3 tăng 20% so với cùng kỳ": "earnings",
            "Doanh thu FPT 9 tháng vượt kế hoạch": "earnings",
            "Thanh tra xử phạt công ty chứng khoán X": "legal",
            "Khởi tố nguyên chủ tịch công ty Y": "legal",
            "VIC phát hành thêm cổ phiếu tăng vốn điều lệ": "issuance",
            "SSI thâu tóm công ty quản lý quỹ": "deal",
            "FPT ký hợp đồng chuyển đổi số mới": "contract",
            "Cổ đông lớn đăng ký giao dịch 2 triệu cổ phiếu": "insider",
            "Ngân hàng Nhà nước giảm lãi suất điều hành": "macro",
            "Dư nợ margin toàn thị trường đạt kỷ lục": "liquidity",
            "VN-Index đóng cửa phiên trước ở 1.268 điểm": "other",
        }
        for text, want in cases.items():
            self.assertEqual(self.key(text), want, text)

    def test_interest_rate_is_macro_not_earnings(self):
        self.assertEqual(self.key("Lãi suất huy động tăng nhẹ"), "macro")

    def test_keywords_match_whole_words_only(self):
        self.assertEqual(self.key("Tập đoàn ký kết hợp đồng"), "contract")
        self.assertEqual(self.key("Phan Đình Dự nhận giải thưởng"), "other")

    def test_every_event_has_a_label_and_a_weight_between_zero_and_one(self):
        for key, label, weight in newsrank.EVENTS:
            self.assertTrue(label)
            self.assertTrue(0 <= weight <= 1, key)

    def test_labels_pass_the_banned_wording_scan(self):
        for _, label, _ in newsrank.EVENTS:
            self.assertEqual(find_banned(label), [], label)


class ClusterTest(unittest.TestCase):
    def test_the_same_story_from_two_sources_is_one_cluster_with_two_sources(self):
        a = item("FPT ký hợp đồng chuyển đổi số tại Nhật Bản", "CafeF", 10, ["FPT"])
        b = item("FPT ký hợp đồng chuyển đổi số mới tại Nhật", "Vietstock", 20, ["FPT"])
        c = item("HPG báo lãi quý 3 tăng 20%", "CafeF", 30, ["HPG"])
        out = newsrank.cluster([a, b, c])
        self.assertEqual(len(out), 2)
        fpt = [x for x in out if x["symbols"] == ["FPT"]][0]
        self.assertEqual(fpt["sources"], 2)
        self.assertEqual(fpt["link"], a["link"], "the newest item of the story represents it")

    def test_cluster_id_does_not_depend_on_item_order(self):
        a = item("FPT ký hợp đồng chuyển đổi số tại Nhật Bản", "CafeF", 10, ["FPT"])
        b = item("FPT ký hợp đồng chuyển đổi số mới tại Nhật", "Vietstock", 20, ["FPT"])
        self.assertEqual(newsrank.cluster([a, b])[0]["cluster"], newsrank.cluster([b, a])[0]["cluster"])

    def test_different_stories_about_one_symbol_stay_apart(self):
        a = item("FPT ký hợp đồng chuyển đổi số", "CafeF", 10, ["FPT"])
        b = item("FPT chia cổ tức tiền mặt 10%", "CafeF", 20, ["FPT"])
        self.assertEqual(len(newsrank.cluster([a, b])), 2)

    def test_same_source_twice_counts_once(self):
        a = item("FPT ký hợp đồng chuyển đổi số tại Nhật Bản", "CafeF", 10, ["FPT"])
        b = item("FPT ký hợp đồng chuyển đổi số mới tại Nhật", "CafeF", 20, ["FPT"])
        self.assertEqual(newsrank.cluster([a, b])[0]["sources"], 1)


class HotScoreTest(unittest.TestCase):
    def score(self, **kw):
        base = {"event": "earnings", "sources": 1, "published": NOW.isoformat(), "symbols": ["HPG"]}
        flows = kw.pop("flows", set())
        watch = kw.pop("watch", set())
        return newsrank.hot_score({**base, **kw}, NOW, watch, flows)

    def test_fresh_earnings_story_with_watch_and_flow_match_scores_87(self):
        self.assertEqual(self.score(watch={"HPG"}, flows={"HPG"}), 87)

    def test_a_perfect_story_scores_100(self):
        self.assertEqual(self.score(sources=3, watch={"HPG"}, flows={"HPG"}), 100)  # 30 + 20 + 20 + 15 + 15

    def test_freshness_fades_from_one_hour_to_twelve(self):
        fresh = self.score(published=(NOW - timedelta(minutes=30)).isoformat())
        half = self.score(published=(NOW - timedelta(hours=6, minutes=30)).isoformat())
        old = self.score(published=(NOW - timedelta(hours=13)).isoformat())
        self.assertGreater(fresh, half)
        self.assertGreater(half, old)
        self.assertEqual(fresh, self.score(published=NOW.isoformat()))

    def test_more_sources_score_higher_up_to_three(self):
        self.assertLess(self.score(sources=1), self.score(sources=2))
        self.assertLess(self.score(sources=2), self.score(sources=3))
        self.assertEqual(self.score(sources=3), self.score(sources=9))

    def test_flow_and_watch_each_add_fifteen(self):
        base = self.score()
        self.assertEqual(self.score(watch={"HPG"}) - base, 15)
        self.assertEqual(self.score(flows={"HPG"}) - base, 15)

    def test_a_symbol_the_story_does_not_mention_adds_nothing(self):
        self.assertEqual(self.score(watch={"VNM"}, flows={"VNM"}), self.score())

    def test_event_weight_orders_the_stories(self):
        self.assertGreater(self.score(event="legal"), self.score(event="other"))

    def test_missing_publish_time_is_treated_as_somewhat_old(self):
        self.assertLess(self.score(published=None), self.score())


if __name__ == "__main__":
    unittest.main()

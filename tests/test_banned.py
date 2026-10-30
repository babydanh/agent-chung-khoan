import unittest

from pipeline.banned import find_banned

DISCLAIMER_SHORT = "Tham khảo, không phải khuyến nghị đầu tư."
DISCLAIMER_LONG = ("Nội dung chỉ mang tính thông tin tham khảo, không phải tư vấn đầu tư, "
                   "khuyến nghị mua/bán hay lời mời giao dịch.")


class BannedPhrasesTest(unittest.TestCase):
    def test_flags_each_forbidden_phrase(self):
        for text in ["Nên mua HPG", "Nên bán FPT", "Khuyến nghị nắm giữ", "Mua ngay kẻo lỡ",
                     "Vùng mua hấp dẫn", "Tín hiệu bán", "Giá mục tiêu 30.000", "Mã vàng tuần này",
                     "Chắc chắn tăng", "Cá mập sắp kéo", "You should buy this", "Price target raised"]:
            self.assertTrue(find_banned(text), text)

    def test_flags_variants_without_accents_with_hidden_characters_and_odd_case(self):
        for text in ["nen mua", "NÊN MUA", "n​ên m‍ua", "khuyen nghi", "Khuyến nghị"]:
            self.assertTrue(find_banned(text), text)

    def test_allows_neutral_wording_and_foreign_flow_phrases(self):
        for text in ["Khối ngoại mua vào 2 triệu cổ phiếu", "Khối ngoại bán ra", "Vùng giá đáng chú ý 25.000 – 26.000",
                     "Dấu hiệu dòng tiền lớn mức 2", "Dữ liệu trễ 15 phút"]:
            self.assertEqual(find_banned(text), [], text)

    def test_required_disclaimers_are_allowed(self):
        self.assertEqual(find_banned(DISCLAIMER_SHORT), [])
        self.assertEqual(find_banned(DISCLAIMER_LONG), [])

    def test_disclaimer_does_not_shelter_a_real_recommendation(self):
        self.assertTrue(find_banned(DISCLAIMER_SHORT + " Khuyến nghị mua HPG."))


if __name__ == "__main__":
    unittest.main()

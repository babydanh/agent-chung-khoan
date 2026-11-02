import unittest

from pipeline.banned import find_banned
from pipeline.indicators import bollinger, pivot
from pipeline.zones import describe, find_zones

PIV = pivot(110, 90, 100)  # P 100, R1 110, S1 90, R2 120, S2 80
BOL = {"lower": 89.0, "mid": 99.0, "upper": 119.0}
ATR = 4.0  # tolerance 0.5 * ATR = 2


class FindZonesTest(unittest.TestCase):
    def test_levels_close_together_form_one_zone_with_both_sources(self):
        zones = find_zones(100, PIV, BOL, ATR)
        low = [z for z in zones if z["high"] < 95]
        self.assertEqual(len(low), 1)
        self.assertEqual((low[0]["low"], low[0]["high"]), (89.0, 90.0))
        self.assertEqual(low[0]["sources"], ["Bollinger dải dưới", "Pivot S1"])

    def test_lone_level_is_not_a_zone(self):
        zones = find_zones(100, PIV, BOL, ATR)
        for z in zones:
            self.assertGreaterEqual(len(z["sources"]), 2)
        self.assertFalse(any(80.0 in (z["low"], z["high"]) for z in zones))  # Pivot S2 has no neighbour

    def test_zone_containing_the_price_is_marked_inside(self):
        zones = find_zones(99.5, PIV, BOL, ATR)
        inside = [z for z in zones if z["position"] == "inside"]
        self.assertEqual(len(inside), 1)
        self.assertEqual((inside[0]["low"], inside[0]["high"]), (99.0, 100.0))

    def test_position_is_above_or_below_the_price(self):
        zones = {z["low"]: z for z in find_zones(100, PIV, BOL, ATR)}
        self.assertEqual(zones[89.0]["position"], "below")
        self.assertEqual(zones[119.0]["position"], "above")

    def test_zones_are_sorted_by_distance_from_price(self):
        zones = find_zones(100, PIV, BOL, ATR)
        dist = [z["distance"] for z in zones]
        self.assertEqual(dist, sorted(dist))

    def test_wider_tolerance_merges_more_levels(self):
        narrow = find_zones(100, PIV, BOL, ATR, tol_k=0.5)
        wide = find_zones(100, PIV, BOL, ATR, tol_k=5.0)
        self.assertLess(len(wide), len(narrow))

    def test_without_atr_or_bands_it_degrades_without_error(self):
        self.assertEqual(find_zones(100, PIV, BOL, None), [])
        self.assertEqual(find_zones(100, PIV, None, 40.0), [])  # one family alone is not a confluence
        self.assertEqual(find_zones(100, None, None, ATR), [])

    def test_input_levels_are_not_mutated(self):
        piv, bol = dict(PIV), dict(BOL)
        find_zones(100, piv, bol, ATR)
        self.assertEqual((piv, bol), (PIV, BOL))


class ZoneShapeTest(unittest.TestCase):
    def test_pivot_levels_of_a_quiet_day_alone_are_not_a_zone(self):
        tight = pivot(100.2, 99.8, 100.0)  # all five levels within 0.8 of each other
        far_bands = {"lower": 60.0, "mid": 70.0, "upper": 80.0}
        self.assertEqual(find_zones(100, tight, far_bands, 4.0), [])
        self.assertEqual(find_zones(100, tight, None, 4.0), [])

    def test_a_zone_needs_a_source_from_each_family(self):
        for z in find_zones(100, PIV, BOL, ATR, tol_k=5.0):
            families = {s.split()[0] for s in z["sources"]}
            self.assertEqual(families, {"Pivot", "Bollinger"})

    def test_zone_width_never_exceeds_the_tolerance(self):
        piv = {"P": 100.0, "R1": 101.5, "S1": 103.0, "R2": 104.5, "S2": 106.0}  # chain of 1.5 steps
        bands = {"lower": 99.0, "mid": 102.0, "upper": 107.0}
        zones = find_zones(100, piv, bands, 4.0)  # tolerance 2.0
        self.assertTrue(zones)
        for z in zones:
            self.assertLessEqual(z["high"] - z["low"], 2.0)


class DescribeTest(unittest.TestCase):
    def test_text_is_vietnamese_and_mentions_range_and_sources(self):
        z = find_zones(100, PIV, BOL, ATR)[0]
        text = describe(z)
        self.assertIn("Vùng giá đáng chú ý", text)
        self.assertIn("Pivot", text)

    def test_every_generated_text_passes_the_banned_scanner(self):
        for price in (70, 85, 99.5, 100, 118, 150):
            for z in find_zones(price, PIV, BOL, ATR, tol_k=1.0):
                self.assertEqual(find_banned(describe(z)), [], describe(z))

    def test_text_has_no_advice_words_even_by_plain_substring(self):
        words = ("mua", "bán", "ban ", "khuyến", "nên ", "khuyen")
        for z in find_zones(100, PIV, BOL, 40.0):
            text = describe(z).lower()
            for w in words:
                self.assertNotIn(w, text)

    def test_real_indicator_output_goes_through_end_to_end(self):
        closes = [50 + (i % 7) * 0.5 for i in range(30)]
        zones = find_zones(closes[-1], pivot(54, 50, 52), bollinger(closes), 1.5)
        for z in zones:
            self.assertEqual(find_banned(describe(z)), [])


if __name__ == "__main__":
    unittest.main()

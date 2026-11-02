import unittest

from pipeline.indicators import atr, bollinger, pivot, true_ranges

TOL = 1e-9


class PivotTest(unittest.TestCase):
    def test_round_numbers(self):
        p = pivot(110, 90, 100)
        self.assertAlmostEqual(p["P"], 100, delta=TOL)
        self.assertAlmostEqual(p["R1"], 110, delta=TOL)
        self.assertAlmostEqual(p["S1"], 90, delta=TOL)
        self.assertAlmostEqual(p["R2"], 120, delta=TOL)
        self.assertAlmostEqual(p["S2"], 80, delta=TOL)

    def test_fractions_match_hand_calculation(self):
        p = pivot(12, 9, 10)  # P = 31/3
        self.assertAlmostEqual(p["P"], 31 / 3, delta=TOL)
        self.assertAlmostEqual(p["R1"], 35 / 3, delta=TOL)  # 2P - L
        self.assertAlmostEqual(p["S1"], 26 / 3, delta=TOL)  # 2P - H
        self.assertAlmostEqual(p["R2"], 31 / 3 + 3, delta=TOL)
        self.assertAlmostEqual(p["S2"], 31 / 3 - 3, delta=TOL)

    def test_levels_are_ordered(self):
        p = pivot(52.4, 49.1, 51.0)
        self.assertLess(p["S2"], p["S1"])
        self.assertLess(p["S1"], p["P"])
        self.assertLess(p["P"], p["R1"])
        self.assertLess(p["R1"], p["R2"])

    def test_high_below_low_is_rejected(self):
        with self.assertRaises(ValueError):
            pivot(9, 10, 9.5)


H = [10, 12, 13, 12]
L = [8, 9, 11, 10]
C = [9, 11, 12, 11]


class TrueRangeTest(unittest.TestCase):
    def test_first_bar_uses_its_own_range_then_gaps_count(self):
        self.assertEqual(true_ranges(H, L, C), [2, 3, 2, 2])

    def test_gap_up_is_counted_through_previous_close(self):
        # bar 2 opens far above the previous close: |high - prev close| = 14 beats high - low = 2
        self.assertEqual(true_ranges([10, 25], [8, 23], [9, 24])[1], 16)

    def test_mismatched_lengths_are_rejected(self):
        with self.assertRaises(ValueError):
            true_ranges([1, 2], [1], [1, 2])


class AtrTest(unittest.TestCase):
    def test_first_value_is_simple_mean_of_first_n_true_ranges(self):
        self.assertAlmostEqual(atr(H[:3], L[:3], C[:3], n=3), 7 / 3, delta=TOL)

    def test_next_value_follows_wilder_smoothing(self):
        # (7/3 * 2 + 2) / 3 = 20/9
        self.assertAlmostEqual(atr(H, L, C, n=3), 20 / 9, delta=TOL)

    def test_constant_range_gives_that_range_with_default_period(self):
        highs = [11.0] * 30
        lows = [9.0] * 30
        closes = [10.0] * 30
        self.assertAlmostEqual(atr(highs, lows, closes), 2.0, delta=TOL)

    def test_too_few_bars_gives_none(self):
        self.assertIsNone(atr(H, L, C, n=5))

    def test_default_period_is_fourteen(self):
        highs = [10 + i for i in range(14)]
        lows = [h - 2 for h in highs]
        closes = [h - 1 for h in highs]
        # TR0 = 2, every later TR = max(2, |h - prev close| = 2, |l - prev close| = 0) = 2
        self.assertAlmostEqual(atr(highs, lows, closes), 2.0, delta=TOL)
        self.assertIsNone(atr(highs[:13], lows[:13], closes[:13]))


class BollingerTest(unittest.TestCase):
    SAMPLE = [2, 4, 4, 4, 5, 5, 7, 9]  # mean 5, population std 2

    def test_bands_match_hand_calculation(self):
        b = bollinger(self.SAMPLE, n=8, k=2)
        self.assertAlmostEqual(b["mid"], 5, delta=TOL)
        self.assertAlmostEqual(b["upper"], 9, delta=TOL)
        self.assertAlmostEqual(b["lower"], 1, delta=TOL)

    def test_width_multiplier_is_applied(self):
        b = bollinger(self.SAMPLE, n=8, k=1.5)
        self.assertAlmostEqual(b["upper"], 8, delta=TOL)
        self.assertAlmostEqual(b["lower"], 2, delta=TOL)

    def test_only_last_n_closes_count(self):
        b = bollinger([1000, -500] + self.SAMPLE, n=8, k=2)
        self.assertAlmostEqual(b["mid"], 5, delta=TOL)

    def test_flat_series_collapses_to_one_line(self):
        b = bollinger([7.5] * 20)
        self.assertEqual((b["lower"], b["mid"], b["upper"]), (7.5, 7.5, 7.5))

    def test_defaults_are_twenty_and_two(self):
        closes = list(range(1, 21))  # mean 10.5, population std sqrt(33.25)
        b = bollinger(closes)
        self.assertAlmostEqual(b["mid"], 10.5, delta=TOL)
        self.assertAlmostEqual(b["upper"], 10.5 + 2 * 33.25 ** 0.5, delta=TOL)
        self.assertIsNone(bollinger(closes[:19]))


if __name__ == "__main__":
    unittest.main()

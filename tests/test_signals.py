import unittest

from datetime import time

from pipeline.signals import US_SESSIONS, VN_SESSIONS, evaluate, robust_z, trading_minutes

TH = {"min_days": 20, "s1_z": 3.5, "min_vol": 10_000, "s2_share": 0.2, "s3_value": 10_000_000_000}
HIST = [90_000, 100_000, 110_000, 100_000, 95_000, 105_000, 100_000, 98_000, 102_000, 100_000] * 2  # 20 days
QUIET = {"vol": 100_000, "val": 5_000_000_000, "fnet": 0, "pt_val": 0}


def ids(result):
    return [s["id"] for s in result["signals"]]


class RobustZTest(unittest.TestCase):
    def test_spike_scores_high_and_typical_value_scores_near_zero(self):
        self.assertGreater(robust_z(400_000, HIST), 10)
        self.assertAlmostEqual(robust_z(100_000, HIST), 0, places=6)

    def test_flat_history_has_no_spread_so_no_score(self):
        self.assertIsNone(robust_z(500, [100] * 20))


class EvaluateTest(unittest.TestCase):
    def test_quiet_window_has_no_signal_and_level_zero(self):
        r = evaluate(QUIET, HIST, TH)
        self.assertEqual((ids(r), r["level"], r["learning"]), ([], 0, False))

    def test_all_three_signals_give_level_three(self):
        d = {"vol": 400_000, "val": 20_000_000_000, "fnet": 120_000, "pt_val": 15_000_000_000}
        r = evaluate(d, HIST, TH)
        self.assertEqual(ids(r), ["S1", "S2", "S3"])
        self.assertEqual(r["level"], 3)

    def test_foreign_net_signal_carries_direction(self):
        buy = evaluate({**QUIET, "fnet": 30_000}, HIST, TH)["signals"][0]
        sell = evaluate({**QUIET, "fnet": -30_000}, HIST, TH)["signals"][0]
        self.assertEqual((buy["id"], buy["dir"]), ("S2", "buy"))
        self.assertEqual((sell["id"], sell["dir"]), ("S2", "sell"))

    def test_tiny_window_volume_never_triggers_anything(self):
        d = {"vol": 500, "val": 1_000_000, "fnet": 500, "pt_val": 0}
        self.assertEqual(ids(evaluate(d, HIST, TH)), [])

    def test_short_baseline_is_learning_skips_s1_and_caps_level_at_one(self):
        d = {"vol": 400_000, "val": 20_000_000_000, "fnet": 120_000, "pt_val": 15_000_000_000}
        r = evaluate(d, HIST[:5], TH)
        self.assertTrue(r["learning"])
        self.assertEqual(ids(r), ["S2", "S3"])  # S1 needs the baseline, others still reported
        self.assertEqual(r["level"], 1)


TH2 = {**TH, "s4_k": 1.5, "s5_k": 1.0}
BIG = {"vol": 100_000, "val": 5_000_000_000, "fnet": 0, "pt_val": 0}


class TradingMinutesTest(unittest.TestCase):
    def test_vn_window_across_lunch_break_skips_the_break(self):
        self.assertEqual(trading_minutes(time(11, 15), time(13, 15), VN_SESSIONS), 30)

    def test_window_inside_one_session_is_plain_difference(self):
        self.assertEqual(trading_minutes(time(9, 30), time(10, 0), VN_SESSIONS), 30)

    def test_time_before_open_and_after_close_is_clipped(self):
        self.assertEqual(trading_minutes(time(9, 0), time(9, 45), US_SESSIONS), 15)
        self.assertEqual(trading_minutes(time(15, 30), time(16, 40), US_SESSIONS), 30)

    def test_window_fully_outside_sessions_is_zero(self):
        self.assertEqual(trading_minutes(time(11, 35), time(12, 55), VN_SESSIONS), 0)


class PerMinuteS1Test(unittest.TestCase):
    HIST_MIN = [30] * 20  # every past window held 30 trading minutes

    def test_same_volume_in_fewer_trading_minutes_triggers_s1(self):
        # 100k over 15 trading minutes (lunch break inside the window) is twice the usual pace
        raw = evaluate(BIG, HIST, TH)
        per_min = evaluate(BIG, HIST, TH, minutes=15, history_minutes=self.HIST_MIN)
        self.assertNotIn("S1", ids(raw))
        self.assertIn("S1", ids(per_min))

    def test_usual_pace_in_a_shorter_window_does_not_trigger(self):
        d = {**BIG, "vol": 50_000}
        r = evaluate(d, HIST, TH, minutes=15, history_minutes=self.HIST_MIN)
        self.assertNotIn("S1", ids(r))

    def test_zero_minutes_is_skipped_instead_of_dividing(self):
        r = evaluate(BIG, HIST, TH, minutes=0, history_minutes=self.HIST_MIN)
        self.assertNotIn("S1", ids(r))

    def test_history_length_must_match(self):
        with self.assertRaises(ValueError):
            evaluate(BIG, HIST, TH, minutes=30, history_minutes=[30] * 5)

    def test_minutes_without_history_minutes_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(BIG, HIST, TH, minutes=30)


class S4Test(unittest.TestCase):
    def test_move_of_at_least_k_atr_triggers_with_direction(self):
        up = evaluate({**BIG, "px_move": 3.0}, HIST, TH2, atr=2.0)
        down = evaluate({**BIG, "px_move": -3.0}, HIST, TH2, atr=2.0)
        self.assertEqual([(s["id"], s["dir"]) for s in up["signals"]], [("S4", "up")])
        self.assertEqual([(s["id"], s["dir"]) for s in down["signals"]], [("S4", "down")])

    def test_smaller_move_does_not_trigger(self):
        self.assertEqual(ids(evaluate({**BIG, "px_move": 2.9}, HIST, TH2, atr=2.0)), [])

    def test_without_atr_or_move_or_threshold_it_stays_off(self):
        self.assertEqual(ids(evaluate({**BIG, "px_move": 9.0}, HIST, TH2)), [])
        self.assertEqual(ids(evaluate(BIG, HIST, TH2, atr=2.0)), [])
        self.assertEqual(ids(evaluate({**BIG, "px_move": 9.0}, HIST, TH, atr=2.0)), [])

    def test_tiny_volume_blocks_it(self):
        d = {"vol": 500, "val": 1, "fnet": 0, "pt_val": 0, "px_move": 9.0}
        self.assertEqual(ids(evaluate(d, HIST, TH2, atr=2.0)), [])

    def test_counts_toward_level_and_learning_cap(self):
        d = {**BIG, "fnet": 30_000, "px_move": 3.0}
        self.assertEqual(evaluate(d, HIST, TH2, atr=2.0)["level"], 2)
        r = evaluate(d, HIST[:5], TH2, atr=2.0)
        self.assertEqual((ids(r), r["level"]), (["S2", "S4"], 1))


class S5Test(unittest.TestCase):
    US_DAY = {**BIG, "open": 105.0, "prev_close": 100.0}

    def test_us_gap_of_at_least_k_atr_triggers_with_direction(self):
        r = evaluate(self.US_DAY, HIST, TH2, atr=4.0, market="US")
        self.assertEqual([(s["id"], s["dir"]) for s in r["signals"]], [("S5", "up")])
        gap_down = {**BIG, "open": 95.0, "prev_close": 100.0}
        r = evaluate(gap_down, HIST, TH2, atr=4.0, market="US")
        self.assertEqual([(s["id"], s["dir"]) for s in r["signals"]], [("S5", "down")])

    def test_small_gap_does_not_trigger(self):
        d = {**BIG, "open": 103.0, "prev_close": 100.0}
        self.assertEqual(ids(evaluate(d, HIST, TH2, atr=4.0, market="US")), [])

    def test_vn_market_never_reports_s5(self):
        self.assertEqual(ids(evaluate(self.US_DAY, HIST, TH2, atr=4.0, market="VN")), [])
        self.assertEqual(ids(evaluate(self.US_DAY, HIST, TH2, atr=4.0)), [])

    def test_missing_inputs_keep_it_off(self):
        self.assertEqual(ids(evaluate(self.US_DAY, HIST, TH2, market="US")), [])
        self.assertEqual(ids(evaluate(BIG, HIST, TH2, atr=4.0, market="US")), [])

    def test_gap_signal_does_not_need_window_volume(self):
        # the opening gap is a fact of the session, not of this window
        d = {"vol": 0, "val": 0, "fnet": 0, "pt_val": 0, "open": 105.0, "prev_close": 100.0}
        self.assertEqual(ids(evaluate(d, HIST, TH2, atr=4.0, market="US")), ["S5"])


if __name__ == "__main__":
    unittest.main()

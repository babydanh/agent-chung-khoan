import unittest

from pipeline.signals import evaluate, robust_z

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


if __name__ == "__main__":
    unittest.main()

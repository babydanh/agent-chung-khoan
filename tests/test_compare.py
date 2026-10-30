import unittest

from pipeline.compare import delta, delta_all

PREV = {"TT": 1000, "TV": 50_000_000, "FB": 100, "FS": 300, "PTQ": 0, "PTV": 0}
CURR = {"TT": 1600, "TV": 81_000_000, "FB": 400, "FS": 350, "PTQ": 200, "PTV": 12_000_000}


class DeltaTest(unittest.TestCase):
    def test_window_numbers_are_differences_of_cumulative_fields(self):
        d = delta(PREV, CURR)
        self.assertEqual(d["vol"], 600)
        self.assertEqual(d["val"], 31_000_000)
        self.assertEqual(d["fnet"], 250)  # (400-350) - (100-300)
        self.assertEqual(d["pt_val"], 12_000_000)

    def test_cumulative_field_going_down_means_new_session_so_no_delta(self):
        self.assertIsNone(delta(CURR, PREV))

    def test_delta_all_skips_symbols_missing_or_unlisted_in_either_snapshot(self):
        prev = {"AAA": PREV, "BBB": PREV, "CCC": {"SB": "CCC", "IT": "12:00:00"}}
        curr = {"AAA": CURR, "CCC": CURR, "DDD": CURR}
        self.assertEqual(set(delta_all(prev, curr)), {"AAA"})


if __name__ == "__main__":
    unittest.main()

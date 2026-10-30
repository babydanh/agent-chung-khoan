import re
import unittest
from datetime import datetime, timezone

from pipeline.banned import find_banned
from pipeline.push import build

UTC = timezone.utc


def vn(h, m=0):  # a Vietnam wall-clock time on 2026-10-30 as UTC
    return datetime(2026, 10, 30, h - 7, m, tzinfo=UTC) if h >= 7 else datetime(2026, 10, 29, h + 17, m, tzinfo=UTC)


class BuildTest(unittest.TestCase):
    def test_vn_bulletin_text_is_only_the_time(self):
        n = build("VN", vn(9, 50), now=vn(9, 51))
        self.assertEqual(n["body"], "Bản tin 09:50 đã có")

    def test_no_digit_other_than_the_time(self):
        n = build("VN", vn(15, 5), now=vn(15, 6))
        left = n["body"].replace("15:05", "") + n["title"]
        self.assertFalse(re.search(r"\d", left))

    def test_output_passes_the_banned_scanner(self):
        n = build("US", vn(21, 30), now=vn(21, 31))
        self.assertEqual(find_banned(n["title"] + " " + n["body"]), [])

    def test_us_bulletin_is_held_back_from_22_to_07_vietnam_time(self):
        for h in (22, 23, 0, 3, 6):
            self.assertIsNone(build("US", vn(h, 30), now=vn(h, 31)), h)

    def test_us_bulletin_goes_out_in_the_evening_and_from_07(self):
        self.assertIsNotNone(build("US", vn(21, 59), now=vn(21, 59)))
        self.assertIsNotNone(build("US", vn(7, 0), now=vn(7, 0)))

    def test_quiet_hours_follow_the_moment_of_sending_not_the_bulletin_time(self):
        self.assertIsNone(build("US", vn(21, 30), now=vn(22, 5)))
        self.assertIsNotNone(build("US", vn(23, 30), now=vn(7, 5)))

    def test_vn_bulletins_are_never_held_back(self):
        self.assertIsNotNone(build("VN", vn(9, 20), now=vn(7, 0)))

    def test_time_is_shown_in_vietnam_time(self):
        self.assertIn("21:05", build("US", vn(21, 5), now=vn(21, 6))["body"])

    def test_naive_datetimes_and_unknown_markets_are_rejected(self):
        with self.assertRaises(ValueError):
            build("VN", datetime(2026, 10, 30, 9, 50), now=vn(9, 51))
        with self.assertRaises(ValueError):
            build("JP", vn(9, 50), now=vn(9, 51))


if __name__ == "__main__":
    unittest.main()

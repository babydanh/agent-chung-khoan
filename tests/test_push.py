import re
import unittest
from datetime import datetime, timedelta, timezone

from pipeline.banned import find_banned
from pipeline.push import build

UTC = timezone.utc


def vn(h, m=0):  # a Vietnam wall-clock time on 2026-10-30 as UTC
    return datetime(2026, 10, 30, h - 7, m, tzinfo=UTC) if h >= 7 else datetime(2026, 10, 29, h + 17, m, tzinfo=UTC)


class BuildTest(unittest.TestCase):
    def test_vn_bulletin_text_is_only_the_time(self):
        n = build("VN", vn(9, 50), now=vn(9, 51))
        self.assertEqual((n["status"], n["body"]), ("send", "Bản tin 09:50 đã có"))

    def test_no_digit_other_than_the_time(self):
        n = build("VN", vn(15, 5), now=vn(15, 6))
        left = n["body"].replace("15:05", "") + n["title"]
        self.assertFalse(re.search(r"\d", left))

    def test_output_passes_the_banned_scanner(self):
        n = build("US", vn(21, 30), now=vn(21, 31))
        self.assertEqual(find_banned(n["title"] + " " + n["body"]), [])

    def test_us_bulletin_is_deferred_not_dropped_from_22_to_07_vietnam_time(self):
        for h in (22, 23, 0, 3, 6):
            n = build("US", vn(h, 30), now=vn(h, 31))
            self.assertEqual(n["status"], "defer", h)
            self.assertEqual(n["body"], f"Bản tin {h:02d}:30 đã có")  # same text, sent later

    def test_deferred_bulletin_goes_out_at_seven_vietnam_time(self):
        late_evening = build("US", vn(23, 30), now=vn(23, 31))
        self.assertEqual(datetime.fromisoformat(late_evening["send_at"]), vn(7, 0) + timedelta(days=1))
        small_hours = build("US", vn(3, 0), now=vn(3, 1))
        self.assertEqual(datetime.fromisoformat(small_hours["send_at"]), vn(7, 0))

    def test_sending_now_has_no_send_at(self):
        self.assertNotIn("send_at", build("US", vn(21, 30), now=vn(21, 31)))

    def test_from_november_every_us_run_lands_in_quiet_hours(self):
        # 14 runs, 10:05..16:50 New York in winter time = 23:05..05:50 Vietnam time next day
        for h, m in [(23, 5), (23, 35), (0, 5), (2, 35), (4, 5), (5, 35), (5, 50)]:
            self.assertEqual(build("US", vn(h, m), now=vn(h, m))["status"], "defer")

    def test_us_bulletin_goes_out_in_the_evening_and_from_07(self):
        self.assertEqual(build("US", vn(21, 59), now=vn(21, 59))["status"], "send")
        self.assertEqual(build("US", vn(7, 0), now=vn(7, 0))["status"], "send")

    def test_quiet_hours_follow_the_moment_of_sending_not_the_bulletin_time(self):
        self.assertEqual(build("US", vn(21, 30), now=vn(22, 5))["status"], "defer")
        self.assertEqual(build("US", vn(23, 30), now=vn(7, 5))["status"], "send")

    def test_vn_bulletins_are_never_held_back(self):
        self.assertEqual(build("VN", vn(9, 20), now=vn(7, 0))["status"], "send")
        self.assertEqual(build("VN", vn(9, 20), now=vn(23, 0))["status"], "send")

    def test_time_is_shown_in_vietnam_time(self):
        self.assertIn("21:05", build("US", vn(21, 5), now=vn(21, 6))["body"])

    def test_naive_datetimes_and_unknown_markets_are_rejected(self):
        with self.assertRaises(ValueError):
            build("VN", datetime(2026, 10, 30, 9, 50), now=vn(9, 51))
        with self.assertRaises(ValueError):
            build("JP", vn(9, 50), now=vn(9, 51))


if __name__ == "__main__":
    unittest.main()

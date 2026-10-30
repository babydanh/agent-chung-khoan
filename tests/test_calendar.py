import unittest
from datetime import datetime, timezone

from pipeline.calendar import is_run_window

CAL = {
    "VN": {"holidays": ["2027-01-01"]},
    "US": {"holidays": ["2026-11-26", "2026-12-25"], "early_close": ["2026-11-27", "2026-12-24"]},
}


def utc(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


class VietnamWindowTest(unittest.TestCase):
    def test_runs_in_morning_and_afternoon_but_not_in_lunch_break(self):
        self.assertTrue(is_run_window("VN", utc(2026, 11, 2, 2, 20), CAL))   # 09:20 ICT
        self.assertTrue(is_run_window("VN", utc(2026, 11, 2, 4, 40), CAL))   # 11:40 ICT
        self.assertFalse(is_run_window("VN", utc(2026, 11, 2, 5, 5), CAL))   # 12:05 ICT
        self.assertTrue(is_run_window("VN", utc(2026, 11, 2, 8, 5), CAL))    # 15:05 ICT, after the close
        self.assertFalse(is_run_window("VN", utc(2026, 11, 2, 8, 15), CAL))  # 15:15 ICT

    def test_closed_on_weekend_and_listed_holiday(self):
        self.assertFalse(is_run_window("VN", utc(2026, 10, 31, 3, 0), CAL))  # Saturday
        self.assertFalse(is_run_window("VN", utc(2027, 1, 1, 3, 0), CAL))    # holiday on a Friday


class UnitedStatesWindowTest(unittest.TestCase):
    def test_follows_new_york_clock_across_the_november_1_time_change(self):
        # Fri 2026-10-30 is still EDT (UTC-4); Mon 2026-11-02 is EST (UTC-5)
        self.assertFalse(is_run_window("US", utc(2026, 10, 30, 13, 55), CAL))  # 09:55 EDT
        self.assertTrue(is_run_window("US", utc(2026, 10, 30, 14, 5), CAL))    # 10:05 EDT
        self.assertFalse(is_run_window("US", utc(2026, 11, 2, 14, 55), CAL))   # 09:55 EST
        self.assertTrue(is_run_window("US", utc(2026, 11, 2, 15, 5), CAL))     # 10:05 EST

    def test_last_runs_after_the_close_are_allowed_then_stop(self):
        self.assertTrue(is_run_window("US", utc(2026, 11, 2, 21, 50), CAL))    # 16:50 EST
        self.assertFalse(is_run_window("US", utc(2026, 11, 2, 21, 55), CAL))  # 16:55 EST

    def test_closed_on_holiday(self):
        self.assertFalse(is_run_window("US", utc(2026, 11, 26, 16, 0), CAL))

    def test_early_close_day_stops_fifty_minutes_after_one_pm(self):
        self.assertTrue(is_run_window("US", utc(2026, 11, 27, 18, 20), CAL))   # 13:20 EST
        self.assertFalse(is_run_window("US", utc(2026, 11, 27, 18, 55), CAL))  # 13:55 EST


class InputGuardTest(unittest.TestCase):
    def test_naive_datetime_is_rejected(self):
        with self.assertRaises(ValueError):
            is_run_window("VN", datetime(2026, 11, 2, 9, 20), CAL)

    def test_unknown_market_is_rejected(self):
        with self.assertRaises(ValueError):
            is_run_window("JP", utc(2026, 11, 2, 2, 20), CAL)


if __name__ == "__main__":
    unittest.main()

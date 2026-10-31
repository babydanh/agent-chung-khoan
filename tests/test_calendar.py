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
        self.assertTrue(is_run_window("VN", utc(2026, 11, 2, 4, 55), CAL))   # 11:55 ICT, the 11:40 run, delayed
        self.assertTrue(is_run_window("VN", utc(2026, 11, 2, 5, 10), CAL))   # 12:10 ICT: the 11:40 run, delayed
        self.assertFalse(is_run_window("VN", utc(2026, 11, 2, 5, 30), CAL))  # 12:30 ICT, lunch break
        self.assertFalse(is_run_window("VN", utc(2026, 11, 2, 5, 20), CAL))  # 12:20 ICT, past the 12:15 end
        self.assertTrue(is_run_window("VN", utc(2026, 11, 2, 8, 5), CAL))    # 15:05 ICT, after the close
        self.assertTrue(is_run_window("VN", utc(2026, 11, 2, 8, 35), CAL))   # 15:35 ICT: the 15:05 run, delayed
        self.assertFalse(is_run_window("VN", utc(2026, 11, 2, 8, 45), CAL))  # 15:45 ICT

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
        self.assertTrue(is_run_window("US", utc(2026, 11, 2, 22, 15), CAL))    # 17:15 EST: the 16:50 run, delayed
        self.assertFalse(is_run_window("US", utc(2026, 11, 2, 22, 25), CAL))  # 17:25 EST

    def test_closed_on_holiday(self):
        self.assertFalse(is_run_window("US", utc(2026, 11, 26, 16, 0), CAL))

    def test_early_close_day_stops_fifty_minutes_after_one_pm(self):
        self.assertTrue(is_run_window("US", utc(2026, 11, 27, 18, 20), CAL))   # 13:20 EST
        self.assertTrue(is_run_window("US", utc(2026, 11, 27, 19, 10), CAL))   # 14:10 EST, still inside 80 minutes
        self.assertFalse(is_run_window("US", utc(2026, 11, 27, 19, 25), CAL))  # 14:25 EST


class InputGuardTest(unittest.TestCase):
    def test_naive_datetime_is_rejected(self):
        with self.assertRaises(ValueError):
            is_run_window("VN", datetime(2026, 11, 2, 9, 20), CAL)

    def test_unknown_market_is_rejected(self):
        with self.assertRaises(ValueError):
            is_run_window("JP", utc(2026, 11, 2, 2, 20), CAL)


class ShippedCalendarTest(unittest.TestCase):
    """config/calendar.json: holidays through 2027 must be weekdays and must close the run window."""

    @classmethod
    def setUpClass(cls):
        import os
        from pipeline.calendar import load
        cls.cal = load(os.path.join(os.path.dirname(__file__), "..", "config", "calendar.json"))

    def test_every_listed_day_is_a_weekday(self):
        from datetime import date
        for market in ("VN", "US"):
            for day in self.cal[market]["holidays"] + self.cal.get(market, {}).get("early_close", []):
                self.assertLess(date.fromisoformat(day).weekday(), 5, (market, day))

    def test_us_2027_holidays_follow_the_exchange_rules(self):
        want = {"2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
                "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"}
        self.assertTrue(want <= set(self.cal["US"]["holidays"]), want - set(self.cal["US"]["holidays"]))
        self.assertIn("2027-11-26", self.cal["US"]["early_close"])

    def test_us_2026_year_end_is_still_listed(self):
        self.assertTrue({"2026-11-26", "2026-12-25"} <= set(self.cal["US"]["holidays"]))

    def test_vn_2027_fixed_holidays_including_weekend_make_up_days(self):
        want = {"2027-01-01", "2027-04-30", "2027-05-03", "2027-09-02"}
        self.assertTrue(want <= set(self.cal["VN"]["holidays"]), want - set(self.cal["VN"]["holidays"]))

    def test_listed_holidays_close_the_run_window(self):
        self.assertFalse(is_run_window("US", utc(2027, 7, 5, 15, 5), self.cal))
        self.assertFalse(is_run_window("VN", utc(2027, 5, 3, 3, 0), self.cal))

    def test_no_duplicates(self):
        for market in ("VN", "US"):
            days = self.cal[market]["holidays"]
            self.assertEqual(len(days), len(set(days)))


if __name__ == "__main__":
    unittest.main()

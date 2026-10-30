import json
import os
import tempfile
import unittest

from pipeline.config import load

GOOD = {"min_days": 20, "s1_z": 3.5, "min_vol": 10000, "s2_share": 0.2, "s3_value": 10_000_000_000}


def write(data):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, f)
    f.close()
    return f.name


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.paths = []

    def tearDown(self):
        for p in self.paths:
            os.unlink(p)

    def path(self, data):
        p = write(data)
        self.paths.append(p)
        return p

    def test_returns_market_thresholds_with_config_version(self):
        th = load(self.path({"version": 3, "VN": GOOD}), "VN")
        self.assertEqual(th["s1_z"], 3.5)
        self.assertEqual(th["version"], 3)

    def test_missing_key_is_an_error_naming_the_key(self):
        bad = {k: v for k, v in GOOD.items() if k != "s2_share"}
        with self.assertRaisesRegex(ValueError, "s2_share"):
            load(self.path({"version": 1, "VN": bad}), "VN")

    def test_missing_market_or_version_is_an_error(self):
        with self.assertRaises(ValueError):
            load(self.path({"version": 1, "VN": GOOD}), "US")
        with self.assertRaises(ValueError):
            load(self.path({"VN": GOOD}), "VN")

    def test_shipped_file_loads_for_vietnam(self):
        self.assertEqual(load("config/thresholds.json", "VN")["min_days"], 20)


if __name__ == "__main__":
    unittest.main()

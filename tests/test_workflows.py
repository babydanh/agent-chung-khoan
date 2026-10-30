import re
import unittest
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / "ci-pending" / "workflows"
VN_TIMES = ["9:20", "9:50", "10:20", "10:50", "11:20", "11:40", "13:20", "13:50", "14:20", "14:50", "15:05"]
US_TIMES = [f"{h}:{m:02d}" for h in range(10, 16) for m in (5, 35)] + ["16:20", "16:50"]


def read(name):
    return (WF / name).read_text(encoding="utf-8")


def crons(text):
    """(hour:minute, timezone) per schedule entry."""
    return [(f"{int(h)}:{int(m):02d}", tz) for m, h, tz in
            re.findall(r'- cron: "(\d+) (\d+) \* \* [\d,\-*]+"\s+timezone: "([^"]+)"', text)]


class SnapshotWorkflowTest(unittest.TestCase):
    def test_vn_schedule_has_the_eleven_runs_in_ho_chi_minh_time(self):
        self.assertEqual(sorted(crons(read("snap-vn.yml"))),
                         sorted((t, "Asia/Ho_Chi_Minh") for t in VN_TIMES))

    def test_us_schedule_has_the_fourteen_runs_in_new_york_time(self):
        found = crons(read("snap-us.yml"))
        self.assertEqual(len(found), 14)
        self.assertEqual(sorted(found), sorted((t, "America/New_York") for t in US_TIMES))

    def test_schedules_run_on_weekdays_only(self):
        for name in ("snap-vn.yml", "snap-us.yml", "eod.yml"):
            for cron in re.findall(r'- cron: "([^"]+)"', read(name)):
                self.assertTrue(cron.endswith(" * * 1-5"), (name, cron))

    def test_runs_are_wired_to_the_right_market(self):
        self.assertIn("python3 -m pipeline.run --market VN", read("snap-vn.yml"))
        self.assertIn("python3 -m pipeline.run --market US", read("snap-us.yml"))
        self.assertIn("python3 -m pipeline.cleanup", read("eod.yml"))


class AllWorkflowsTest(unittest.TestCase):
    NAMES = ("snap-vn.yml", "snap-us.yml", "eod.yml", "ci.yml")

    def test_least_privilege_and_manual_trigger(self):
        for n in self.NAMES:
            t = read(n)
            self.assertRegex(t, r"permissions:\s+contents: read", n)
            self.assertNotRegex(t, r"contents: write|id-token|write-all", n)
        for n in self.NAMES[:3]:
            self.assertIn("workflow_dispatch:", read(n), n)

    def test_scheduled_workflows_do_not_overlap_themselves(self):
        for n in self.NAMES[:3]:
            t = read(n)
            self.assertIn("concurrency:", t, n)
            self.assertIn("cancel-in-progress: false", t, n)

    def test_every_action_is_pinned_to_a_full_commit_sha(self):
        for n in self.NAMES:
            uses = re.findall(r"uses:\s*(\S+)", read(n))
            self.assertTrue(uses, n)
            for u in uses:
                self.assertRegex(u, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$", (n, u))

    def test_secrets_come_from_the_secrets_context_and_missing_ones_fail_the_run(self):
        for n, names in (("snap-vn.yml", ["SUPABASE_URL", "SUPABASE_SECRET_KEY"]),
                         ("snap-us.yml", ["SUPABASE_URL", "SUPABASE_SECRET_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"]),
                         ("eod.yml", ["SUPABASE_URL", "SUPABASE_SECRET_KEY"])):
            t = read(n)
            for s in names:
                self.assertIn(f"{s}: ${{{{ secrets.{s} }}}}", t, (n, s))
                self.assertIn(f'"{s}"', t, (n, s))  # named in the presence check
            self.assertIn("exit 1", t, n)

    def test_secret_values_are_never_echoed(self):
        for n in self.NAMES:
            self.assertNotRegex(read(n), r"echo[^\n]*\$\{?\{?\s*secrets\.", n)
            self.assertNotIn("set -x", read(n), n)

    def test_ci_runs_the_unit_tests_on_push_and_pull_request(self):
        t = read("ci.yml")
        self.assertIn("push:", t)
        self.assertIn("pull_request:", t)
        self.assertIn("python3 -m unittest", t)
        self.assertNotIn("secrets.", t)


if __name__ == "__main__":
    unittest.main()

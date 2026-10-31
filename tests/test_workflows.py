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


class FailureAlertTest(unittest.TestCase):
    NAMES = ("snap-vn.yml", "snap-us.yml", "eod.yml")

    def step(self, text, title):
        i = text.index(f"- name: {title}")
        j = text.find("\n      - ", i + 1)
        return text[i:] if j < 0 else text[i:j]

    def test_every_scheduled_workflow_ends_with_a_telegram_alert_on_failure(self):
        for n in self.NAMES:
            t = read(n)
            step = self.step(t, "Alert on failure")
            self.assertIn("if: failure()", step, n)
            self.assertIn("TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}", step, n)
            self.assertIn("TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}", step, n)
            self.assertIn("python3 -m pipeline.alert", step, n)
            self.assertIn("github.run_id", step, n)
            self.assertIn("github.workflow", step, n)
            self.assertTrue(t.rstrip().endswith(step.rstrip()), f"{n}: the alert must be the last step")

    def test_telegram_secrets_are_only_given_to_the_alert_step(self):
        for n in self.NAMES:
            t = read(n)
            self.assertEqual(t.count("secrets.TELEGRAM_BOT_TOKEN"), 1, n)
            self.assertEqual(t.count("secrets.TELEGRAM_CHAT_ID"), 1, n)

    def test_secrets_live_on_steps_not_on_the_job(self):
        for n in self.NAMES:
            t = read(n)
            self.assertNotRegex(t, r"\n    env:\n", n)  # job-level env
            for s in ("SUPABASE_SECRET_KEY",):
                self.assertIn(f"        env:\n          SUPABASE_URL", t, n)
            self.assertNotIn("APCA_API_SECRET_KEY: ${{ secrets.APCA_API_SECRET_KEY }}\n    steps", t)

    def test_checkout_does_not_keep_credentials(self):
        for n in self.NAMES + ("ci.yml",):
            t = read(n)
            i = t.index("actions/checkout@")
            self.assertIn("persist-credentials: false", t[i:i + 300], n)

    def test_the_alert_step_does_not_echo_anything_secret(self):
        for n in self.NAMES:
            self.assertNotIn("echo", self.step(read(n), "Alert on failure"), n)


class EodJobTest(unittest.TestCase):
    def test_eod_cleans_up_then_checks_the_day_and_always_runs_the_check(self):
        t = read("eod.yml")
        self.assertIn("python3 -m pipeline.cleanup", t)
        i = t.index("python3 -m pipeline.eod")
        self.assertIn("if: always()", t[max(0, i - 400):i])
        self.assertIn("ALERT_DETAIL_FILE", t)

    def test_eod_runs_after_both_markets_have_finished(self):
        self.assertEqual(crons(read("eod.yml")), [("18:00".lstrip("0"), "Asia/Ho_Chi_Minh")])


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

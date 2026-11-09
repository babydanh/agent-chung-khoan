import re
import unittest
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"
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


class BulletinStepTest(unittest.TestCase):
    def test_each_snapshot_workflow_writes_its_bulletin_after_the_snapshot(self):
        for n, m in (("snap-vn.yml", "VN"), ("snap-us.yml", "US")):
            t = read(n)
            self.assertIn(f"python3 -m pipeline.bulletin --market {m}", t, n)
            self.assertLess(t.index(f"pipeline.run --market {m}"), t.index("pipeline.bulletin"), n)
            i = t.index("- name: Write bulletin")
            step = t[i:t.index("- name: Alert on failure")]
            self.assertIn("ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}", step, n)
            self.assertIn("SUPABASE_SECRET_KEY: ${{ secrets.SUPABASE_SECRET_KEY }}", step, n)

    def test_the_model_key_is_only_given_to_the_bulletin_step(self):
        for n in ("snap-vn.yml", "snap-us.yml"):
            self.assertEqual(read(n).count("secrets.ANTHROPIC_API_KEY"), 1, n)


class BotSwitchTest(unittest.TestCase):
    """The scheduled jobs only run once the owner sets the repository variable BOT_ENABLED to true, so a fresh
    checkout without secrets does not fail every half hour."""
    GUARD = "if: ${{ vars.BOT_ENABLED == 'true' }}"

    def jobs(self, text):
        i = text.index("\njobs:\n")
        return re.split(r"\n  (?=[a-z][\w-]*:\n)", text[i + len("\njobs:\n"):])

    def test_every_scheduled_job_is_behind_the_switch(self):
        for n in ("snap-vn.yml", "snap-us.yml", "eod.yml", "weekend.yml"):
            for job in self.jobs(read(n)):
                head = job.split("steps:")[0]
                self.assertIn(self.GUARD, head, f"{n}: {job.splitlines()[0]}")

    def test_the_switch_is_a_variable_not_a_secret(self):
        for n in ("snap-vn.yml", "snap-us.yml", "eod.yml"):
            self.assertNotIn("secrets.BOT_ENABLED", read(n), n)

    def test_tests_and_the_app_build_do_not_need_the_switch(self):
        for n in ("ci.yml", "app.yml"):
            self.assertNotIn("BOT_ENABLED", read(n), n)


class CliTokenTest(unittest.TestCase):
    """TC-BULLETIN-CLI-09/10: the subscription token reaches only the bulletin step, with a pinned CLI installed first."""

    def test_the_cli_token_is_only_given_to_the_bulletin_step(self):
        for n in ("snap-vn.yml", "snap-us.yml"):
            t = read(n)
            self.assertEqual(t.count("secrets.CLAUDE_CODE_OAUTH_TOKEN"), 1, n)
            i = t.index("- name: Write bulletin")
            self.assertIn("CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}",
                          t[i:t.index("- name: Alert on failure")], n)

    def test_a_pinned_cli_is_installed_before_the_bulletin_step(self):
        for n in ("snap-vn.yml", "snap-us.yml"):
            t = read(n)
            self.assertRegex(t, r"npm install -g @anthropic-ai/claude-code@\d+\.\d+\.\d+\n", n)  # no floating version
            self.assertLess(t.index("@anthropic-ai/claude-code@"), t.index("- name: Write bulletin"), n)


class AppBuiltInConnectionTest(unittest.TestCase):
    """TC-APP-PRELOAD: the APK is built with the URL and the public (anon) key inside (--dart-define) and opens without a
    login. No account, email or password is baked in (the repository and its artifacts are public)."""

    def step(self):
        t = read("app.yml")
        i = t.index("- name: \"Build APK")
        return t[i:t.index("- uses: actions/upload-artifact")]

    def test_the_apk_build_gets_the_url_and_public_key_defines(self):
        step = self.step()
        for d in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):
            self.assertIn(f"--dart-define={d}=", step, d)

    def test_the_public_key_secret_is_only_given_to_the_apk_build_step(self):
        self.assertEqual(read("app.yml").count("secrets.APP_SUPABASE_ANON_KEY"), 1)
        self.assertIn("secrets.APP_SUPABASE_ANON_KEY", self.step())

    def test_no_login_is_baked_into_the_apk(self):
        t = read("app.yml")
        for word in ("PASSWORD", "APP_LOGIN", "SUPABASE_EMAIL"):
            self.assertNotIn(word, t, word)


class WeekendWorkflowTest(unittest.TestCase):
    """TC-WEEKEND-09: the weekend bulletin runs on Saturday and Sunday only, written by code, with no model credentials."""

    def test_it_runs_only_on_saturday_and_sunday_in_vietnam_time(self):
        t = read("weekend.yml")
        found = re.findall(r'- cron: "(\d+) (\d+) \* \* (\d)"\s+timezone: "([^"]+)"', t)
        self.assertEqual(sorted((d, tz) for _, _, d, tz in found), [("0", "Asia/Ho_Chi_Minh"), ("6", "Asia/Ho_Chi_Minh")])
        self.assertEqual(len(re.findall(r"- cron:", t)), 2)

    def test_it_refreshes_the_last_close_after_the_bulletin(self):  # TC-REFRESH-05
        t = read("weekend.yml")
        self.assertIn("python3 -m pipeline.run --market VN --refresh-quotes", t)
        self.assertLess(t.index("pipeline.bulletin"), t.index("--refresh-quotes"))
        i = t.index("--refresh-quotes")
        step = t[t.rfind("- name:", 0, i):i]
        self.assertIn("SUPABASE_SECRET_KEY: ${{ secrets.SUPABASE_SECRET_KEY }}", step)
        self.assertNotIn("APCA", t, "the weekend refresh is VN only")

    def test_it_runs_the_vn_weekend_bulletin_and_needs_no_model_credentials(self):
        t = read("weekend.yml")
        self.assertIn("python3 -m pipeline.bulletin --market VN --weekend", t)
        for word in ("ANTHROPIC", "CLAUDE", "claude-code"):
            self.assertNotIn(word, t, word)


class FailureAlertTest(unittest.TestCase):
    NAMES = ("snap-vn.yml", "snap-us.yml", "eod.yml", "weekend.yml")

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

    def test_the_alert_step_also_reaches_the_app_for_the_right_market(self):  # TC-ALERT-APP-04
        for n, market in (("snap-vn.yml", "VN"), ("snap-us.yml", "US"), ("eod.yml", "VN"), ("weekend.yml", "VN")):
            step = self.step(read(n), "Alert on failure")
            self.assertIn("SUPABASE_URL: ${{ secrets.SUPABASE_URL }}", step, n)
            self.assertIn("SUPABASE_SECRET_KEY: ${{ secrets.SUPABASE_SECRET_KEY }}", step, n)
            self.assertIn(f"ALERT_MARKET: {market}", step, n)

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


class DailyWorkflowTest(unittest.TestCase):
    """TC-DAILY-15: daily candles for the app chart, after the last VN snapshot, behind the same switch and alert rules."""

    def test_it_runs_once_after_the_last_vn_snapshot_on_weekdays(self):
        t = read("daily.yml")
        self.assertEqual(crons(t), [("15:45", "Asia/Ho_Chi_Minh")])
        self.assertTrue(re.findall(r'- cron: "([^"]+)"', t)[0].endswith(" * * 1-5"))
        self.assertIn("workflow_dispatch:", t)

    def test_it_fetches_seven_sessions_by_default_and_the_dispatch_input_can_fill_history(self):
        t = read("daily.yml")
        self.assertIn("python3 -m pipeline.daily", t)
        self.assertIn("DAILY_DAYS: ${{ inputs.days || '7' }}", t)
        self.assertRegex(t, r'days:\n\s+description: .*\n\s+default: "90"')

    def test_it_follows_the_workflow_rules_of_the_other_jobs(self):
        t = read("daily.yml")
        self.assertIn(BotSwitchTest.GUARD, t.split("steps:")[0])
        self.assertRegex(t, r"permissions:\s+contents: read")
        self.assertIn("cancel-in-progress: false", t)
        self.assertIn("persist-credentials: false", t[t.index("actions/checkout@"):][:300])
        for u in re.findall(r"uses:\s*(\S+)", t):
            self.assertRegex(u, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$", u)
        self.assertNotRegex(t, r"\n    env:\n")
        self.assertEqual(t.count("secrets.TELEGRAM_BOT_TOKEN"), 1)
        i = t.index("- name: Alert on failure")
        self.assertIn("if: failure()", t[i:])
        self.assertIn("ALERT_MARKET: VN", t[i:])
        self.assertTrue(t.rstrip().endswith(t[i:].rstrip()), "the alert must be the last step")


class AllWorkflowsTest(unittest.TestCase):
    NAMES = ("snap-vn.yml", "snap-us.yml", "eod.yml", "weekend.yml", "ci.yml")

    def test_least_privilege_and_manual_trigger(self):
        for n in self.NAMES:
            t = read(n)
            self.assertRegex(t, r"permissions:\s+contents: read", n)
            self.assertNotRegex(t, r"contents: write|id-token|write-all", n)
        for n in self.NAMES[:4]:
            self.assertIn("workflow_dispatch:", read(n), n)

    def test_scheduled_workflows_do_not_overlap_themselves(self):
        for n in self.NAMES[:4]:
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
                         ("eod.yml", ["SUPABASE_URL", "SUPABASE_SECRET_KEY"]),
                         ("weekend.yml", ["SUPABASE_URL", "SUPABASE_SECRET_KEY"])):
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

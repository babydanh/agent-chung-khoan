"""Alert for a failed workflow run (python3 -m pipeline.alert). Secrets come from the environment only. The alert
goes to every channel that is configured: the app (a digest row, so it shows in the inbox and as a notification;
needs SUPABASE_URL and SUPABASE_SECRET_KEY) and Telegram (needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID).
With no channel at all the run fails loudly. The message carries the workflow name, the run URL and an optional
short detail file, never a secret."""
import logging
import os
import sys
from datetime import datetime, timezone

from pipeline import push
from pipeline.sources.http import SourceError, request_json
from pipeline.supa import from_env

log = logging.getLogger("pipeline.alert")
API = "https://api.telegram.org"
REQUIRED = ("WORKFLOW_NAME", "RUN_URL")
DETAIL_MAX = 800


def build_message(workflow, run_url, detail=""):
    text = f"{workflow} failed\n{run_url}"
    detail = (detail or "").strip()
    return text + ("\n" + detail[:DETAIL_MAX] if detail else "")


def build_digest_body(workflow, run_url, detail=""):
    """The app shows the first line, so it says what happened; the run URL and detail follow."""
    detail = (detail or "").strip()
    return f"Cảnh báo: {workflow} chạy lỗi.\n{run_url}" + ("\n" + detail[:DETAIL_MAX] if detail else "")


def send(token, chat_id, text, base=API, **http):
    resp = request_json(f"{base}/bot{token}/sendMessage",
                        {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}, **http)
    if not isinstance(resp, dict) or resp.get("ok") is not True:
        raise RuntimeError("Telegram did not accept the message")


def _read_detail(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(DETAIL_MAX * 2)
    except OSError:
        return ""


def _has(env, *names):
    return all((env.get(k) or "").strip() for k in names)


def _store_in_app(env, now, sleep):
    local = now.astimezone(push.VN)
    detail = _read_detail(env["ALERT_DETAIL_FILE"]) if env.get("ALERT_DETAIL_FILE") else ""
    db = from_env(env)
    db.sleep = sleep
    db.upsert("digests", [{"market": (env.get("ALERT_MARKET") or "VN").strip(), "digest_date": local.date().isoformat(),
                           "kind": f"alert-{local:%H%M}",
                           "body": build_digest_body(env["WORKFLOW_NAME"], env["RUN_URL"], detail)}],
              "market,digest_date,kind", merge=False)


def main(env, base=API, sleep=None, now=None):
    missing = [k for k in REQUIRED if not (env.get(k) or "").strip()]
    if missing:
        log.error("missing environment variable(s): %s", ", ".join(missing))
        return 2
    to_app, to_telegram = _has(env, "SUPABASE_URL", "SUPABASE_SECRET_KEY"), _has(env, "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    if not (to_app or to_telegram):
        log.error("no alert channel: set SUPABASE_URL and SUPABASE_SECRET_KEY, or TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        return 2
    now = now or datetime.now(timezone.utc)
    failed = False
    if to_app:
        try:
            _store_in_app(env, now, sleep)
        except (SourceError, RuntimeError) as e:
            log.error("alert not stored in the app: %s", str(e).replace(env["SUPABASE_SECRET_KEY"].strip(), "***"))
            failed = True
    if to_telegram:
        token = env["TELEGRAM_BOT_TOKEN"].strip()
        detail = _read_detail(env["ALERT_DETAIL_FILE"]) if env.get("ALERT_DETAIL_FILE") else ""
        try:
            send(token, env["TELEGRAM_CHAT_ID"].strip(), build_message(env["WORKFLOW_NAME"], env["RUN_URL"], detail),
                 base=base, sleep=sleep)
        except (SourceError, RuntimeError) as e:
            log.error("alert not sent: %s", str(e).replace(token, "***"))
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main(os.environ))

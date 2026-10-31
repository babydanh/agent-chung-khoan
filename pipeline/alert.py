"""Telegram alert for a failed workflow run (python3 -m pipeline.alert). Secrets come from the environment only;
a missing one fails loudly and nothing is sent. The message carries the workflow name, the run URL and an
optional short detail file, never a secret."""
import logging
import os
import sys

from pipeline.sources.http import SourceError, request_json

log = logging.getLogger("pipeline.alert")
API = "https://api.telegram.org"
REQUIRED = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "WORKFLOW_NAME", "RUN_URL")
DETAIL_MAX = 800


def build_message(workflow, run_url, detail=""):
    text = f"{workflow} failed\n{run_url}"
    detail = (detail or "").strip()
    return text + ("\n" + detail[:DETAIL_MAX] if detail else "")


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


def main(env, base=API, sleep=None):
    missing = [k for k in REQUIRED if not (env.get(k) or "").strip()]
    if missing:
        log.error("missing environment variable(s): %s", ", ".join(missing))
        return 2
    token = env["TELEGRAM_BOT_TOKEN"].strip()
    detail = _read_detail(env["ALERT_DETAIL_FILE"]) if env.get("ALERT_DETAIL_FILE") else ""
    text = build_message(env["WORKFLOW_NAME"], env["RUN_URL"], detail)
    try:
        send(token, env["TELEGRAM_CHAT_ID"].strip(), text, base=base, sleep=sleep)
    except (SourceError, RuntimeError) as e:
        log.error("alert not sent: %s", str(e).replace(token, "***"))
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main(os.environ))

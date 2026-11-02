"""Bulletin job: read the latest signals of a market, write the bulletin (agent + guard) to `digests`, store the
news it used in `news`, and record the push decision in the heartbeat. Nothing is sent from here (see pipeline.push).

Usage: python3 -m pipeline.bulletin --market VN|US
Secrets from the environment: SUPABASE_URL, SUPABASE_SECRET_KEY, ANTHROPIC_API_KEY (a missing model key makes the
run fail after storing the code-built fallback bulletin).
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline import agent, calendar, news, push
from pipeline.sources.http import SourceError, request_json
from pipeline.supa import from_env

log = logging.getLogger("pipeline.bulletin")
ROOT = Path(__file__).resolve().parent.parent
JOB = "bulletin"
MAX_SIGNAL_AGE = timedelta(hours=3)  # older signals belong to an earlier run, not to this bulletin


def _latest_items(db, market, now):
    last = db.select("signals", {"market": "eq." + market, "select": "asof", "order": "asof.desc", "limit": 1})
    if not last or now - datetime.fromisoformat(last[0]["asof"]) > MAX_SIGNAL_AGE:
        return []
    rows = db.select_all("signals", {"market": "eq." + market, "asof": "eq." + last[0]["asof"], "select": "symbol,level,items"},
                         order="symbol.asc")
    return [{"symbol": r["symbol"], "level": r["level"], "signals": r["items"]} for r in rows]


def _news(market, known, get_text, now):
    if market != "VN":  # the feeds are Vietnamese; US bulletins go out without headlines
        return []
    try:
        return news.fetch_all(news.FEEDS, known, get_text, now).items
    except news.NewsError as e:
        log.warning("no news for the bulletin: %s", e)
        return []


def main(argv, env, now=None, get_text=None, make=agent.make_bulletin, sleep=None):
    ap = argparse.ArgumentParser(prog="pipeline.bulletin")
    ap.add_argument("--market", required=True, choices=("VN", "US"))
    market = ap.parse_args(argv).market
    now = now or datetime.now(timezone.utc)
    try:
        db = from_env(env)
    except RuntimeError as e:
        log.error("%s", e)
        return 2
    db.sleep = sleep
    get_text = get_text or (lambda url: request_json(url, text=True, sleep=sleep))
    local = now.astimezone(push.VN)
    known = set(calendar.load(ROOT / "config" / "symbols.json")[market])

    try:
        items = _latest_items(db, market, now)
        headlines = _news(market, known, get_text, now)
        published = {n["id"]: n["published"] for n in headlines}  # the agent's news list does not carry the time
        bulletin = make(items, headlines, env.get("ANTHROPIC_API_KEY"), f"{local:%H:%M}")
        db.upsert("digests", [{"market": market, "digest_date": local.date().isoformat(), "kind": f"slot-{local:%H%M}",
                               "body": "\n".join(bulletin["paragraphs"])}],
                  "market,digest_date,kind", merge=False)  # a rerun keeps the first bulletin of the slot
        used = [{"market": market, "symbol": None, "title": n["title"], "url": n["link"], "source": n.get("source"),
                 "published_at": published.get(n["id"])} for n in bulletin["news"] if published.get(n["id"])]
        if used:
            db.upsert("news", used, "url", merge=False)
        detail = {**agent.heartbeat_detail(bulletin), "items": len(items), "push": push.build(market, now, now)}
        db.upsert("heartbeat", [{"market": market, "job": JOB, "last_seen": now.isoformat(), "detail": detail}], "market,job")
    except SourceError as e:
        log.error("bulletin not stored: %s", e)
        return 1
    log.info("bulletin source=%s items=%d push=%s", bulletin["source"], len(items), detail["push"]["status"])
    return agent.exit_code(bulletin)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main(sys.argv[1:], os.environ))

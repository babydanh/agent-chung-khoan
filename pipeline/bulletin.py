"""Bulletin job: read the latest signals of a market, write the bulletin (agent + guard) to `digests`, store the
news it used in `news`, and record the push decision in the heartbeat. Nothing is sent from here (see pipeline.push).

Usage: python3 -m pipeline.bulletin --market VN|US [--weekend]
Secrets from the environment: SUPABASE_URL, SUPABASE_SECRET_KEY, ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN (the
API key wins; with neither, the run fails after storing the code-built fallback bulletin).
--weekend (VN only): the Saturday/Sunday bulletin of pipeline.weekend, built by code; it needs no model credentials.
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline import agent, calendar, news, news_notes, push, weekend
from pipeline.sources.http import SourceError, request_json
from pipeline.supa import from_env

log = logging.getLogger("pipeline.bulletin")
ROOT = Path(__file__).resolve().parent.parent
JOB = "bulletin"
MAX_SIGNAL_AGE = timedelta(hours=3)  # older signals belong to an earlier run, not to this bulletin
NOTES_SEEN_AGE = timedelta(days=4)  # a headline noted within this window is not sent to the model again (feeds keep 3 days)
WEEKEND_SIGNAL_AGE = timedelta(days=5)  # the weekend bulletin reports the last session, however long ago it closed


QUIET_START, QUIET_END = 1, 5  # Vietnam hours: no model bulletin from 01:00 up to 05:00, nor on Saturday and Sunday


def model_quiet(local):
    """True in the hours the bot does not ask the model (saves tokens). Only the model step is skipped: the snapshot job
    has already run, so prices, signals and the end-of-day check are whole."""
    return local.weekday() >= 5 or QUIET_START <= local.hour < QUIET_END


def _latest_items(db, market, now, max_age=MAX_SIGNAL_AGE):
    last = db.select("signals", {"market": "eq." + market, "select": "asof", "order": "asof.desc", "limit": 1})
    if not last or now - datetime.fromisoformat(last[0]["asof"]) > max_age:
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


def _notes(db, market, headlines, env, now, annotate):
    """Model notes on the headlines that have none yet; returns how many were stored. Optional: whatever goes wrong
    here is logged and the bulletin goes on."""
    if not headlines:
        return 0
    try:
        since = (now - NOTES_SEEN_AGE).isoformat()
        seen = {r["url"] for r in db.select_all("news_notes", {"market": "eq." + market, "select": "url", "created_at": "gte." + since},
                                                order="url.asc")}
        rows = annotate(headlines, seen, env.get("ANTHROPIC_API_KEY"), env.get("CLAUDE_CODE_OAUTH_TOKEN"))
        if rows:
            db.upsert("news_notes", [{**r, "market": market} for r in rows], "url", merge=False)  # first note of a headline stays
        return len(rows)
    except Exception:  # noqa: BLE001 - notes are an extra; they must never turn the bulletin job red
        log.exception("headline notes not stored")
        return 0


def _weekend(db, market, now, local, known, get_text):
    """One digest per day, kind 'weekend', built by code from the last session's signals and the latest headlines."""
    paragraphs = weekend.build(_latest_items(db, market, now, WEEKEND_SIGNAL_AGE), _news(market, known, get_text, now))
    db.upsert("digests", [{"market": market, "digest_date": local.date().isoformat(), "kind": "weekend",
                           "body": "\n".join(paragraphs)}], "market,digest_date,kind", merge=False)
    log.info("weekend bulletin stored, %d lines", len(paragraphs))


def main(argv, env, now=None, get_text=None, make=agent.make_bulletin, annotate=news_notes.annotate, sleep=None):
    ap = argparse.ArgumentParser(prog="pipeline.bulletin")
    ap.add_argument("--market", required=True, choices=("VN", "US"))
    ap.add_argument("--weekend", action="store_true")
    args = ap.parse_args(argv)
    market = args.market
    now = now or datetime.now(timezone.utc)
    if args.weekend and market != "VN":  # the feeds are Vietnamese: a US weekend bulletin would have nothing to say
        log.info("no weekend bulletin for %s", market)
        return 0
    if not args.weekend and model_quiet(now.astimezone(push.VN)):  # the weekend bulletin is built by code: no model, no cost
        log.info("quiet hours (01:00-05:00 or Saturday/Sunday, Vietnam time): no bulletin this run")
        return 0
    try:
        db = from_env(env)
    except RuntimeError as e:
        log.error("%s", e)
        return 2
    db.sleep = sleep
    get_text = get_text or (lambda url: request_json(url, text=True, sleep=sleep))
    local = now.astimezone(push.VN)
    known = set(calendar.load(ROOT / "config" / "symbols.json")[market])

    if args.weekend:
        try:
            _weekend(db, market, now, local, known, get_text)
        except SourceError as e:
            log.error("weekend bulletin not stored: %s", e)
            return 1
        return 0
    try:
        items = _latest_items(db, market, now)
        headlines = _news(market, known, get_text, now)
        published = {n["id"]: n["published"] for n in headlines}  # the agent's news list does not carry the time
        named = {n["id"]: (n.get("symbols") or [None])[0] for n in headlines}  # nor the ticker it names
        bulletin = make(items, headlines, env.get("ANTHROPIC_API_KEY"), f"{local:%H:%M}",
                        cli_token=env.get("CLAUDE_CODE_OAUTH_TOKEN"))
        db.upsert("digests", [{"market": market, "digest_date": local.date().isoformat(), "kind": f"slot-{local:%H%M}",
                               "body": "\n".join(bulletin["paragraphs"])}],
                  "market,digest_date,kind", merge=False)  # a rerun keeps the first bulletin of the slot
        used = [{"market": market, "symbol": named.get(n["id"]), "title": n["title"], "url": n["link"], "source": n.get("source"),
                 "published_at": published.get(n["id"])} for n in bulletin["news"] if published.get(n["id"])]
        if used:
            db.upsert("news", used, "url", merge=False)
        noted = _notes(db, market, headlines, env, now, annotate)
        detail = {**agent.heartbeat_detail(bulletin), "items": len(items), "notes": noted, "push": push.build(market, now, now)}
        db.upsert("heartbeat", [{"market": market, "job": JOB, "last_seen": now.isoformat(), "detail": detail}], "market,job")
    except SourceError as e:
        log.error("bulletin not stored: %s", e)
        return 1
    log.info("bulletin source=%s items=%d push=%s", bulletin["source"], len(items), detail["push"]["status"])
    return agent.exit_code(bulletin)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main(sys.argv[1:], os.environ))

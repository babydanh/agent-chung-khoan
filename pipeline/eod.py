"""End-of-day check (python3 -m pipeline.eod): did every scheduled snapshot of the last finished trading day
happen, and is the heartbeat as new as the last scheduled run? Catches runs that never started (cancelled queue
entries, a workflow GitHub switched off) which no failure() step can see."""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from pipeline import calendar
from pipeline.run import ROOT, expected_runs
from pipeline.supa import from_env

log = logging.getLogger("pipeline.eod")
MARKETS = ("VN", "US")
LOOKBACK_DAYS = 10  # long enough to cross a Tet holiday
SETTLE = timedelta(minutes=30)  # a day counts as finished this long after its last scheduled run


def check_market(db, market, now, cal):
    """(problems, summary) for the most recent finished trading day of a market."""
    local = now.astimezone(calendar.TZ[market])
    for back in range(LOOKBACK_DAYS):
        day = local.date() - timedelta(days=back)
        runs = expected_runs(market, day, cal)
        if not runs or runs[-1][0] + SETTLE > now:
            continue
        slots = [slot for _, slot in runs]
        have = {datetime.fromisoformat(r["slot_start"]).astimezone(timezone.utc) for r in db.select_all(
            "snapshot_meta", {"select": "slot_start", "market": "eq." + market, "slot_start": "gte." + slots[0].isoformat()},
            order="market.asc,slot_start.asc")}
        missing = [s for s in slots if s not in have]
        problems = []
        tz = calendar.TZ[market]
        if missing:
            times = ", ".join(s.astimezone(tz).strftime("%H:%M") for s in missing)
            problems.append(f"{market} {day}: {len(missing)} slot(s) missing ({times})")
        beat = db.select("heartbeat", {"select": "last_seen", "market": "eq." + market, "job": "eq.snapshot"})
        if not beat:
            problems.append(f"{market}: no heartbeat row at all")
        elif datetime.fromisoformat(beat[0]["last_seen"]) < runs[-1][0]:
            problems.append(f"{market}: heartbeat last seen {beat[0]['last_seen']}, "
                            f"older than the last scheduled run of {day}")
        return problems, f"{market} {day}: {len(slots) - len(missing)}/{len(slots)} slots"
    return [], f"{market}: no finished trading day in the last {LOOKBACK_DAYS} days"


def main(env, now=None, cal=None):
    try:
        db = from_env(env)
    except RuntimeError as e:
        log.error("%s", e)
        return 2
    now = now or datetime.now(timezone.utc)
    cal = cal or calendar.load(ROOT / "config" / "calendar.json")
    all_problems = []
    for market in MARKETS:
        problems, summary = check_market(db, market, now, cal)
        log.info("%s", summary)
        for p in problems:
            log.warning("%s", p)
        all_problems += problems
    if all_problems:
        path = env.get("ALERT_DETAIL_FILE")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(all_problems))
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main(os.environ))

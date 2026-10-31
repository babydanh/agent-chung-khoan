"""Retention: keep 40 sessions of bars_30m and 30 days of signals; report database size."""
import logging
import sys
from datetime import datetime, timedelta, timezone

from pipeline.sources.http import SourceError
from pipeline.supa import from_env

log = logging.getLogger("pipeline.cleanup")
KEEP_SESSIONS = 40
SIGNAL_DAYS = 30
DB_LIMIT_MB = 400


def bars_cutoff(bar_starts, keep=KEEP_SESSIONS):
    """Start (UTC midnight) of the oldest session to keep; None when there are not more than `keep` sessions."""
    dates = sorted({datetime.fromisoformat(s).astimezone(timezone.utc).date() for s in bar_starts}, reverse=True)
    if len(dates) <= keep:
        return None
    d = dates[keep - 1]
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def signals_cutoff(now, days=SIGNAL_DAYS):
    return now - timedelta(days=days)


def db_report(db_mb, limit=DB_LIMIT_MB):
    """(log level, message); an unknown size is a warning so a broken probe does not go unnoticed."""
    if db_mb is None:
        return "warning", "db_mb=unknown"
    if db_mb > limit:
        return "warning", f"db_mb={db_mb} is over {limit} MB"
    return "info", f"db_mb={db_mb}"


def run(db, now):
    starts = [r["bar_start"] for r in db.select_all("bars_30m", {"select": "bar_start"}, order="market.asc,symbol.asc,bar_start.asc")]
    cut = bars_cutoff(starts)
    if cut:
        db.delete("bars_30m", {"bar_start": "lt." + cut.isoformat()})
        log.info("bars_30m: deleted before %s", cut.isoformat())
    db.delete("signals", {"asof": "lt." + signals_cutoff(now).isoformat()})
    try:
        size = db.rpc("db_size_mb")
    except SourceError as e:
        log.warning("db_size_mb unavailable (%s)", e)
        size = None
    level, msg = db_report(size)
    getattr(log, level)(msg)
    return 1 if level == "warning" else 0  # an unknown or oversized database must fail the job, not just log


def main(env, now=None):
    try:
        db = from_env(env)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return run(db, now or datetime.now(timezone.utc))


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main(os.environ))

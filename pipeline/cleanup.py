"""Retention: call the SQL function cleanup_old_data (single source of truth for every cutoff, see docs/schema.md); report database size."""
import logging
import sys
from datetime import datetime, timezone

from pipeline.sources.http import SourceError
from pipeline.supa import from_env

log = logging.getLogger("pipeline.cleanup")
DB_LIMIT_MB = 400


def db_report(db_mb, limit=DB_LIMIT_MB):
    """(log level, message); an unknown size is a warning so a broken probe does not go unnoticed."""
    if db_mb is None:
        return "warning", "db_mb=unknown"
    if db_mb > limit:
        return "warning", f"db_mb={db_mb} is over {limit} MB"
    return "info", f"db_mb={db_mb}"


def run(db, now):
    failed = False
    try:
        deleted = db.rpc("cleanup_old_data")
        log.info("cleanup_old_data deleted %s", ", ".join(f"{k}={v}" for k, v in sorted((deleted or {}).items())))
    except SourceError as e:
        log.error("cleanup_old_data failed (%s)", e)
        failed = True
    try:
        size = db.rpc("db_size_mb")
    except SourceError as e:
        log.warning("db_size_mb unavailable (%s)", e)
        size = None
    level, msg = db_report(size)
    getattr(log, level)(msg)
    return 1 if failed or level == "warning" else 0  # a failed purge or an unknown/oversized database must fail the job


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

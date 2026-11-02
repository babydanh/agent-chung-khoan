"""Run-window gate: should a snapshot run now? Holidays come from config/calendar.json."""
import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = {"VN": ZoneInfo("Asia/Ho_Chi_Minh"), "US": ZoneInfo("America/New_York")}
# Run windows, not exchange hours: they include the last run after the close.
# The ends leave room for late cron starts; double runs are stopped by snapshot_meta, not by this gate.
VN_WINDOWS = ((time(9, 0), time(12, 15)), (time(13, 0), time(15, 40)))
US_FIRST_RUN = time(10, 0)
US_CLOSE, US_EARLY_CLOSE = time(16, 0), time(13, 0)
US_LAST_RUN_AFTER_CLOSE = timedelta(minutes=80)  # the feed is 15 minutes late, plus cron delay


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def is_run_window(market, now, cal):
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if market not in TZ:
        raise ValueError(f"unknown market {market}")
    local = now.astimezone(TZ[market])
    day = local.date().isoformat()
    if local.weekday() >= 5 or day in cal[market]["holidays"]:
        return False
    if market == "VN":
        return any(start <= local.time() <= end for start, end in VN_WINDOWS)
    close = US_EARLY_CLOSE if day in cal["US"]["early_close"] else US_CLOSE
    last = (datetime.combine(local.date(), close) + US_LAST_RUN_AFTER_CLOSE).time()
    return US_FIRST_RUN <= local.time() <= last

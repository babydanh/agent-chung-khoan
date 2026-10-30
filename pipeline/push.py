"""Push notification content and timing. Logic only: nothing is sent from here."""
from datetime import datetime
from zoneinfo import ZoneInfo

from pipeline.banned import find_banned

VN = ZoneInfo("Asia/Ho_Chi_Minh")
QUIET_START, QUIET_END = 22, 7  # US bulletins are held back from 22:00 to 07:00 Vietnam time
TITLE = "Agent Chứng Khoán"


def _local(dt):
    if dt.tzinfo is None:
        raise ValueError("datetimes must be timezone-aware")
    return dt.astimezone(VN)


def build(market, bulletin_time, now):
    """{"title", "body"} for a new bulletin, or None when it must not be pushed right now."""
    if market not in ("VN", "US"):
        raise ValueError(f"unknown market {market}")
    shown, current = _local(bulletin_time), _local(now)
    if market == "US" and (current.hour >= QUIET_START or current.hour < QUIET_END):
        return None
    note = {"title": TITLE, "body": f"Bản tin {shown:%H:%M} đã có"}
    if find_banned(note["title"] + " " + note["body"]):
        raise ValueError("notification text failed the banned-wording scan")
    return note

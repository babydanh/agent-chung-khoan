"""Push notification content and timing. Logic only: nothing is sent from here."""
from datetime import datetime, timedelta
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
    """Notification for a new bulletin.

    {"status": "send", ...} now, or {"status": "defer", ..., "send_at": ISO time} when a US bulletin lands in the
    quiet hours: it is held until 07:00 Vietnam time, never dropped. The text is the same either way.
    """
    if market not in ("VN", "US"):
        raise ValueError(f"unknown market {market}")
    shown, current = _local(bulletin_time), _local(now)
    note = {"title": TITLE, "body": f"Bản tin {shown:%H:%M} đã có"}
    if find_banned(note["title"] + " " + note["body"]):
        raise ValueError("notification text failed the banned-wording scan")
    if market == "US" and (current.hour >= QUIET_START or current.hour < QUIET_END):
        send_at = current.replace(hour=QUIET_END, minute=0, second=0, microsecond=0)
        if current.hour >= QUIET_START:
            send_at += timedelta(days=1)
        return {"status": "defer", "send_at": send_at.isoformat(), **note}
    return {"status": "send", **note}

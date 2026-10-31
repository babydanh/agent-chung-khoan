"""Large-money and price-move signals S1-S5 for one symbol and one window. Thresholds come from config/thresholds.json."""
from datetime import time
from statistics import median

# Trading sessions in local exchange time, used to count trading minutes (breaks excluded).
VN_SESSIONS = ((time(9, 0), time(11, 30)), (time(13, 0), time(14, 45)))
US_SESSIONS = ((time(9, 30), time(16, 0)),)
US_EARLY_SESSIONS = ((time(9, 30), time(13, 0)),)


def _minute(t):
    return t.hour * 60 + t.minute


def trading_minutes(start, end, sessions):
    """Minutes of [start, end] (datetime.time, same day) that fall inside the sessions."""
    a, b = _minute(start), _minute(end)
    return sum(max(0, min(b, _minute(e)) - max(a, _minute(s))) for s, e in sessions)


def robust_z(value, history):
    """Median/MAD z-score; None when the history has no spread."""
    med = median(history)
    mad = median(abs(x - med) for x in history)
    if mad == 0:
        return None
    return 0.6745 * (value - med) / mad


def evaluate(d, history, th, atr=None, market=None, minutes=None, history_minutes=None):
    """history = window volumes of the same slot on past days. Level is capped at 1 while the baseline is short.

    Optional inputs keep the old call shape working:
    - minutes / history_minutes: trading minutes of this window and of each past window; S1 then compares
      volume per trading minute instead of raw window volume.
    - atr: latest ATR14; enables S4 (d["px_move"], th["s4_k"]) and, for market "US", S5
      (d["open"], d["prev_close"], th["s5_k"]).
    """
    if minutes is not None:
        if history_minutes is None:
            raise ValueError("minutes needs history_minutes")
        if len(history_minutes) != len(history):
            raise ValueError("history_minutes must match history")
    value, base = d["vol"], history
    if minutes is not None:
        # a window without trading minutes cannot form a rate: it is left out of the baseline
        value = d["vol"] / minutes if minutes > 0 else None
        base = [v / m for v, m in zip(history, history_minutes) if m > 0]
    learning = len(base) < th["min_days"]  # count the baseline actually used, not the raw history
    big = d["vol"] >= th["min_vol"]
    signals = []
    if big and not learning:
        z = robust_z(value, base) if value is not None and base else None  # empty baseline (min_days <= 0): no score
        if z is not None and z >= th["s1_z"]:
            signals.append({"id": "S1", "dir": None})
    if big and abs(d["fnet"]) >= th["s2_share"] * d["vol"]:
        signals.append({"id": "S2", "dir": "buy" if d["fnet"] > 0 else "sell"})
    if d["pt_val"] >= th["s3_value"]:
        signals.append({"id": "S3", "dir": None})
    k4 = th.get("s4_k")
    if big and atr and k4 is not None and "px_move" in d and abs(d["px_move"]) >= k4 * atr:
        signals.append({"id": "S4", "dir": "up" if d["px_move"] > 0 else "down"})
    k5 = th.get("s5_k")
    if market == "US" and atr and k5 is not None and "open" in d and "prev_close" in d:
        gap = d["open"] - d["prev_close"]
        if abs(gap) >= k5 * atr:
            signals.append({"id": "S5", "dir": "up" if gap > 0 else "down"})
    level = min(len(signals), 1 if learning else 3)
    return {"signals": signals, "level": level, "learning": learning}

"""Large-money signals S1-S3 for one symbol and one window. Thresholds come from config/thresholds.json."""
from statistics import median


def robust_z(value, history):
    """Median/MAD z-score; None when the history has no spread."""
    med = median(history)
    mad = median(abs(x - med) for x in history)
    if mad == 0:
        return None
    return 0.6745 * (value - med) / mad


def evaluate(d, history, th):
    """history = window volumes of the same slot on past days. Level is capped at 1 while the baseline is short."""
    learning = len(history) < th["min_days"]
    big = d["vol"] >= th["min_vol"]
    signals = []
    if big and not learning:
        z = robust_z(d["vol"], history)
        if z is not None and z >= th["s1_z"]:
            signals.append({"id": "S1", "dir": None})
    if big and abs(d["fnet"]) >= th["s2_share"] * d["vol"]:
        signals.append({"id": "S2", "dir": "buy" if d["fnet"] > 0 else "sell"})
    if d["pt_val"] >= th["s3_value"]:
        signals.append({"id": "S3", "dir": None})
    level = min(len(signals), 1 if learning else 3)
    return {"signals": signals, "level": level, "learning": learning}

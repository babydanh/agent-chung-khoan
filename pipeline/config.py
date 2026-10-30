"""Per-market thresholds from config/thresholds.json."""
import json

REQUIRED = ("min_days", "s1_z", "min_vol", "s2_share", "s3_value")


def load(path, market):
    """Return the thresholds of one market plus the file version; fail loudly on missing keys."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "version" not in data:
        raise ValueError(f"{path}: missing 'version'")
    th = data.get(market)
    if th is None:
        raise ValueError(f"{path}: no thresholds for market {market}")
    missing = [k for k in REQUIRED if k not in th]
    if missing:
        raise ValueError(f"{path}: market {market} is missing {', '.join(missing)}")
    return {**th, "version": data["version"]}

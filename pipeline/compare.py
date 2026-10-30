"""Window numbers between two snapshots of the price board (cumulative-in-day fields)."""

CUMULATIVE = ("TT", "TV", "FB", "FS", "PTQ", "PTV")


def delta(prev, curr):
    """Return the numbers of the window between two rows, or None if a cumulative field went down."""
    d = {f: curr[f] - prev[f] for f in CUMULATIVE}
    if any(v < 0 for v in d.values()):
        return None  # new session or corrected data: the two rows are not comparable
    return {"vol": d["TT"], "val": d["TV"], "fnet": d["FB"] - d["FS"], "pt_val": d["PTV"]}


def delta_all(prev_rows, curr_rows):
    """Deltas for every symbol that has live data (a TT field) in both snapshots."""
    out = {}
    for sym, curr in curr_rows.items():
        prev = prev_rows.get(sym)
        if prev is None or "TT" not in prev or "TT" not in curr:
            continue
        d = delta(prev, curr)
        if d is not None:
            out[sym] = d
    return out

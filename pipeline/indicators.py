"""Price indicators: classic pivot levels, ATR (Wilder) and Bollinger bands. Pure functions, no I/O."""
from statistics import fmean, pstdev


def pivot(high, low, close):
    """Classic floor-trader pivot levels from the previous session's high, low and close."""
    if high < low:
        raise ValueError("high is below low")
    p = (high + low + close) / 3
    rng = high - low
    return {"P": p, "R1": 2 * p - low, "S1": 2 * p - high, "R2": p + rng, "S2": p - rng}


def true_ranges(highs, lows, closes):
    """True range per bar; the first bar has no previous close, so it is just high - low."""
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows and closes must have the same length")
    out = []
    for i, (h, l) in enumerate(zip(highs, lows)):
        if i == 0:
            out.append(h - l)
        else:
            pc = closes[i - 1]
            out.append(max(h - l, abs(h - pc), abs(l - pc)))
    return out


def atr(highs, lows, closes, n=14):
    """Latest ATR with Wilder smoothing (seed = mean of the first n true ranges); None if fewer than n bars."""
    tr = true_ranges(highs, lows, closes)
    if len(tr) < n:
        return None
    value = fmean(tr[:n])
    for x in tr[n:]:
        value = (value * (n - 1) + x) / n
    return value


def bollinger(closes, n=20, k=2):
    """Bands over the last n closes (population standard deviation); None if fewer than n closes."""
    if len(closes) < n:
        return None
    window = closes[-n:]
    mid = fmean(window)
    width = k * pstdev(window)
    return {"lower": mid - width, "mid": mid, "upper": mid + width}

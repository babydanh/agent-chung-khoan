"""Price zones worth watching: places where several levels (pivot, Bollinger) sit close together.

Output is descriptive only. Every number comes from code; the text never says what to do.
"""

_PIVOT_NAMES = {"P": "Pivot P", "R1": "Pivot R1", "R2": "Pivot R2", "S1": "Pivot S1", "S2": "Pivot S2"}
_BOLL_NAMES = {"lower": "Bollinger dải dưới", "mid": "Bollinger đường giữa", "upper": "Bollinger dải trên"}
_WHERE = {"inside": "chứa giá hiện tại", "above": "nằm trên giá hiện tại", "below": "nằm dưới giá hiện tại"}


def _levels(pivot_levels, bands):
    out = []
    for key, name in _PIVOT_NAMES.items():
        if pivot_levels and key in pivot_levels:
            out.append((pivot_levels[key], name))
    for key, name in _BOLL_NAMES.items():
        if bands and key in bands:
            out.append((bands[key], name))
    return sorted(out)


def find_zones(price, pivot_levels, bands, atr, tol_k=0.5):
    """Group levels at most tol_k * ATR apart; keep groups of 2+ sources, nearest to price first.

    Returns [] when ATR is unknown: without it there is no scale for "close together".
    """
    if not atr:
        return []
    tol = tol_k * atr
    groups = []
    for value, name in _levels(pivot_levels, bands):
        if groups and value - groups[-1][-1][0] <= tol:
            groups[-1].append((value, name))
        else:
            groups.append([(value, name)])
    zones = []
    for g in groups:
        if len(g) < 2:
            continue
        low, high = g[0][0], g[-1][0]
        if low <= price <= high:
            position, distance = "inside", 0.0
        elif price < low:
            position, distance = "above", low - price
        else:
            position, distance = "below", price - high
        zones.append({"low": low, "high": high, "sources": sorted(n for _, n in g),
                      "position": position, "distance": distance})
    return sorted(zones, key=lambda z: z["distance"])


def describe(zone):
    """One neutral Vietnamese sentence for a zone."""
    low, high = zone["low"], zone["high"]
    span = f"{low:,.2f}" if low == high else f"{low:,.2f} - {high:,.2f}"
    return (f"Vùng giá đáng chú ý {span}: {len(zone['sources'])} mốc nằm gần nhau "
            f"({', '.join(zone['sources'])}); vùng {_WHERE[zone['position']]}.")

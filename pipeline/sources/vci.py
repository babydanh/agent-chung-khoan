"""VCI (Vietcap) price board, fallback VN source. Rows are nested; flatten them to the KBS shape.

Only the three top-level keys (bidAsk, listingInfo, matchPrice) were confirmed by the probe run; the inner
names below follow Vietcap's public board and must be re-checked against a live response.
"""
from pipeline.sources.http import request_json

URL = "https://trading.vietcap.com.vn/api/price/symbols/getList"
HEADERS = {"Origin": "https://trading.vietcap.com.vn", "Referer": "https://trading.vietcap.com.vn/"}


def fetch(symbols, url=URL, **http):
    out = {}
    for item in request_json(url, {"symbols": list(symbols)}, headers=HEADERS, **http):
        info, mp = item.get("listingInfo") or {}, item.get("matchPrice") or {}
        if "accumulatedVolume" not in mp or not info.get("symbol"):
            continue
        sym = info["symbol"]
        out[sym] = {"SB": sym, "EX": info.get("board"), "CP": mp.get("matchPrice", 0),
                    "RE": info.get("refPrice", 0), "CL": info.get("ceiling", 0), "FL": info.get("floor", 0),
                    "TT": mp["accumulatedVolume"], "TV": mp.get("accumulatedValue", 0),
                    "FB": mp.get("foreignBuyVolume", 0), "FS": mp.get("foreignSellVolume", 0),
                    "FR": mp.get("currentRoom", 0),
                    "PTQ": 0, "PTV": 0}  # negotiated deals are not in this feed (unconfirmed)
    return out

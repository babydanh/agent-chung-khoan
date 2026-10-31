"""Alpaca market-data snapshots (US). Keys are passed in by the caller, never read here."""
import urllib.parse

from pipeline.sources.http import SourceError, request_json

URL = "https://data.alpaca.markets/v2/stocks/snapshots"


def fetch(symbols, key_id, secret, feed="iex", url=URL, **http):
    """Map snapshots to the board shape. The free IEX feed counts IEX volume only, not the whole tape."""
    if not key_id or not secret:
        raise SourceError("Alpaca credentials are missing")
    q = urllib.parse.urlencode({"symbols": ",".join(symbols), "feed": feed})
    data = request_json(f"{url}?{q}", headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret}, **http)
    if not isinstance(data, dict):
        raise SourceError(f"Alpaca answered with {type(data).__name__}, not an object")
    out = {}
    for sym, snap in data.items():
        if not isinstance(snap, dict):
            continue
        bar = snap.get("dailyBar")
        if not bar:
            continue
        vol = bar.get("v", 0)
        out[sym] = {"SB": sym, "EX": "US", "CP": (snap.get("latestTrade") or {}).get("p", bar.get("c", 0)),
                    "RE": (snap.get("prevDailyBar") or {}).get("c", 0), "OP": bar.get("o", 0),
                    "TT": vol, "TV": vol * bar.get("vw", 0), "FB": 0, "FS": 0, "FR": 0, "PTQ": 0, "PTV": 0,
                    "SRC": "Alpaca", "PT": True}  # no negotiated deals in the US: a true zero
    if not out:
        raise SourceError("Alpaca returned no symbols with a daily bar")
    return out

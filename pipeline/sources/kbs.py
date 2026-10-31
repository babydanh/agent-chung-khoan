"""KBS price board (primary VN source). One POST per chunk of symbols; rows without TT are not live."""
from pipeline.sources.http import SourceError, request_json

URL = "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stock/iss"
CHUNK = 1500
NUMERIC = ("CP", "RE", "CL", "FL", "TT", "TV", "FB", "FS", "FR", "PTQ", "PTV")


def fetch(symbols, url=URL, **http):
    out = {}
    for i in range(0, len(symbols), CHUNK):
        rows = request_json(url, {"code": ",".join(symbols[i:i + CHUNK])}, **http)
        if not isinstance(rows, list):
            raise SourceError(f"KBS answered with {type(rows).__name__}, not a list")
        for r in rows:
            if not isinstance(r, dict) or "TT" not in r or "SB" not in r:
                continue
            out[r["SB"]] = {"SB": r["SB"], "EX": r.get("EX"), "SRC": "KBS", "PT": True,
                            **{k: r.get(k, 0) for k in NUMERIC}}
    if not out:
        raise SourceError("KBS returned no live rows")
    return out

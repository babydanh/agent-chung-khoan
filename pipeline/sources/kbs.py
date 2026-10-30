"""KBS price board (primary VN source). One POST per chunk of symbols; rows without TT are not live."""
from pipeline.sources.http import request_json

URL = "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stock/iss"
CHUNK = 1500
NUMERIC = ("CP", "RE", "CL", "FL", "TT", "TV", "FB", "FS", "FR", "PTQ", "PTV")


def fetch(symbols, url=URL, **http):
    out = {}
    for i in range(0, len(symbols), CHUNK):
        rows = request_json(url, {"code": ",".join(symbols[i:i + CHUNK])}, **http)
        for r in rows:
            if "TT" not in r:
                continue
            out[r["SB"]] = {"SB": r["SB"], "EX": r.get("EX"), **{k: r.get(k, 0) for k in NUMERIC}}
    return out

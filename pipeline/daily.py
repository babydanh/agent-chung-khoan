"""Daily candles (python3 -m pipeline.daily): fill bars_1d for the app's price chart.

VCI (one symbol per request, it answers an empty list for several) first, KBS data_day as the fallback. Rows are
upserted by (market, symbol, trade_date), so a rerun only refreshes days that were still open. DAILY_DAYS is how many
sessions to fetch (default 7, one first run with 90 fills the history)."""
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from pipeline.sources.http import SourceError, request_json
from pipeline.supa import from_env

log = logging.getLogger("pipeline.daily")
VCI_URL = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
VCI_HEADERS = {"Origin": "https://trading.vietcap.com.vn", "Referer": "https://trading.vietcap.com.vn/"}
KBS_URL = "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stocks"
VN = timezone(timedelta(hours=7))  # no daylight saving, so no tz database needed
DEFAULT_DAYS, MAX_DAYS = 7, 400
WORKERS = 6
MAX_FAILED = 0.10  # share of symbols that may fail before the job is red


def _row(symbol, date, o, h, l, c, v, val):
    return {"market": "VN", "symbol": symbol, "trade_date": date, "open": o, "high": h, "low": l, "close": c,
            "vol": None if v is None else int(v), "val": None if val is None else int(round(val))}


def parse_vci(item):
    """Parallel arrays o/h/l/c/v/t (t = epoch seconds) to rows, oldest first; days without a close are skipped.
    accumulatedValue is in millions of VND."""
    keys = ("o", "h", "l", "c", "v", "t", "accumulatedValue")
    cols = [item.get(k) or [] for k in keys]
    if not item.get("symbol") or len({len(c) for c in cols}) != 1:
        return []
    rows = []
    for o, h, l, c, v, t, av in zip(*cols):
        if c is None or t is None:
            continue
        date = datetime.fromtimestamp(int(t), VN).date().isoformat()
        rows.append(_row(item["symbol"], date, o, h, l, c, v, None if av is None else av * 1_000_000))
    return sorted(rows, key=lambda r: r["trade_date"])


def parse_kbs(data):
    """KBS data_day (newest first, value in VND) to the same rows, oldest first."""
    rows = [_row(data["symbol"], d["t"][:10], d.get("o"), d.get("h"), d.get("l"), d["c"], d.get("v"), d.get("va"))
            for d in (data or {}).get("data_day") or [] if d.get("c") is not None and d.get("t")]
    return sorted(rows, key=lambda r: r["trade_date"])


def _from_vci(symbol, days, now, url, **http):
    body = {"timeFrame": "ONE_DAY", "symbols": [symbol], "countBack": days, "to": int(now.timestamp())}
    data = request_json(url, body, headers=VCI_HEADERS, **http)
    return parse_vci(data[0]) if isinstance(data, list) and data and isinstance(data[0], dict) else []


def _from_kbs(symbol, days, now, url, **http):
    start = (now - timedelta(days=days * 2 + 10)).astimezone(VN).strftime("%d-%m-%Y")
    end = now.astimezone(VN).strftime("%d-%m-%Y")
    data = request_json(f"{url}/{symbol}/data_day?sdate={start}&edate={end}", **http)
    return parse_kbs(data) if isinstance(data, dict) and data.get("symbol") else []


def fetch_symbol(symbol, days, now, vci_url=VCI_URL, kbs_url=KBS_URL, **http):
    """The last `days` sessions of one symbol. SourceError when neither source has any (never an empty success)."""
    errors = []
    for name, source, url in (("VCI", _from_vci, vci_url), ("KBS", _from_kbs, kbs_url)):
        try:
            rows = source(symbol, days, now, url, **http)
        except SourceError as e:
            errors.append(f"{name}: {e}")
            continue
        if rows:
            return rows[-days:]
        errors.append(f"{name}: no candles")
    raise SourceError(f"{symbol}: " + "; ".join(errors))


def vn_symbols(db):
    """The three-character VN codes of the live board (warrants and bonds have longer codes)."""
    rows = db.select_all("quotes_latest", {"select": "symbol", "market": "eq.VN"}, order="market.asc,symbol.asc")
    return sorted(r["symbol"] for r in rows if re.fullmatch(r"[A-Z0-9]{3}", r["symbol"]))


def days_from(env):
    try:
        days = int((env.get("DAILY_DAYS") or "").strip())
    except ValueError:
        return DEFAULT_DAYS
    return days if 1 <= days <= MAX_DAYS else DEFAULT_DAYS


def run(db, symbols, days, now, fetch=fetch_symbol):
    if not symbols:
        log.error("no symbols to fetch (quotes_latest has no VN rows yet)")
        return 1

    def one(symbol):
        try:
            return symbol, fetch(symbol, days, now), None
        except SourceError as e:
            return symbol, [], e

    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(one, symbols))
    rows = [r for _, rs, _ in results for r in rs]
    failed = [(s, e) for s, _, e in results if e]
    for s, e in failed[:20]:
        log.warning("%s", e)
    try:
        db.upsert("bars_1d", rows, "market,symbol,trade_date")
    except SourceError as e:
        log.error("bars_1d upsert failed (%s)", e)
        return 1
    log.info("bars_1d: %d rows for %d/%d symbols (%d sessions asked)", len(rows), len(symbols) - len(failed), len(symbols), days)
    return 1 if not rows or len(failed) > len(symbols) * MAX_FAILED else 0


def main(env, now=None):
    try:
        db = from_env(env)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        symbols = vn_symbols(db)
    except SourceError as e:
        log.error("could not read quotes_latest (%s)", e)
        return 1
    return run(db, symbols, days_from(env), now or datetime.now(timezone.utc))


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main(os.environ))

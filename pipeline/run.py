"""One snapshot run: python -m pipeline.run --market VN|US.

Gates (run window, market closed) -> fetch board -> window numbers vs the previous snapshot -> signals ->
upsert to Supabase. Re-running a slot never changes what the first run wrote.
"""
import argparse
import logging
import os
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from pipeline import calendar, compare, config, signals, sources
from pipeline.sources import alpaca
from pipeline.sources.http import SourceError
from pipeline.supa import from_env

log = logging.getLogger("pipeline.run")
ROOT = Path(__file__).resolve().parent.parent
CLOSED_SHARE = 0.95
BASELINE_DAYS = 20
HISTORY_LOOKBACK = timedelta(days=45)

# Scheduled run times (local) per market; see the workflows. A slot is the half hour a run falls in.
RUNS = {
    "VN": [time(9, 20), time(9, 50), time(10, 20), time(10, 50), time(11, 20), time(11, 40), time(13, 20),
           time(13, 50), time(14, 20), time(14, 50), time(15, 5)],
    "US": [time(10, 5), time(10, 35), time(11, 5), time(11, 35), time(12, 5), time(12, 35), time(13, 5),
           time(13, 35), time(14, 5), time(14, 35), time(15, 5), time(15, 35), time(16, 20), time(16, 50)],
}
SESSIONS = {"VN": signals.VN_SESSIONS, "US": signals.US_SESSIONS}


def slot_start(market, now):
    """Start of the local half hour containing now, as an aware UTC datetime."""
    local = now.astimezone(calendar.TZ[market])
    return local.replace(minute=local.minute // 30 * 30, second=0, microsecond=0).astimezone(timezone.utc)


def window_minutes(market, run_time):
    """Trading minutes between the previous scheduled run and this one (the first run counts from the open)."""
    sessions = SESSIONS[market]
    runs = RUNS[market]
    i = runs.index(run_time)
    start = runs[i - 1] if i else sessions[0][0]
    return signals.trading_minutes(start, run_time, sessions)


def slot_minutes(market, slot):
    """Window minutes for a slot (UTC datetime); None when no scheduled run falls in that slot."""
    local = slot.astimezone(calendar.TZ[market])
    for t in RUNS[market]:
        if (t.hour, t.minute // 30 * 30) == (local.hour, local.minute):
            return window_minutes(market, t)
    return None


def closed(prev_rows, curr_rows):
    """True when at least 95% of the symbols live in both snapshots show the same cumulative volume."""
    both = [s for s in curr_rows if s in prev_rows and "TT" in curr_rows[s] and "TT" in prev_rows[s]]
    if not both:
        return False
    same = sum(1 for s in both if curr_rows[s]["TT"] == prev_rows[s]["TT"])
    return same / len(both) >= CLOSED_SHARE


def _quote_to_row(q):
    return {"SB": q["symbol"], "CP": q["price"], "TT": q["vol"], "TV": q["val"], "FB": q["f_buy"],
            "FS": q["f_sell"], "PTQ": q["pt_vol"], "PTV": q["pt_val"]}


def _row_to_quote(sym, r, asof):
    big = lambda v: int(round(v or 0))
    return {"symbol": sym, "exchange": r.get("EX") or "", "price": r.get("CP"), "ref_price": r.get("RE"),
            "ceil_price": r.get("CL"), "floor_price": r.get("FL"), "vol": big(r.get("TT")),
            "val": big(r.get("TV")), "f_buy": big(r.get("FB")), "f_sell": big(r.get("FS")),
            "f_room": big(r.get("FR")), "pt_vol": big(r.get("PTQ")), "pt_val": big(r.get("PTV")), "asof": asof}


def _history(db, market, slot, now):
    """symbol -> window volumes of the same slot on past days (newest first, at most 20)."""
    since = (now - HISTORY_LOOKBACK).isoformat()
    want = (slot.hour, slot.minute)
    per_day = {}
    for r in db.select_all("bars_30m", {"select": "symbol,bar_start,vol", "bar_start": "gte." + since}):
        ts = datetime.fromisoformat(r["bar_start"]).astimezone(timezone.utc)
        if (ts.hour, ts.minute) == want and ts.date() < slot.date():
            per_day.setdefault(r["symbol"], {})[ts.date()] = r["vol"]
    return {s: [v for _, v in sorted(days.items(), reverse=True)[:BASELINE_DAYS]] for s, days in per_day.items()}


def process(market, now, rows, prev_quotes, history, th):
    """Pure core: (bars, signal rows, quote rows) for one run."""
    slot = slot_start(market, now)
    prev_rows = {q["symbol"]: _quote_to_row(q) for q in prev_quotes}
    deltas = compare.delta_all(prev_rows, rows)
    minutes = slot_minutes(market, slot)
    bars, sigs = [], []
    for sym, d in deltas.items():
        bars.append({"symbol": sym, "bar_start": slot.isoformat(), "vol": int(d["vol"]), "val": int(round(d["val"])),
                     "fnet": int(d["fnet"]), "pt_val": int(round(d["pt_val"]))})
        hist = history.get(sym, [])
        kw = {}
        if minutes is not None:
            kw = {"minutes": minutes, "history_minutes": [minutes] * len(hist)}
        res = signals.evaluate(d, hist, th, market=market, **kw)
        if res["level"] > 0:
            sigs.append({"asof": slot.isoformat(), "symbol": sym, "level": res["level"],
                         "learning": res["learning"], "items": res["signals"]})
    quotes = [_row_to_quote(sym, r, now.isoformat()) for sym, r in rows.items()]
    return bars, sigs, quotes


def main(argv, env, now=None, fetch=None, symbols=None, sleep=None):
    ap = argparse.ArgumentParser(prog="pipeline.run")
    ap.add_argument("--market", required=True, choices=("VN", "US"))
    market = ap.parse_args(argv).market
    now = now or datetime.now(timezone.utc)

    try:
        db = from_env(env)
        if market == "US":
            missing = [k for k in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY") if not (env.get(k) or "").strip()]
            if missing:
                raise RuntimeError("missing environment variable(s): " + ", ".join(missing))
    except RuntimeError as e:
        log.error("%s", e)
        print(f"error: {e}", file=sys.stderr)
        return 2
    db.sleep = sleep

    cal = calendar.load(ROOT / "config" / "calendar.json")
    if not calendar.is_run_window(market, now, cal):
        log.info("outside the run window, nothing to do")
        return 0

    th = config.load(ROOT / "config" / "thresholds.json", market)
    if symbols is None:
        symbols = calendar.load(ROOT / "config" / "symbols.json")[market]
    if fetch is None:
        if market == "VN":
            fetch = lambda syms: sources.fetch_vn(syms, sleep=sleep)
        else:
            fetch = lambda syms: alpaca.fetch(syms, env["APCA_API_KEY_ID"], env["APCA_API_SECRET_KEY"], sleep=sleep)
    try:
        rows = fetch(symbols)
    except SourceError as e:
        log.error("no data source answered: %s", e)
        return 1

    slot = slot_start(market, now).isoformat()
    if db.select("snapshot_meta", {"market": "eq." + market, "asof": "eq." + slot, "select": "id"}):
        log.info("already ran slot %s", slot)
        return 0
    prev_quotes = db.select_all("quotes_latest", {"select": "*", "symbol": "in.(" + ",".join(rows) + ")"})
    prev_rows = {q["symbol"]: _quote_to_row(q) for q in prev_quotes}
    if closed(prev_rows, rows):
        log.info("closed: volumes unchanged since the previous snapshot")
        return 0

    bars, sigs, quotes = process(market, now, rows, prev_quotes, _history(db, market, slot_start(market, now), now), th)
    db.upsert("bars_30m", bars, "symbol,bar_start", merge=False)
    db.upsert("signals", sigs, "asof,symbol", merge=False)
    db.upsert("quotes_latest", quotes, "symbol")
    db.upsert("snapshot_meta", [{"market": market, "asof": slot, "symbols": len(rows), "signals": len(sigs)}],
              "market,asof", merge=False)
    try:
        db.upsert("heartbeat", [{"market": market, "asof": now.isoformat(), "status": "ok"}], "market")
    except SourceError as e:
        log.warning("heartbeat not written: %s", e)
    log.info("slot=%s symbols=%d bars=%d signals=%d", slot, len(rows), len(bars), len(sigs))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main(sys.argv[1:], os.environ))

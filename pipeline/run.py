"""One snapshot run: python -m pipeline.run --market VN|US.

Gates (run window, feed health, market closed) -> window numbers vs the previous snapshot -> signals ->
upsert to Supabase. Every row carries its market and uses the keys of migration 0002. Re-running a slot never
changes what the first run wrote.
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
MIN_LIVE_SHARE = 0.5  # fewer live symbols than this means the feed is broken
MIN_WINDOW_SHARE = 0.9
MAX_WINDOW_SLOTS = 1.5  # a window longer than this many slots is no basis for a per-minute comparison
SLOT_MINUTES = 30
LATE_WARN_MINUTES = 10
JOB = "snapshot"
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


def _scheduled(market, local):
    """Latest scheduled run time of that local day at or before `local`, as a datetime; None before the first."""
    best = None
    for t in RUNS[market]:
        at = local.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if at <= local and (best is None or at > best):
            best = at
    return best


def slot_start(market, now):
    """Slot of the scheduled run this execution belongs to (a delayed run keeps its own slot), as UTC."""
    local = now.astimezone(calendar.TZ[market])
    ref = _scheduled(market, local) or local
    return ref.replace(minute=ref.minute // 30 * 30, second=0, microsecond=0).astimezone(timezone.utc)


def late_minutes(market, now):
    local = now.astimezone(calendar.TZ[market])
    ref = _scheduled(market, local)
    return 0 if ref is None else int((local - ref).total_seconds() // 60)


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


def actual_minutes(market, prev_asof, now):
    """Trading minutes since the real previous snapshot (since the open on a new day); 0 drops S1 when too long."""
    tz = calendar.TZ[market]
    local = now.astimezone(tz)
    prev = prev_asof.astimezone(tz) if prev_asof else None
    start = prev.time() if prev and prev.date() == local.date() else SESSIONS[market][0][0]
    m = signals.trading_minutes(start, local.time(), SESSIONS[market])
    if m > MAX_WINDOW_SLOTS * SLOT_MINUTES:
        log.warning("window of %d trading minutes is too long for a per-minute volume check: S1 skipped", m)
        return 0
    return m


def closed(prev_rows, curr_rows):
    """True when the market looks closed: at least half of the symbols are comparable and 95% of those show no
    movement in volume or negotiated deals since the previous snapshot."""
    both = [s for s in curr_rows if s in prev_rows and "TT" in curr_rows[s] and "TT" in prev_rows[s]]
    if not both or len(both) < MIN_LIVE_SHARE * len(curr_rows):
        return False
    keys = ("TT", "PTQ", "PTV")
    same = sum(1 for s in both if all(curr_rows[s].get(k, 0) == prev_rows[s].get(k, 0) for k in keys))
    return same / len(both) >= CLOSED_SHARE


def _quote_to_row(q):
    return {"SB": q["symbol"], "CP": q["price"], "TT": q["vol"], "TV": q["val"], "FB": q["f_buy"],
            "FS": q["f_sell"], "PTQ": q["pt_vol"], "PTV": q["pt_val"]}


def _row_to_quote(market, sym, r, asof):
    big = lambda v: int(round(v or 0))
    return {"market": market, "symbol": sym, "exchange": r.get("EX") or "", "price": r.get("CP"),
            "ref_price": r.get("RE"), "ceil_price": r.get("CL"), "floor_price": r.get("FL"),
            "vol": big(r.get("TT")), "val": big(r.get("TV")), "f_buy": big(r.get("FB")), "f_sell": big(r.get("FS")),
            "f_room": big(r.get("FR")), "pt_vol": big(r.get("PTQ")), "pt_val": big(r.get("PTV")), "asof": asof}


def _carry_negotiated(rows, prev_rows):
    """A source without negotiated-deal data (VCI) keeps the previous values, so the window shows no change
    instead of a negative one (which would silently drop the symbol) and the next source switch stays sane."""
    out = {}
    for sym, r in rows.items():
        if r.get("PT") is False:
            p = prev_rows.get(sym, {})
            r = {**r, "PTQ": p.get("PTQ", 0), "PTV": p.get("PTV", 0)}
        out[sym] = r
    return out


def _history(db, market, slot, now):
    """symbol -> window volumes of the same local half hour on past days (newest first, at most 20)."""
    tz = calendar.TZ[market]
    since = (now - HISTORY_LOOKBACK).isoformat()
    want = slot.astimezone(tz)
    per_day = {}
    rows = db.select_all("bars_30m", {"select": "symbol,bar_start,vol", "market": "eq." + market,
                                      "bar_start": "gte." + since})
    for r in rows:
        ts = datetime.fromisoformat(r["bar_start"]).astimezone(tz)  # local clock: stays aligned across DST changes
        if (ts.hour, ts.minute) == (want.hour, want.minute) and ts.date() < want.date():
            per_day.setdefault(r["symbol"], {})[ts.date()] = r["vol"]
    return {s: [v for _, v in sorted(days.items(), reverse=True)[:BASELINE_DAYS]] for s, days in per_day.items()}


def _prev_asof(prev_quotes):
    stamps = [datetime.fromisoformat(q["asof"]) for q in prev_quotes if q.get("asof")]
    return max(stamps) if stamps else None


def process(market, now, rows, prev_quotes, history, th):
    """Core: (bars, signal rows, quote rows) for one run."""
    slot = slot_start(market, now)
    tz = calendar.TZ[market]
    prev_asof = _prev_asof(prev_quotes)
    prev_rows = {q["symbol"]: _quote_to_row(q) for q in prev_quotes}
    rows = _carry_negotiated(rows, prev_rows)
    if prev_asof and prev_asof.astimezone(tz).date() == now.astimezone(tz).date():
        base = prev_rows
    else:  # first run of the day: yesterday's totals are not a baseline, count from the open
        base = {s: {"TT": 0, "TV": 0, "FB": 0, "FS": 0, "PTQ": 0, "PTV": 0} for s in rows}
    deltas = compare.delta_all(base, rows)
    minutes = actual_minutes(market, prev_asof, now)
    hist_minutes = slot_minutes(market, slot)
    hist_minutes = SLOT_MINUTES if hist_minutes is None else hist_minutes
    bars, sigs = [], []
    for sym, d in deltas.items():
        bars.append({"market": market, "symbol": sym, "bar_start": slot.isoformat(), "vol": int(d["vol"]),
                     "val": int(round(d["val"])), "fnet": int(d["fnet"]), "pt_val": int(round(d["pt_val"]))})
        hist = history.get(sym, [])
        res = signals.evaluate(d, hist, th, market=market, minutes=minutes,
                               history_minutes=[hist_minutes] * len(hist))
        if res["level"] > 0:
            sigs.append({"market": market, "asof": slot.isoformat(), "symbol": sym, "level": res["level"],
                         "learning": res["learning"], "items": res["signals"]})
    if len(deltas) < MIN_WINDOW_SHARE * len(rows):
        log.warning("only %d of %d symbols have a window (new symbols, session reset or a source switch)",
                    len(deltas), len(rows))
    quotes = [_row_to_quote(market, sym, r, now.isoformat()) for sym, r in rows.items()]
    return bars, sigs, quotes


def _heartbeat(db, market, now, detail):
    db.upsert("heartbeat", [{"market": market, "job": JOB, "last_seen": now.isoformat(), "detail": detail}],
              "market,job")


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
    late = late_minutes(market, now)
    if late > LATE_WARN_MINUTES:
        log.warning("run is late by %d minutes (cron delay); it keeps the slot of its scheduled time", late)

    th = config.load(ROOT / "config" / "thresholds.json", market)
    if symbols is None:
        symbols = calendar.load(ROOT / "config" / "symbols.json")[market]
    slot_dt = slot_start(market, now)
    slot = slot_dt.isoformat()
    if db.select("snapshot_meta", {"market": "eq." + market, "slot_start": "eq." + slot, "select": "id"}):
        log.info("already ran slot %s", slot)
        return 0
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
    need = max(1, MIN_LIVE_SHARE * len(symbols))
    if len(rows) < need:
        log.error("feed has %d live symbols of %d requested (need %d): nothing written", len(rows), len(symbols), need)
        return 1
    source = next(iter(rows.values())).get("SRC", "unknown")
    pt = all(r.get("PT") is not False for r in rows.values())

    prev_quotes = db.select_all("quotes_latest", {"select": "*", "market": "eq." + market})
    prev_rows = {q["symbol"]: _quote_to_row(q) for q in prev_quotes}
    detail = {"source": source, "pt": pt, "symbols": len(rows)}
    if slot_minutes(market, slot_dt) != 0 and closed(prev_rows, rows):
        # the run after the close is exempt: negotiated deals after the bell are the point of that run
        log.warning("closed: volumes unchanged since the previous snapshot")
        _heartbeat(db, market, now, {**detail, "status": "closed"})
        log.error("a weekday not listed in config/calendar.json looks closed: check for a missing holiday")
        return 1

    bars, sigs, quotes = process(market, now, rows, prev_quotes, _history(db, market, slot_dt, now), th)
    db.upsert("bars_30m", bars, "market,symbol,bar_start", merge=False)
    db.upsert("signals", sigs, "market,asof,symbol", merge=False)
    # the slot is recorded before the quotes move on: a crash in between makes the rerun skip, never overwrite
    db.upsert("snapshot_meta", [{"market": market, "asof": now.isoformat(), "slot_start": slot,
                                 "symbols": len(rows), "signals": len(sigs)}], "market,slot_start", merge=False)
    db.upsert("quotes_latest", quotes, "market,symbol")
    try:
        _heartbeat(db, market, now, {**detail, "status": "ok", "bars": len(bars), "signals": len(sigs)})
    except SourceError as e:
        log.error("heartbeat not written: %s", e)
        return 1
    log.info("slot=%s source=%s symbols=%d bars=%d signals=%d", slot, source, len(rows), len(bars), len(sigs))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main(sys.argv[1:], os.environ))

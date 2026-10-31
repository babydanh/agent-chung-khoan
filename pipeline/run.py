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
MIN_DELTA_SHARE = 0.5  # on a later run of the day, fewer windows than this means a reset, not a market
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


def sessions_for(market, day_iso, cal):
    """Trading sessions of a local day: the early session on US early-close days."""
    if market == "US" and day_iso in cal.get("US", {}).get("early_close", []):
        return signals.US_EARLY_SESSIONS
    return SESSIONS[market]


def window_minutes(market, run_time, sessions=None):
    """Trading minutes between the previous scheduled run and this one (the first run counts from the open)."""
    sessions = sessions or SESSIONS[market]
    runs = RUNS[market]
    i = runs.index(run_time)
    start = runs[i - 1] if i else sessions[0][0]
    return signals.trading_minutes(start, run_time, sessions)


def slot_minutes(market, slot, sessions=None):
    """Window minutes for a slot (UTC datetime); None when no scheduled run falls in that slot."""
    local = slot.astimezone(calendar.TZ[market])
    for t in RUNS[market]:
        if (t.hour, t.minute // 30 * 30) == (local.hour, local.minute):
            return window_minutes(market, t, sessions)
    return None


def _raw_minutes(market, prev_asof, now, sessions=None):
    """Trading minutes since the real previous snapshot (since the open on a new day)."""
    tz = calendar.TZ[market]
    local = now.astimezone(tz)
    sessions = sessions or SESSIONS[market]
    prev = prev_asof.astimezone(tz) if prev_asof else None
    start = prev.time() if prev and prev.date() == local.date() else sessions[0][0]
    return signals.trading_minutes(start, local.time(), sessions)


def actual_minutes(market, prev_asof, now, sessions=None):
    """_raw_minutes, or 0 (S1 skipped, with a warning) when the window is too long for a per-minute comparison."""
    m = _raw_minutes(market, prev_asof, now, sessions)
    if m > MAX_WINDOW_SLOTS * SLOT_MINUTES:
        log.warning("window of %d trading minutes is too long for a per-minute volume check: S1 skipped", m)
        return 0
    return m


def closed(prev_rows, curr_rows):
    """True when the market looks closed: at least half of the symbols are comparable and 95% of those show no
    movement in volume (or negotiated deals, when the source has them) since the previous snapshot."""
    both = [s for s in curr_rows if s in prev_rows and "TT" in curr_rows[s] and "TT" in prev_rows[s]]
    if not both or len(both) < MIN_LIVE_SHARE * len(curr_rows):
        return False

    def same(s):
        keys = ("TT",) if curr_rows[s].get("PT") is False else ("TT", "PTQ", "PTV")  # no PT data: nothing to compare
        return all(curr_rows[s].get(k, 0) == prev_rows[s].get(k, 0) for k in keys)

    return sum(1 for s in both if same(s)) / len(both) >= CLOSED_SHARE


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
                                      "bar_start": "gte." + since}, order="market.asc,symbol.asc,bar_start.asc")
    for r in rows:
        ts = datetime.fromisoformat(r["bar_start"]).astimezone(tz)  # local clock: stays aligned across DST changes
        if (ts.hour, ts.minute) == (want.hour, want.minute) and ts.date() < want.date():
            per_day.setdefault(r["symbol"], {})[ts.date()] = r["vol"]
    return {s: [v for _, v in sorted(days.items(), reverse=True)[:BASELINE_DAYS]] for s, days in per_day.items()}


def _prev_asof(prev_quotes):
    stamps = [datetime.fromisoformat(q["asof"]) for q in prev_quotes if q.get("asof")]
    return max(stamps) if stamps else None


def process(market, now, rows, prev_quotes, history, th, sessions=None, stats=None):
    """Core: (bars, signal rows, quote rows) for one run. `stats` (a dict) receives numbers for the heartbeat."""
    stats = {} if stats is None else stats
    slot = slot_start(market, now)
    tz = calendar.TZ[market]
    sessions = sessions or SESSIONS[market]
    prev_asof = _prev_asof(prev_quotes)
    prev_rows = {q["symbol"]: _quote_to_row(q) for q in prev_quotes}
    same_day = bool(prev_asof) and prev_asof.astimezone(tz).date() == now.astimezone(tz).date()
    if same_day:
        base = prev_rows
    else:  # first run of the day: yesterday's totals (negotiated deals too) are not a baseline, count from the open
        base = {s: {"TT": 0, "TV": 0, "FB": 0, "FS": 0, "PTQ": 0, "PTV": 0} for s in rows}
    rows = _carry_negotiated(rows, base)
    deltas = compare.delta_all(base, rows)
    raw = _raw_minutes(market, prev_asof, now, sessions)
    too_long = raw > MAX_WINDOW_SLOTS * SLOT_MINUTES
    if too_long:
        log.warning("window of %d trading minutes is too long: S1 skipped and no bar written to the baseline", raw)
    minutes = 0 if too_long else raw
    hist_minutes = slot_minutes(market, slot, sessions)
    hist_minutes = SLOT_MINUTES if hist_minutes is None else hist_minutes
    bars, sigs = [], []
    for sym, d in deltas.items():
        if not too_long:
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
    stats.update(deltas=len(deltas), same_day=same_day, bars_skipped=too_long,
                 s1_skipped="window_too_long" if too_long else ("no_trading_minutes" if raw == 0 else None))
    quotes = [_row_to_quote(market, sym, r, now.isoformat()) for sym, r in rows.items()]
    return bars, sigs, quotes


def expected_runs(market, day, cal):
    """[(scheduled run time, slot)] as UTC datetimes for a local day: the runs inside the run window; none on
    weekends and holidays. US early-close days stop earlier because the window does."""
    tz = calendar.TZ[market]
    out = []
    for t in RUNS[market]:
        at = datetime.combine(day, t, tzinfo=tz)
        if calendar.is_run_window(market, at.astimezone(timezone.utc), cal):
            out.append((at.astimezone(timezone.utc), at.replace(minute=at.minute // 30 * 30).astimezone(timezone.utc)))
    return out


def expected_slots(market, day, cal):
    return [slot for _, slot in expected_runs(market, day, cal)]


def _missed_slots(db, market, slot_dt, now, cal):
    """Earlier slots of today that were scheduled but have no snapshot_meta row (delayed or lost runs)."""
    tz = calendar.TZ[market]
    day = now.astimezone(tz).date()
    earlier = [s for s in expected_slots(market, day, cal) if s < slot_dt]
    if not earlier:
        return []
    have = {datetime.fromisoformat(r["slot_start"]).astimezone(timezone.utc) for r in db.select_all(
        "snapshot_meta", {"select": "slot_start", "market": "eq." + market, "slot_start": "gte." + earlier[0].isoformat()},
        order="market.asc,slot_start.asc")}
    return [s.isoformat() for s in earlier if s not in have]


def _heartbeat(db, market, now, detail):
    db.upsert("heartbeat", [{"market": market, "job": JOB, "last_seen": now.isoformat(), "detail": detail}],
              "market,job")


def _slot_complete(db, market, meta_asof):
    """True when quotes_latest and the heartbeat are at least as new as the recorded slot."""
    quotes = db.select("quotes_latest", {"select": "asof", "market": "eq." + market, "order": "asof.desc", "limit": 1})
    beat = db.select("heartbeat", {"select": "last_seen", "market": "eq." + market, "job": "eq." + JOB})
    want = datetime.fromisoformat(meta_asof)
    return (bool(quotes) and datetime.fromisoformat(quotes[0]["asof"]) >= want
            and bool(beat) and datetime.fromisoformat(beat[0]["last_seen"]) >= want)


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
    local_day = now.astimezone(calendar.TZ[market]).date()
    sessions = sessions_for(market, local_day.isoformat(), cal)
    slot_dt = slot_start(market, now)
    slot = slot_dt.isoformat()
    if fetch is None:
        if market == "VN":
            fetch = lambda syms: sources.fetch_vn(syms, sleep=sleep)
        else:
            fetch = lambda syms: alpaca.fetch(syms, env["APCA_API_KEY_ID"], env["APCA_API_SECRET_KEY"], sleep=sleep)

    meta = db.select("snapshot_meta", {"market": "eq." + market, "slot_start": "eq." + slot, "select": "id,asof"})
    if meta and _slot_complete(db, market, meta[0]["asof"]):
        log.info("already ran slot %s", slot)
        return 0

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
    missed = _missed_slots(db, market, slot_dt, now, cal)
    if missed:
        log.warning("missed slot(s) before %s: %s", slot, ", ".join(missed))
    detail = {"source": source, "pt": pt, "symbols": len(rows), "requested": len(symbols),
              "missing": len(symbols) - len(rows), "late_minutes": late, "missed_slots": missed}

    if meta:  # the slot was recorded but the quotes or the heartbeat never followed: finish, do not skip
        log.warning("slot %s was recorded but quotes_latest or the heartbeat is missing: finishing it", slot)
        db.upsert("quotes_latest", [_row_to_quote(market, s, r, now.isoformat()) for s, r in rows.items()],
                  "market,symbol")
        try:
            _heartbeat(db, market, now, {**detail, "status": "ok", "recovered": True})
        except SourceError as e:
            log.error("heartbeat not written: %s", e)
            return 1
        return 0

    prev_quotes = db.select_all("quotes_latest", {"select": "*", "market": "eq." + market}, order="market.asc,symbol.asc")
    prev_rows = {q["symbol"]: _quote_to_row(q) for q in prev_quotes}
    if slot_minutes(market, slot_dt, sessions) != 0 and closed(prev_rows, rows):
        # the run after the close is exempt: negotiated deals after the bell are the point of that run
        log.warning("closed: volumes unchanged since the previous snapshot")
        _heartbeat(db, market, now, {**detail, "status": "closed"})
        log.error("a weekday not listed in config/calendar.json looks closed: check for a missing holiday")
        return 1

    stats = {}
    bars, sigs, quotes = process(market, now, rows, prev_quotes, _history(db, market, slot_dt, now), th,
                                 sessions=sessions, stats=stats)
    detail.update(deltas=stats["deltas"], s1_skipped=stats["s1_skipped"])
    if stats["same_day"] and stats["deltas"] < MIN_DELTA_SHARE * len(rows):
        # e.g. every cumulative volume dropped: a feed reset or a source switch. No snapshot, but move the
        # baseline on so the next run is not stuck behind it.
        log.error("only %d of %d symbols have a window on a later run of the day: no snapshot written",
                  stats["deltas"], len(rows))
        db.upsert("quotes_latest", quotes, "market,symbol")
        _heartbeat(db, market, now, {**detail, "status": "no_windows"})
        return 1

    db.upsert("bars_30m", bars, "market,symbol,bar_start", merge=False)
    db.upsert("signals", sigs, "market,asof,symbol", merge=False)
    # the slot is recorded before the quotes move on: a crash in between is finished by the rerun, never skipped
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

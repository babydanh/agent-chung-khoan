"""Telegram notifications: symbols that reach the signal level, and hot headlines (python3 -m pipeline.notify
--market VN|US). No model is used: the headline event comes from keywords (pipeline.newsrank) and every figure
from the signals. Text is built from templates and scanned with find_banned; nothing is sent if the scan fails.

State lives in the heartbeat row (VN, "notify") shared by both markets: stories already sent, a queue of messages held
back (quiet hours 22:00-07:00 Vietnam time, or the hourly limit) and the send times of the last hour. Secrets come
from the environment only: SUPABASE_URL, SUPABASE_SECRET_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline import alert, calendar, news, newsrank, push
from pipeline.banned import find_banned
from pipeline.bulletin import _latest_items
from pipeline.sources.http import SourceError, request_json
from pipeline.supa import from_env

log = logging.getLogger("pipeline.notify")
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "notify.json"
REQUIRED = ("hot", "max_per_hour", "signal_level", "flow_level", "watch")
STATE_MARKET, JOB = "VN", "notify"
KEEP_SENT = timedelta(days=3)
QUEUE_MAX, QUEUE_MAX_AGE = 30, timedelta(hours=24)
SIGNAL_ORDER = 100  # signal notices rank above headlines


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    missing = [k for k in REQUIRED if k not in cfg]
    if missing:
        raise ValueError(f"{path}: missing {', '.join(missing)}")
    if not all(isinstance(cfg["watch"].get(m), list) for m in ("VN", "US")):
        raise ValueError(f"{path}: watch needs a VN and a US list")
    return cfg


def _signal_label(item):
    i, d = item.get("id"), item.get("dir")
    return {"S1": "KL tăng đột biến", "S2": "NN ròng âm" if d == "sell" else "NN ròng dương", "S3": "Thoả thuận lớn",
            "S4": "Biến động giá", "S5": "Gap mở cửa"}.get(i, i or "")


def _signal_notices(rows, local_date, cfg, now):
    out = []
    for r in rows:
        if r["level"] < cfg["signal_level"]:
            continue
        labels = [x for x in (_signal_label(s) for s in r["signals"] or []) if x]
        text = f"{r['symbol']} · Mức {r['level']}" + (f"\n{' · '.join(labels)}" if labels else "")
        out.append({"key": f"lv:{r['market']}:{r['symbol']}:{local_date}:{r['level']}", "text": text,
                    "score": SIGNAL_ORDER + r["level"], "at": now.isoformat()})
    return out


def _flow_note(symbols, rows, flow_level):
    for r in rows:
        if r["symbol"] in symbols and r["level"] >= flow_level:
            labels = [x for x in (_signal_label(s) for s in r["signals"] or []) if x]
            return f"Khớp dòng tiền: Mức {r['level']}" + (f" · {', '.join(labels)}" if labels else "")
    return None


def _news_notices(items, rows, cfg, market, now, local):
    flows = {r["symbol"] for r in rows if r["level"] >= cfg["flow_level"]}
    watch = set(cfg["watch"].get(market, []))
    stories = newsrank.cluster([{**i, "event": None} for i in items])
    out = []
    for st in stories:
        key, label, _ = newsrank.classify(st["title"] + " " + st["summary"])
        st["event"] = key
        score = newsrank.hot_score(st, now, watch, flows)
        if score < cfg["hot"]:
            continue
        lines = [f"{(st['symbols'] or ['Thị trường'])[0]} · {label}", st["title"],
                 f"{st['source']} · {push._local(datetime.fromisoformat(st['published'])):%H:%M}" if st["published"] else st["source"]]
        note = _flow_note(st["symbols"], rows, cfg["flow_level"])
        if note:
            lines.append(note)
        lines.append(st["link"])
        out.append({"key": "n:" + st["cluster"], "text": "\n".join(lines), "score": score, "at": now.isoformat()})
    return out


def _clean(msgs):
    ok = []
    for m in msgs:
        bad = find_banned(m["text"])
        if bad:
            log.warning("message %s dropped by the wording scan: %s", m["key"], bad)
            continue
        ok.append(m)
    return ok


def _quiet(local):
    return local.hour >= push.QUIET_START or local.hour < push.QUIET_END


def _load_state(db, now):
    rows = db.select("heartbeat", {"market": "eq." + STATE_MARKET, "job": "eq." + JOB, "select": "detail"})
    d = (rows[0].get("detail") if rows else None) or {}
    sent = {k: v for k, v in (d.get("sent") or {}).items() if now - datetime.fromisoformat(v) < KEEP_SENT}
    queue = [m for m in d.get("queue") or [] if now - datetime.fromisoformat(m["at"]) < QUEUE_MAX_AGE]
    recent = [t for t in d.get("recent") or [] if now - datetime.fromisoformat(t) < timedelta(hours=1)]
    return {"sent": sent, "queue": queue, "recent": recent}


def _save_state(db, state, now):
    db.upsert("heartbeat", [{"market": STATE_MARKET, "job": JOB, "last_seen": now.isoformat(), "detail": state}], "market,job")


def main(argv, env, now=None, get_text=None, sleep=None, config=None, telegram_base=alert.API):
    ap = argparse.ArgumentParser(prog="pipeline.notify")
    ap.add_argument("--market", required=True, choices=("VN", "US"))
    market = ap.parse_args(argv).market
    now = now or datetime.now(timezone.utc)
    missing = [k for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not (env.get(k) or "").strip()]
    if missing:
        log.error("missing environment variable(s): %s", ", ".join(missing))
        return 2
    try:
        db = from_env(env)
        cfg = config or load_config(CONFIG_PATH)
    except (RuntimeError, ValueError) as e:
        log.error("%s", e)
        return 2
    db.sleep = sleep
    token, chat = env["TELEGRAM_BOT_TOKEN"].strip(), env["TELEGRAM_CHAT_ID"].strip()
    local = push._local(now)
    get_text = get_text or (lambda url: request_json(url, text=True, sleep=sleep))
    try:
        state = _load_state(db, now)
        rows = _latest_items(db, market, now)
        rows = [{**r, "market": market} for r in rows]
        fresh = _signal_notices(rows, local.date().isoformat(), cfg, now)
        if market == "VN":
            known = set(calendar.load(ROOT / "config" / "symbols.json")["VN"])
            try:
                fresh += _news_notices(news.fetch_all(news.FEEDS, known, get_text, now).items, rows, cfg, market, now, local)
            except news.NewsError as e:
                log.warning("no headlines this run: %s", e)
        queued = {m["key"] for m in state["queue"]}
        fresh = [m for m in _clean(fresh) if m["key"] not in state["sent"] and m["key"] not in queued]
        msgs = sorted(state["queue"] + fresh, key=lambda m: -m["score"])
        code = _deliver(msgs, state, cfg, now, local, token, chat, telegram_base, sleep)
        _save_state(db, state, now)
    except SourceError as e:
        log.error("notify stopped: %s", str(e).replace(token, "***"))
        return 1
    return code


def _deliver(msgs, state, cfg, now, local, token, chat, base, sleep):
    if _quiet(local) or not msgs:
        state["queue"] = msgs[:QUEUE_MAX]
        return 0
    budget = max(cfg["max_per_hour"] - len(state["recent"]), 0)
    if budget == 0:
        state["queue"] = msgs[:QUEUE_MAX]
        return 0
    covered, summary = [], None
    plan = msgs
    if len(msgs) > budget:
        plan, covered = msgs[:max(budget - 1, 0)], msgs[max(budget - 1, 0):]
        summary = {"key": "sum:" + now.isoformat(), "text": f"Còn {len(covered)} tin nóng chưa gửi", "score": 0, "at": now.isoformat()}
        plan = plan + [summary]
    done = 0
    for m in plan:
        try:
            alert.send(token, chat, m["text"], base=base, sleep=sleep)
        except (SourceError, RuntimeError) as e:
            log.error("telegram refused a message: %s", str(e).replace(token, "***"))
            break
        state["sent"][m["key"]] = now.isoformat()
        state["recent"].append(now.isoformat())
        done += 1
    if done == len(plan):
        for m in covered:
            state["sent"][m["key"]] = now.isoformat()
        state["queue"] = []
        return 0
    state["queue"] = ([m for m in plan[done:] if m is not summary] + covered)[:QUEUE_MAX]
    return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main(sys.argv[1:], os.environ))

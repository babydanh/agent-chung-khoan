# S4 / S5 are not active yet

`pipeline.signals.evaluate` can report S4 (price move >= `s4_k` x ATR) and S5 (US opening gap >= `s5_k` x ATR),
but `pipeline/run.py` does not pass `atr`, `px_move`, `open` or `prev_close`, so neither signal can fire.
The thresholds `s4_k` / `s5_k` in `config/thresholds.json` have no effect until then.

Why: ATR14 needs daily bars. The `bars_1d` table exists (migration 0002) but nothing fills it. Filling it from the
price boards would give a wrong ATR (they only hold the current day), so the wiring waits for a daily-bar source
(a later phase) instead of guessing.

When daily bars exist: read the last 15 sessions from `bars_1d`, call `indicators.atr`, pass `atr=` and the extra
fields to `evaluate` in `run.process`, and add a test that a gap of `s5_k` x ATR produces an S5 row.

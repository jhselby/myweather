"""Production %-vs-raw trajectory, stratified by observed synoptic regime.

Question this exists to answer: are we ACTUALLY improving, or has the recent
"−9% mean" trajectory been carried by favorable weather in the calibration
window? Aggregate Production % is regime-blind — if we've been in a lot of
nw_flow (which HRRR handles well) our corrections have less bite and look
smaller than they really are; if we've been in a lot of ne_flow they look
bigger. Neither reads as "the pipeline is getting better/worse."

Method:
  Read the pair log. For each row, key by (obs_day, regime_obs, field). For
  each cell, compute:
      mae_raw  = mean |forecast_l1 - observed|
      mae_prod = mean |forecast     - observed|   # forecast = Production
      prod_pct_vs_raw = (mae_prod - mae_raw) / mae_raw
  Append one row per (day, regime, field) to a rolling JSONL history file.

  Emits ONLY days that just closed (yesterday + a lookback window for late-
  arriving pairs). Idempotent: if a row for (day, regime, field) is already
  in the history file, skip.

Debug page consumer: a rolling per-(regime, field) trajectory chart. In two
weeks we can answer "did ne_flow Production actually get better on 07-09
when the ws skip-table fired, or did we just get lucky with regime mix?"

Output:
  analysis/output/production_regime_trajectory.jsonl (one row per
  (day, regime, field), n_pairs, mae_raw, mae_prod, prod_pct_vs_raw)

Run:
  python3 analysis/production_regime_trajectory.py
"""
import os
import sys
import json
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "output", "production_regime_trajectory.jsonl",
)
# Only emit rows for days that closed at least LAG_DAYS ago — lets late-
# arriving pair rows land before we freeze that day's number. 2 days matches
# the pair-log latency I've been seeing (obs_time trails real-time by ~10h;
# 48h gives plenty of margin).
LAG_DAYS = 2
# Don't rewalk the whole log every night — only the last WINDOW_DAYS.
WINDOW_DAYS = 30
MIN_N_PER_CELL = 30


def _existing_keys():
    """Set of (day, regime, field) tuples already in the output file."""
    seen = set()
    if not os.path.exists(OUT_PATH):
        return seen
    with open(OUT_PATH) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            k = (r.get("day"), r.get("regime"), r.get("field"))
            if all(k):
                seen.add(k)
    return seen


def main():
    now = datetime.now()
    freeze_before = (now - timedelta(days=LAG_DAYS)).date()
    window_start = (now - timedelta(days=WINDOW_DAYS)).date()

    # (day, regime, field) -> [n, sum|err_raw|, sum|err_prod|]
    cells = defaultdict(lambda: [0, 0.0, 0.0])
    rows_scanned = 0
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            rows_scanned += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            field = r.get("field")
            if not field:
                continue
            obs_t = r.get("obs_time")
            if not obs_t or len(obs_t) < 10:
                continue
            try:
                day = datetime.strptime(obs_t[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if day < window_start or day > freeze_before:
                continue
            so = r.get("state_obs") or {}
            regime = so.get("regime_synoptic") or so.get("regime_flow")
            if not regime:
                continue
            fc_l1 = r.get("forecast_l1")
            fc_prod = r.get("forecast")
            obs = r.get("observed")
            if fc_l1 is None or fc_prod is None or obs is None:
                continue
            try:
                err_raw = abs(float(fc_l1) - float(obs))
                err_prod = abs(float(fc_prod) - float(obs))
            except (TypeError, ValueError):
                continue
            key = (day.isoformat(), regime, field)
            c = cells[key]
            c[0] += 1
            c[1] += err_raw
            c[2] += err_prod

    print(f"rows scanned: {rows_scanned:,}   (day, regime, field) cells: {len(cells):,}")

    seen = _existing_keys()
    new_rows = []
    for (day_str, regime, field), (n, sr, sp) in cells.items():
        if n < MIN_N_PER_CELL:
            continue
        if (day_str, regime, field) in seen:
            continue
        mae_raw = sr / n
        mae_prod = sp / n
        # Guard against divide-by-zero on rows where both are exactly 0.
        pct = ((mae_prod - mae_raw) / mae_raw) if mae_raw > 0 else 0.0
        new_rows.append({
            "day":              day_str,
            "regime":           regime,
            "field":            field,
            "n_pairs":          n,
            "mae_raw":          round(mae_raw, 4),
            "mae_prod":         round(mae_prod, 4),
            "prod_pct_vs_raw":  round(pct * 100, 2),
        })

    # Append in day-then-field order so a human tailing the file sees a
    # coherent trajectory.
    new_rows.sort(key=lambda r: (r["day"], r["regime"], r["field"]))
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "a") as fh:
        for r in new_rows:
            fh.write(json.dumps(r) + "\n")

    print(f"new rows appended: {len(new_rows)}")
    if new_rows:
        print(f"day range emitted: {new_rows[0]['day']} → {new_rows[-1]['day']}")
    print(f"output: {OUT_PATH}")

    # Print a compact today's-slice summary for the digest tail.
    print()
    print("Latest day per regime × field (Production % vs raw; negative = better):")
    latest_day = max((r["day"] for r in new_rows + list(_replay_recent())), default=None)
    if latest_day:
        recent = [r for r in _replay_recent() if r["day"] == latest_day]
        recent.sort(key=lambda r: (r["regime"], r["field"]))
        print(f"  === {latest_day} ===")
        print(f"  {'regime':<14} {'field':<5} {'n':>6} {'MAE raw':>9} {'MAE prod':>9} {'Δ%':>7}")
        for r in recent:
            print(f"  {r['regime']:<14} {r['field']:<5} {r['n_pairs']:>6,} "
                  f"{r['mae_raw']:>9.3f} {r['mae_prod']:>9.3f} "
                  f"{r['prod_pct_vs_raw']:>+7.2f}")


def _replay_recent():
    if not os.path.exists(OUT_PATH):
        return
    with open(OUT_PATH) as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


if __name__ == "__main__":
    main()

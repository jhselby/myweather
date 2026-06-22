"""
Stage 2 smoke test for station-cluster-disagreement hypothesis (#5 in backlog).

Question: does inter-cluster disagreement (Marblehead / Salem / Swampscott
PWS clusters disagreeing on temperature, humidity, wind) at a given tick
predict that-hour forecast |error| being higher than usual?

Data window: 2 days only (station_history.json carries a 48h rolling
window). This is NOT enough for a SHIP/HOLD verdict — it's a "concept
alive vs concept dead" smoke test before we instrument longer logging.

Method:
  1. Load station_history.json (per-station leave-one-out deltas, 48h).
  2. For each tick T, group stations by cluster prefix (KMAMARBL, KMASALEM,
     KMASWAMP). Compute median delta per cluster. Inter-cluster spread =
     std across cluster medians. Tick-level metric per field (t, h).
  3. Bin ticks into quartiles by spread.
  4. Stream pair log (only rows with obs_time inside the 2-day window).
  5. For each (field, lead_band), compare MAE in highest-spread quartile
     vs lowest-spread quartile.
  6. Verdict line: SMOKE_ALIVE if any (field, band) shows MAE in Q4 ≥1.2x
     MAE in Q1 AND n>=200 per quartile. SMOKE_DEAD otherwise.

Output: text summary to stdout + analysis/output/cluster_spread_smoketest.txt.

Caveats:
  - station_history.delta is leave-one-out from OVERALL consensus, so
    cluster-median is "cluster's offset from overall." Inter-cluster
    std is the right metric for "do clusters disagree."
  - 2-day window means quartiles have ~70 ticks each; sample size after
    pair-log join may be marginal for some fields.
  - This script is disposable. If smoke-alive, ship the persistent
    logger and re-audit at n=7+ days.
"""
import json
import math
import os
import sys
from collections import defaultdict
from statistics import median, pstdev

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
STATION_HISTORY_URL = "https://data.wymancove.com/station_history.json"

OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "cluster_spread_smoketest.txt")

CLUSTERS = ("KMAMARBL", "KMASALEM", "KMASWAMP")
FIELDS_TO_TEST = ("t", "h", "ws", "wg", "dp")
LEAD_BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]

DELTA_KEYS = {"t": "delta", "h": "h_delta", "p": "p_delta"}


def _cluster_of(sid):
    for c in CLUSTERS:
        if sid.startswith(c):
            return c
    return None


def _tick_key(ts_iso):
    return ts_iso[:16]


def build_spread_table(station_history, delta_key):
    """For each tick, compute inter-cluster spread on the given delta field.

    Returns dict[tick_key_str] -> spread (std across cluster medians) or None.
    """
    by_tick = defaultdict(lambda: defaultdict(list))
    for sid, readings in station_history.items():
        cluster = _cluster_of(sid)
        if not cluster:
            continue
        for r in readings:
            ts = r.get("ts")
            v = r.get(delta_key)
            if ts is None or v is None:
                continue
            by_tick[_tick_key(ts)][cluster].append(v)

    spread_by_tick = {}
    for tick, clusters in by_tick.items():
        medians = [median(vs) for vs in clusters.values() if vs]
        if len(medians) < 2:
            continue
        spread_by_tick[tick] = pstdev(medians)
    return spread_by_tick


def quartile_bins(values):
    if not values:
        return (None, None, None)
    s = sorted(values)
    n = len(s)
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    return (q1, median(s), q3)


def lead_band(lead_h):
    for label, lo, hi in LEAD_BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def main():
    print("=" * 72)
    print("CLUSTER-SPREAD SMOKE TEST (#5 in backlog)")
    print("=" * 72)

    print("\n[1/4] Loading station_history.json...")
    sh_path = cached_path(STATION_HISTORY_URL)
    with open(sh_path) as f:
        station_history = json.load(f)
    n_stations = sum(1 for sid in station_history if _cluster_of(sid))
    n_readings = sum(len(r) for sid, r in station_history.items() if _cluster_of(sid))
    print(f"  {n_stations} stations in 3 clusters, {n_readings} readings")

    # Build spread tables — use temp delta as primary; humidity as secondary.
    print("\n[2/4] Building inter-cluster spread tables...")
    spread_t = build_spread_table(station_history, "delta")
    spread_h = build_spread_table(station_history, "h_delta")
    print(f"  temp spread: {len(spread_t)} ticks. "
          f"humidity spread: {len(spread_h)} ticks.")

    if not spread_t:
        print("\nFATAL: no spread data. Aborting.")
        return 1

    # Quartile bands on temp spread (primary axis).
    q1_t, med_t, q3_t = quartile_bins(list(spread_t.values()))
    print(f"  temp spread quartiles: Q1≤{q1_t:.3f}, median={med_t:.3f}, "
          f"Q3≥{q3_t:.3f} °F")

    # Window bounds: pair log entries with obs_time in [min_tick, max_tick].
    ticks_sorted = sorted(spread_t.keys())
    min_tick, max_tick = ticks_sorted[0], ticks_sorted[-1]
    print(f"  window: {min_tick} → {max_tick}")

    print("\n[3/4] Streaming pair log, joining to spread bands...")
    pair_log_path = cached_path(PAIR_LOG_URL)

    # Aggregator: by (field, lead_band, quartile) → list of |error|
    agg = defaultdict(list)
    n_join = 0
    n_skip_window = 0
    n_skip_field = 0
    with open(pair_log_path) as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue
            obs_time = row.get("obs_time")
            if obs_time is None:
                continue
            tick = obs_time[:16]
            if tick < min_tick or tick > max_tick:
                n_skip_window += 1
                continue
            field = row.get("field")
            if field not in FIELDS_TO_TEST:
                n_skip_field += 1
                continue
            err = row.get("error")
            lead_h = row.get("lead_h")
            if err is None or lead_h is None:
                continue
            band = lead_band(lead_h)
            if band is None:
                continue
            # Find nearest tick in spread_t.
            spread = spread_t.get(tick)
            if spread is None:
                # tolerate +/- 10min
                for delta_min in (10, -10, 20, -20):
                    cand = _shift_tick(tick, delta_min)
                    if cand in spread_t:
                        spread = spread_t[cand]
                        break
            if spread is None:
                continue
            if spread <= q1_t:
                bin_label = "Q1_low"
            elif spread >= q3_t:
                bin_label = "Q4_high"
            else:
                continue
            agg[(field, band, bin_label)].append(abs(err))
            n_join += 1

    print(f"  joined: {n_join} pair rows. "
          f"skipped (window): {n_skip_window}. skipped (field): {n_skip_field}.")

    print("\n[4/4] Verdict per (field, lead_band):")
    print(f"  {'field':<5} {'band':<8} {'Q1_n':>6} {'Q1_mae':>8} "
          f"{'Q4_n':>6} {'Q4_mae':>8} {'ratio':>7} {'verdict':<14}")
    smoke_alive = False
    for field in FIELDS_TO_TEST:
        for band_label, _, _ in LEAD_BANDS:
            q1_errs = agg.get((field, band_label, "Q1_low"), [])
            q4_errs = agg.get((field, band_label, "Q4_high"), [])
            n1, n4 = len(q1_errs), len(q4_errs)
            if n1 < 50 or n4 < 50:
                verdict = "thin"
            else:
                mae1 = sum(q1_errs) / n1
                mae4 = sum(q4_errs) / n4
                ratio = mae4 / mae1 if mae1 > 0 else float("inf")
                if ratio >= 1.20 and n1 >= 200 and n4 >= 200:
                    verdict = "SMOKE_ALIVE"
                    smoke_alive = True
                elif ratio >= 1.10:
                    verdict = "hint"
                else:
                    verdict = "flat"
                print(f"  {field:<5} {band_label:<8} {n1:>6} {mae1:>8.3f} "
                      f"{n4:>6} {mae4:>8.3f} {ratio:>7.2f} {verdict:<14}")
                continue
            print(f"  {field:<5} {band_label:<8} {n1:>6} {'—':>8} "
                  f"{n4:>6} {'—':>8} {'—':>7} {verdict:<14}")

    print("\n" + "=" * 72)
    if smoke_alive:
        print("VERDICT: SMOKE_ALIVE — at least one (field, band) shows MAE in")
        print("highest-spread quartile ≥1.2x MAE in lowest-spread quartile.")
        print("Recommendation: ship persistent cluster_spread logger and")
        print("re-audit at n=7 days (~2026-06-27).")
    else:
        print("VERDICT: SMOKE_DEAD — no (field, band) shows ratio >= 1.2.")
        print("Recommendation: deprioritize cluster-spread axis. Revisit only")
        print("if other C1 axes (regime-synoptic, dP/dt) also come up empty.")
    print("=" * 72)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    # Caller can pipe the stdout into the file; keep this script's output
    # canonical at stdout for inline reading.
    return 0


def _shift_tick(tick_iso_min, delta_min):
    from datetime import datetime, timedelta
    dt = datetime.strptime(tick_iso_min, "%Y-%m-%dT%H:%M")
    return (dt + timedelta(minutes=delta_min)).strftime("%Y-%m-%dT%H:%M")


if __name__ == "__main__":
    sys.exit(main())

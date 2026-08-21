#!/usr/bin/env python3
"""L5_NBM solar biases — (regime × hour_local) cells, mirror of HRRR
`l5_recompute_biases_hourly.py`.

Reads the pair log, filters to sr rows carrying `forecast_l3_nbm`, and
writes a per (regime × hour_local) signed-bias table to
`weather_collector/data/lsr_nbm_bias_table_curated.json`.

Sign convention (mirrors HRRR L5 fitter):
    bias = forecast_l3_nbm - observed
    correction at apply time = -bias (see l5_nbm.py::l5_nbm_correction)

Retention 30 days. Min cell n = 30 (cells below floor fall back to
regime-overall mean; regimes with n<50 get a 0.0 fallback so we don't
apply noisy corrections from undersampled regimes). sr rows with
raw_solar (forecast_l1) below SUN_UP_THRESHOLD are ignored — no real
solar to correct at night.

Runtime:
    python3 -m analysis.l5_nbm_recompute_biases_hourly
    MYWEATHER_REFRESH=1 python3 -m analysis.l5_nbm_recompute_biases_hourly
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import pair_log_paths

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"  # kept for compat
OUT_PATH = Path(__file__).resolve().parent.parent / "weather_collector" / "data" / "lsr_nbm_bias_table_curated.json"

SUN_UP_THRESHOLD = 50.0
MIN_CELL_N = 30
RETENTION_DAYS = 30
REGIMES = ["frontal", "sw_flow", "pre_frontal", "sea_breeze",
           "nw_flow", "calm", "se_flow", "ne_flow"]


def fit():
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    cutoff = (now - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")

    by_cell = defaultdict(list)     # (regime, hour) → [errors]
    by_regime = defaultdict(list)   # regime → [errors]
    n_in = 0
    n_solar = 0
    n_kept = 0

    for path in pair_log_paths():
        with open(path) as fin:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                n_in += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("field") != "sr":
                    continue
                n_solar += 1
                obs_time = row.get("obs_time", "")
                if obs_time < cutoff:
                    continue
                lead_h = row.get("lead_h")
                if lead_h is None or lead_h < 1 or lead_h >= 48:
                    continue
                l3_nbm = row.get("forecast_l3_nbm")
                obs = row.get("observed")
                raw = row.get("forecast_l1")  # sun-up gate off HRRR raw
                if l3_nbm is None or obs is None or raw is None:
                    continue
                if raw < SUN_UP_THRESHOLD:
                    continue
                state_obs = row.get("state_obs") or {}
                regime = state_obs.get("regime_synoptic")
                if regime is None:
                    continue
                if len(obs_time) < 13:
                    continue
                try:
                    hour = int(obs_time[11:13])
                except ValueError:
                    continue
                err = l3_nbm - obs
                by_cell[(regime, hour)].append(err)
                by_regime[regime].append(err)
                n_kept += 1

    lookup = {}
    fallbacks = {}
    for regime in REGIMES:
        regime_vals = by_regime.get(regime, [])
        if len(regime_vals) >= 50:
            fallbacks[regime] = round(sum(regime_vals) / len(regime_vals), 2)
        else:
            fallbacks[regime] = 0.0
        cells = {}
        for hour in range(24):
            v = by_cell.get((regime, hour), [])
            if len(v) >= MIN_CELL_N:
                cells[str(hour)] = round(sum(v) / len(v), 2)
        lookup[regime] = cells

    output = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M"),
        "n_pairs": n_kept,
        "retention_days": RETENTION_DAYS,
        "min_cell_n": MIN_CELL_N,
        "sun_up_threshold": SUN_UP_THRESHOLD,
        "skip_regimes": [],
        "bias_by_regime_hour": lookup,
        "fallback_by_regime": fallbacks,
    }
    with open(OUT_PATH, "w") as fout:
        json.dump(output, fout, separators=(",", ":"))
        fout.write("\n")

    print(f"l5_nbm_recompute_biases_hourly: scanned {n_in:,} rows, "
          f"{n_solar:,} sr rows, {n_kept:,} usable daytime with regime "
          f"(cutoff {cutoff})")
    for regime in REGIMES:
        n = len(by_regime.get(regime, []))
        filled = len(lookup.get(regime, {}))
        fb = fallbacks.get(regime, 0.0)
        print(f"  {regime:<14} n={n:<5} filled_hours={filled:<3} fallback={fb:+.2f} W/m²")
    print(f"  wrote {OUT_PATH}")


if __name__ == "__main__":
    fit()

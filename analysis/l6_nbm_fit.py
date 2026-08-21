#!/usr/bin/env python3
"""L6_NBM cove correction fit (option-1 Phase 7, 2026-08-21).

Mirrors HRRR's L6 (`cove_correction.py`) fit shape on the NBM cascade.
Scaffold-only today: L6_NBM is shipped with `ENABLED=False`, so this
fit runs to warm the curated table stub but the apply-time module
ignores the table until the enablement gate opens.

Reads the pair log, filters to t rows carrying `error_l3_nbm` (t is
the only L6_NBM_FIELD; t skips L4_NBM and L5_NBM on the NBM cascade
just as it skips L4/L5 on HRRR), and writes recency-weighted signed
means to `weather_collector/data/l6_nbm_cove_curated.json`:

  - `delta_by_octant[True|False][octant]`: mean Δ per (sb_active, octant)
  - `hour_delta_sb_off[hour_local]`: mean Δ per hour when sb_off

Same schema as `cove_correction._DELTA_BY_OCTANT` / `_HOUR_DELTA_SB_OFF`
so the enablement path is a lookup-table substitution, not a schema
migration.

Sign convention: `error = forecast - observed`, correction returned in
the table = `-mean(error)`, apply as `l6_nbm = l3_nbm + delta`.

Runtime:
    python3 -m analysis.l6_nbm_fit
    MYWEATHER_REFRESH=1 python3 -m analysis.l6_nbm_fit
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path, pair_log_paths

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_PATH = Path(__file__).resolve().parent.parent / "weather_collector" / "data" / "l6_nbm_cove_curated.json"

FIELD = "t"
TAU_DAYS = 14
RETENTION_DAYS = 30
MIN_PAIRS_PER_BIN = 20

_OCTANTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _octant(wind_dir_deg):
    if wind_dir_deg is None:
        return None
    return _OCTANTS[int((wind_dir_deg + 22.5) % 360 / 45)]


def _hour_local(valid_time):
    if not isinstance(valid_time, str) or len(valid_time) < 13:
        return None
    try:
        return int(valid_time[11:13])
    except (ValueError, TypeError):
        return None


def fit():
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    cutoff = (now - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")

    oct_sums = defaultdict(float)   # (sb_active, octant) → Σ err·w
    oct_wts = defaultdict(float)
    oct_ns = defaultdict(int)

    hr_sums = defaultdict(float)    # hour_local → Σ err·w  (sb_off only)
    hr_wts = defaultdict(float)
    hr_ns = defaultdict(int)

    n_in = 0
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
                if row.get("field") != FIELD:
                    continue
                obs_time = row.get("obs_time", "")
                if obs_time < cutoff:
                    continue
                try:
                    obs_dt = datetime.strptime(obs_time, "%Y-%m-%dT%H:%M")
                except ValueError:
                    continue
                err = row.get("error_l3_nbm")
                if err is None:
                    continue
                wd = row.get("wd_forecast")
                oct_ = _octant(wd)
                if oct_ is None:
                    continue
                hod = _hour_local(row.get("valid_time") or obs_time)
                if hod is None:
                    continue
                sb_active = bool(row.get("sb_active"))
                age_days = max(0.0, (now - obs_dt).total_seconds() / 86400.0)
                w = math.exp(-age_days / TAU_DAYS)
                oct_sums[(sb_active, oct_)] += float(err) * w
                oct_wts[(sb_active, oct_)] += w
                oct_ns[(sb_active, oct_)] += 1
                if not sb_active:
                    hr_sums[hod] += float(err) * w
                    hr_wts[hod] += w
                    hr_ns[hod] += 1
                n_kept += 1

    delta_by_octant = {"true": {}, "false": {}}
    for (sb, oct_), n in oct_ns.items():
        if n < MIN_PAIRS_PER_BIN:
            continue
        w = oct_wts[(sb, oct_)]
        if w <= 0:
            continue
        delta_by_octant["true" if sb else "false"][oct_] = round(-oct_sums[(sb, oct_)] / w, 2)

    hour_delta_sb_off = {}
    for h, n in hr_ns.items():
        if n < MIN_PAIRS_PER_BIN:
            continue
        w = hr_wts[h]
        if w <= 0:
            continue
        hour_delta_sb_off[str(h)] = round(-hr_sums[h] / w, 2)

    output = {
        "fitted_at": now.strftime("%Y-%m-%dT%H:%M"),
        "n_pairs": n_kept,
        "retention_days": RETENTION_DAYS,
        "weighting": {"method": "exponential_decay", "tau_days": TAU_DAYS},
        "min_pairs_per_bin": MIN_PAIRS_PER_BIN,
        "fields_covered": [FIELD],
        "delta_by_octant": delta_by_octant,
        "hour_delta_sb_off": hour_delta_sb_off,
    }
    with open(OUT_PATH, "w") as fout:
        json.dump(output, fout, separators=(",", ":"))
        fout.write("\n")

    print(f"l6_nbm_fit: scanned {n_in:,} rows, kept {n_kept:,} t rows in window "
          f"(cutoff {cutoff})")
    print(f"  delta_by_octant sb_active: {delta_by_octant['true']}")
    print(f"  delta_by_octant sb_off:    {delta_by_octant['false']}")
    print(f"  hour_delta_sb_off:         {hour_delta_sb_off}")
    print(f"  wrote {OUT_PATH}")


if __name__ == "__main__":
    fit()

#!/usr/bin/env python3
"""L4_NBM per-hour-of-day diurnal residual fit (option-1 Phase 5, 2026-08-21).

Reads the pair log, filters to rows carrying `error_l3_nbm` for the two
L4_NBM_FIELDS (cc, ch), and writes a per-hour-of-day recency-weighted
signed-residual table to `weather_collector/data/l4_nbm_curated.json`.

Sign convention (mirrors decay_fit.py L4 branch): `error = forecast -
observed`, so the correction applied at forecast time is
`l4_nbm = l3_nbm - correction`.

Scope mirrors HRRR's `L4_FIELDS = {"cc", "ch"}` — the two fields where
the HRRR-side diurnal L4 has earned its way in. Recency weighting matches
L3_NBM / decay_fit: `w = exp(-age_days / TAU_DAYS)` with TAU_DAYS=14.
Retention 30 days. Per-hour-of-day bin fit only publishes when
n_samples ≥ MIN_PAIRS_PER_BIN (default 20); thinner bins stay null and
`l4_nbm.py` falls through to identity at apply time.

Runtime:
    python3 -m analysis.l4_nbm_fit
    MYWEATHER_REFRESH=1 python3 -m analysis.l4_nbm_fit  # force re-download
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import pair_log_paths

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"  # kept for compat
OUT_PATH = Path(__file__).resolve().parent.parent / "weather_collector" / "data" / "l4_nbm_curated.json"

FIELDS = ("cc", "ch")
HOD_BINS = 24
TAU_DAYS = 14
RETENTION_DAYS = 30
MIN_PAIRS_PER_BIN = 20


def _hod_from_valid(valid_time):
    if not isinstance(valid_time, str) or len(valid_time) < 13:
        return None
    try:
        return int(valid_time[11:13])
    except (ValueError, TypeError):
        return None


def fit():
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    cutoff = (now - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")

    sums = defaultdict(float)     # key (field, hod) → Σ err·w
    weights = defaultdict(float)  # key (field, hod) → Σ w
    counts = defaultdict(int)     # key (field, hod) → n
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
                field = row.get("field")
                if field not in FIELDS:
                    continue
                obs_time = row.get("obs_time", "")
                if obs_time < cutoff:
                    continue
                try:
                    obs_dt = datetime.strptime(obs_time, "%Y-%m-%dT%H:%M")
                except ValueError:
                    continue
                hod = _hod_from_valid(row.get("valid_time") or obs_time)
                if hod is None:
                    continue
                err = row.get("error_l3_nbm")
                if err is None:
                    continue
                age_days = max(0.0, (now - obs_dt).total_seconds() / 86400.0)
                w = math.exp(-age_days / TAU_DAYS)
                sums[(field, hod)] += float(err) * w
                weights[(field, hod)] += w
                counts[(field, hod)] += 1
                n_kept += 1

    corrections = {}
    n_samples = {}
    total_published = 0
    for f in FIELDS:
        c_arr = [None] * HOD_BINS
        n_arr = [0] * HOD_BINS
        for h in range(HOD_BINS):
            n = counts.get((f, h), 0)
            n_arr[h] = n
            w = weights.get((f, h), 0.0)
            if n >= MIN_PAIRS_PER_BIN and w > 0:
                c_arr[h] = round(sums[(f, h)] / w, 3)
                total_published += 1
        corrections[f] = c_arr
        n_samples[f] = n_arr

    output = {
        "fitted_at": now.strftime("%Y-%m-%dT%H:%M"),
        "n_pairs": n_kept,
        "retention_days": RETENTION_DAYS,
        "weighting": {"method": "exponential_decay", "tau_days": TAU_DAYS},
        "min_pairs_per_bin": MIN_PAIRS_PER_BIN,
        "fields_covered": list(FIELDS),
        "corrections": corrections,
        "n_samples": n_samples,
    }
    with open(OUT_PATH, "w") as fout:
        json.dump(output, fout, separators=(",", ":"))
        fout.write("\n")

    print(f"l4_nbm_fit: scanned {n_in:,} rows, kept {n_kept:,} in window "
          f"(cutoff {cutoff})")
    print(f"  published {total_published}/{len(FIELDS) * HOD_BINS} "
          f"(field, hod) cells (n≥{MIN_PAIRS_PER_BIN})")
    for f in FIELDS:
        filled = sum(1 for c in corrections[f] if c is not None)
        pairs = sum(n_samples[f])
        print(f"    {f}: {filled}/{HOD_BINS} bins filled, {pairs:,} pairs")
    print(f"  wrote {OUT_PATH}")


if __name__ == "__main__":
    fit()

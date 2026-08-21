#!/usr/bin/env python3
"""L3_NBM per-lead bias fit (option-1 Phase 3, 2026-08-19).

Reads the pair log, filters to rows carrying `error_l2_nbm` for the four
scalar L3_NBM fields (t / ws / wg / h), and writes a per-lead recency-
weighted signed-bias table to
`weather_collector/data/l3_nbm_curated.json`.

Sign convention (mirrors decay_fit.py): `error = forecast - observed`, so
the correction applied at forecast time is `l3_nbm = l2_nbm - bias`.

Recency weighting matches decay_fit: `w = exp(-age_days / TAU_DAYS)` with
TAU_DAYS=14. Retention 30 days. Per-lead bin fit only publishes when
n_samples ≥ MIN_PAIRS_PER_LEAD (default 20); thinner bins stay null and
`l3_nbm.py` falls through to identity at apply time.

wd excluded from scope: fitting a circular residual with linear per-lead
mean produces wraparound-polluted corrections. HRRR-side wd is fitted via
sin/cos components (`wd_components` in decay_corrections.json) but is not
in HRRR's L3_FIELDS whitelist either. Deferred until we decide L3_NBM wd
is worth the sin/cos plumbing.

Runtime:
    python3 -m analysis.l3_nbm_fit
    MYWEATHER_REFRESH=1 python3 -m analysis.l3_nbm_fit  # force re-download
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
OUT_PATH = Path(__file__).resolve().parent.parent / "weather_collector" / "data" / "l3_nbm_curated.json"

FIELDS = ("t", "ws", "wg", "h", "ch", "sr", "dp", "cc")
WD_FIELD = "wd"  # fit via sin/cos components; separate branch, same weighting.
LEAD_BINS = 48
TAU_DAYS = 14
RETENTION_DAYS = 30
MIN_PAIRS_PER_LEAD = 20


def _round_for(field, v):
    """Same rounding conventions as forecast_snapshot._round_for for the fit
    output — keeps the curated JSON diff readable and mirrors runtime precision."""
    if field == "t":  return round(v, 2)
    if field == "h":  return round(v, 1)
    if field == "ws": return round(v, 2)
    if field == "wg": return round(v, 2)
    return round(v, 3)


def fit():
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    cutoff = (now - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")

    sums = defaultdict(float)     # key (field, lead_h) → Σ err·w
    weights = defaultdict(float)  # key (field, lead_h) → Σ w
    counts = defaultdict(int)     # key (field, lead_h) → n (unweighted, for gating)
    # wd fit is circular; accumulate sin/cos residuals of the l2_nbm forecast
    # vs obs (both in radians, populated by forecast_error_log's wd branch).
    # Applied at forecast time via atan2 of the sin/cos-corrected pair.
    wd_sin_sums    = defaultdict(float)  # key lead_h → Σ err_sin·w
    wd_cos_sums    = defaultdict(float)
    wd_sin_weights = defaultdict(float)
    wd_cos_weights = defaultdict(float)
    wd_counts      = defaultdict(int)
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
                if field not in FIELDS and field != WD_FIELD:
                    continue
                lead_h = row.get("lead_h")
                if lead_h is None or not (0 <= lead_h < LEAD_BINS):
                    continue
                obs_time = row.get("obs_time", "")
                if obs_time < cutoff:
                    continue
                try:
                    obs_dt = datetime.strptime(obs_time, "%Y-%m-%dT%H:%M")
                except ValueError:
                    continue
                age_days = max(0.0, (now - obs_dt).total_seconds() / 86400.0)
                w = math.exp(-age_days / TAU_DAYS)
                if field == WD_FIELD:
                    e_sin = row.get("error_sin_l2_nbm")
                    e_cos = row.get("error_cos_l2_nbm")
                    if e_sin is None or e_cos is None:
                        continue
                    wd_sin_sums[lead_h]    += float(e_sin) * w
                    wd_cos_sums[lead_h]    += float(e_cos) * w
                    wd_sin_weights[lead_h] += w
                    wd_cos_weights[lead_h] += w
                    wd_counts[lead_h]      += 1
                    n_kept += 1
                    continue
                err = row.get("error_l2_nbm")
                if err is None:
                    continue
                sums[(field, lead_h)] += float(err) * w
                weights[(field, lead_h)] += w
                counts[(field, lead_h)] += 1
                n_kept += 1

    corrections = {}
    n_samples = {}
    total_published = 0
    for f in FIELDS:
        c_arr = [None] * LEAD_BINS
        n_arr = [0] * LEAD_BINS
        for h in range(LEAD_BINS):
            n = counts.get((f, h), 0)
            n_arr[h] = n
            w = weights.get((f, h), 0.0)
            if n >= MIN_PAIRS_PER_LEAD and w > 0:
                c_arr[h] = _round_for(f, sums[(f, h)] / w)
                total_published += 1
        corrections[f] = c_arr
        n_samples[f] = n_arr

    # wd: emit per-lead sin/cos correction arrays. Apply step uses them as
    # corrected_sin = sin(l2_nbm_rad) − sin_corr; same for cos; then
    # atan2(corrected_sin, corrected_cos) recovers the corrected angle.
    wd_sin = [None] * LEAD_BINS
    wd_cos = [None] * LEAD_BINS
    wd_n   = [0] * LEAD_BINS
    wd_published = 0
    for h in range(LEAD_BINS):
        n = wd_counts.get(h, 0)
        wd_n[h] = n
        if n >= MIN_PAIRS_PER_LEAD:
            ws_ = wd_sin_weights.get(h, 0.0)
            wc_ = wd_cos_weights.get(h, 0.0)
            if ws_ > 0 and wc_ > 0:
                wd_sin[h] = round(wd_sin_sums[h] / ws_, 5)
                wd_cos[h] = round(wd_cos_sums[h] / wc_, 5)
                wd_published += 1
    corrections["wd_components"] = {"sin": wd_sin, "cos": wd_cos}
    n_samples["wd"] = wd_n

    output = {
        "fitted_at": now.strftime("%Y-%m-%dT%H:%M"),
        "n_pairs": n_kept,
        "retention_days": RETENTION_DAYS,
        "weighting": {"method": "exponential_decay", "tau_days": TAU_DAYS},
        "min_pairs_per_lead": MIN_PAIRS_PER_LEAD,
        "fields_covered": list(FIELDS) + [WD_FIELD],
        "corrections": corrections,
        "n_samples": n_samples,
    }
    with open(OUT_PATH, "w") as fout:
        json.dump(output, fout, separators=(",", ":"))
        fout.write("\n")

    print(f"l3_nbm_fit: scanned {n_in:,} rows, kept {n_kept:,} in window "
          f"(cutoff {cutoff})")
    print(f"  published {total_published}/{len(FIELDS) * LEAD_BINS} "
          f"scalar (field, lead) cells (n≥{MIN_PAIRS_PER_LEAD})")
    for f in FIELDS:
        filled = sum(1 for c in corrections[f] if c is not None)
        pairs = sum(n_samples[f])
        print(f"    {f}: {filled}/{LEAD_BINS} leads filled, {pairs:,} pairs")
    wd_pairs = sum(n_samples["wd"])
    print(f"    wd: {wd_published}/{LEAD_BINS} lead sin/cos pairs filled, {wd_pairs:,} pairs")
    print(f"  wrote {OUT_PATH}")


if __name__ == "__main__":
    fit()

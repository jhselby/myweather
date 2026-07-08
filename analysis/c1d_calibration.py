"""
C1d confidence-layer calibration — Stage 1 marginal (standalone).

Follows the v1 pattern in c1_confidence_calibration.py. C1d is the KBOS-vs-KBVY
cloud disagreement axis, promoted 2026-06-29 by h_cloud_disagreement_orthogonality.py
(10 orthogonal cells vs C1a + C1e).

Kept separate from the multi-axis v2 join to avoid cell-dilution — see the
Stage 4 audit (2026-07-08) which reports the multi-axis table INSUFFICIENT
across all 951 cells; adding C1d to the join would delay clean per-cell
verdicts by weeks. This script emits a marginal premium that
`confidence_layer.py` can apply on top of the legacy transition premium.

Axis:
    σ ∈ {high, low}   using the data's own Q1/Q3 cuts on cloud_inter_source_sigma
    Middle quartiles (Q1 < σ < Q3) are dropped for a clean HIGH-vs-LOW contrast
    (same choice as h_cloud_disagreement_orthogonality.py).
    Fields covered:  cc, cl, cm, ch
    Bands covered:   0-5h, 6-11h, 12-23h, 24-47h

Output:
    - Text table per (field, band): low_mae, high_mae, premium
    - analysis/output/c1d_confidence_premium.json — feeds curate step

Run:
    python3 analysis/c1d_calibration.py
    MYWEATHER_REFRESH=1 python3 analysis/c1d_calibration.py
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis._cache import cached_path


PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"

FIELDS = ("cc", "cl", "cm", "ch")

BANDS = [
    ("0-5h",   0, 6),
    ("6-11h",  6, 12),
    ("12-23h", 12, 24),
    ("24-47h", 24, 48),
]

TEST_DAYS = 14
MIN_N = 100
MIN_SIGMA_SAMPLES = 5000  # matches h_cloud_disagreement_orthogonality gate

OUTPUT_JSON = os.path.join(os.path.dirname(__file__), "output", "c1d_confidence_premium.json")


def _band_for_lead(lead_h):
    if lead_h is None:
        return None
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def measure_premium():
    """Two-pass over the pair log. Pass 1 computes the Q1/Q3 σ cuts from
    cloud_inter_source_sigma within the test window. Pass 2 aggregates |err|
    per (field, band, sigma_HIGH) using forecast_l4 as the user-facing value.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TEST_DAYS)).strftime("%Y-%m-%dT%H:%M")
    path = cached_path(PAIR_LOG_URL)

    sigmas = []
    pairs_seen = 0
    with open(path) as f:
        for line in f:
            if not line:
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            ot = p.get("obs_time") or ""
            if ot < cutoff:
                continue
            pairs_seen += 1
            if p.get("field") not in FIELDS:
                continue
            s = p.get("cloud_inter_source_sigma")
            if s is None:
                continue
            sigmas.append(float(s))

    if len(sigmas) < MIN_SIGMA_SAMPLES:
        print(f"  ⚠ Only {len(sigmas):,} rows with cloud_inter_source_sigma "
              f"(need ≥{MIN_SIGMA_SAMPLES:,}). Aborting; try again as pair log fills.")
        return None, pairs_seen, 0

    s_sorted = sorted(sigmas)
    q1 = s_sorted[len(s_sorted) // 4]
    q3 = s_sorted[(3 * len(s_sorted)) // 4]
    print(f"  σ distribution: n={len(sigmas):,}, Q1≤{q1:.2f}, median={median(s_sorted):.2f}, Q3≥{q3:.2f}")

    accs = defaultdict(lambda: [0.0, 0])
    pairs_used = 0
    with open(path) as f:
        for line in f:
            if not line:
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            ot = p.get("obs_time") or ""
            if ot < cutoff:
                continue
            field = p.get("field")
            if field not in FIELDS:
                continue
            sigma = p.get("cloud_inter_source_sigma")
            if sigma is None:
                continue
            sigma = float(sigma)
            if q1 < sigma < q3:
                continue
            sigma_high = sigma >= q3

            lead = p.get("lead_h")
            band = _band_for_lead(lead)
            if band is None:
                continue

            obs = p.get("observed")
            fc = (p.get("forecast_l4") or p.get("forecast_l3")
                  or p.get("forecast_l2") or p.get("forecast_l1")
                  or p.get("forecast"))
            if obs is None or fc is None:
                continue

            accs[(field, band, sigma_high)][0] += abs(fc - obs)
            accs[(field, band, sigma_high)][1] += 1
            pairs_used += 1

    cells = {}
    for (field, band, sigma_high), (sum_err, n) in accs.items():
        slot = "high" if sigma_high else "low"
        cells.setdefault(field, {}).setdefault(band, {})[slot] = {
            "mae": sum_err / n if n else None,
            "n":   n,
        }

    out = {}
    for field, bands in cells.items():
        out[field] = {}
        for band, halves in bands.items():
            low = halves.get("low")
            high = halves.get("high")
            if (low is None or high is None
                    or low["n"] < MIN_N or high["n"] < MIN_N
                    or low["mae"] is None or high["mae"] is None):
                continue
            premium_abs = high["mae"] - low["mae"]
            premium_pct = 100 * premium_abs / low["mae"] if low["mae"] else None
            out[field][band] = {
                "low_mae":     round(low["mae"], 4),
                "high_mae":    round(high["mae"], 4),
                "premium_abs": round(premium_abs, 4),
                "premium_pct": round(premium_pct, 2) if premium_pct is not None else None,
                "n_low":       low["n"],
                "n_high":      high["n"],
                "sigma_q1":    round(q1, 4),
                "sigma_q3":    round(q3, 4),
            }
    return out, pairs_seen, pairs_used


def main():
    print(f"C1d confidence calibration · {TEST_DAYS}-day window · min_n={MIN_N}")
    print("=" * 88)
    result = measure_premium()
    cells, seen, used = result
    print(f"Pairs scanned: {seen:,}   used: {used:,}")
    if cells is None:
        return
    print()

    field_order = [f for f in FIELDS if f in cells]
    print(f"{'field':<6} {'band':<8} {'low':>10} {'high':>10} {'premium':>10} {'premium%':>10}  {'n_low':>8} / {'n_high':>8}")
    print("-" * 88)
    for field in field_order:
        for band, _, _ in BANDS:
            c = cells.get(field, {}).get(band)
            if c is None:
                continue
            print(f"{field:<6} {band:<8} {c['low_mae']:>10.4f} {c['high_mae']:>10.4f} "
                  f"{c['premium_abs']:>+10.4f} {c['premium_pct']:>+9.2f}%  "
                  f"{c['n_low']:>8,} / {c['n_high']:>8,}")
        print()

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "test_days": TEST_DAYS,
            "min_n": MIN_N,
            "cells": cells,
        }, f, indent=2)
    print(f"Wrote {OUTPUT_JSON}")


if __name__ == "__main__":
    main()

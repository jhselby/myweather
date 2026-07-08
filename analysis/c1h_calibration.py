"""
C1h confidence-layer calibration — Stage 1 marginal (standalone).

Follows the v1 pattern in c1_confidence_calibration.py. C1h fires when the
forecast has moved by more than a per-field threshold across the last 6h:

    H = |fc[lead] − fc[lead-6]| > THRESH[field]

Promoted 2026-07-08 by h_c1h_orthogonality.py (9 orthogonal cells vs C1f + C1e).
Kept separate from the multi-axis v2 join to avoid cell-dilution — see the
Stage 4 audit (2026-07-08) which reports the multi-axis table INSUFFICIENT
across all 951 cells; adding C1h to the join would delay clean per-cell
verdicts by weeks. This script emits a marginal premium that
`confidence_layer.py` can apply on top of the legacy transition premium.

Axis:
    H ∈ {fires, flat}   fires = |Δ fc over 6h| exceeds field threshold
    Thresholds mirror h_trend_direction.py / h_c1h_orthogonality.py:
        cc 20, cl 15, cm 15, ch 15, t 3
    Fields covered:  cc, cl, cm, ch, t
    Bands covered:   6-11h, 12-23h, 24-47h  (0-5h has no in-run L−6 predecessor)

Output:
    - Text table per (field, band): flat_mae, fires_mae, premium
    - analysis/output/c1h_confidence_premium.json — feeds curate step

Run:
    python3 analysis/c1h_calibration.py
    MYWEATHER_REFRESH=1 python3 analysis/c1h_calibration.py
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis._cache import cached_path


PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"

FIELDS = ("cc", "cl", "cm", "ch", "t")
THRESH = {"cc": 20, "cl": 15, "cm": 15, "ch": 15, "t": 3}

BANDS = [
    ("6-11h",  6, 12),
    ("12-23h", 12, 24),
    ("24-47h", 24, 48),
]

TEST_DAYS = 14
MIN_N = 100

OUTPUT_JSON = os.path.join(os.path.dirname(__file__), "output", "c1h_confidence_premium.json")


def _band_for_lead(lead_h):
    if lead_h is None:
        return None
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def measure_premium():
    """Two-pass over the pair log. Pass 1 indexes forecast_l1 by
    (run_time, field, lead) so we can look up the L−6 predecessor. Pass 2
    accumulates |err| per (field, band, H) using forecast_l4 (or the best
    downstream value) as the user-facing forecast.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TEST_DAYS)).strftime("%Y-%m-%dT%H:%M")
    path = cached_path(PAIR_LOG_URL)

    fc_l1_by_key = {}
    rows = []
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

            field = p.get("field")
            if field not in FIELDS:
                continue
            lead = p.get("lead_h")
            rt = p.get("run_time")
            fc_l1 = p.get("forecast_l1")
            if lead is None or rt is None or fc_l1 is None:
                continue
            try:
                lead = int(lead)
            except (TypeError, ValueError):
                continue
            fc_l1_by_key[(rt, field, lead)] = fc_l1

            band = _band_for_lead(lead)
            if band is None:
                continue

            obs = p.get("observed")
            fc = (p.get("forecast_l4") or p.get("forecast_l3")
                  or p.get("forecast_l2") or p.get("forecast_l1")
                  or p.get("forecast"))
            if obs is None or fc is None:
                continue

            rows.append((field, band, rt, lead, fc, abs(fc - obs)))

    accs = defaultdict(lambda: [0.0, 0])
    pairs_used = 0
    pairs_missing_prev = 0
    for (field, band, rt, lead, fc_l, err_abs) in rows:
        prev = fc_l1_by_key.get((rt, field, lead - 6))
        if prev is None:
            pairs_missing_prev += 1
            continue
        thr = THRESH[field]
        fires = abs(fc_l - prev) > thr
        accs[(field, band, fires)][0] += err_abs
        accs[(field, band, fires)][1] += 1
        pairs_used += 1

    cells = {}
    for (field, band, fires), (sum_err, n) in accs.items():
        slot = "fires" if fires else "flat"
        cells.setdefault(field, {}).setdefault(band, {})[slot] = {
            "mae": sum_err / n if n else None,
            "n":   n,
        }

    out = {}
    for field, bands in cells.items():
        out[field] = {}
        for band, halves in bands.items():
            flat = halves.get("flat")
            fires = halves.get("fires")
            if (flat is None or fires is None
                    or flat["n"] < MIN_N or fires["n"] < MIN_N
                    or flat["mae"] is None or fires["mae"] is None):
                continue
            premium_abs = fires["mae"] - flat["mae"]
            premium_pct = 100 * premium_abs / flat["mae"] if flat["mae"] else None
            out[field][band] = {
                "flat_mae":     round(flat["mae"], 4),
                "fires_mae":    round(fires["mae"], 4),
                "premium_abs":  round(premium_abs, 4),
                "premium_pct":  round(premium_pct, 2) if premium_pct is not None else None,
                "n_flat":       flat["n"],
                "n_fires":      fires["n"],
                "threshold":    THRESH[field],
            }
    return out, pairs_seen, pairs_used, pairs_missing_prev


def main():
    print(f"C1h confidence calibration · {TEST_DAYS}-day window · min_n={MIN_N}")
    print(f"Thresholds: {THRESH}")
    print("=" * 88)
    cells, seen, used, no_prev = measure_premium()
    print(f"Pairs scanned: {seen:,}   used: {used:,}   dropped (no L−6): {no_prev:,}")
    print()

    field_order = [f for f in FIELDS if f in cells]
    print(f"{'field':<6} {'band':<8} {'flat':>10} {'fires':>10} {'premium':>10} {'premium%':>10}  {'n_flat':>8} / {'n_fires':>8}")
    print("-" * 88)
    for field in field_order:
        for band, _, _ in BANDS:
            c = cells.get(field, {}).get(band)
            if c is None:
                continue
            print(f"{field:<6} {band:<8} {c['flat_mae']:>10.4f} {c['fires_mae']:>10.4f} "
                  f"{c['premium_abs']:>+10.4f} {c['premium_pct']:>+9.2f}%  "
                  f"{c['n_flat']:>8,} / {c['n_fires']:>8,}")
        print()

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "test_days": TEST_DAYS,
            "min_n": MIN_N,
            "thresholds": THRESH,
            "cells": cells,
        }, f, indent=2)
    print(f"Wrote {OUTPUT_JSON}")


if __name__ == "__main__":
    main()

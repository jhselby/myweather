"""
C1 confidence-layer calibration — Stage 1 manual analysis.

Per the hypothesis promotion pipeline ([[feedback-hypothesis-promotion-pipeline]]):
this is the Stage 1 manual analysis for C1 framed as a confidence-widening
layer (not a bias-correction layer). The earlier bias-correction C1 path was
ruled out 2026-06-19 — every formulation of regime_bias and l1_fallback
either regressed or barely cleared zero across leakage-free per-cutoff tests.

Premise: the regime-transition signal IS real (R6 audit confirmed +10-85%
transition penalty across multiple fields/bands) but is uncorrectable by
point-estimate subtraction. The honest response is to widen the displayed
uncertainty on transition hours rather than try to move the forecast value.

What this script measures: for each (field, lead_band), the MAE on stable
pairs (state_fc.regime_synoptic == state_obs.regime_synoptic) vs transition
pairs (rfc != rob). The DELTA is the "transition uncertainty premium" — the
calibration target for an C1 confidence-widening lookup table.

Output:
  - Text table: per (field, band) stable_mae, transition_mae, premium, n
  - JSON file at analysis/output/c1_confidence_premium.json — feeds the
    eventual `confidence_layer.py` processor when it's built

Run:
  python3 analysis/c1_confidence_calibration.py
  MYWEATHER_REFRESH=1 python3 analysis/c1_confidence_calibration.py  # force fresh cache
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# Path bootstrapping so `python3 analysis/c1_confidence_calibration.py` runs
# without -m. Mirrors the pattern in other analysis/ scripts.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis._cache import cached_path


PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"

# Lead bands match the R6 audit + walk-forward validator buckets.
BANDS = [
    ("0-5h",   0, 6),
    ("6-11h",  6, 12),
    ("12-23h", 12, 24),
    ("24-47h", 24, 48),
]
# Test window — how much recent pair data to include. 14d is the sweet spot:
# enough sample per (field, band) cell to get stable estimates, recent enough
# that the bias structure hasn't drifted.
TEST_DAYS = 14

# Cells with fewer than this many samples are dropped — the premium estimate
# becomes noise below ~100 pairs. Tighter than the 30-sample threshold used
# in the regime_bias work because here a noisy premium directly miscalibrates
# user-facing confidence bands.
MIN_N = 100

OUTPUT_JSON = os.path.join(os.path.dirname(__file__), "output", "c1_confidence_premium.json")


def _band_for_lead(lead_h):
    if lead_h is None:
        return None
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def measure_premium():
    """Stream the cached pair log; accumulate (field, band, is_transition)
    stats; return the calibration table.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TEST_DAYS)).strftime("%Y-%m-%dT%H:%M")
    # (field, band, is_transition) -> [sum_abs_err, n]
    accs = defaultdict(lambda: [0.0, 0])

    path = cached_path(PAIR_LOG_URL)
    pairs_seen = 0
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
            pairs_seen += 1

            field = p.get("field")
            obs = p.get("observed")
            lead = p.get("lead_h")
            if field is None or obs is None or lead is None:
                continue
            band = _band_for_lead(lead)
            if band is None:
                continue

            sfc = p.get("state_fc") or {}
            sob = p.get("state_obs") or {}
            rfc = sfc.get("regime_synoptic")
            rob = sob.get("regime_synoptic")
            if not rfc or not rob:
                continue

            # Use forecast_l4 if present (post-full-stack value) else fall back
            # through the layer chain. This is the value the user actually sees.
            fc = (p.get("forecast_l4") or p.get("forecast_l3")
                  or p.get("forecast_l2") or p.get("forecast_l1")
                  or p.get("forecast"))
            if fc is None:
                continue

            is_transition = (rfc != rob)
            key = (field, band, is_transition)
            accs[key][0] += abs(fc - obs)
            accs[key][1] += 1
            pairs_used += 1

    # Build per-(field, band) calibration entries.
    cells = {}
    for (field, band, is_trans), (sum_err, n) in accs.items():
        cells.setdefault(field, {}).setdefault(band, {})
        cells[field][band]["transition" if is_trans else "stable"] = {
            "mae": sum_err / n if n else None,
            "n":   n,
        }

    # Compute premium per cell where both stable and transition have ≥ MIN_N.
    out = {}
    for field, bands in cells.items():
        out[field] = {}
        for band, halves in bands.items():
            stable = halves.get("stable")
            trans  = halves.get("transition")
            if (stable is None or trans is None
                    or stable["n"] < MIN_N or trans["n"] < MIN_N
                    or stable["mae"] is None or trans["mae"] is None):
                continue
            premium_abs = trans["mae"] - stable["mae"]
            premium_pct = 100 * premium_abs / stable["mae"] if stable["mae"] else None
            out[field][band] = {
                "stable_mae":    round(stable["mae"], 4),
                "transition_mae": round(trans["mae"], 4),
                "premium_abs":   round(premium_abs, 4),
                "premium_pct":   round(premium_pct, 2) if premium_pct is not None else None,
                "n_stable":      stable["n"],
                "n_transition":  trans["n"],
            }
    return out, pairs_seen, pairs_used


def main():
    print(f"C1 confidence-layer calibration · {TEST_DAYS}-day window · min_n={MIN_N}")
    print("=" * 80)
    cells, seen, used = measure_premium()
    print(f"Pairs scanned: {seen:,}   used: {used:,}")
    print()

    # Field order: high-signal first (matches the R6 audit ranking).
    field_order = ["ws", "wg", "wd", "t", "dp", "h", "pa", "pr", "cc", "cl", "cm", "ch", "sr", "pp"]
    field_order = [f for f in field_order if f in cells]
    print(f"{'field':<6} {'band':<8} {'stable':>10} {'transition':>12} {'premium':>10} {'premium%':>10}  {'n_st':>8} / {'n_tr':>8}")
    print("-" * 80)
    for field in field_order:
        for band, lo, hi in BANDS:
            c = cells.get(field, {}).get(band)
            if c is None:
                continue
            print(f"{field:<6} {band:<8} {c['stable_mae']:>10.4f} {c['transition_mae']:>12.4f} "
                  f"{c['premium_abs']:>+10.4f} {c['premium_pct']:>+9.2f}%  "
                  f"{c['n_stable']:>8,} / {c['n_transition']:>8,}")
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

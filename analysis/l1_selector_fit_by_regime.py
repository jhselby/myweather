#!/usr/bin/env python3
"""L1 selector diagnostic — per (field, regime, band) fit.

Sibling to `l1_selector_fit.py`. That script fits the runtime selector at
(field, band) granularity. This one splits the same comparison by
`fc_regime` to surface cells where NBM Prod beats HRRR Prod under a
specific regime, but is MASKED because the pooled band picked HRRR.

Output: analysis/l1_selector_by_regime_report.json + a stdout table
sorted by lift on masked cells. Halves-stable check per
[[feedback_grid_select_halves_stable]] — a masked cell is only flagged
when both halves also lift toward NBM.

This is diagnostic-only. Runtime `l1_selector.py` is not touched.
Promote a cell by extending the runtime to key on (field, regime, band)
in a follow-up ship once we've seen the flagged set is stable.

Runtime:
    python3 -m analysis.l1_selector_fit_by_regime
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import pair_log_paths
from analysis.l1_selector_fit import (
    FIELDS, BANDS, HRRR_LAYER_PRIORITY_BY_FIELD,
    _band_for, _hrrr_prod_error, _nbm_prod_error,
    MIN_N as POOLED_MIN_N, MIN_LIFT_PCT as POOLED_MIN_LIFT,
)

OUT_PATH = Path(__file__).resolve().parent / "l1_selector_by_regime_report.json"

REGIMES = ["nw_flow", "se_flow", "sw_flow", "pre_frontal", "sea_breeze",
           "ne_flow", "calm", "frontal", "unknown"]
WINDOW_DAYS = 30
MIN_N_REGIME = 60          # per (field, regime, band) cell
MIN_LIFT_PCT_REGIME = 3.0  # same threshold as pooled


def _new_bucket():
    return {"hrrr_abs": 0.0, "hrrr_n": 0,
            "nbm_abs":  0.0, "nbm_n":  0,
            "paired_n": 0,
            "hrrr_abs_h1": 0.0, "nbm_abs_h1": 0.0, "paired_n_h1": 0,
            "hrrr_abs_h2": 0.0, "nbm_abs_h2": 0.0, "paired_n_h2": 0}


def _cell_stats(b):
    hrrr_mae = (b["hrrr_abs"] / b["hrrr_n"]) if b["hrrr_n"] else None
    nbm_mae  = (b["nbm_abs"]  / b["nbm_n"])  if b["nbm_n"]  else None
    lift_pct = None
    if hrrr_mae is not None and nbm_mae is not None and hrrr_mae > 0:
        lift_pct = 100.0 * (hrrr_mae - nbm_mae) / hrrr_mae
    return hrrr_mae, nbm_mae, lift_pct


def _halves_lift(b):
    def _one(hrrr_abs, nbm_abs, n):
        if n == 0:
            return None
        h = hrrr_abs / n
        m = nbm_abs / n
        if h <= 0:
            return None
        return 100.0 * (h - m) / h
    return _one(b["hrrr_abs_h1"], b["nbm_abs_h1"], b["paired_n_h1"]), \
           _one(b["hrrr_abs_h2"], b["nbm_abs_h2"], b["paired_n_h2"])


def fit():
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    window_start_dt = now - timedelta(days=WINDOW_DAYS)
    window_mid_dt   = now - timedelta(days=WINDOW_DAYS // 2)
    window_start = window_start_dt.strftime("%Y-%m-%dT%H:%M")
    window_mid   = window_mid_dt.strftime("%Y-%m-%dT%H:%M")

    pooled = defaultdict(_new_bucket)   # key: (field, band)
    regime = defaultdict(_new_bucket)   # key: (field, regime, band)

    n_in = n_kept = 0
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
                band = _band_for(row.get("lead_h"))
                if band is None:
                    continue
                obs_time = row.get("obs_time", "")
                if obs_time < window_start:
                    continue
                state_fc = row.get("state_fc") or {}
                reg = state_fc.get("regime_synoptic") or "unknown"
                if reg not in REGIMES:
                    reg = "unknown"
                n_kept += 1

                h = _hrrr_prod_error(row, field)
                n = _nbm_prod_error(row)
                is_h2 = obs_time >= window_mid

                for key, acc in (((field, band), pooled),
                                 ((field, reg, band), regime)):
                    b = acc[key]
                    if h is not None:
                        b["hrrr_abs"] += h
                        b["hrrr_n"]   += 1
                    if n is not None:
                        b["nbm_abs"] += n
                        b["nbm_n"]   += 1
                    if h is not None and n is not None:
                        b["paired_n"] += 1
                        if is_h2:
                            b["hrrr_abs_h2"] += h
                            b["nbm_abs_h2"]  += n
                            b["paired_n_h2"] += 1
                        else:
                            b["hrrr_abs_h1"] += h
                            b["nbm_abs_h1"]  += n
                            b["paired_n_h1"] += 1

    def _pooled_pick(field, band):
        b = pooled.get((field, band))
        if not b:
            return "hrrr", None, None, None, 0
        hmae, nmae, lift = _cell_stats(b)
        paired = b["paired_n"]
        if (nmae is not None and paired >= POOLED_MIN_N
                and lift is not None and lift >= POOLED_MIN_LIFT):
            return "nbm", hmae, nmae, lift, paired
        return "hrrr", hmae, nmae, lift, paired

    masked_cells = []
    all_cells = []
    for field in FIELDS:
        pooled_by_band = {band: _pooled_pick(field, band)
                          for band, _, _ in BANDS}
        for reg in REGIMES:
            for band, _, _ in BANDS:
                b = regime.get((field, reg, band))
                if not b:
                    continue
                hmae, nmae, lift = _cell_stats(b)
                paired = b["paired_n"]
                h1, h2 = _halves_lift(b)
                halves_stable_nbm = (
                    h1 is not None and h2 is not None
                    and h1 > 0 and h2 > 0
                )
                cell = {
                    "field": field, "regime": reg, "band": band,
                    "hrrr_prod_mae": round(hmae, 3) if hmae is not None else None,
                    "nbm_prod_mae":  round(nmae, 3) if nmae is not None else None,
                    "lift_pct":      round(lift, 2) if lift is not None else None,
                    "n":             paired,
                    "half1_lift_pct": round(h1, 2) if h1 is not None else None,
                    "half2_lift_pct": round(h2, 2) if h2 is not None else None,
                    "halves_stable_nbm": halves_stable_nbm,
                    "pooled_pick": pooled_by_band[band][0],
                }
                all_cells.append(cell)
                pooled_source = pooled_by_band[band][0]
                if (pooled_source == "hrrr"
                        and paired >= MIN_N_REGIME
                        and lift is not None and lift >= MIN_LIFT_PCT_REGIME
                        and halves_stable_nbm):
                    masked_cells.append(cell)

    masked_cells.sort(key=lambda c: c["lift_pct"], reverse=True)

    output = {
        "fitted_at": now.strftime("%Y-%m-%dT%H:%M"),
        "window_days": WINDOW_DAYS,
        "min_n_regime": MIN_N_REGIME,
        "min_lift_pct_regime": MIN_LIFT_PCT_REGIME,
        "pooled_min_n": POOLED_MIN_N,
        "pooled_min_lift_pct": POOLED_MIN_LIFT,
        "n_rows_scanned": n_in,
        "n_rows_kept":    n_kept,
        "n_masked_cells": len(masked_cells),
        "masked_cells":   masked_cells,
        "all_cells":      all_cells,
        "notes": (
            "Diagnostic-only. Runtime l1_selector.py still keys on (field, band). "
            "A masked cell is one where the pooled band picks HRRR but the regime × "
            "band cell shows NBM lift >= min_lift_pct_regime on n >= min_n_regime with "
            "both halves lifting toward NBM. Promotion requires runtime extension to "
            "(field, regime, band) plus a stability watch across daily reads."
        ),
    }
    with open(OUT_PATH, "w") as fout:
        json.dump(output, fout, indent=2)
        fout.write("\n")

    print("\n" + "=" * 92)
    print(f"L1 selector by-regime diagnostic — window {WINDOW_DAYS}d · fitted_at {output['fitted_at']}")
    print(f"Masked cells: pooled-picks-HRRR but regime × band flags NBM (halves-stable, n≥{MIN_N_REGIME}, lift≥{MIN_LIFT_PCT_REGIME}%)")
    print("=" * 92)
    print(f"{'field':<5} {'regime':<12} {'band':<7} {'HRRR':>7} {'NBM':>7} {'lift':>8} {'h1':>7} {'h2':>7} {'n':>6}")
    print("-" * 92)
    if not masked_cells:
        print("(none)")
    for c in masked_cells:
        print(f"{c['field']:<5} {c['regime']:<12} {c['band']:<7} "
              f"{c['hrrr_prod_mae']:>7.2f} {c['nbm_prod_mae']:>7.2f} "
              f"{c['lift_pct']:>+7.1f}% {c['half1_lift_pct']:>+6.1f}% "
              f"{c['half2_lift_pct']:>+6.1f}% {c['n']:>6,}")
    print("=" * 92)
    print(f"Total flagged: {len(masked_cells)}  (of {len(all_cells)} regime×band cells seen)")
    print(f"  wrote {OUT_PATH}")


if __name__ == "__main__":
    fit()

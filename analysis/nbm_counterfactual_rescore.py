#!/usr/bin/env python3
"""Counterfactual NBM Prod rescore (v0.6.475, 2026-08-25).

Grades what NBM Prod would look like *today* if the freshly-transferred
HRRR skip topology had been active on the NBM cascade since v0.6.440
launch. Uses the pair log's per-layer error stamps (error_raw_nbm,
error_l2_nbm, error_l3_nbm, error_l4_nbm, error_l5_nbm, error_l6_nbm,
error_chp_nbm, error_wdp_nbm) — no re-fitting or re-inference needed;
we just pick a different layer's error per row based on whether the
runtime skip table would have suppressed the deeper layer for that
(field × regime × lead-band) cell.

Emits a per-(field, band) diff of:
  * NBM Prod MAE — baseline (skips-off, matches current live Prod)
  * NBM Prod MAE — counterfactual (skips-on, HRRR-topology transfer)
  * Delta MAE and lift %
  * Would the selector's pick have flipped?

Read-only: does NOT write l1_selector_table_curated.json — that's the
next step (re-run analysis/l1_selector_fit.py after this report clears).

Regime source: row.state_fc.regime_synoptic (regime the model expected
at forecast hour). Not exactly what the runtime uses (runtime uses
regime at run-time), but the closest per-row proxy and matches the
"what would fire have decided" question.

Runtime:
    python3 -m analysis.nbm_counterfactual_rescore
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import pair_log_paths
from weather_collector.processors import skip_table_nbm

FIELDS = ("t", "ws", "wg", "wd", "h", "ch", "sr", "dp", "cc")
BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]
WINDOW_DAYS = 30
MIN_N = 200
MIN_LIFT_PCT = 3.0

# NBM cascade priority per field (deepest → shallowest). Mirrors
# l1_selector_fit._nbm_prod_error but keyed per-field for skip lookup.
NBM_LAYER_PRIORITY_BY_FIELD = {
    "t":   ["l6_nbm", "l3_nbm", "l2_nbm", "raw_nbm"],
    "ws":  ["l3_nbm", "l2_nbm", "raw_nbm"],
    "wg":  ["l3_nbm", "l2_nbm", "raw_nbm"],
    "wd":  ["wdp_nbm", "l3_nbm", "l2_nbm", "raw_nbm"],
    "h":   ["l3_nbm", "l2_nbm", "raw_nbm"],
    "ch":  ["chp_nbm", "l4_nbm", "l3_nbm", "l2_nbm", "raw_nbm"],
    "cc":  ["l4_nbm", "l3_nbm", "l2_nbm", "raw_nbm"],
    "sr":  ["l5_nbm", "l3_nbm", "l2_nbm", "raw_nbm"],
    "dp":  ["l3_nbm", "l2_nbm", "raw_nbm"],
}

# HRRR-side priority — copied from l1_selector_fit for the flip
# comparison. Kept in sync manually.
HRRR_LAYER_PRIORITY_BY_FIELD = {
    "t":   ["l6", "l4", "l3", "l2", "l1"],
    "ws":  ["wsbp", "l4", "l3", "l2", "l1"],
    "wg":  ["l4", "l3", "l2", "l1"],
    "wd":  ["wdp", "l4", "l3", "l2", "l1"],
    "h":   ["l4", "l3", "l2", "l1"],
    "ch":  ["chp", "l6", "l4", "l3", "l2", "l1"],
    "cc":  ["l6", "l4", "l3", "l2", "l1"],
    "sr":  ["l5", "l1"],
    "dp":  ["dpbp", "l3", "l2", "l1"],
}


def _band_for(lead_h):
    if lead_h is None:
        return None
    if lead_h < 6:  return "0-5"
    if lead_h < 12: return "6-11"
    if lead_h < 24: return "12-23"
    if lead_h < 48: return "24-47"
    return None


def _regime_from(row):
    for key in ("state_fc", "state_obs"):
        st = row.get(key)
        if isinstance(st, dict):
            r = st.get("regime_synoptic")
            if r:
                return r
    return None


def _hrrr_prod_error(row, field):
    for lyr in HRRR_LAYER_PRIORITY_BY_FIELD.get(field, ["l1"]):
        e = row.get(f"error_{lyr}")
        if e is not None:
            return abs(float(e))
    return None


def _nbm_prod_error(row, field, regime, lead_h, apply_skips):
    """Walk NBM cascade deepest-first, honoring skip topology when
    apply_skips=True. Returns first available error."""
    for lyr in NBM_LAYER_PRIORITY_BY_FIELD.get(field, ["l3_nbm"]):
        if apply_skips and skip_table_nbm.should_skip(field, lyr, regime, lead_h):
            continue
        e = row.get(f"error_{lyr}")
        if e is not None:
            return abs(float(e))
    return None


def rescore():
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    window_start = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M")

    # Accumulate baseline + counterfactual side-by-side per (field, band).
    acc = defaultdict(lambda: {
        "hrrr_abs": 0.0, "hrrr_n": 0,
        "nbm_off_abs": 0.0, "nbm_off_n": 0,
        "nbm_on_abs":  0.0, "nbm_on_n":  0,
        "paired_off": 0, "paired_on": 0,
    })
    n_in = 0
    n_kept = 0
    n_regime_missing = 0

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
                lead_h = row.get("lead_h")
                band = _band_for(lead_h)
                if band is None:
                    continue
                obs_time = row.get("obs_time", "")
                if obs_time < window_start:
                    continue
                n_kept += 1
                regime = _regime_from(row)
                if regime is None:
                    n_regime_missing += 1
                key = (field, band)
                h = _hrrr_prod_error(row, field)
                n_off = _nbm_prod_error(row, field, regime, lead_h, apply_skips=False)
                n_on  = _nbm_prod_error(row, field, regime, lead_h, apply_skips=True)
                if h is not None:
                    acc[key]["hrrr_abs"] += h
                    acc[key]["hrrr_n"]   += 1
                if n_off is not None:
                    acc[key]["nbm_off_abs"] += n_off
                    acc[key]["nbm_off_n"]   += 1
                if n_on is not None:
                    acc[key]["nbm_on_abs"]  += n_on
                    acc[key]["nbm_on_n"]    += 1
                if h is not None and n_off is not None:
                    acc[key]["paired_off"] += 1
                if h is not None and n_on is not None:
                    acc[key]["paired_on"] += 1

    print("=" * 100)
    print(f"NBM counterfactual rescore — window {WINDOW_DAYS}d · scanned {n_in:,} rows · kept {n_kept:,}")
    if n_regime_missing:
        print(f"  ⚠ {n_regime_missing:,} kept rows had no regime — those rows saw "
              f"apply_skips=True as a no-op (should_skip returns False on regime=None).")
    print("=" * 100)
    hdr = (f"{'field':<5} {'band':<8} "
           f"{'HRRR Prod':>10} {'NBM off':>10} {'NBM on':>10} "
           f"{'Δ MAE':>10} {'Δ NBM lift':>12} "
           f"{'pick off':>10} {'pick on':>10} {'flip?':>6} "
           f"{'n':>8}")
    print(hdr)
    print("-" * len(hdr))

    n_flipped = 0
    n_cells_with_lift = 0
    for field in FIELDS:
        for band, _, _ in BANDS:
            b = acc.get((field, band)) or {}
            hrrr_n = b.get("hrrr_n", 0)
            off_n  = b.get("nbm_off_n", 0)
            on_n   = b.get("nbm_on_n", 0)
            hrrr_mae = (b["hrrr_abs"] / hrrr_n) if hrrr_n else None
            off_mae  = (b["nbm_off_abs"] / off_n) if off_n else None
            on_mae   = (b["nbm_on_abs"]  / on_n)  if on_n  else None
            d_mae = None
            d_lift = None
            if off_mae is not None and on_mae is not None:
                d_mae = on_mae - off_mae
                if off_mae > 0:
                    d_lift = -100.0 * d_mae / off_mae   # positive = counterfactual better

            def _pick(nbm_mae, paired):
                if (nbm_mae is not None and hrrr_mae is not None
                        and paired >= MIN_N and hrrr_mae > 0):
                    lift = 100.0 * (hrrr_mae - nbm_mae) / hrrr_mae
                    if lift >= MIN_LIFT_PCT:
                        return "nbm", lift
                return "hrrr", None

            pick_off, lift_off = _pick(off_mae, b.get("paired_off", 0))
            pick_on,  lift_on  = _pick(on_mae,  b.get("paired_on",  0))
            flipped = pick_off != pick_on
            if flipped:
                n_flipped += 1
            if d_lift is not None and abs(d_lift) >= 0.5:
                n_cells_with_lift += 1

            def _fmt(x, w=10, s='.2f'):
                return f"{x:{s}}".rjust(w) if x is not None else "—".rjust(w)

            print(f"{field:<5} {band:<8} "
                  f"{_fmt(hrrr_mae):>10} {_fmt(off_mae):>10} {_fmt(on_mae):>10} "
                  f"{_fmt(d_mae):>10} "
                  f"{(f'{d_lift:+.2f}%' if d_lift is not None else '—'):>12} "
                  f"{pick_off:>10} {pick_on:>10} "
                  f"{('YES' if flipped else ''):>6} "
                  f"{off_n:>8,}")
    print("-" * len(hdr))
    print(f"Selector pick flips: {n_flipped} cells (out of {len(FIELDS)*len(BANDS)})")
    print(f"Cells with |Δ NBM lift| ≥ 0.5%: {n_cells_with_lift}")
    print("=" * 100)
    print("Notes:")
    print("  * 'NBM off' = current live Prod (skips off, matches today's per-field diagnostic).")
    print("  * 'NBM on'  = counterfactual Prod as if the v0.6.475 HRRR-topology skip transfer")
    print("               had been active from v0.6.440 launch.")
    print("  * 'flip?'   = would the selector's pick change? YES flags cells where the transfer")
    print("               materially changes user-visible routing.")
    print("  * If lift changes look good, run `python3 -m analysis.l1_selector_fit` next to")
    print("    write the clean selector table (fitter walks the same skip topology at runtime).")


if __name__ == "__main__":
    rescore()

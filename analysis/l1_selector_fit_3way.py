#!/usr/bin/env python3
"""L1 selector 3-way fitter — HRRR / NBM / NWS per (field, regime, band).

Standalone analysis-only fitter. Sibling of l1_selector_fit_by_regime.py.
Diagnostic path — runtime (weather_collector/processors/l1_selector.py) is
not touched until a walker-gate + 7-day stability read agrees.

NWS emits 5 fields on Wyman Cove's feed:
  t, wd, ws, dp — 100% coverage
  pp             — 76% coverage
Others (h, wg, sr, cc, cl, cm, ch, pa, pr) have no NWS forecast; those
stay 2-way (unchanged).

Method (per NWS-covered field × regime × lead-band):
  1. Load pair log within WINDOW_DAYS. Per row we need:
       error_l1 (HRRR side), error_raw_nbm, error_nws
       state_fc.regime_synoptic
  2. Compute MAE per source over the 30d window.
  3. Halves-stability: split chronologically at window midpoint. NWS is
     "3-way OPTIMAL" only if NWS beats min(HRRR, NBM) in BOTH halves.
  4. Emit per-cell verdict:
       NWS_WIRE — NWS beats best-of-HRRR-NBM by ≥ MIN_LIFT_PCT, n ≥ MIN_N,
                  halves-stable direction
       UNSTABLE — NWS wins pooled but not both halves
       MASKED_BY_POOLED — NWS wins in this (regime, band) but the pooled
                          band already picks HRRR or NBM (mirror of the
                          by-regime fitter's masked_cells pattern)
       not-optimal — HRRR or NBM is best

Output: analysis/l1_selector_3way_report.json + stdout summary.

Follow-on wire path (do NOT do this until 7-day stability read agrees):
  * Extend weather_collector/processors/l1_selector.py pick_source() with
    a 3-way branch keyed on the curated JSON's cells_cleared_for_wire_nws.
  * Extend l1_selector_fit_by_regime_walker.py to track a THIRD direction
    (NWS-wire) alongside NBM-wire and HRRR-wire. Same 3-day gate +
    escalation-clause discipline as v0.6.586-588.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import pair_log_paths

NWS_FIELDS = ("t", "wd", "ws", "dp", "pp")
BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]
REGIMES = ["nw_flow", "se_flow", "sw_flow", "pre_frontal", "sea_breeze",
           "ne_flow", "calm", "frontal", "unknown"]
WINDOW_DAYS = 30
MIN_N       = 60
MIN_LIFT_PCT = 3.0  # NWS advantage over best-of-HRRR-NBM

OUT_PATH = Path(__file__).resolve().parent / "l1_selector_3way_report.json"


def band_for(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def _new_bucket():
    return {
        "hrrr_abs": 0.0, "nbm_abs": 0.0, "nws_abs": 0.0, "n": 0,
        "hrrr_abs_h1": 0.0, "nbm_abs_h1": 0.0, "nws_abs_h1": 0.0, "n_h1": 0,
        "hrrr_abs_h2": 0.0, "nbm_abs_h2": 0.0, "nws_abs_h2": 0.0, "n_h2": 0,
    }


def _mae(abs_sum, n):
    return (abs_sum / n) if n else None


def _cell_verdict(b):
    if b["n"] < MIN_N:
        return None
    mae_h = _mae(b["hrrr_abs"], b["n"])
    mae_n = _mae(b["nbm_abs"], b["n"])
    mae_w = _mae(b["nws_abs"], b["n"])
    if None in (mae_h, mae_n, mae_w):
        return None
    best_hnn = min(mae_h, mae_n)
    if best_hnn <= 0:
        return None
    lift_pct = 100.0 * (best_hnn - mae_w) / best_hnn
    # Halves check — NWS must win in each half independently
    mae_h_h1 = _mae(b["hrrr_abs_h1"], b["n_h1"]); mae_n_h1 = _mae(b["nbm_abs_h1"], b["n_h1"]); mae_w_h1 = _mae(b["nws_abs_h1"], b["n_h1"])
    mae_h_h2 = _mae(b["hrrr_abs_h2"], b["n_h2"]); mae_n_h2 = _mae(b["nbm_abs_h2"], b["n_h2"]); mae_w_h2 = _mae(b["nws_abs_h2"], b["n_h2"])
    halves_stable = False
    lift_h1 = lift_h2 = None
    if all(x is not None for x in (mae_h_h1, mae_n_h1, mae_w_h1, mae_h_h2, mae_n_h2, mae_w_h2)):
        best_h1 = min(mae_h_h1, mae_n_h1); best_h2 = min(mae_h_h2, mae_n_h2)
        if best_h1 > 0 and best_h2 > 0:
            lift_h1 = 100.0 * (best_h1 - mae_w_h1) / best_h1
            lift_h2 = 100.0 * (best_h2 - mae_w_h2) / best_h2
            halves_stable = (lift_h1 >= MIN_LIFT_PCT and lift_h2 >= MIN_LIFT_PCT)
    return {
        "n": b["n"], "mae_hrrr": round(mae_h, 4), "mae_nbm": round(mae_n, 4),
        "mae_nws": round(mae_w, 4), "lift_pct": round(lift_pct, 2),
        "lift_pct_h1": round(lift_h1, 2) if lift_h1 is not None else None,
        "lift_pct_h2": round(lift_h2, 2) if lift_h2 is not None else None,
        "halves_stable": halves_stable,
    }


def circular_error(field, forecast, observed):
    if field != "wd":
        return abs(float(forecast) - float(observed))
    d = (float(forecast) - float(observed)) % 360
    if d > 180: d -= 360
    return abs(d)


def fit():
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    window_start_dt = now - timedelta(days=WINDOW_DAYS)
    window_mid_dt   = now - timedelta(days=WINDOW_DAYS // 2)

    # (field, regime, band) -> bucket
    cells = defaultdict(_new_bucket)
    # (field, band) pooled — mirror of the by-regime fitter's pooled comparison
    pooled = defaultdict(_new_bucket)

    n_in = n_use = 0
    for path in pair_log_paths():
        with open(path, "rb") as fh:
            for raw in fh:
                n_in += 1
                try:
                    r = json.loads(raw)
                except Exception:
                    continue
                f = r.get("field")
                if f not in NWS_FIELDS: continue
                lead = r.get("lead_h")
                if lead is None: continue
                band = band_for(int(lead))
                if not band: continue
                try:
                    odt = datetime.fromisoformat((r.get("obs_time") or "")[:19])
                except Exception:
                    continue
                if odt < window_start_dt: continue
                e_h = r.get("error_l1")
                e_n = r.get("error_raw_nbm")
                e_w = r.get("error_nws")
                if e_h is None or e_n is None or e_w is None: continue
                sf = (r.get("state_fc") or {}).get("regime_synoptic") or "unknown"
                if sf not in REGIMES: sf = "unknown"
                a_h = abs(float(e_h)); a_n = abs(float(e_n)); a_w = abs(float(e_w))

                for key in ((f, sf, band), None):  # None means pooled
                    b = cells[(f, sf, band)] if key else pooled[(f, band)]
                    b["hrrr_abs"] += a_h; b["nbm_abs"] += a_n; b["nws_abs"] += a_w
                    b["n"] += 1
                    if odt <= window_mid_dt:
                        b["hrrr_abs_h1"] += a_h; b["nbm_abs_h1"] += a_n; b["nws_abs_h1"] += a_w
                        b["n_h1"] += 1
                    else:
                        b["hrrr_abs_h2"] += a_h; b["nbm_abs_h2"] += a_n; b["nws_abs_h2"] += a_w
                        b["n_h2"] += 1
                    if not key: break  # only iterate pooled once
                    # actually iterate BOTH (per-cell and pooled)
                    b_pool = pooled[(f, band)]
                    b_pool["hrrr_abs"] += a_h; b_pool["nbm_abs"] += a_n; b_pool["nws_abs"] += a_w
                    b_pool["n"] += 1
                    if odt <= window_mid_dt:
                        b_pool["hrrr_abs_h1"] += a_h; b_pool["nbm_abs_h1"] += a_n; b_pool["nws_abs_h1"] += a_w
                        b_pool["n_h1"] += 1
                    else:
                        b_pool["hrrr_abs_h2"] += a_h; b_pool["nbm_abs_h2"] += a_n; b_pool["nws_abs_h2"] += a_w
                        b_pool["n_h2"] += 1
                    break
                n_use += 1

    # Verdicts
    per_cell = {}
    nws_wire = []
    for (f, reg, band), b in cells.items():
        v = _cell_verdict(b)
        if not v: continue
        # Verdict tag
        if v["lift_pct"] >= MIN_LIFT_PCT and v["halves_stable"]:
            v["verdict"] = "NWS_WIRE"
            nws_wire.append((f, reg, band, v))
        elif v["lift_pct"] >= MIN_LIFT_PCT:
            v["verdict"] = "UNSTABLE"
        else:
            v["verdict"] = "not-optimal"
        per_cell[f"{f}/{reg}/{band}"] = v

    pooled_view = {}
    for (f, band), b in pooled.items():
        v = _cell_verdict(b)
        if not v: continue
        pooled_view[f"{f}/{band}"] = v

    # MASKED_BY_POOLED — NWS wire fires per-cell but pooled picks HRRR or NBM
    for f, reg, band, v in nws_wire:
        p = pooled_view.get(f"{f}/{band}")
        if p and (p.get("lift_pct") or 0) < MIN_LIFT_PCT:
            v["masked_by_pooled"] = True

    out = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": "l1_selector_fit_3way.py",
        "window_days": WINDOW_DAYS,
        "min_n": MIN_N,
        "min_lift_pct": MIN_LIFT_PCT,
        "n_rows_used": n_use,
        "cells_cleared_for_wire_nws": [{"field": f, "regime": r, "band": b, **v} for f, r, b, v in nws_wire],
        "per_cell": per_cell,
        "pooled": pooled_view,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT_PATH}")
    print(f"rows used: {n_use:,} of {n_in:,}\n")

    # Stdout summary
    print(f"NWS-WIRE candidates (halves-stable, lift ≥ {MIN_LIFT_PCT}%):")
    print(f"{'field':<5} {'regime':<12} {'band':<7} {'n':>6} {'HRRR':>7} {'NBM':>7} {'NWS':>7} {'lift%':>7} {'h1/h2':>14}  pool_mask")
    print("-" * 92)
    for f, reg, band, v in sorted(nws_wire, key=lambda x: -x[3]["lift_pct"]):
        p_mask = "★ masked" if v.get("masked_by_pooled") else ""
        print(f"{f:<5} {reg:<12} {band:<7} {v['n']:>6,} {v['mae_hrrr']:>7.3f} {v['mae_nbm']:>7.3f} {v['mae_nws']:>7.3f} {v['lift_pct']:>6.1f}% {v['lift_pct_h1']:>6.1f}/{v['lift_pct_h2']:>6.1f}  {p_mask}")

    if len(nws_wire) >= 3:
        print(f"\nVERDICT: STAGE 1 PROMOTE — {len(nws_wire)} NWS-wire cells clear halves-stable + lift ≥ {MIN_LIFT_PCT}%. Follow-on: extend walker to 3-way, wait for 7-day stability, then wire runtime.")
    else:
        print(f"\nVERDICT: HOLD — {len(nws_wire)} NWS-wire cells clear. Need ≥3 for structural extension.")


if __name__ == "__main__":
    fit()

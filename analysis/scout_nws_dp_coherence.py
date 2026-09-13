#!/usr/bin/env python3
"""Scout: NWS-t agreement gate feasibility for the 3 cleared dp cells.

Answers the question parked in [[project_nws_dp_coherence_wire]] option A:
if we only route dp to NWS when |t_nws - t_selected| <= TOL, how much of
the escalation lift survives, and at what coverage cost?

For each of the 3 cells cleared today (2026-09-13):
  - dp/nw_flow/0-5   (walker escalation +25.0%, n=1,238)
  - dp/nw_flow/12-23 (walker escalation +29.3%, n=1,721)
  - dp/pre_frontal/12-23 (walker escalation +23.6%, n=1,078)

Method (per cell):
  1. Pull dp pair-log rows in the 30d fitter window matching regime x band.
  2. Join to the concurrent t row on (run_time, valid_time). Compute
     |Δt| = |forecast_nws_t - forecast_t| (the "selected" t is the row's
     `forecast` field — final pipeline pick after all layers).
  3. For each tolerance in {0.5, 1.0, 2.0, 3.0, 5.0, inf} °F, compute:
       coverage      = rows_within_tol / rows_total
       mae_nws       = mean |dp_nws - obs| on rows_within_tol
       mae_selected  = mean |dp_selected - obs| on rows_within_tol
       lift_pct      = 100 * (mae_selected - mae_nws) / mae_selected
       lift_pct_all  = same but on all rows (unfiltered baseline)
  4. Report a table per cell.

Interpretation:
  - A tolerance where coverage stays high AND lift stays close to the
    unfiltered baseline is a good candidate gate.
  - A tolerance that halves coverage while doubling lift means the NWS
    win is concentrated on rows where NWS-t agrees — the gate would work.
  - Flat lift across all tolerances means the NWS-t agreement is not
    correlated with dp accuracy — gate wouldn't do useful work; a
    different coherence approach is needed.

Runtime:
    python3 -m analysis.scout_nws_dp_coherence
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import pair_log_paths

WINDOW_DAYS = 30
BANDS = {"0-5": (0, 6), "6-11": (6, 12), "12-23": (12, 24), "24-47": (24, 48)}

TARGET_CELLS = [
    ("dp", "nw_flow", "0-5"),
    ("dp", "nw_flow", "12-23"),
    ("dp", "pre_frontal", "12-23"),
]

TOLERANCES_F = [0.5, 1.0, 2.0, 3.0, 5.0, float("inf")]


def _band_for(lead_h):
    for name, (lo, hi) in BANDS.items():
        if lo <= lead_h < hi:
            return name
    return None


def scout():
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    window_start = now - timedelta(days=WINDOW_DAYS)

    # Build (run_time, valid_time) -> t_row snapshot, then a parallel pass for dp.
    # Memory-conservative: single pass, keep only the fields we need per key.
    t_by_key = {}   # (run_time, valid_time) -> (forecast_t_selected, forecast_nws_t)
    dp_rows = []    # list of (regime, band, dp_nws, dp_selected, obs, run_time, valid_time)

    n_scanned = 0
    for path in pair_log_paths():
        with open(path, "rb") as fh:
            for raw in fh:
                n_scanned += 1
                try:
                    r = json.loads(raw)
                except Exception:
                    continue
                fld = r.get("field")
                if fld not in ("t", "dp"):
                    continue
                obs_time = r.get("obs_time") or ""
                try:
                    odt = datetime.fromisoformat(obs_time[:19])
                except Exception:
                    continue
                if odt < window_start:
                    continue
                key = (r.get("run_time"), r.get("valid_time"))
                if fld == "t":
                    t_sel = r.get("forecast")
                    t_nws = r.get("forecast_nws")
                    if t_sel is not None and t_nws is not None:
                        t_by_key[key] = (float(t_sel), float(t_nws))
                    continue
                # dp row
                dp_nws = r.get("forecast_nws")
                dp_sel = r.get("forecast")
                obs = r.get("observed")
                if dp_nws is None or dp_sel is None or obs is None:
                    continue
                lead = r.get("lead_h")
                if lead is None:
                    continue
                band = _band_for(int(lead))
                if band is None:
                    continue
                sf = ((r.get("state_fc") or {}).get("regime_synoptic")) or "unknown"
                dp_rows.append((sf, band, float(dp_nws), float(dp_sel),
                                float(obs), key[0], key[1]))

    print(f"Scanned {n_scanned:,} rows; t-snapshots kept {len(t_by_key):,}; dp rows kept {len(dp_rows):,}")
    print()

    # Per cell: bucket dp rows by |Δt| and compute MAE_nws vs MAE_selected.
    for target_field, target_reg, target_band in TARGET_CELLS:
        rows = [(dp_nws, dp_sel, obs, rt, vt)
                for (reg, band, dp_nws, dp_sel, obs, rt, vt) in dp_rows
                if reg == target_reg and band == target_band]
        # Attach |Δt|
        attached = []
        n_missing_t = 0
        for dp_nws, dp_sel, obs, rt, vt in rows:
            t_pair = t_by_key.get((rt, vt))
            if t_pair is None:
                n_missing_t += 1
                continue
            t_sel, t_nws = t_pair
            attached.append((abs(t_nws - t_sel), dp_nws, dp_sel, obs))

        n_total = len(attached)
        print("=" * 90)
        print(f"CELL: dp / {target_reg} / {target_band}")
        print(f"  rows total = {n_total}  (missing t-pair: {n_missing_t}; "
              f"the fitter's n uses HRRR/NBM/NWS pairing, this scout also needs t)")
        if not n_total:
            print("  (no rows after t-join)")
            continue

        # Unfiltered baseline
        base_mae_nws = sum(abs(dn - ob) for _, dn, _, ob in attached) / n_total
        base_mae_sel = sum(abs(ds - ob) for _, _, ds, ob in attached) / n_total
        base_lift = 100.0 * (base_mae_sel - base_mae_nws) / base_mae_sel if base_mae_sel > 0 else 0.0
        print(f"  baseline (no gate): MAE_selected={base_mae_sel:.3f}  MAE_nws={base_mae_nws:.3f}  "
              f"lift={base_lift:+.2f}%")

        # |Δt| distribution — a few percentiles
        deltas = sorted(d for d, _, _, _ in attached)
        pcts = [10, 25, 50, 75, 90, 95, 99]
        pct_vals = [deltas[int(len(deltas) * p / 100)] for p in pcts]
        pct_str = "  ".join(f"p{p}={v:.2f}" for p, v in zip(pcts, pct_vals))
        print(f"  |Δt| °F percentiles:  {pct_str}")
        print()

        # Bucket by tolerance
        print(f"  {'tol_F':>7}  {'coverage':>10}  {'n_in':>6}  {'MAE_sel':>8}  {'MAE_nws':>8}  "
              f"{'lift%':>8}  {'lift_vs_base_pp':>16}")
        for tol in TOLERANCES_F:
            within = [(dn, ds, ob) for dt, dn, ds, ob in attached if dt <= tol]
            n_in = len(within)
            cov = 100.0 * n_in / n_total if n_total else 0.0
            if n_in == 0:
                print(f"  {tol:>7.1f}  {cov:>9.1f}%  {n_in:>6}  {'—':>8}  {'—':>8}  {'—':>8}  {'—':>16}")
                continue
            mae_nws = sum(abs(dn - ob) for dn, _, ob in within) / n_in
            mae_sel = sum(abs(ds - ob) for _, ds, ob in within) / n_in
            lift = 100.0 * (mae_sel - mae_nws) / mae_sel if mae_sel > 0 else 0.0
            delta_from_base = lift - base_lift
            print(f"  {tol:>7.1f}  {cov:>9.1f}%  {n_in:>6}  {mae_sel:>8.3f}  {mae_nws:>8.3f}  "
                  f"{lift:>+7.2f}%  {delta_from_base:>+15.2f}pp")
        print()


if __name__ == "__main__":
    scout()

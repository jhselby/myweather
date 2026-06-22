"""
C1 confidence-layer — Stage 3.5 calibration audit.

Per the hypothesis promotion pipeline ([[feedback-hypothesis-promotion-pipeline]]):
the layer is gated (`ENABLED=False`) until the displayed bands are confirmed to
contain truth at the claimed rate. This script does that confirmation.

Method:
  1. Load the Stage 2 curated table at weather_collector/data/c1_confidence_curated.json
  2. Re-measure per-(field, band) stable_mae and transition_mae on RECENT pair-log
     data (default: last 7 days), the same window users would see when ENABLED.
  3. For each wired cell, compute drift = (measured - curated) / curated. Tag as:
       • CALIBRATED — |drift| < CALIBRATION_THRESHOLD on BOTH stable and transition
       • DRIFTED    — either side moved more than that
       • THIN       — n_measured below MIN_N (not enough recent data to judge)
  4. Pass rule: ≥ PASS_FRACTION of non-THIN cells are CALIBRATED.

When this script returns PASS (typically after ~7 days of accumulated stamped
data), flipping confidence_layer.ENABLED=True is safe. Re-run weekly; if drift
emerges, re-curate (run c1_confidence_calibration.py + c1_curate_confidence_table.py)
and re-deploy.

Run:
  python3 analysis/c1_calibration_audit.py
  python3 analysis/c1_calibration_audit.py --days 14   # use a wider window
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis._cache import cached_path


PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"

BANDS = [
    ("0-5h",   0, 6),
    ("6-11h",  6, 12),
    ("12-23h", 12, 24),
    ("24-47h", 24, 48),
]

# Calibration thresholds. Tunable.
CALIBRATION_THRESHOLD = 0.20   # |drift| < 20% to count as CALIBRATED
MIN_N = 200                    # cells with fewer recent pairs tagged THIN
PASS_FRACTION = 0.75           # ≥75% of non-THIN cells must CALIBRATE

CURATED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "weather_collector", "data", "c1_confidence_curated.json",
)


def _band_for_lead(lead_h):
    if lead_h is None:
        return None
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def measure_recent(window_days):
    """Stream the cached pair log; accumulate stable/transition MAE per
    (field, band) over the last `window_days`.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime("%Y-%m-%dT%H:%M")
    accs = defaultdict(lambda: [0.0, 0])  # (field, band, is_transition) -> [sum_abs_err, n]
    path = cached_path(PAIR_LOG_URL)
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
            fc = (p.get("forecast_l4") or p.get("forecast_l3")
                  or p.get("forecast_l2") or p.get("forecast_l1")
                  or p.get("forecast"))
            if fc is None:
                continue
            is_trans = (rfc != rob)
            accs[(field, band, is_trans)][0] += abs(fc - obs)
            accs[(field, band, is_trans)][1] += 1

    # Pivot into {field: {band: {stable_mae, transition_mae, n_stable, n_transition}}}
    out = {}
    for (field, band, is_trans), (sum_err, n) in accs.items():
        out.setdefault(field, {}).setdefault(band, {})
        side = "transition" if is_trans else "stable"
        out[field][band][f"{side}_mae"] = sum_err / n if n else None
        out[field][band][f"n_{side}"]   = n
    return out


def classify_cell(curated, measured):
    """Return (status, drift_stable, drift_transition) for one cell.

    measured may be None / partial — return THIN in that case.
    """
    if measured is None:
        return "THIN", None, None
    n_st = measured.get("n_stable", 0)
    n_tr = measured.get("n_transition", 0)
    if n_st < MIN_N or n_tr < MIN_N:
        return "THIN", None, None
    m_stable = measured.get("stable_mae")
    m_trans  = measured.get("transition_mae")
    c_stable = curated["stable_mae"]
    c_trans  = curated["transition_mae"]
    if m_stable is None or m_trans is None or c_stable == 0 or c_trans == 0:
        return "THIN", None, None
    drift_stable = (m_stable - c_stable) / c_stable
    drift_trans  = (m_trans  - c_trans)  / c_trans
    if abs(drift_stable) < CALIBRATION_THRESHOLD and abs(drift_trans) < CALIBRATION_THRESHOLD:
        return "CALIBRATED", drift_stable, drift_trans
    return "DRIFTED", drift_stable, drift_trans


def run_audit(window_days):
    if not os.path.exists(CURATED_PATH):
        sys.exit(f"Missing curated table at {CURATED_PATH} — run c1_curate_confidence_table.py first")
    with open(CURATED_PATH) as f:
        curated_doc = json.load(f)
    curated_cells = curated_doc.get("cells", {})

    print(f"C1 calibration audit · window={window_days}d · "
          f"calibration_threshold=±{int(CALIBRATION_THRESHOLD*100)}% · "
          f"pass_fraction={int(PASS_FRACTION*100)}%")
    print("=" * 96)
    print("Measuring recent pair-log MAE per (field, band, transition)...", flush=True)
    measured = measure_recent(window_days)
    print("  done.")
    print()

    results = []
    print(f"{'field':<5} {'band':<8} {'status':<11} {'curated_st→tr':>20} "
          f"{'measured_st→tr':>20} {'drift_st':>10} {'drift_tr':>10}")
    print("-" * 96)
    for field, bands in curated_cells.items():
        for band, c in bands.items():
            # Only audit cells that the curated table actually wired (SHIP or
            # MARGINAL). REVIEW/SKIP cells are excluded from C1 stamping in
            # confidence_layer.py and therefore from audit by symmetry.
            if c.get("status") not in ("SHIP", "MARGINAL"):
                continue
            m = measured.get(field, {}).get(band)
            status, ds, dt = classify_cell(c, m)
            cur_str  = f"{c['stable_mae']:.3f}→{c['transition_mae']:.3f}"
            if m and m.get("stable_mae") is not None and m.get("transition_mae") is not None:
                mea_str = f"{m['stable_mae']:.3f}→{m['transition_mae']:.3f}"
            else:
                mea_str = "—"
            ds_str = f"{ds*100:+.1f}%" if ds is not None else "—"
            dt_str = f"{dt*100:+.1f}%" if dt is not None else "—"
            print(f"{field:<5} {band:<8} {status:<11} {cur_str:>20} {mea_str:>20} {ds_str:>10} {dt_str:>10}")
            results.append({
                "field": field, "band": band, "status": status,
                "drift_stable": ds, "drift_transition": dt,
                "n_stable":     m.get("n_stable", 0) if m else 0,
                "n_transition": m.get("n_transition", 0) if m else 0,
            })
        print()

    counts = {"CALIBRATED": 0, "DRIFTED": 0, "THIN": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    judgeable = counts["CALIBRATED"] + counts["DRIFTED"]
    pass_rate = (counts["CALIBRATED"] / judgeable) if judgeable else 0.0
    verdict = "PASS" if pass_rate >= PASS_FRACTION and judgeable >= 10 else "HOLD"
    print("=" * 96)
    print(f"Totals: {counts['CALIBRATED']} CALIBRATED, {counts['DRIFTED']} DRIFTED, {counts['THIN']} THIN")
    print(f"Pass rate (CALIBRATED / judgeable): {pass_rate:.2%}")
    print(f"Verdict: {verdict}")
    if verdict == "HOLD":
        print()
        if judgeable < 10:
            print("  HOLD reason: < 10 judgeable cells. Window too short, or pair log too sparse.")
        else:
            print(f"  HOLD reason: pass rate {pass_rate:.2%} < {PASS_FRACTION:.0%} threshold.")
            print(f"  Next step: re-curate (c1_confidence_calibration.py + c1_curate_confidence_table.py)")
            print(f"  to capture the drift, then re-deploy.")

    return verdict, results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7,
                        help="Recent pair-log window in days (default 7)")
    args = parser.parse_args()
    run_audit(args.days)


if __name__ == "__main__":
    main()

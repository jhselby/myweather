"""
Stage 2 analysis for pressure-tendency hypothesis (backlog Group A #3).

Question: does pressure tendency (dP/dt over 3h, already stamped on every
pair-log entry as state_fc.pressure_trend_hpa_3h) predict that-hour
forecast |error|, AND is the signal orthogonal to:
  - R6 regime-transition flag (state_fc.regime_synoptic vs state_obs)
  - cluster-spread quartile (where data overlaps)

Unlike cluster-spread, dP/dt is already in the pair log going back the
full retention window. No persistent logger needed. If verdict is clean,
this becomes an C1 axis purely by extending the cal-table key tuple.

Method:
  1. Stream pair log.
  2. Bin pressure_trend_hpa_3h into 4 categories:
       falling_fast  (<= -1.0 hPa/3h)
       falling       (-1.0 to -0.3)
       flat          (-0.3 to +0.3)
       rising        (> +0.3)
  3. Per (field, lead_band): MAE per bin. Compute inflation ratio
     = max(bin MAE) / flat-bin MAE.
  4. Orthogonality vs R6: split by transition flag, repeat. Does the
     inflation hold in the stable subset?

Verdict per (field, band):
  ORTHOGONAL   — inflation >=1.25 in stable subset AND in transition subset
  CONFOUNDED   — inflation only in transition subset
  REDUNDANT    — flat across all bins in stable subset
  AMBIGUOUS    — partial / inconsistent
  THIN         — insufficient sample in any bin

Overall:
  PROMOTE if >=3 ORTHOGONAL verdicts (treat as C1 axis #3)
  KILL    if >=80% REDUNDANT
  else AMBIGUOUS
"""
import json
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"

FIELDS_TO_TEST = ("t", "h", "ws", "wg", "dp", "pp", "cc", "sr")
LEAD_BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]

# Bin edges in hPa/3h. Reference axis = "flat" (calm pressure).
BIN_EDGES = [
    ("falling_fast", float("-inf"), -1.0),
    ("falling",      -1.0,         -0.3),
    ("flat",         -0.3,         0.3),
    ("rising",       0.3,          float("inf")),
]


def lead_band(lead_h):
    for label, lo, hi in LEAD_BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def pt_bin(pt):
    for label, lo, hi in BIN_EDGES:
        if lo <= pt < hi:
            return label
    return None


def main():
    print("=" * 80)
    print("PRESSURE-TENDENCY (dP/dt) C1 AXIS — STAGE 2")
    print("=" * 80)

    print("\n[1/4] Streaming pair log...")
    pair_log_path = cached_path(PAIR_LOG_URL)

    # agg[(field, band, pt_bin, transition)] -> list of |error|
    agg = defaultdict(list)
    # Just for sanity: counts per pt_bin per transition
    pt_counts = defaultdict(int)
    pt_trans_counts = {b[0]: {"T": 0, "S": 0} for b in BIN_EDGES}

    n_rows = 0
    n_used = 0
    n_skip_no_pt = 0
    n_skip_no_regime = 0
    with open(pair_log_path) as f:
        for line in f:
            n_rows += 1
            try:
                row = json.loads(line)
            except Exception:
                continue
            field = row.get("field")
            if field not in FIELDS_TO_TEST:
                continue
            err = row.get("error")
            lead_h = row.get("lead_h")
            if err is None or lead_h is None:
                continue
            band = lead_band(lead_h)
            if band is None:
                continue
            sf = row.get("state_fc") or {}
            so = row.get("state_obs") or {}
            pt = sf.get("pressure_trend_hpa_3h")
            if pt is None:
                n_skip_no_pt += 1
                continue
            pt_label = pt_bin(pt)
            if pt_label is None:
                continue
            fc_reg = sf.get("regime_synoptic")
            obs_reg = so.get("regime_synoptic")
            if fc_reg is None or obs_reg is None:
                n_skip_no_regime += 1
                # still bin by pt for the all-pairs view
                agg[(field, band, pt_label, "ALL")].append(abs(err))
                pt_counts[pt_label] += 1
                continue
            trans = "T" if fc_reg != obs_reg else "S"
            agg[(field, band, pt_label, trans)].append(abs(err))
            agg[(field, band, pt_label, "ALL")].append(abs(err))
            pt_counts[pt_label] += 1
            pt_trans_counts[pt_label][trans] += 1
            n_used += 1

    print(f"  scanned {n_rows:,} rows. Used {n_used:,}. "
          f"skipped (no pt): {n_skip_no_pt:,}. "
          f"skipped (no regime, still counted in ALL): {n_skip_no_regime:,}.")

    print("\n[2/4] Pressure-tendency bin distribution:")
    total_pt = sum(pt_counts.values()) or 1
    for label, _, _ in BIN_EDGES:
        c = pt_counts[label]
        print(f"  {label:<13} n={c:>8,} ({100*c/total_pt:5.1f}%)")

    print("\n  Co-occurrence with R6 transition:")
    for label, _, _ in BIN_EDGES:
        c = pt_trans_counts[label]
        tot = c["T"] + c["S"]
        if tot:
            print(f"  {label:<13} P(trans)={c['T']/tot:.1%}  (n={tot:,})")

    print("\n[3/4] Per-(field, band) MAE by pressure-tendency bin:")
    print("      flat = reference. Ratio = max(other bin MAE) / flat MAE.\n")
    print(f"  {'field':<5} {'band':<8} {'flat_n':>7} {'flat':>7} "
          f"{'falling':>9} {'fall_fast':>11} {'rising':>8} "
          f"{'max_r':>6}  {'verdict_all':<11}  {'verdict_stable':<14}")

    counts = {"ORTHOGONAL": 0, "CONFOUNDED": 0, "REDUNDANT": 0,
              "AMBIGUOUS": 0, "THIN": 0}

    def _mae(items):
        return (sum(items) / len(items)) if items else None

    def _ratio(mae, ref):
        if mae is None or ref is None or ref <= 0:
            return None
        return mae / ref

    def _verdict_from(bins_mae, bins_n, min_n=100):
        ref = bins_mae.get("flat")
        ref_n = bins_n.get("flat", 0)
        if ref is None or ref_n < min_n:
            return "THIN", None
        max_r = 0.0
        for label, _, _ in BIN_EDGES:
            if label == "flat":
                continue
            n = bins_n.get(label, 0)
            mae = bins_mae.get(label)
            if n < min_n or mae is None:
                continue
            r = mae / ref
            if r > max_r:
                max_r = r
        return ("INFLATED" if max_r >= 1.25 else "FLAT", max_r)

    for field in FIELDS_TO_TEST:
        for band_label, _, _ in LEAD_BANDS:
            bins_mae_all = {}
            bins_n_all = {}
            bins_mae_s = {}
            bins_n_s = {}
            bins_mae_t = {}
            bins_n_t = {}
            for label, _, _ in BIN_EDGES:
                items_all = agg.get((field, band_label, label, "ALL"), [])
                items_s = agg.get((field, band_label, label, "S"), [])
                items_t = agg.get((field, band_label, label, "T"), [])
                bins_mae_all[label] = _mae(items_all)
                bins_n_all[label] = len(items_all)
                bins_mae_s[label] = _mae(items_s)
                bins_n_s[label] = len(items_s)
                bins_mae_t[label] = _mae(items_t)
                bins_n_t[label] = len(items_t)

            ref_mae = bins_mae_all.get("flat")
            ref_n = bins_n_all.get("flat", 0)

            v_all, r_all = _verdict_from(bins_mae_all, bins_n_all, min_n=100)
            v_s, r_s = _verdict_from(bins_mae_s, bins_n_s, min_n=100)
            v_t, r_t = _verdict_from(bins_mae_t, bins_n_t, min_n=100)

            # Per-cell verdict
            if v_all == "THIN" or v_s == "THIN":
                cell = "THIN"
            elif v_s == "INFLATED" and v_t == "INFLATED":
                cell = "ORTHOGONAL"
            elif v_s == "FLAT" and v_t == "INFLATED":
                cell = "CONFOUNDED"
            elif v_s == "FLAT" and v_t in ("FLAT", "THIN"):
                cell = "REDUNDANT"
            elif v_s == "INFLATED" and v_t in ("FLAT", "THIN"):
                # signal in stable but not transition — usually still useful
                cell = "ORTHOGONAL"
            else:
                cell = "AMBIGUOUS"

            counts[cell] += 1

            def fmt(x, w=7, p=3):
                return f"{x:>{w}.{p}f}" if x is not None else f"{'—':>{w}}"

            print(f"  {field:<5} {band_label:<8} {ref_n:>7,} {fmt(ref_mae)} "
                  f"{fmt(bins_mae_all.get('falling'), 9)} "
                  f"{fmt(bins_mae_all.get('falling_fast'), 11)} "
                  f"{fmt(bins_mae_all.get('rising'), 8)} "
                  f"{r_all if r_all is not None else '—':>6.2f}  "
                  f"{v_all:<11}  S:{v_s}/T:{v_t} → {cell}")

    print("\n[4/4] Overall verdict:")
    print(f"  ORTHOGONAL: {counts['ORTHOGONAL']}, "
          f"CONFOUNDED: {counts['CONFOUNDED']}, "
          f"REDUNDANT:  {counts['REDUNDANT']}, "
          f"AMBIGUOUS:  {counts['AMBIGUOUS']}, "
          f"THIN:       {counts['THIN']}")
    print()
    if counts["ORTHOGONAL"] >= 3:
        print("  → STABLE: pressure tendency is an additive C1 axis. Axis is live")
        print("    since 2026-06-20 as axis_3 in c1_confidence_calibration_v2.py;")
        print("    this is a stability re-check pass, not a new candidate.")
    elif counts["REDUNDANT"] >= 0.8 * (32 - counts["THIN"]):
        print("  → KILL: pressure tendency is mostly redundant with other axes.")
    elif counts["CONFOUNDED"] > counts["ORTHOGONAL"]:
        print("  → PROBABLY KILL: pt signal exists only inside transition pairs,")
        print("    which C1 already captures via the regime axis.")
    else:
        print("  → AMBIGUOUS — review the per-cell table; check whether a couple")
        print("    fields are doing all the lifting.")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())

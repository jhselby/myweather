"""1D ims-threshold refit for ch cells that came out STABLE in v5.

Ablation (analysis/l1_selector_ch_ablation.py) established that the
ch cells' entire signal is a threshold on ims. This refits that
threshold cleanly, with the same halves-stable A/B quartile gate v5
uses, and prints a candidate `_IMS_SELECTOR_CELLS` dict block for
weather_collector/processors/l1_selector.py.

For each (regime, band) cell:
  1. Sort by time, split into quartiles Q1..Q4.
  2. Pair A: train = Q1+Q2, val (inner 30%), test = Q3.
  3. Pair B: train = Q2+Q3, val (inner 30%), test = Q4.
  4. Grid search over threshold T and direction (H_low, H_high) on val;
     score by MAE-vs-served on test.
  5. STABLE iff both pairs clear:
       test_lift_pct >= 3%
       test_lift_pct >= 0.5 * train_lift_pct
       0.05 < test_frac_nbm < 0.60

Prints the STABLE cells with their surviving threshold + direction.
Emits a paste-ready _IMS_SELECTOR_CELLS block.

Suspect cells flagged during ablation (trivial-baseline parity) are
excluded from the ship candidate list at the bottom of the output.
"""
import os, sys, json, math
from collections import defaultdict, Counter
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path
from l1_selector_per_obs_classifier_stage1_v5 import (
    MIN_N_CELL, MIN_N_TEST_PER_PAIR, MIN_LIFT_PCT, VAL_FRAC,
    served_mae, build_features,
)

PAIR_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"
FIELD = "ch"

# Sweep every ch cell — v5-STABLE ones plus the pre-existing hardcoded
# _IMS_SELECTOR_CELLS. `CELLS = None` triggers a full sweep of every
# (regime, band) that clears MIN_N_CELL rows.
CELLS = None

# Cells the ablation flagged as suspect (trivial-baseline parity).
SUSPECT = {("se_flow", "0-5h")}


def mae_at_ims_threshold(rows, T, direction):
    """direction 'H_low' = pick NBM when ims >= T; 'H_high' = pick NBM when ims < T."""
    total = 0.0
    nbm_count = 0
    for r in rows:
        ims = r["x"][0]  # ims is column 0
        if direction == "H_low":
            pick_nbm = ims >= T
        else:
            pick_nbm = ims < T
        if pick_nbm:
            total += r["en"]; nbm_count += 1
        else:
            total += r["eh"]
    return total / len(rows), nbm_count / len(rows)


def fit_ims_pair(train_rows, test_rows):
    """Grid-search threshold + direction on val slice, score on test."""
    cut = int(len(train_rows) * (1 - VAL_FRAC))
    fit_rows, val_rows = train_rows[:cut], train_rows[cut:]
    if len(fit_rows) < 100 or len(val_rows) < 60:
        return None

    # Grid: percentiles of ims in the fit set.
    ims_vals = sorted(r["x"][0] for r in fit_rows)
    grid_pcts = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50,
                 55, 60, 65, 70, 75, 80, 85, 90, 95]
    grid = sorted(set(ims_vals[int(len(ims_vals) * p / 100.0)] for p in grid_pcts))

    best = None
    for direction in ("H_low", "H_high"):
        for T in grid:
            m_v, f_v = mae_at_ims_threshold(val_rows, T, direction)
            # non-degenerate on val
            if not (0.05 < f_v < 0.60):
                continue
            if best is None or m_v < best[0]:
                best = (m_v, T, direction)
    if best is None:
        return None
    _, T_star, dir_star = best

    base_te = served_mae(test_rows)
    base_tr = served_mae(train_rows)
    if base_te <= 0 or base_tr <= 0:
        return None

    fit_te, fnbm_te = mae_at_ims_threshold(test_rows, T_star, dir_star)
    fit_tr, fnbm_tr = mae_at_ims_threshold(train_rows, T_star, dir_star)

    return dict(
        T=T_star, direction=dir_star,
        n_train=len(train_rows), n_test=len(test_rows),
        test_lift_pct=(base_te - fit_te) / base_te * 100,
        train_lift_pct=(base_tr - fit_tr) / base_tr * 100,
        test_frac_nbm=fnbm_te, train_frac_nbm=fnbm_tr,
    )


def _pair_clears(p):
    return (
        p["test_lift_pct"] >= MIN_LIFT_PCT and
        p["test_lift_pct"] >= 0.5 * p["train_lift_pct"] and
        0.05 < p["test_frac_nbm"] < 0.60 and
        p["n_test"] >= MIN_N_TEST_PER_PAIR
    )


def main():
    print(f"Loading pair-log for field={FIELD}...")
    fc_by_vt = defaultdict(list)
    rows_raw = []
    with open(cached_path(PAIR_URL), "rb") as fh:
        for raw in fh:
            try: r = json.loads(raw)
            except Exception: continue
            if r.get("field") != FIELD: continue
            vt = r.get("valid_time"); fc = r.get("forecast")
            if vt is not None and fc is not None:
                fc_by_vt[vt].append(float(fc))
            rows_raw.append(r)
    vt_spread = {vt: max(fcs) - min(fcs) for vt, fcs in fc_by_vt.items() if len(fcs) >= 2}
    print(f"  {len(rows_raw):,} raw rows, {len(vt_spread):,} VTs with spread")

    rows_all = list(build_features(rows_raw, vt_spread, Counter()))
    print(f"  {len(rows_all):,} rows after build_features filter\n")

    by_cell = defaultdict(list)
    for r in rows_all:
        by_cell[(r["regime"], r["band"])].append(r)

    print(f"{'cell':<28}{'A T':>8}{'A dir':>10}{'A lift':>10}{'A fNBM':>10}  "
          f"{'B T':>8}{'B dir':>10}{'B lift':>10}{'B fNBM':>10}  verdict")
    print("-" * 130)

    cells_to_test = sorted(by_cell.keys()) if CELLS is None else CELLS
    stable = []
    for regime, band in cells_to_test:
        rows = sorted(by_cell.get((regime, band), []), key=lambda r: r["t"])
        if len(rows) < MIN_N_CELL:
            print(f"{regime+'/'+band:<28}(insufficient rows: {len(rows)})")
            continue
        q = len(rows) // 4
        Q1, Q2, Q3, Q4 = rows[:q], rows[q:2*q], rows[2*q:3*q], rows[3*q:]
        pA = fit_ims_pair(Q1 + Q2, Q3)
        pB = fit_ims_pair(Q2 + Q3, Q4)
        if pA is None or pB is None:
            print(f"{regime+'/'+band:<28}(fit failed)")
            continue
        A_ok = _pair_clears(pA)
        B_ok = _pair_clears(pB)
        # Additional gate: both pairs must agree on direction; otherwise
        # the threshold direction isn't halves-stable.
        dir_ok = pA["direction"] == pB["direction"]
        verdict = "STABLE" if (A_ok and B_ok and dir_ok) else "one-window" if (A_ok or B_ok) else "UNSTABLE"
        marker = "★" if verdict == "STABLE" else " "
        suspect = " (SUSPECT)" if (regime, band) in SUSPECT else ""
        print(f"{regime+'/'+band+suspect:<28}"
              f"{pA['T']:>+8.1f}{pA['direction']:>10}{pA['test_lift_pct']:>+9.2f}%{pA['test_frac_nbm']*100:>9.1f}%  "
              f"{pB['T']:>+8.1f}{pB['direction']:>10}{pB['test_lift_pct']:>+9.2f}%{pB['test_frac_nbm']*100:>9.1f}%  "
              f"{marker} {verdict}")
        if verdict == "STABLE":
            # Ship threshold = mean of A and B thresholds (both directions agree).
            T_ship = (pA["T"] + pB["T"]) / 2.0
            stable.append(dict(
                regime=regime, band=band, T=T_ship, direction=pA["direction"],
                A=pA, B=pB, suspect=(regime, band) in SUSPECT,
            ))

    print()
    if not stable:
        print("VERDICT: no ch cells surviving ims-threshold halves-stable gate.")
        return

    ship = [c for c in stable if not c["suspect"]]
    print(f"VERDICT: {len(stable)} STABLE ims-threshold cell(s) — "
          f"{len(ship)} shippable (excluded {len(stable)-len(ship)} SUSPECT)")

    print()
    print("Candidate _IMS_SELECTOR_CELLS block for l1_selector.py:")
    print("-" * 60)
    print("_IMS_SELECTOR_CELLS = {")
    for c in ship:
        band_key = c["band"].rstrip("h")   # runtime uses "12-23", ablation uses "12-23h"
        print(f'    ({FIELD!r}, {c["regime"]!r:<14}, {band_key!r:<8}): '
              f'({c["T"]:.1f}, {c["direction"]!r}),  '
              f'# A+{c["A"]["test_lift_pct"]:.1f}%/B+{c["B"]["test_lift_pct"]:.1f}%')
    print("}")


if __name__ == "__main__":
    main()

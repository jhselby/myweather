"""Feature ablation on the 4 ch STABLE cells from v5.

For each ch cell that cleared halves-stable, refit the GBM 13 times:
  1. full 12-feature baseline (matches v5)
  2-13. each feature dropped one at a time (drop_one)

The question: does any single feature carry all the lift? If dropping
one feature collapses lift toward zero, that feature is either the
whole signal (probably legit but narrow) or leaky (fake).

Prints a table per cell: feature dropped, resulting halves-stable
test lift (average of pair A and B), delta vs baseline.

Also runs a "trivial-only" fit (just lead_h, sin_hod, cos_hod) to
verify the ch lift is NOT explainable by lead-band + time-of-day
alone.
"""
import os, sys, json, math
from collections import defaultdict, Counter
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path
from l1_selector_per_obs_classifier_stage1_v5 import (
    FEATURE_NAMES, GBM_PARAMS, MIN_N_CELL, MIN_N_TEST_PER_PAIR,
    VAL_FRAC, THETA_GRID, lead_band, hour_local, mae_at_theta,
    served_mae, build_features,
)

PAIR_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"
FIELD = os.environ.get("ABLATION_FIELD", "ch")

# From v5's report today. Override with ABLATION_FIELD=<field>.
CELLS_BY_FIELD = {
    "ch": [
        ("pre_frontal", "12-23h"),
        ("pre_frontal", "6-11h"),
        ("se_flow", "0-5h"),
        ("se_flow", "6-11h"),
    ],
    "sr": [
        ("nw_flow", "12-23h"),
        ("nw_flow", "24-47h"),
        ("se_flow", "12-23h"),
        ("se_flow", "24-47h"),
        ("sw_flow", "6-11h"),
    ],
}
CELLS = CELLS_BY_FIELD[FIELD]


def fit_pair_masked(train_rows, test_rows, feat_mask):
    """Same as v5's fit_pair but ONLY uses features where feat_mask[i]=True."""
    cut = int(len(train_rows) * (1 - VAL_FRAC))
    fit_rows, val_rows = train_rows[:cut], train_rows[cut:]
    if len(fit_rows) < 100 or len(val_rows) < 60:
        return None
    idx = [i for i, m in enumerate(feat_mask) if m]
    if not idx:
        return None
    X_fit = np.array([[r["x"][i] for i in idx] for r in fit_rows], dtype=float)
    y_fit = np.array([r["y"] for r in fit_rows], dtype=float)
    X_val = np.array([[r["x"][i] for i in idx] for r in val_rows], dtype=float)
    y_val = np.array([r["y"] for r in val_rows], dtype=float)
    X_te = np.array([[r["x"][i] for i in idx] for r in test_rows], dtype=float)
    if len(set(y_fit.tolist())) < 2:
        return None
    clf = GradientBoostingClassifier(**GBM_PARAMS)
    clf.fit(X_fit, y_fit)
    val_losses = []
    for pp in clf.staged_predict_proba(X_val):
        pv = np.clip(pp[:, 1], 1e-6, 1 - 1e-6)
        val_losses.append(-float(np.mean(y_val*np.log(pv) + (1-y_val)*np.log(1-pv))))
    best_round = int(np.argmin(val_losses)) + 1
    def _proba_at(X):
        for i, pp in enumerate(clf.staged_predict_proba(X), start=1):
            if i == best_round:
                return pp[:, 1]
        return clf.predict_proba(X)[:, 1]
    p_val = _proba_at(X_val)
    p_te = _proba_at(X_te)
    base_te = served_mae(test_rows)
    if base_te <= 0: return None
    best = None
    for th in THETA_GRID:
        m_v, _ = mae_at_theta(val_rows, p_val, th)
        if best is None or m_v < best[0]:
            best = (m_v, th)
    theta_star = best[1]
    fit_te, fnbm_te = mae_at_theta(test_rows, p_te, theta_star)
    return dict(
        test_lift_pct=(base_te - fit_te) / base_te * 100,
        test_frac_nbm=fnbm_te, n_test=len(test_rows),
    )


def sweep_ablation(rows_all):
    """Full ablation across all 4 ch cells."""
    by_cell = defaultdict(list)
    for r in rows_all:
        by_cell[(r["regime"], r["band"])].append(r)

    print(f"{'cell':<28}{'variant':<28}{'A_liftTe':>10}{'B_liftTe':>10}{'avg':>10}{'delta':>10}")
    print("-" * 100)

    for regime, band in CELLS:
        rows = sorted(by_cell.get((regime, band), []), key=lambda r: r["t"])
        if len(rows) < MIN_N_CELL:
            print(f"{regime+'/'+band:<28}(insufficient rows: {len(rows)})")
            continue
        q = len(rows) // 4
        Q1, Q2, Q3, Q4 = rows[:q], rows[q:2*q], rows[2*q:3*q], rows[3*q:]
        trainA, testA = Q1 + Q2, Q3
        trainB, testB = Q2 + Q3, Q4

        variants = [("(baseline: all 12)", [True]*len(FEATURE_NAMES))]
        for i, name in enumerate(FEATURE_NAMES):
            mask = [True]*len(FEATURE_NAMES); mask[i] = False
            variants.append((f"drop {name}", mask))
        # Trivial-only baseline: lead_h, sin_hod, cos_hod
        trivial_names = ("lead_h", "sin_hod", "cos_hod")
        variants.append(("trivial only (lead+hod)",
                        [n in trivial_names for n in FEATURE_NAMES]))
        # ims-only (does ims alone match the full model?)
        variants.append(("ims only",
                        [n == "ims" for n in FEATURE_NAMES]))

        baseline_avg = None
        cell_lbl = f"{regime}/{band}"
        for label, mask in variants:
            pa = fit_pair_masked(trainA, testA, mask)
            pb = fit_pair_masked(trainB, testB, mask)
            if pa is None or pb is None:
                print(f"{cell_lbl:<28}{label:<28}(fit failed)")
                cell_lbl = ""
                continue
            avg = (pa["test_lift_pct"] + pb["test_lift_pct"]) / 2
            if baseline_avg is None:
                baseline_avg = avg
                delta_str = "—"
            else:
                delta_str = f"{avg - baseline_avg:+.2f}"
            print(f"{cell_lbl:<28}{label:<28}"
                  f"{pa['test_lift_pct']:>+9.2f}%{pb['test_lift_pct']:>+9.2f}%"
                  f"{avg:>+9.2f}%{delta_str:>10}")
            cell_lbl = ""
        print()


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

    sweep_ablation(rows_all)


if __name__ == "__main__":
    main()

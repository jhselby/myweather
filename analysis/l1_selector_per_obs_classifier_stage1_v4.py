"""Stage 1 v4 — non-linear per-obs classifier with halves-stable gate.

Same GBM, same 12 features, same fresh-data pair-log as v3. Stricter
gate: quartile split (Q1-Q4 by time) run as TWO independent pairs,
matching the l1_blender_stage1 halves-stable pattern.

  Pair A: train = Q1+Q2, val = last 30% of that, test = Q3
  Pair B: train = Q2+Q3, val = last 30% of that, test = Q4

STABLE iff BOTH pairs clear:
  • test_lift_pct >= MIN_LIFT_PCT (3%) vs always-HRRR baseline
  • test_lift_pct >= 0.5 × train_lift_pct (no overfit collapse)
  • 0.05 < test_frac_nbm < 0.60 (non-degenerate)

MARGINAL: both pairs same sign of test lift but one below MIN_LIFT_PCT.
one-window: one pair STABLE-eligible, other fails.
UNSTABLE: mixed signs, or neither pair reaches MIN_LIFT_PCT.

v3 promoted 20+ cells on a single time-split — this v4 tests which
of them survive when the test-half window itself has to hold up
across two independent temporal folds. Cells surviving here are
much less likely to be window artifacts.

Field via argv[1] (default: h). Sweep with:
  for f in h ch wg sr cc t dp ws wd; do python3 -m analysis.l1_selector_per_obs_classifier_stage1_v4 $f; done
"""
import os, sys, json, math
from collections import defaultdict
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"
FIELD = sys.argv[1] if len(sys.argv) > 1 else "h"
BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]

MIN_N_CELL = 400          # need n/4 ≥ 100 per quartile
MIN_N_TEST_PER_PAIR = 90  # allow some slack; per-pair test is the smallest slice
MIN_LIFT_PCT = 3.0
VAL_FRAC = 0.30

GBM_PARAMS = dict(
    max_depth=3, min_samples_leaf=30, learning_rate=0.05,
    subsample=0.9, n_estimators=300, random_state=0,
)

THETA_GRID = [i / 20.0 for i in range(4, 17)]

FEATURE_NAMES = [
    "ims", "xr_spread", "lead_h",
    "sin_hod", "cos_hod",
    "cc_inter_sigma", "pressure_trend",
    "wd_sin", "wd_cos",
    "ws_fc", "cloud_low_fc", "solar_wm2_fc",
]


def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def load_pair_log():
    with open(cached_path(PAIR_URL), "rb") as fh:
        for raw in fh:
            try: r = json.loads(raw)
            except Exception: continue
            if r.get("field") != FIELD: continue
            yield r


def hour_local(obs_time):
    try: return int(obs_time[11:13])
    except Exception: return 12


def build_features(rows_raw, vt_spread):
    for r in rows_raw:
        vt = r.get("valid_time")
        xr = vt_spread.get(vt)
        if xr is None: continue
        lead = r.get("lead_h")
        if lead is None: continue
        band = lead_band(int(lead))
        if not band: continue
        fc_l1, fc_nbm_raw = r.get("forecast_l1"), r.get("forecast_raw_nbm")
        err_l4, err_l3_nbm = r.get("error_l4"), r.get("error_l3_nbm")
        if None in (fc_l1, fc_nbm_raw, err_l4, err_l3_nbm): continue
        sfc = r.get("state_fc") or {}
        regime = sfc.get("regime_synoptic")
        if not regime: continue
        cc_sigma = float(r.get("cloud_inter_source_sigma") or 0.0)
        p_trend = float(sfc.get("pressure_trend_hpa_3h") or 0.0)
        hh = hour_local(r.get("obs_time", ""))
        ims = abs(float(fc_l1) - float(fc_nbm_raw))
        wd = sfc.get("wind_dir")
        wd_sin = math.sin(math.radians(float(wd))) if wd is not None else 0.0
        wd_cos = math.cos(math.radians(float(wd))) if wd is not None else 0.0
        ws_fc = float(sfc.get("wind_speed") or 0.0)
        cloud_low_fc = float(sfc.get("cloud_low") or 0.0)
        solar_fc = float(sfc.get("solar_wm2") or 0.0)
        eh = abs(float(err_l4)); en = abs(float(err_l3_nbm))
        yield {
            "regime": regime, "band": band, "t": r.get("obs_time", ""),
            "x": [ims, xr, float(lead),
                  math.sin(2*math.pi*hh/24.0), math.cos(2*math.pi*hh/24.0),
                  cc_sigma, p_trend,
                  wd_sin, wd_cos,
                  ws_fc, cloud_low_fc, solar_fc],
            "y": 1 if en < eh else 0,
            "eh": eh, "en": en,
        }


def mae_at_theta(rows, probs, theta):
    picks = probs > theta
    total = sum((rows[i]["en"] if picks[i] else rows[i]["eh"]) for i in range(len(rows)))
    return total / len(rows), float(picks.mean())


def always_hrrr_mae(rows):
    return sum(r["eh"] for r in rows) / len(rows) if rows else 0.0


def fit_pair(train_rows, test_rows):
    """Fit GBM on train (inner val for theta*), score on test.
    Returns dict with test_lift_pct, train_lift_pct, test_frac_nbm,
    theta_star, n_trees, or None if the pair can't be scored."""
    cut = int(len(train_rows) * (1 - VAL_FRAC))
    fit_rows, val_rows = train_rows[:cut], train_rows[cut:]
    if len(fit_rows) < 100 or len(val_rows) < 60:
        return None

    X_fit = np.array([r["x"] for r in fit_rows], dtype=float)
    y_fit = np.array([r["y"] for r in fit_rows], dtype=float)
    X_val = np.array([r["x"] for r in val_rows], dtype=float)
    y_val = np.array([r["y"] for r in val_rows], dtype=float)
    X_te = np.array([r["x"] for r in test_rows], dtype=float)

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

    p_fit, p_val, p_te = _proba_at(X_fit), _proba_at(X_val), _proba_at(X_te)

    base_tr = always_hrrr_mae(train_rows)
    base_te = always_hrrr_mae(test_rows)
    if base_tr <= 0 or base_te <= 0:
        return None

    best = None
    for th in THETA_GRID:
        m_v, _ = mae_at_theta(val_rows, p_val, th)
        if best is None or m_v < best[0]:
            best = (m_v, th)
    theta_star = best[1]

    p_tr = np.concatenate([p_fit, p_val])
    fit_tr, fnbm_tr = mae_at_theta(train_rows, p_tr, theta_star)
    fit_te, fnbm_te = mae_at_theta(test_rows, p_te, theta_star)

    return dict(
        n_train=len(train_rows), n_test=len(test_rows),
        theta_star=theta_star, n_trees=best_round,
        test_baseline=base_te, test_fit_mae=fit_te,
        train_baseline=base_tr, train_fit_mae=fit_tr,
        test_lift_pct=(base_te - fit_te) / base_te * 100,
        train_lift_pct=(base_tr - fit_tr) / base_tr * 100,
        test_frac_nbm=fnbm_te, train_frac_nbm=fnbm_tr,
    )


def classify(pairA, pairB):
    """STABLE / MARGINAL / one-window / UNSTABLE per l1_blender_stage1
    pattern, adapted to the classifier's lift definition."""
    def _pair_clears(p):
        return (
            p["test_lift_pct"] >= MIN_LIFT_PCT and
            p["test_lift_pct"] >= 0.5 * p["train_lift_pct"] and
            0.05 < p["test_frac_nbm"] < 0.60 and
            p["n_test"] >= MIN_N_TEST_PER_PAIR
        )
    A_ok = _pair_clears(pairA)
    B_ok = _pair_clears(pairB)
    if A_ok and B_ok:
        return "STABLE"
    same_sign = (pairA["test_lift_pct"] > 0) == (pairB["test_lift_pct"] > 0)
    if A_ok or B_ok:
        return "one-window"
    if same_sign and (pairA["test_lift_pct"] + pairB["test_lift_pct"]) / 2 >= MIN_LIFT_PCT:
        return "MARGINAL"
    return "UNSTABLE"


print(f"Loading pair-log for field={FIELD}...")
fc_by_vt = defaultdict(list)
rows_raw = []
for r in load_pair_log():
    vt = r.get("valid_time")
    fc = r.get("forecast")
    if vt is None or fc is None: continue
    fc_by_vt[vt].append(float(fc))
    rows_raw.append(r)
vt_spread = {vt: max(fcs) - min(fcs) for vt, fcs in fc_by_vt.items() if len(fcs) >= 2}
print(f"  {len(rows_raw):,} rows, {len(vt_spread):,} VTs with spread")

by_cell = defaultdict(list)
for row in build_features(rows_raw, vt_spread):
    by_cell[(row["regime"], row["band"])].append(row)

print(f"  {len(by_cell)} (regime, band) cells\n")

print("=" * 148)
print(f"l1_selector_per_obs_classifier_stage1_v4 — GBM halves-stable "
      f"(depth={GBM_PARAMS['max_depth']}, min_leaf={GBM_PARAMS['min_samples_leaf']}, "
      f"lr={GBM_PARAMS['learning_rate']}), field={FIELD}, {len(FEATURE_NAMES)} features")
print("=" * 148)
print(f"{'regime':<14}{'band':<8}{'n':>5}  "
      f"{'A_liftTe':>9}{'A_liftTr':>9}{'A_fNBM':>7}  "
      f"{'B_liftTe':>9}{'B_liftTr':>9}{'B_fNBM':>7}  verdict")
print("-" * 148)

stable = []
all_results = []
for key in sorted(by_cell.keys()):
    regime, band = key
    rows = by_cell[key]
    if len(rows) < MIN_N_CELL: continue
    rows.sort(key=lambda r: r["t"])
    n = len(rows); q = n // 4
    if q < MIN_N_TEST_PER_PAIR: continue
    Q1, Q2, Q3, Q4 = rows[:q], rows[q:2*q], rows[2*q:3*q], rows[3*q:]
    trainA, testA = Q1 + Q2, Q3
    trainB, testB = Q2 + Q3, Q4

    pairA = fit_pair(trainA, testA)
    pairB = fit_pair(trainB, testB)
    if pairA is None or pairB is None: continue

    verdict = classify(pairA, pairB)
    print(f"{regime:<14}{band:<8}{n:>5}  "
          f"{pairA['test_lift_pct']:>+8.2f}%{pairA['train_lift_pct']:>+8.2f}%{pairA['test_frac_nbm']*100:>6.1f}%  "
          f"{pairB['test_lift_pct']:>+8.2f}%{pairB['train_lift_pct']:>+8.2f}%{pairB['test_frac_nbm']*100:>6.1f}%  {verdict}")

    res = dict(
        regime=regime, band=band, n=n,
        pairA=pairA, pairB=pairB,
        verdict=verdict,
    )
    all_results.append(res)
    if verdict == "STABLE":
        stable.append(res)

print("=" * 148)
if stable:
    print(f"VERDICT: STAGE 1 STABLE — {len(stable)} cell(s) clear halves-stable non-linear per-obs classifier gate.")
    for r in stable:
        avg_lift = (r["pairA"]["test_lift_pct"] + r["pairB"]["test_lift_pct"]) / 2
        avg_fnbm = (r["pairA"]["test_frac_nbm"] + r["pairB"]["test_frac_nbm"]) / 2 * 100
        print(f"           {r['regime']:<14}{r['band']:<8}  "
              f"avg testLift +{avg_lift:.2f}%  avg fNBM_te={avg_fnbm:.1f}%  "
              f"n={r['n']}")
else:
    print(f"VERDICT: STAGE 1 HOLD — no cell survives halves-stable test on field={FIELD}.")
print("=" * 148)

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output",
                       f"l1_selector_per_obs_classifier_stage1_v4_{FIELD}.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as fh:
    json.dump({
        "field": FIELD, "features": FEATURE_NAMES,
        "model": "sklearn.GradientBoostingClassifier",
        "params": GBM_PARAMS, "min_lift_pct": MIN_LIFT_PCT,
        "cells": all_results,
        "stable": [{"regime": r["regime"], "band": r["band"],
                    "avg_test_lift_pct": (r["pairA"]["test_lift_pct"] + r["pairB"]["test_lift_pct"]) / 2}
                   for r in stable],
    }, fh, indent=2)
print(f"wrote {out_path}")

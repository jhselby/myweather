"""Stage 1 v3 — per-obs classifier, NON-LINEAR (LightGBM) model.

Identical in every way to v2b except the fit/predict block: same 12
features, same (regime, band) cells, same halves-stable time split,
same nested val slice for θ sweep, same MIN_LIFT_PCT / MIN_N_TEST /
non-degenerate gate. Only difference: instead of L2 logistic
regression, fit a shallow LightGBM classifier on the fit slice.

Question the experiment answers: does a non-linear decision boundary
recover per-obs signal that the linear v2b couldn't? v2b on fresh
data (2026-09-24) returned STAGE 1 HOLD across h and t with every
cell marked "degenerate" (fNBM 67-99%) — a signature that either the
features don't carry per-obs signal OR the linear model can't
separate the classes. This experiment isolates which.

Read: cell-level test lift ≥ +3% halves-stable that v2b did NOT clear
is evidence the features DO carry signal and non-linear is worth
promoting further. Continued STAGE 1 HOLD is evidence the feature
set — not the model class — is the bottleneck.

Not for shipping curated tables in this form. If any cell clears,
lift ≥ +5% at Stage 1, promote to a proper CV + Stage 2 walk-forward
before writing a live selector table.

Field via argv[1] (default: h). Run: python3 -m analysis.l1_selector_per_obs_classifier_stage1_v3 h
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
MIN_N_CELL = 400
MIN_N_TEST = 150
MIN_LIFT_PCT = 3.0
VAL_FRAC = 0.30

# Gradient-boosted trees — deliberately small model. Cell training
# sets are ~200-800 rows; deep trees would overfit. max_depth 3,
# min_samples_leaf 30 (kills single-noisy-row splits), subsample 0.9
# (small stochastic bagging). n_estimators is walked; early stop uses
# staged_predict against the val slice to pick round count honestly.
GBM_PARAMS = dict(
    max_depth=3,
    min_samples_leaf=30,
    learning_rate=0.05,
    subsample=0.9,
    n_estimators=300,
    random_state=0,
)
EARLY_STOP_PATIENCE = 20

THETA_GRID = [i / 20.0 for i in range(4, 17)]

FEATURE_NAMES = [
    "ims", "xr_spread", "lead_h",
    "sin_hod", "cos_hod",
    "cc_inter_sigma",
    "pressure_trend",
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
    try:
        return int(obs_time[11:13])
    except Exception:
        return 12


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
            "x": [
                ims, xr, float(lead),
                math.sin(2 * math.pi * hh / 24.0),
                math.cos(2 * math.pi * hh / 24.0),
                cc_sigma, p_trend,
                wd_sin, wd_cos,
                ws_fc, cloud_low_fc, solar_fc,
            ],
            "y": 1 if en < eh else 0,
            "eh": eh, "en": en,
        }


def mae_at_theta(rows, probs, theta):
    picks_nbm = probs > theta
    total = 0.0
    for i, r in enumerate(rows):
        total += r["en"] if picks_nbm[i] else r["eh"]
    return total / len(rows), float(picks_nbm.mean())


def always_hrrr_mae(rows):
    return sum(r["eh"] for r in rows) / len(rows) if rows else 0.0


def per_obs_oracle_mae(rows):
    return sum(min(r["eh"], r["en"]) for r in rows) / len(rows) if rows else 0.0


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

print("=" * 145)
print(f"l1_selector_per_obs_classifier_stage1_v3 — GBM (depth={GBM_PARAMS['max_depth']}, "
      f"min_leaf={GBM_PARAMS['min_samples_leaf']}, lr={GBM_PARAMS['learning_rate']}), "
      f"field={FIELD}, {len(FEATURE_NAMES)} features")
print("=" * 145)
print(f"{'regime':<14}{'band':<8}{'nTr':>5}{'nTe':>5}  "
      f"{'nTrees':>7}  {'θ*':>5}  "
      f"{'baseHR_Te':>9}{'fitMAE_Te':>9}{'liftTe%':>8}  "
      f"{'baseHR_Tr':>9}{'fitMAE_Tr':>9}{'liftTr%':>8}  "
      f"{'oracleTe':>8}{'capture%':>9}  {'fNBM_Te':>7}  verdict")
print("-" * 145)

promote = []
all_results = []
for key in sorted(by_cell.keys()):
    regime, band = key
    rows = by_cell[key]
    if len(rows) < MIN_N_CELL: continue
    rows.sort(key=lambda r: r["t"])
    mid = len(rows) // 2
    tr_full, te = rows[:mid], rows[mid:]
    if len(te) < MIN_N_TEST: continue
    cut = int(len(tr_full) * (1 - VAL_FRAC))
    fit_rows, val_rows = tr_full[:cut], tr_full[cut:]
    if len(fit_rows) < 100 or len(val_rows) < 60: continue

    X_fit = np.array([r["x"] for r in fit_rows], dtype=float)
    y_fit = np.array([r["y"] for r in fit_rows], dtype=float)
    X_val = np.array([r["x"] for r in val_rows], dtype=float)
    y_val = np.array([r["y"] for r in val_rows], dtype=float)
    X_te = np.array([r["x"] for r in te], dtype=float)

    # No standardization needed for trees — scale-invariant.
    # Fit full n_estimators then walk staged_predict on val to pick
    # best round; use that many trees for test prediction.
    clf = GradientBoostingClassifier(**GBM_PARAMS)
    clf.fit(X_fit, y_fit)

    # Walk val log-loss per round; take round with min loss + patience gate
    val_losses = []
    for p in clf.staged_predict_proba(X_val):
        pv = np.clip(p[:, 1], 1e-6, 1 - 1e-6)
        val_losses.append(-float(np.mean(y_val * np.log(pv) + (1 - y_val) * np.log(1 - pv))))
    best_round = int(np.argmin(val_losses)) + 1  # 1-indexed
    n_trees = best_round

    # Predict at best_round via staged_predict_proba on each set
    def _proba_at_round(X, r):
        for i, pp in enumerate(clf.staged_predict_proba(X), start=1):
            if i == r:
                return pp[:, 1]
        return clf.predict_proba(X)[:, 1]

    p_fit = _proba_at_round(X_fit, best_round)
    p_val = _proba_at_round(X_val, best_round)
    p_te = _proba_at_round(X_te, best_round)

    base_tr = always_hrrr_mae(tr_full)
    base_te = always_hrrr_mae(te)
    oracle_te = per_obs_oracle_mae(te)
    if base_tr <= 0 or base_te <= 0: continue

    best = None
    for th in THETA_GRID:
        m_v, _ = mae_at_theta(val_rows, p_val, th)
        if best is None or m_v < best[0]:
            best = (m_v, th)
    _, theta_star = best

    p_tr_full = np.concatenate([p_fit, p_val])
    fit_tr, fnbm_tr = mae_at_theta(tr_full, p_tr_full, theta_star)
    fit_te, fnbm_te = mae_at_theta(te, p_te, theta_star)

    lift_tr = (base_tr - fit_tr) / base_tr * 100
    lift_te = (base_te - fit_te) / base_te * 100
    capture = (base_te - fit_te) / max(base_te - oracle_te, 1e-9) * 100

    non_degenerate = 0.05 < fnbm_te < 0.60
    is_promote = (
        lift_te >= MIN_LIFT_PCT and lift_tr >= MIN_LIFT_PCT and
        lift_te >= 0.5 * lift_tr and len(te) >= MIN_N_TEST and
        non_degenerate
    )
    verdict = "★ PROMOTE" if is_promote else (
        "degenerate" if not non_degenerate else
        "overfit" if lift_tr >= MIN_LIFT_PCT and lift_te < MIN_LIFT_PCT else
        "weak" if lift_tr >= 1.0 or lift_te >= 1.0 else "-"
    )
    print(f"{regime:<14}{band:<8}{len(tr_full):>5}{len(te):>5}  "
          f"{n_trees:>7}  {theta_star:>5.2f}  "
          f"{base_te:>9.3f}{fit_te:>9.3f}{lift_te:>+7.2f}%  "
          f"{base_tr:>9.3f}{fit_tr:>9.3f}{lift_tr:>+7.2f}%  "
          f"{oracle_te:>8.3f}{capture:>+8.1f}%  {fnbm_te*100:>6.1f}%  {verdict}")

    res = {
        "regime": regime, "band": band,
        "n_train": len(tr_full), "n_test": len(te),
        "n_trees": int(n_trees),
        "theta_star": theta_star,
        "test_baseline": base_te, "test_fit_mae": fit_te,
        "train_baseline": base_tr, "train_fit_mae": fit_tr,
        "test_oracle": oracle_te,
        "test_lift_pct": lift_te, "train_lift_pct": lift_tr,
        "test_capture_pct": capture,
        "test_frac_nbm": fnbm_te, "train_frac_nbm": fnbm_tr,
    }
    all_results.append(res)
    if is_promote:
        promote.append(res)

print("=" * 145)
if promote:
    print(f"VERDICT: STAGE 1 PROMOTE — {len(promote)} cell(s) clear held-out MAE lift ≥ {MIN_LIFT_PCT}% halves-stable,")
    print(f"         non-degenerate NBM fraction (5-60%), no overfit collapse. Non-linear DOES recover signal here.")
    for r in promote:
        print(f"           {r['regime']:<14}{r['band']:<8}  θ*={r['theta_star']:.2f}  "
              f"test +{r['test_lift_pct']:.2f}% (train +{r['train_lift_pct']:.2f}%)  "
              f"captured {r['test_capture_pct']:.1f}% of gap  fNBM_te={r['test_frac_nbm']*100:.1f}%")
else:
    print(f"VERDICT: STAGE 1 HOLD — no cell clears held-out MAE lift ≥ {MIN_LIFT_PCT}% halves-stable.")
    print(f"         Non-linear (LightGBM) with these 12 features found no per-obs signal on field={FIELD}.")
    print(f"         Combined with v2b HOLD (linear same features), this bounds the ceiling: the")
    print(f"         feature set — not the model class — is the bottleneck. Enrich features before re-trying.")
print("=" * 145)

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output",
                       f"l1_selector_per_obs_classifier_stage1_v3_{FIELD}.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as fh:
    json.dump({
        "field": FIELD, "features": FEATURE_NAMES, "model": "sklearn.GradientBoostingClassifier",
        "params": GBM_PARAMS,
        "min_lift_pct": MIN_LIFT_PCT, "cells": all_results,
        "promote": [{"regime": r["regime"], "band": r["band"], "theta_star": r["theta_star"],
                     "test_lift_pct": r["test_lift_pct"]} for r in promote],
    }, fh, indent=2)
print(f"wrote {out_path}")

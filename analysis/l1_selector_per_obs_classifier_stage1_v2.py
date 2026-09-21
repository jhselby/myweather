"""Stage 1 v2b — per-obs continuous classifier for the L1 selector.

v2 (2026-09-20 parked): 8 features, hand-rolled L2 logistic. Best cell
(pre_frontal/6-11h on t) captured 10% of oracle gap out-of-sample —
real signal but sub-gate. Diagnosis: 8-feature linear model missed
physical drivers of per-obs disagreement (BL coupling, radiation,
advection sign, daytime solar).

v2b (2026-09-21): extended to 12 features. Added:
    wind_dir_sin, wind_dir_cos  — advection sign (cold vs warm advection
        flips which model is right; HRRR PBL bias depends on which way
        the wind is blowing)
    wind_speed_fc  — BL coupling proxy (light wind → decoupled BL →
        HRRR overshoots night cooling and morning heating)
    cloud_low_fc   — radiation coupling (cl_low blocks night cooling,
        modulates HRRR's diurnal bias)
    solar_wm2_fc   — daytime driver (finer than hour_of_day for cells
        where sun angle matters — captures season+cloud combined)
Bumped L2 to 5.0 given feature count.

Rule shape: per (regime, band), fit L2-regularized logistic regression
on the train half:
    P(NBM wins | features) = sigmoid(β0 + β·x)
Route the row to NBM iff P > θ, else HRRR. Sweep θ on val slice
(nested inside train); take θ* that minimizes val MAE. Apply θ* on
test → test MAE.

Gates (Stage 1):
  • test_lift_pct >= MIN_LIFT_PCT  (vs always-HRRR)
  • train_lift_pct >= MIN_LIFT_PCT
  • test_lift_pct >= 0.5 * train_lift_pct  (no overfit collapse)
  • n_test >= MIN_N_TEST
  • fraction of test rows routed to NBM in (0.05, 0.60) — avoid degenerate
    always-HRRR / always-NBM (which would just reproduce the baseline
    or fall off cliff).

Field via argv[1] (default: t).
"""
import os, sys, json, math
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"
FIELD = sys.argv[1] if len(sys.argv) > 1 else "t"
BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N_CELL = 400
MIN_N_TEST = 150
MIN_LIFT_PCT = 3.0
L2_LAMBDA = 5.0     # bumped from 3.0 (09-21 v2b): more features, keep overfit floor
IRLS_MAX_ITER = 50
IRLS_TOL = 1e-6
THETA_GRID = [i / 20.0 for i in range(4, 17)]   # 0.20 .. 0.80
VAL_FRAC = 0.30     # last 30% of train half used to pick theta*

FEATURE_NAMES = [
    "ims", "xr_spread", "lead_h",
    "sin_hod", "cos_hod",
    "cc_disagree", "cc_inter_sigma",
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
    # obs_time like "2026-09-19T14:00:00-04:00" or "...Z"; take the "T HH"
    try:
        hh = int(obs_time[11:13])
    except Exception:
        return 12  # fallback
    return hh


def build_features(rows_raw, vt_spread):
    """Yield dicts with x (list), y (0/1 NBM wins), eh, en, regime, band, t."""
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
        sob = r.get("state_obs") or {}
        regime = sfc.get("regime_synoptic")
        if not regime: continue
        cc_fc, cc_obs = sfc.get("cloud_cover"), sob.get("cloud_cover")
        cc_disagree = abs(float(cc_fc) - float(cc_obs)) if cc_fc is not None and cc_obs is not None else 0.0
        cc_sigma = float(r.get("cloud_inter_source_sigma") or 0.0)
        p_trend = float(sfc.get("pressure_trend_hpa_3h") or 0.0)
        hh = hour_local(r.get("obs_time", ""))
        ims = abs(float(fc_l1) - float(fc_nbm_raw))
        # New physics features
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
                cc_disagree, cc_sigma, p_trend,
                wd_sin, wd_cos,
                ws_fc, cloud_low_fc, solar_fc,
            ],
            "y": 1 if en < eh else 0,
            "eh": eh, "en": en,
        }


def standardize(X_train, X_test):
    """Return X_train_z, X_test_z, mu, sd (per feature)."""
    mu = X_train.mean(axis=0)
    sd = X_train.std(axis=0)
    sd[sd < 1e-8] = 1.0
    return (X_train - mu) / sd, (X_test - mu) / sd, mu, sd


def sigmoid(z):
    z = np.clip(z, -30, 30)
    return 1.0 / (1.0 + np.exp(-z))


def fit_logistic_l2(X, y, lam):
    """IRLS for L2-regularized logistic regression. X includes intercept column."""
    n, k = X.shape
    beta = np.zeros(k)
    reg = lam * np.eye(k)
    reg[0, 0] = 0.0  # don't regularize intercept
    for _ in range(IRLS_MAX_ITER):
        p = sigmoid(X @ beta)
        w = p * (1 - p)
        w = np.clip(w, 1e-6, None)
        # gradient and Hessian of NLL + L2
        grad = X.T @ (p - y) + reg @ beta
        H = X.T @ (X * w[:, None]) + reg
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        beta_new = beta - step
        if np.max(np.abs(beta_new - beta)) < IRLS_TOL:
            beta = beta_new
            break
        beta = beta_new
    return beta


def mae_at_theta(rows, probs, theta):
    """MAE if we pick NBM when prob > theta, else HRRR."""
    picks_nbm = probs > theta
    frac_nbm = float(picks_nbm.mean())
    total = 0.0
    for i, r in enumerate(rows):
        total += r["en"] if picks_nbm[i] else r["eh"]
    return total / len(rows), frac_nbm


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

print("=" * 132)
print(f"l1_selector_per_obs_classifier_stage1_v2b — logistic on {len(FEATURE_NAMES)} features, field={FIELD}, L2={L2_LAMBDA}")
print("=" * 132)
print(f"{'regime':<14}{'band':<8}{'nTr':>5}{'nTe':>5}  "
      f"{'θ*':>5}  {'baseHR_Te':>9}{'fitMAE_Te':>9}{'liftTe%':>8}  "
      f"{'baseHR_Tr':>9}{'fitMAE_Tr':>9}{'liftTr%':>8}  "
      f"{'oracleTe':>8}{'capture%':>9}  {'fNBM_Te':>7}  verdict")
print("-" * 132)

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
    # nested split of train: fit on first (1-VAL_FRAC), pick θ* on last VAL_FRAC
    cut = int(len(tr_full) * (1 - VAL_FRAC))
    fit_rows, val_rows = tr_full[:cut], tr_full[cut:]
    if len(fit_rows) < 100 or len(val_rows) < 60: continue

    X_fit = np.array([r["x"] for r in fit_rows], dtype=float)
    y_fit = np.array([r["y"] for r in fit_rows], dtype=float)
    X_val = np.array([r["x"] for r in val_rows], dtype=float)
    X_te = np.array([r["x"] for r in te], dtype=float)

    # standardize using fit-slice moments only
    mu = X_fit.mean(axis=0); sd = X_fit.std(axis=0); sd[sd < 1e-8] = 1.0
    X_fit_z = (X_fit - mu) / sd
    X_val_z = (X_val - mu) / sd
    X_te_z = (X_te - mu) / sd
    Xf = np.hstack([np.ones((len(fit_rows), 1)), X_fit_z])
    Xv = np.hstack([np.ones((len(val_rows), 1)), X_val_z])
    Xe = np.hstack([np.ones((len(te), 1)), X_te_z])

    beta = fit_logistic_l2(Xf, y_fit, L2_LAMBDA)
    p_val = sigmoid(Xv @ beta)
    p_te = sigmoid(Xe @ beta)
    p_fit = sigmoid(Xf @ beta)

    base_tr = always_hrrr_mae(tr_full)
    base_te = always_hrrr_mae(te)
    oracle_te = per_obs_oracle_mae(te)
    if base_tr <= 0 or base_te <= 0: continue

    # sweep theta on VALIDATION slice only (fit is untouched)
    best = None
    for th in THETA_GRID:
        m_v, _ = mae_at_theta(val_rows, p_val, th)
        if best is None or m_v < best[0]:
            best = (m_v, th)
    _, theta_star = best
    # train_MAE for display: apply θ* to full train (fit + val) using their probs
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
          f"{theta_star:>5.2f}  {base_te:>9.3f}{fit_te:>9.3f}{lift_te:>+7.2f}%  "
          f"{base_tr:>9.3f}{fit_tr:>9.3f}{lift_tr:>+7.2f}%  "
          f"{oracle_te:>8.3f}{capture:>+8.1f}%  {fnbm_te*100:>6.1f}%  {verdict}")

    res = {
        "regime": regime, "band": band,
        "n_train": len(tr_full), "n_test": len(te),
        "theta_star": theta_star,
        "test_baseline": base_te, "test_fit_mae": fit_te,
        "train_baseline": base_tr, "train_fit_mae": fit_tr,
        "test_oracle": oracle_te,
        "test_lift_pct": lift_te, "train_lift_pct": lift_tr,
        "test_capture_pct": capture,
        "test_frac_nbm": fnbm_te, "train_frac_nbm": fnbm_tr,
        "beta_std": beta.tolist(),  # first is intercept, then FEATURE_NAMES order
    }
    all_results.append(res)
    if is_promote:
        promote.append(res)

print("=" * 132)
if promote:
    print(f"VERDICT: STAGE 1 PROMOTE — {len(promote)} cell(s) clear held-out MAE lift ≥ {MIN_LIFT_PCT}% halves-stable,")
    print(f"         non-degenerate NBM fraction (5-60%), no overfit collapse. Advance to Stage 2.")
    for r in promote:
        print(f"           {r['regime']:<14}{r['band']:<8}  θ*={r['theta_star']:.2f}  "
              f"test +{r['test_lift_pct']:.2f}% (train +{r['train_lift_pct']:.2f}%)  "
              f"captured {r['test_capture_pct']:.1f}% of gap  fNBM_te={r['test_frac_nbm']*100:.1f}%")
else:
    print(f"VERDICT: STAGE 1 HOLD — no cell clears held-out MAE lift ≥ {MIN_LIFT_PCT}% halves-stable.")
    print(f"         Field={FIELD} may need richer features, different regularization, or a")
    print(f"         non-linear model — but likely the per-obs signal isn't recoverable with this")
    print(f"         feature set on this data window.")
print("=" * 132)

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output",
                       f"l1_selector_per_obs_classifier_stage1_v2b_{FIELD}.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as fh:
    json.dump({
        "field": FIELD, "features": FEATURE_NAMES, "l2_lambda": L2_LAMBDA,
        "min_lift_pct": MIN_LIFT_PCT, "cells": all_results,
        "promote": [{"regime": r["regime"], "band": r["band"], "theta_star": r["theta_star"],
                     "test_lift_pct": r["test_lift_pct"]} for r in promote],
    }, fh, indent=2)
print(f"wrote {out_path}")

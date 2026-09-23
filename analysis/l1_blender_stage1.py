"""Stage 1 — per-obs blender for the L1 selector seat.

Successor to `l1_selector_per_obs_classifier_stage1_v2.py`. Same 12-feature
plumbing; different prediction target: continuous blend weight ω ∈ [0,1]
via L2 ridge regression on per-row optimal ω* = clip((y-N)/(H-N), 0, 1),
instead of binary sigmoid over {H, N}.

Motivation: the picker plateaus at ~20-30% oracle capture, EVER, because
binary loss is discontinuous — a slightly-off choice pays the full HRRR-NBM
gap. A continuous blend captures the "both partially right" majority.
See project_l1_selector_blend_vs_pick.md.

Inputs — pipeline-END outputs, not raw:
  HRRR:  forecast_l6 (ch, t) → l5 (sr) → l4 (dp, h, wg), with fallback.
  NBM:   forecast_l3_nbm → l2_nbm → forecast_raw_nbm, with fallback.

Gates: per (regime, band) cell needs BOTH walk-forward pairs to clear
  • test-lift-vs-BEST-single-source ≥ MIN_LIFT_PCT
  • test-lift-vs-HRRR ≥ 0.5 * train-lift-vs-HRRR (no overfit collapse)
  • ω_mean drift across pairs ≤ OMEGA_DRIFT_TOL
  • n_test ≥ MIN_N_TEST
  • ω_mean ∈ (0.05, 0.95) — non-degenerate blend, not just always-one-source

Baseline is BEST single source (min of HRRR-MAE and NBM-MAE). Beating the
already-serving side is the honest bar — the selector routes to that side
today.

Field via argv[1] (default: dp).
"""
import os, sys, json, math
from collections import defaultdict
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"
FIELD = sys.argv[1] if len(sys.argv) > 1 else "dp"

BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
HRRR_TERMINAL = {"ch": "forecast_l6", "t": "forecast_l6",
                 "sr": "forecast_l5",
                 "dp": "forecast_l4", "h": "forecast_l4", "wg": "forecast_l4"}
HRRR_FALLBACK = ["forecast_l6", "forecast_l5", "forecast_l4", "forecast_l3", "forecast_l2"]
NBM_FALLBACK = ["forecast_l3_nbm", "forecast_l2_nbm", "forecast_raw_nbm"]

MIN_N_CELL = 800
MIN_N_TEST = 100
MIN_LIFT_PCT = 3.0
OVERFIT_RATIO = 0.5
OMEGA_DRIFT_TOL = 0.15
OMEGA_DEGEN_LO = 0.05
OMEGA_DEGEN_HI = 0.95
RIDGE_LAMBDA = 5.0

FEATURE_NAMES = [
    "ims", "xr_spread", "lead_h",
    "sin_hod", "cos_hod",
    "cc_inter_sigma", "pressure_trend",
    "wd_sin", "wd_cos",
    "ws_fc", "cloud_low_fc", "solar_wm2_fc",
]


def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi: return label
    return None


def hour_local(t):
    try: return int(t[11:13])
    except: return 12


def get_hrrr(r, field):
    v = r.get(HRRR_TERMINAL.get(field, "forecast_l4"))
    if v is not None: return v
    for k in HRRR_FALLBACK:
        v = r.get(k)
        if v is not None: return v
    return None


def get_nbm(r):
    for k in NBM_FALLBACK:
        v = r.get(k)
        if v is not None: return v
    return None


def optimal_omega(h, n, y):
    if abs(h - n) < 1e-9: return 0.5
    return max(0.0, min(1.0, (y - n) / (h - n)))


def load_cells(field):
    fc_by_vt = defaultdict(list)
    raw = []
    with open(cached_path(PAIR_URL)) as fh:
        for line in fh:
            try: r = json.loads(line)
            except Exception: continue
            if r.get("field") != field: continue
            vt, fc = r.get("valid_time"), r.get("forecast")
            if vt is not None and fc is not None:
                fc_by_vt[vt].append(float(fc))
            raw.append(r)
    vt_spread = {vt: max(f) - min(f) for vt, f in fc_by_vt.items() if len(f) >= 2}

    cells = defaultdict(list)
    dropped_no_nbm = 0
    for r in raw:
        vt, xr = r.get("valid_time"), vt_spread.get(r.get("valid_time"))
        if xr is None: continue
        lead = r.get("lead_h")
        if lead is None: continue
        band = lead_band(int(lead))
        if not band: continue
        fc_h = get_hrrr(r, field); fc_n = get_nbm(r); obs = r.get("observed")
        if None in (fc_h, fc_n, obs):
            if fc_n is None: dropped_no_nbm += 1
            continue
        sfc = r.get("state_fc") or {}
        regime = sfc.get("regime_synoptic")
        if not regime: continue
        h_val, n_val, y_val = float(fc_h), float(fc_n), float(obs)
        ims = abs(h_val - n_val)
        cc_sigma = float(r.get("cloud_inter_source_sigma") or 0.0)
        p_trend = float(sfc.get("pressure_trend_hpa_3h") or 0.0)
        hh = hour_local(r.get("obs_time", ""))
        wd = sfc.get("wind_dir")
        wd_sin = math.sin(math.radians(float(wd))) if wd is not None else 0.0
        wd_cos = math.cos(math.radians(float(wd))) if wd is not None else 0.0
        ws_fc = float(sfc.get("wind_speed") or 0.0)
        cloud_low_fc = float(sfc.get("cloud_low") or 0.0)
        solar_fc = float(sfc.get("solar_wm2") or 0.0)
        x = [ims, xr, float(lead),
             math.sin(2*math.pi*hh/24.0), math.cos(2*math.pi*hh/24.0),
             cc_sigma, p_trend, wd_sin, wd_cos, ws_fc, cloud_low_fc, solar_fc]
        cells[(regime, band)].append({
            "t": r.get("obs_time", ""),
            "h": h_val, "n": n_val, "y": y_val, "x": x,
        })
    return cells, dropped_no_nbm


def fit_ridge(train, lam=RIDGE_LAMBDA):
    X = np.array([r["x"] for r in train], dtype=float)
    y = np.array([optimal_omega(r["h"], r["n"], r["y"]) for r in train], dtype=float)
    mu, sd = X.mean(axis=0), X.std(axis=0); sd[sd < 1e-8] = 1.0
    Xz = (X - mu) / sd
    X1 = np.hstack([np.ones((len(train), 1)), Xz])
    reg = lam * np.eye(X1.shape[1]); reg[0,0] = 0.0
    beta = np.linalg.solve(X1.T @ X1 + reg, X1.T @ y)
    return beta, mu, sd


def apply_ridge(beta, mu, sd, rows):
    X = np.array([r["x"] for r in rows], dtype=float)
    Xz = (X - mu) / sd
    X1 = np.hstack([np.ones((len(rows), 1)), Xz])
    return np.clip(X1 @ beta, 0.0, 1.0)


def mae(rows, pick_fn):
    return sum(abs(pick_fn(r) - r["y"]) for r in rows) / len(rows)


def score_pair(train, test):
    beta, mu, sd = fit_ridge(train)
    hr_tr = mae(train, lambda r: r["h"])
    hr_te = mae(test, lambda r: r["h"])
    nb_te = mae(test, lambda r: r["n"])
    w_tr = apply_ridge(beta, mu, sd, train)
    w_te = apply_ridge(beta, mu, sd, test)
    m_tr = sum(abs(w_tr[i]*train[i]["h"] + (1-w_tr[i])*train[i]["n"] - train[i]["y"])
               for i in range(len(train))) / len(train)
    m_te = sum(abs(w_te[i]*test[i]["h"]  + (1-w_te[i])*test[i]["n"]  - test[i]["y"])
               for i in range(len(test))) / len(test)
    best_te = min(hr_te, nb_te)
    return {
        "train_lift_vs_hrrr_pct": 100*(hr_tr - m_tr)/hr_tr if hr_tr > 0 else 0.0,
        "test_lift_vs_hrrr_pct":  100*(hr_te - m_te)/hr_te if hr_te > 0 else 0.0,
        "test_lift_vs_best_pct":  100*(best_te - m_te)/best_te if best_te > 0 else 0.0,
        "hrrr_mae_te": hr_te, "nbm_mae_te": nb_te, "blend_mae_te": m_te,
        "omega_mean_te": float(w_te.mean()),
        "omega_std_te":  float(w_te.std()),
        "beta": beta.tolist(), "mu": mu.tolist(), "sd": sd.tolist(),
    }


def classify(pairA, pairB):
    both_ship = pairA["test_lift_vs_best_pct"] >= MIN_LIFT_PCT and pairB["test_lift_vs_best_pct"] >= MIN_LIFT_PCT
    not_overfit = (
        (pairA["train_lift_vs_hrrr_pct"] <= 0 or pairA["test_lift_vs_hrrr_pct"] >= OVERFIT_RATIO * pairA["train_lift_vs_hrrr_pct"]) and
        (pairB["train_lift_vs_hrrr_pct"] <= 0 or pairB["test_lift_vs_hrrr_pct"] >= OVERFIT_RATIO * pairB["train_lift_vs_hrrr_pct"])
    )
    omega_stable = abs(pairA["omega_mean_te"] - pairB["omega_mean_te"]) <= OMEGA_DRIFT_TOL
    om_mu = (pairA["omega_mean_te"] + pairB["omega_mean_te"]) / 2
    non_degen = OMEGA_DEGEN_LO < om_mu < OMEGA_DEGEN_HI
    same_sign = (pairA["test_lift_vs_best_pct"] > 0) == (pairB["test_lift_vs_best_pct"] > 0)
    if both_ship and not_overfit and omega_stable and non_degen: return "STABLE"
    if both_ship and same_sign: return "MARGINAL"
    if same_sign and (pairA["test_lift_vs_best_pct"] + pairB["test_lift_vs_best_pct"]) / 2 >= MIN_LIFT_PCT: return "one-window"
    return "UNSTABLE"


def main():
    print(f"Loading pair log for field={FIELD}, HRRR terminal={HRRR_TERMINAL.get(FIELD, 'l4')}")
    cells, dropped = load_cells(FIELD)
    print(f"  {len(cells)} cells; {dropped} rows dropped (no NBM)")

    print("=" * 148)
    print(f"l1_blender_stage1 — ridge on ω, field={FIELD}, features={len(FEATURE_NAMES)}, λ={RIDGE_LAMBDA}")
    print("=" * 148)
    print(f"{'regime':<14}{'band':<8}{'n':>5}  "
          f"{'HR_te':>6}{'NB_te':>6}  "
          f"{'A_v_best':>9}{'A_v_HR':>8}{'A_ω̄':>6}  "
          f"{'B_v_best':>9}{'B_v_HR':>8}{'B_ω̄':>6}  verdict")
    print("-" * 148)

    all_results = []
    stable_cells = []

    for key in sorted(cells.keys()):
        regime, band = key
        rows = cells[key]
        if len(rows) < MIN_N_CELL: continue
        rows.sort(key=lambda r: r["t"])
        n = len(rows); q = n // 4
        if q < 100: continue
        Q1, Q2, Q3, Q4 = rows[:q], rows[q:2*q], rows[2*q:3*q], rows[3*q:]
        trA, teA = Q1 + Q2, Q3
        trB, teB = Q2 + Q3, Q4
        if min(len(teA), len(teB)) < MIN_N_TEST: continue

        pairA = score_pair(trA, teA)
        pairB = score_pair(trB, teB)
        verdict = classify(pairA, pairB)

        print(f"{regime:<14}{band:<8}{n:>5}  "
              f"{pairA['hrrr_mae_te']:>6.2f}{pairA['nbm_mae_te']:>6.2f}  "
              f"{pairA['test_lift_vs_best_pct']:>+9.2f}{pairA['test_lift_vs_hrrr_pct']:>+8.2f}{pairA['omega_mean_te']:>6.2f}  "
              f"{pairB['test_lift_vs_best_pct']:>+9.2f}{pairB['test_lift_vs_hrrr_pct']:>+8.2f}{pairB['omega_mean_te']:>6.2f}  "
              f"{verdict}")

        # For the curated table we use pairB (later train window) — it's the closest
        # to what a fresh-fit deploy would produce today. beta/mu/sd stored from B.
        rec = {
            "regime": regime, "band": band, "n": n, "verdict": verdict,
            "pair_A": {k: pairA[k] for k in ["train_lift_vs_hrrr_pct", "test_lift_vs_hrrr_pct",
                                               "test_lift_vs_best_pct", "hrrr_mae_te", "nbm_mae_te",
                                               "blend_mae_te", "omega_mean_te", "omega_std_te"]},
            "pair_B": {k: pairB[k] for k in ["train_lift_vs_hrrr_pct", "test_lift_vs_hrrr_pct",
                                               "test_lift_vs_best_pct", "hrrr_mae_te", "nbm_mae_te",
                                               "blend_mae_te", "omega_mean_te", "omega_std_te"]},
            "coefficients": {"beta": pairB["beta"], "mu": pairB["mu"], "sd": pairB["sd"]},
        }
        all_results.append(rec)
        if verdict == "STABLE": stable_cells.append(rec)

    print("=" * 148)
    if stable_cells:
        print(f"VERDICT: STAGE 1 STABLE — {len(stable_cells)} cell(s) cleared halves-stable lift ≥ {MIN_LIFT_PCT}% vs best single source,")
        print(f"         non-degenerate ω, no overfit collapse, ω drift ≤ {OMEGA_DRIFT_TOL}. Field={FIELD}.")
        for r in stable_cells:
            m_a = r["pair_A"]["test_lift_vs_best_pct"]; m_b = r["pair_B"]["test_lift_vs_best_pct"]
            print(f"           {r['regime']:<14}{r['band']:<8}  A+{m_a:.1f}% / B+{m_b:.1f}%  "
                  f"ω̄ A={r['pair_A']['omega_mean_te']:.2f} B={r['pair_B']['omega_mean_te']:.2f}")
    else:
        print(f"VERDICT: STAGE 1 HOLD — no cell cleared halves-stable ≥ {MIN_LIFT_PCT}%. Field={FIELD}.")
    print("=" * 148)

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"l1_blender_stage1_{FIELD}.json")
    with open(out_path, "w") as fh:
        json.dump({
            "field": FIELD,
            "hrrr_terminal": HRRR_TERMINAL.get(FIELD, "forecast_l4"),
            "features": FEATURE_NAMES,
            "ridge_lambda": RIDGE_LAMBDA,
            "min_lift_pct": MIN_LIFT_PCT,
            "cells": all_results,
            "stable": [{"regime": r["regime"], "band": r["band"],
                        "test_lift_vs_best_A": r["pair_A"]["test_lift_vs_best_pct"],
                        "test_lift_vs_best_B": r["pair_B"]["test_lift_vs_best_pct"],
                        "omega_mean_B": r["pair_B"]["omega_mean_te"]}
                       for r in stable_cells],
        }, fh, indent=2)
    print(f"wrote {out_path}")


if __name__ == "__main__": main()

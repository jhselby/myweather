"""Stage 1 (multi-axis) — L1 selector per-obs picker on 3 axes for field=h.

Stage 1 single-axis (ims-only) held: near-miss on sea_breeze/24-47h,
otherwise no cell generalized. Single-threshold on one feature is too
rigid — Stage 0 revealed non-monotonic win-rate patterns (U-shapes)
that a threshold can't capture.

This test combines three per-obs axes, each of which independently
carries some signal per Stage 0 / C1 orthogonality studies:
  • ims      = |forecast_l1 - forecast_raw_nbm|                (inter-model spread)
  • cluster  = cloud_inter_source_sigma                        (intra-model cloud sigma)
  • statew   = |state_fc.wind_speed - state_obs.wind_speed|    (state fc/obs disagreement, wind)

For each cell (regime, band): fit per-axis quartile→winner lookup on
train half (H if train MAE_H<MAE_N in that bin, else N). For each test
row: get 3 axis-votes, apply weighted vote using axis-specific train
confidence (|MAE_H - MAE_N| / MAE_N per bin). Compare test MAE vs
always-min baseline.

Ship criterion (Stage 1):
  • test_mae_lift_pct >= MIN_LIFT_PCT
  • train_mae_lift_pct >= MIN_LIFT_PCT
  • n_test >= MIN_N_TEST
  • test_lift >= 0.5 * train_lift  (overfit guard)
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"
FIELD = sys.argv[1] if len(sys.argv) > 1 else "h"
BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N_CELL = 400
MIN_N_TEST = 150
MIN_LIFT_PCT = 3.0
MIN_BIN_N = 30   # per-axis per-quartile min-n on train


def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def load_rows():
    with open(cached_path(PAIR_URL), "rb") as fh:
        for raw in fh:
            try: r = json.loads(raw)
            except Exception: continue
            if r.get("field") != FIELD: continue
            lead = r.get("lead_h")
            if lead is None: continue
            band = lead_band(int(lead))
            if not band: continue
            fc_l1, fc_nbm_raw = r.get("forecast_l1"), r.get("forecast_raw_nbm")
            err_l4, err_l3_nbm = r.get("error_l4"), r.get("error_l3_nbm")
            if None in (fc_l1, fc_nbm_raw, err_l4, err_l3_nbm): continue
            regime = (r.get("state_fc") or {}).get("regime_synoptic")
            if not regime: continue
            cluster = r.get("cloud_inter_source_sigma")
            if cluster is None: continue
            fcs = r.get("state_fc") or {}
            obs = r.get("state_obs") or {}
            ws_fc, ws_obs = fcs.get("wind_speed"), obs.get("wind_speed")
            if ws_fc is None or ws_obs is None: continue
            yield {
                "regime": regime, "band": band,
                "axes": {
                    "ims": abs(float(fc_l1) - float(fc_nbm_raw)),
                    "cluster": float(cluster),
                    "statew": abs(float(ws_fc) - float(ws_obs)),
                },
                "eh": abs(float(err_l4)),
                "en": abs(float(err_l3_nbm)),
                "t": r.get("obs_time", ""),
            }


AXES = ("ims", "cluster", "statew")


def quartile_thresholds(values):
    vs = sorted(values)
    n = len(vs)
    return (vs[n // 4], vs[n // 2], vs[3 * n // 4])


def qbin(v, t):
    q1, q2, q3 = t
    if v <= q1: return 0
    if v <= q2: return 1
    if v <= q3: return 2
    return 3


def fit_axis(rows, axis):
    """Return {threshold_tuple, bin_pick, bin_confidence}.
    Pick per bin = H if train MAE_H < MAE_N else N.
    Confidence per bin = |MAE_H - MAE_N| / max(min(MAE_H, MAE_N), eps)."""
    vals = [r["axes"][axis] for r in rows]
    if len(set(vals)) < 4:
        return None  # degenerate axis in this cell
    thresholds = quartile_thresholds(vals)
    per_bin = defaultdict(lambda: [0, 0.0, 0.0])
    for r in rows:
        b = qbin(r["axes"][axis], thresholds)
        per_bin[b][0] += 1
        per_bin[b][1] += r["eh"]
        per_bin[b][2] += r["en"]
    bin_pick = {}
    bin_conf = {}
    for b, (n, sh, sn) in per_bin.items():
        if n < MIN_BIN_N: continue
        mh, mn = sh / n, sn / n
        bin_pick[b] = "H" if mh < mn else "N"
        bin_conf[b] = abs(mh - mn) / max(min(mh, mn), 1e-6)
    return {"thresholds": thresholds, "bin_pick": bin_pick, "bin_conf": bin_conf}


def predict(rows, axis_fits):
    """Apply weighted-vote across axes to each row; return MAE."""
    if not rows: return (0.0, 0)
    picks_H = 0; picks_N = 0; total_err = 0.0; n_used = 0
    for r in rows:
        vote_H = 0.0
        vote_N = 0.0
        for axis in AXES:
            fit = axis_fits.get(axis)
            if not fit: continue
            b = qbin(r["axes"][axis], fit["thresholds"])
            pick = fit["bin_pick"].get(b)
            conf = fit["bin_conf"].get(b, 0.0)
            if pick == "H": vote_H += conf
            elif pick == "N": vote_N += conf
        if vote_H + vote_N == 0:
            # no axis had confident pick — fall back to train-cell-average winner
            # (approximated by comparing this row against zero — punt to "H")
            total_err += r["eh"]
            picks_H += 1
        elif vote_H >= vote_N:
            total_err += r["eh"]; picks_H += 1
        else:
            total_err += r["en"]; picks_N += 1
        n_used += 1
    return (total_err / n_used, n_used, picks_H, picks_N)


def always_min_mae(rows):
    if not rows: return 0.0
    seh = sum(r["eh"] for r in rows); sen = sum(r["en"] for r in rows)
    n = len(rows)
    return min(seh, sen) / n


def per_obs_oracle(rows):
    if not rows: return 0.0
    return sum(min(r["eh"], r["en"]) for r in rows) / len(rows)


print(f"Loading pair-log for field={FIELD}...")
by_cell = defaultdict(list)
for r in load_rows():
    by_cell[(r["regime"], r["band"])].append(r)

print(f"  {len(by_cell)} (regime, band) cells\n")

print("=" * 122)
print(f"h_l1_selector_multiaxis_stage1 — 3-axis weighted-vote picker (ims + cluster + state_wind)")
print("=" * 122)
print(f"{'regime':<14}{'band':<8}"
      f"  {'nTr':>5}{'nTe':>5}"
      f"  {'baselTr':>8}{'fitTr':>8}{'liftTr%':>8}"
      f"  {'baselTe':>8}{'fitTe':>8}{'liftTe%':>8}  {'oracleTe':>8}  {'captured%':>9}"
      f"  {'H/N test':>10}  verdict")
print("-" * 122)

promote = []
results = []
for key, rows in sorted(by_cell.items()):
    if len(rows) < MIN_N_CELL: continue
    rows.sort(key=lambda r: r["t"])
    mid = len(rows) // 2
    train, test = rows[:mid], rows[mid:]
    if len(test) < MIN_N_TEST: continue

    fits = {}
    for axis in AXES:
        fit = fit_axis(train, axis)
        if fit: fits[axis] = fit

    train_mae, _, _, _ = predict(train, fits)
    test_mae, n_test, pH, pN = predict(test, fits)
    tr_base = always_min_mae(train)
    te_base = always_min_mae(test)
    te_oracle = per_obs_oracle(test)
    tr_lift = (tr_base - train_mae) / tr_base * 100 if tr_base else 0
    te_lift = (te_base - test_mae) / te_base * 100 if te_base else 0
    te_cap = (te_base - test_mae) / max(te_base - te_oracle, 1e-9) * 100

    verdict = "-"
    if (te_lift >= MIN_LIFT_PCT and tr_lift >= MIN_LIFT_PCT
            and n_test >= MIN_N_TEST and te_lift >= 0.5 * tr_lift):
        verdict = "★ PROMOTE"
        promote.append((key, tr_lift, te_lift, te_cap))
    elif te_lift >= 1.0:
        verdict = "weak"
    elif tr_lift >= 3.0 and te_lift < 0:
        verdict = "overfit"

    results.append({
        "regime": key[0], "band": key[1],
        "n_train": len(train), "n_test": n_test,
        "train_baseline": tr_base, "train_fit": train_mae, "train_lift_pct": tr_lift,
        "test_baseline": te_base, "test_fit": test_mae, "test_lift_pct": te_lift,
        "test_oracle": te_oracle, "test_capture_pct": te_cap,
        "picks_H_test": pH, "picks_N_test": pN,
        "axes_fit": list(fits.keys()),
    })
    print(f"{key[0]:<14}{key[1]:<8}"
          f"  {len(train):>5}{n_test:>5}"
          f"  {tr_base:>8.3f}{train_mae:>8.3f}{tr_lift:>+7.2f}%"
          f"  {te_base:>8.3f}{test_mae:>8.3f}{te_lift:>+7.2f}%  {te_oracle:>8.3f}  {te_cap:>+8.1f}%"
          f"  {pH:>4}/{pN:<4}  {verdict}")

print("=" * 122)
if promote:
    print(f"VERDICT: STAGE 1 (multi-axis) PROMOTE — {len(promote)} cell(s) clear test lift ≥ {MIN_LIFT_PCT}%")
    print(f"         halves-stable, non-overfit. Advance to Stage 2 (multi-cell fit + halves-stable")
    print(f"         across ≥3 chronological splits + orthogonality vs regime × band alone + 7-day walker).")
    for key, tr, te, cap in promote:
        print(f"           {key[0]:<14}{key[1]:<8}  train +{tr:.2f}% / test +{te:.2f}%  captured {cap:.1f}% of per-obs gap")
else:
    print(f"VERDICT: STAGE 1 (multi-axis) HOLD — no cell clears held-out MAE lift ≥ {MIN_LIFT_PCT}% halves-stable.")
    print(f"         Three axes together (ims + cluster + state_wind) still don't generalize on")
    print(f"         held-out for field=h. Options: try field=sr (bigger oracle gap, more model divergence),")
    print(f"         add more axes (state_fc/obs on other channels), or model the axes non-linearly.")
print("=" * 122)

out = {"field": FIELD, "axes": AXES, "min_lift_pct": MIN_LIFT_PCT, "cells": results,
       "promote": [{"regime": k[0], "band": k[1], "test_lift_pct": te, "test_capture_pct": cap}
                   for k, _, te, cap in promote]}
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output",
                       f"{FIELD}_l1_selector_multiaxis_stage1.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as fh:
    json.dump(out, fh, indent=2)
print(f"wrote {out_path}")

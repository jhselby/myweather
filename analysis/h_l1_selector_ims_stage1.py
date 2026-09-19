"""Stage 1 — Fit a per-obs ims threshold for the L1 selector on field=h.

Stage 0 (h_l1_selector_ims_stage0) showed halves-stable win-rate spread
across ims quartiles for ~12 cells, with 2 cells passing the crude
per-quartile-pick shadow gate. Stage 1 fits a proper per-obs decision
rule keyed on continuous ims and validates on held-out chronological
halves.

Rule shape: within each (regime, band), pick a single ims threshold T
and a direction ("H_low" = pick HRRR if ims<T else NBM, or "H_high" =
opposite). Sweep candidate thresholds from ims percentiles 10..90 on
the train half; select whichever (T, direction) minimizes train MAE.
Apply that rule to the test half; report test MAE vs baselines.

Baselines:
  • always_min_MAE — pick whichever model wins cell average on train
  • per_obs_oracle_MAE — pick per-obs winner (unreachable upper bound)

Ship criterion (Stage 1):
  • test_mae_lift_pct >= MIN_LIFT_PCT vs always-min
  • train_mae_lift_pct >= MIN_LIFT_PCT (halves-stable)
  • n_test >= MIN_N_TEST
  • test_mae_lift_pct >= 0.5 * train_mae_lift_pct (no overfit collapse)

Cells that clear Stage 1 advance to Stage 2 (multi-cell fit, orthogonality
vs existing selector axes, 7-day walker gate). If ≥1 cell clears, we
have a real L1-per-obs axis and can start planning the wire.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"
FIELD = "h"
BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N_CELL = 400        # need >= 200 train + 200 test per cell
MIN_N_TEST = 150
MIN_LIFT_PCT = 3.0      # test MAE lift over always-min to promote
THRESHOLD_PERCENTILES = list(range(10, 91, 5))   # sweep at 5-pt steps


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
            yield {
                "regime": regime, "band": band,
                "ims": abs(float(fc_l1) - float(fc_nbm_raw)),
                "eh": abs(float(err_l4)),
                "en": abs(float(err_l3_nbm)),
                "t": r.get("obs_time", ""),
            }


def percentile(sorted_vals, pct):
    if not sorted_vals: return 0.0
    idx = min(len(sorted_vals) - 1, int(len(sorted_vals) * pct / 100))
    return sorted_vals[idx]


def apply_rule(rows, threshold, direction):
    """Return (mae, n) applying rule."""
    if not rows: return (0.0, 0)
    s = 0.0
    for r in rows:
        if direction == "H_low":
            pick_h = r["ims"] < threshold
        else:  # H_high
            pick_h = r["ims"] >= threshold
        s += r["eh"] if pick_h else r["en"]
    return (s / len(rows), len(rows))


def always_min_mae(rows):
    """MAE of always-pick-cell-winner (the current-selector best-case for this cell)."""
    if not rows: return 0.0
    seh = sum(r["eh"] for r in rows)
    sen = sum(r["en"] for r in rows)
    n = len(rows)
    return min(seh, sen) / n


def per_obs_oracle_mae(rows):
    if not rows: return 0.0
    return sum(min(r["eh"], r["en"]) for r in rows) / len(rows)


def fit_and_eval(rows_train, rows_test):
    """Fit best (threshold, direction) on train; eval on test.
    Return dict with fit + baselines + lifts."""
    ims_sorted = sorted(r["ims"] for r in rows_train)
    best = None  # (train_mae, threshold, direction)
    for pct in THRESHOLD_PERCENTILES:
        T = percentile(ims_sorted, pct)
        for direction in ("H_low", "H_high"):
            m, _ = apply_rule(rows_train, T, direction)
            if best is None or m < best[0]:
                best = (m, T, direction, pct)
    train_fit_mae, T, direction, pct = best
    test_mae, n_test = apply_rule(rows_test, T, direction)

    train_baseline = always_min_mae(rows_train)
    test_baseline = always_min_mae(rows_test)
    train_oracle = per_obs_oracle_mae(rows_train)
    test_oracle = per_obs_oracle_mae(rows_test)

    return {
        "T": T, "pct": pct, "direction": direction,
        "n_train": len(rows_train), "n_test": n_test,
        "train_fit_mae": train_fit_mae, "test_mae": test_mae,
        "train_baseline": train_baseline, "test_baseline": test_baseline,
        "train_oracle": train_oracle, "test_oracle": test_oracle,
        "train_lift_pct": (train_baseline - train_fit_mae) / train_baseline * 100 if train_baseline else 0,
        "test_lift_pct": (test_baseline - test_mae) / test_baseline * 100 if test_baseline else 0,
        "test_capture_pct": (test_baseline - test_mae) / max(test_baseline - test_oracle, 1e-9) * 100,
    }


# Load and group
print(f"Loading pair-log for field={FIELD}...")
by_cell = defaultdict(list)
for r in load_rows():
    by_cell[(r["regime"], r["band"])].append(r)


results = []
for key, rows in sorted(by_cell.items()):
    if len(rows) < MIN_N_CELL: continue
    rows.sort(key=lambda r: r["t"])
    mid = len(rows) // 2
    train, test = rows[:mid], rows[mid:]
    if len(test) < MIN_N_TEST: continue
    res = fit_and_eval(train, test)
    res["regime"], res["band"] = key
    results.append(res)


# Report
print("=" * 118)
print(f"h_l1_selector_ims_stage1 — per-obs ims threshold fit (train→test halves)")
print("=" * 118)
print(f"{'regime':<14}{'band':<8}{'rule':<9}{'T':>7}  {'nTr':>5}{'nTe':>5}"
      f"  {'baselTr':>8}{'fitTr':>8}{'liftTr%':>8}"
      f"  {'baselTe':>8}{'fitTe':>8}{'liftTe%':>8}  {'oracleTe':>8}  {'captured%':>9}  verdict")
print("-" * 118)

promote = []
for r in results:
    verdict = "-"
    lift_te = r["test_lift_pct"]
    lift_tr = r["train_lift_pct"]
    if (lift_te >= MIN_LIFT_PCT and lift_tr >= MIN_LIFT_PCT
            and r["n_test"] >= MIN_N_TEST
            and lift_te >= 0.5 * lift_tr):
        verdict = "★ PROMOTE"
        promote.append(r)
    elif lift_tr >= MIN_LIFT_PCT and lift_te < MIN_LIFT_PCT:
        verdict = "overfit"
    elif lift_tr >= 1.0 or lift_te >= 1.0:
        verdict = "weak"
    print(f"{r['regime']:<14}{r['band']:<8}{r['direction']:<9}{r['T']:>7.2f}  "
          f"{r['n_train']:>5}{r['n_test']:>5}  "
          f"{r['train_baseline']:>8.3f}{r['train_fit_mae']:>8.3f}{lift_tr:>+7.2f}%  "
          f"{r['test_baseline']:>8.3f}{r['test_mae']:>8.3f}{lift_te:>+7.2f}%  "
          f"{r['test_oracle']:>8.3f}  {r['test_capture_pct']:>+8.1f}%  {verdict}")

print("=" * 118)
if promote:
    print(f"VERDICT: STAGE 1 PROMOTE — {len(promote)} cell(s) clear held-out MAE lift ≥ {MIN_LIFT_PCT}%")
    print(f"         halves-stable, non-overfit. Advance to Stage 2 (orthogonality vs existing")
    print(f"         selector axes + halves-stable across 3+ chronological splits + 7-day walker).")
    for r in promote:
        print(f"           {r['regime']:<14}{r['band']:<8}  rule: {r['direction']} ims@{r['T']:.2f}  "
              f"train +{r['train_lift_pct']:.2f}% / test +{r['test_lift_pct']:.2f}%  "
              f"captured {r['test_capture_pct']:.1f}% of per-obs gap")
else:
    print(f"VERDICT: STAGE 1 HOLD — no cell clears held-out MAE lift ≥ {MIN_LIFT_PCT}% halves-stable.")
    print(f"         Signal exists (Stage 0) but single-threshold rule doesn't generalize.")
    print(f"         Options: (a) multi-feature rule (ims + regime interactions); (b) try other axes")
    print(f"         (xr_q, cluster_spread, state_fc/obs) that may carry stronger per-obs signal.")
print("=" * 118)

# Write JSON for downstream tools
out = {"field": FIELD, "min_lift_pct": MIN_LIFT_PCT, "cells": results, "promote": [
    {"regime": r["regime"], "band": r["band"], "T": r["T"], "direction": r["direction"],
     "test_lift_pct": r["test_lift_pct"], "test_capture_pct": r["test_capture_pct"]}
    for r in promote]}
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output",
                       "h_l1_selector_ims_stage1.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as fh:
    json.dump(out, fh, indent=2)
print(f"wrote {out_path}")

"""Stage 1 v5 — GBM per-obs classifier, scored vs error_prod_real, full
matrix sweep, serialized to the new curated JSON format for the router.

Differences from v4:
  1. Sweeps ALL fields (not one at a time) — this is the selector-
     replacement benchmark, not a per-field experiment.
  2. Baseline is the top-level `error` field (what production actually
     served for this row, post-selector, post-any-applied-layer), not
     `error_l4` (always-HRRR). This is the honest ship-gain: does the
     classifier's per-obs pick beat what the stack served today?
  3. Emits a candidate `l1_learned_selector_curated.json` with the
     surviving STABLE cells serialized as GBM trees (feature/threshold/
     left/right/value arrays) — runtime lives in l1_selector.py
     (_tree_predict + _learned_predict "gbm" branch).
  4. Cells that fail halves-stable are dropped from the curated output.
     Runtime falls through to the regime walker + base table for those.

Halves-stable gate matches v4 (quartile A/B pairs, MIN_LIFT_PCT=3%,
0.05 < fNBM < 0.60, no-overfit-collapse). Lift here is vs served
baseline, so 3% is a stronger bar than v4's 3%-vs-always-HRRR.

Run:
  python3 -m analysis.l1_selector_per_obs_classifier_stage1_v5

Writes:
  analysis/output/l1_selector_per_obs_classifier_stage1_v5.json
    — full sweep report (all cells + verdicts)
  analysis/output/l1_learned_selector_curated_v5_candidate.json
    — candidate for weather_collector/data/l1_learned_selector_curated.json
      (surviving STABLE cells only, GBM-serialized). Review before
      copying into place.
"""
import os, sys, json, math
from collections import defaultdict, Counter
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"

# Fields with a live NBM parallel pipeline in the pair-log (both
# forecast_raw_nbm and error_l3_nbm present). dp is derived from
# (t, h) via Magnus so has no direct NBM forecast; cl/cm are cloud
# sub-components consumed only by the cc composition layer; pp is
# derived downstream. All four show zero rows through build_features
# and are dropped here to keep the sweep output legible. Selector-
# replacement scope is intrinsically the fields with two-cascade
# routing, so this exclusion is definitional, not a workaround.
FIELDS = ["t", "h", "ws", "wg", "wd", "cc", "ch", "sr"]

BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]

MIN_N_CELL = 400
MIN_N_TEST_PER_PAIR = 90
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


def hour_local(obs_time):
    try: return int(obs_time[11:13])
    except Exception: return 12


def load_rows_by_field():
    """Single pass over the pair-log. Bucket rows by field."""
    by_field = defaultdict(list)
    fc_by_vt_field = defaultdict(lambda: defaultdict(list))
    with open(cached_path(PAIR_URL), "rb") as fh:
        for raw in fh:
            try: r = json.loads(raw)
            except Exception: continue
            field = r.get("field")
            if field not in FIELDS: continue
            vt = r.get("valid_time"); fc = r.get("forecast")
            if vt is not None and fc is not None:
                fc_by_vt_field[field][vt].append(float(fc))
            by_field[field].append(r)
    vt_spread_by_field = {
        f: {vt: max(fcs) - min(fcs) for vt, fcs in vtm.items() if len(fcs) >= 2}
        for f, vtm in fc_by_vt_field.items()
    }
    return by_field, vt_spread_by_field


def build_features(rows_raw, vt_spread, drop=None):
    """Yields per-obs feature rows, with the served baseline (top-level
    `error`) alongside the HRRR/NBM per-row errors. `drop`, if given,
    is a Counter that gets incremented per drop reason — used by the
    sweep to attribute sparsity."""
    if drop is None:
        drop = Counter()
    for r in rows_raw:
        vt = r.get("valid_time")
        if vt_spread.get(vt) is None:
            drop["no_vt_spread"] += 1; continue
        xr = vt_spread[vt]
        lead = r.get("lead_h")
        if lead is None:
            drop["no_lead"] += 1; continue
        band = lead_band(int(lead))
        if not band:
            drop["lead_out_of_band"] += 1; continue
        fc_l1 = r.get("forecast_l1"); fc_nbm_raw = r.get("forecast_raw_nbm")
        err_l4 = r.get("error_l4")
        # NBM-side error: prefer error_l3_nbm (L3-corrected) where the field
        # actually has L3 NBM live; else fall back to error_raw_nbm. For
        # fields without an L3 NBM stage (t, h, ws, wd, sr, cc — anything
        # not in L3_FIELDS), the router's real choice is HRRR-terminal vs
        # raw NBM, and error_raw_nbm is the correct target.
        err_nbm = r.get("error_l3_nbm")
        nbm_source = "l3_nbm"
        if err_nbm is None:
            err_nbm = r.get("error_raw_nbm")
            nbm_source = "raw_nbm"
        # Served baseline: top-level `error` is what production returned for
        # this row (post-selector, post-any-applied-layer). This is the honest
        # baseline the classifier needs to beat.
        err_served = r.get("error")
        if fc_l1 is None: drop["no_forecast_l1"] += 1; continue
        if fc_nbm_raw is None: drop["no_forecast_raw_nbm"] += 1; continue
        if err_l4 is None: drop["no_error_l4"] += 1; continue
        if err_nbm is None: drop["no_error_nbm_either"] += 1; continue
        if err_served is None: drop["no_error_served"] += 1; continue
        sfc = r.get("state_fc") or {}
        regime = sfc.get("regime_synoptic")
        if not regime: drop["no_regime"] += 1; continue
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
        eh = abs(float(err_l4)); en = abs(float(err_nbm))
        es = abs(float(err_served))
        yield {
            "regime": regime, "band": band, "t": r.get("obs_time", ""),
            "x": [ims, xr, float(lead),
                  math.sin(2*math.pi*hh/24.0), math.cos(2*math.pi*hh/24.0),
                  cc_sigma, p_trend,
                  wd_sin, wd_cos,
                  ws_fc, cloud_low_fc, solar_fc],
            "y": 1 if en < eh else 0,
            "eh": eh, "en": en, "es": es,
            "nbm_source": nbm_source,
        }


def mae_at_theta(rows, probs, theta):
    picks = probs > theta
    total = sum((rows[i]["en"] if picks[i] else rows[i]["eh"]) for i in range(len(rows)))
    return total / len(rows), float(picks.mean())


def served_mae(rows):
    return sum(r["es"] for r in rows) / len(rows) if rows else 0.0


def fit_pair(train_rows, test_rows):
    cut = int(len(train_rows) * (1 - VAL_FRAC))
    fit_rows, val_rows = train_rows[:cut], train_rows[cut:]
    if len(fit_rows) < 100 or len(val_rows) < 60:
        return None

    X_fit = np.array([r["x"] for r in fit_rows], dtype=float)
    y_fit = np.array([r["y"] for r in fit_rows], dtype=float)
    X_val = np.array([r["x"] for r in val_rows], dtype=float)
    y_val = np.array([r["y"] for r in val_rows], dtype=float)
    X_te = np.array([r["x"] for r in test_rows], dtype=float)

    # Need both classes present to fit.
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

    p_fit, p_val, p_te = _proba_at(X_fit), _proba_at(X_val), _proba_at(X_te)

    base_tr = served_mae(train_rows)
    base_te = served_mae(test_rows)
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
        clf=clf, best_round=best_round,
        n_train=len(train_rows), n_test=len(test_rows),
        theta_star=theta_star,
        test_baseline=base_te, test_fit_mae=fit_te,
        train_baseline=base_tr, train_fit_mae=fit_tr,
        test_lift_pct=(base_te - fit_te) / base_te * 100,
        train_lift_pct=(base_tr - fit_tr) / base_tr * 100,
        test_frac_nbm=fnbm_te, train_frac_nbm=fnbm_tr,
    )


def classify(pairA, pairB):
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


def fit_final(all_rows):
    """Refit on all rows (Q1..Q4) after halves-stable is cleared. This is
    the model that ships. Uses the same early-stopping trick against an
    inner val slice."""
    n = len(all_rows)
    cut = int(n * (1 - VAL_FRAC))
    fit_rows = all_rows[:cut]
    val_rows = all_rows[cut:]
    X_fit = np.array([r["x"] for r in fit_rows], dtype=float)
    y_fit = np.array([r["y"] for r in fit_rows], dtype=float)
    X_val = np.array([r["x"] for r in val_rows], dtype=float)
    y_val = np.array([r["y"] for r in val_rows], dtype=float)
    if len(set(y_fit.tolist())) < 2:
        return None, None
    clf = GradientBoostingClassifier(**GBM_PARAMS)
    clf.fit(X_fit, y_fit)
    val_losses = []
    for pp in clf.staged_predict_proba(X_val):
        pv = np.clip(pp[:, 1], 1e-6, 1 - 1e-6)
        val_losses.append(-float(np.mean(y_val*np.log(pv) + (1-y_val)*np.log(1-pv))))
    best_round = int(np.argmin(val_losses)) + 1
    return clf, best_round


def _theta_for_final(clf, best_round, all_rows):
    """Pick θ* on the same val slice used for early stopping."""
    n = len(all_rows)
    cut = int(n * (1 - VAL_FRAC))
    val_rows = all_rows[cut:]
    X_val = np.array([r["x"] for r in val_rows], dtype=float)
    p_val = None
    for i, pp in enumerate(clf.staged_predict_proba(X_val), start=1):
        if i == best_round:
            p_val = pp[:, 1]; break
    if p_val is None:
        p_val = clf.predict_proba(X_val)[:, 1]
    best = None
    for th in THETA_GRID:
        m_v, _ = mae_at_theta(val_rows, p_val, th)
        if best is None or m_v < best[0]:
            best = (m_v, th)
    return best[1]


def serialize_gbm(clf, best_round, theta_star):
    """Export the first `best_round` trees of a sklearn GBM to plain-JSON
    arrays for pure-python runtime replay. init_ is the log-odds base
    rate (loss_.init_.class_prior_ path); we pull it from the model's
    init prediction to avoid sklearn-version drift."""
    init_pred = float(clf._raw_predict_init(np.zeros((1, len(FEATURE_NAMES)))).flatten()[0])
    trees_out = []
    lr = clf.learning_rate
    for est in clf.estimators_[:best_round, 0]:
        t = est.tree_
        trees_out.append({
            "feature": [int(x) for x in t.feature.tolist()],
            "threshold": [float(x) for x in t.threshold.tolist()],
            "left": [int(x) for x in t.children_left.tolist()],
            "right": [int(x) for x in t.children_right.tolist()],
            "value": [float(v[0][0]) for v in t.value.tolist()],
        })
    return {
        "model_type": "gbm",
        "theta": float(theta_star),
        "init": init_pred,
        "learning_rate": float(lr),
        "trees": trees_out,
    }


def sweep_field(field, rows_raw, vt_spread):
    # Track why rows drop, so the report can attribute sparsity to
    # missing features vs. missing regime vs. missing NBM pipeline.
    drop = Counter()
    by_cell = defaultdict(list)
    n_input = len(rows_raw)
    for row in build_features(rows_raw, vt_spread, drop):
        by_cell[(row["regime"], row["band"])].append(row)

    kept = sum(len(v) for v in by_cell.values())
    print(f"\n=== field={field} ({kept:,}/{n_input:,} kept, {len(by_cell)} cells) ===")
    if drop:
        top = ", ".join(f"{k}:{v}" for k, v in drop.most_common(4))
        print(f"    drops: {top}")
    print(f"{'regime':<14}{'band':<8}{'n':>5}  "
          f"{'A_liftTe':>9}{'A_fNBM':>7}  "
          f"{'B_liftTe':>9}{'B_fNBM':>7}  verdict")
    print("-" * 100)

    results = []
    for key in sorted(by_cell.keys()):
        regime, band = key
        rows = by_cell[key]
        if len(rows) < MIN_N_CELL: continue
        rows.sort(key=lambda r: r["t"])
        n = len(rows); q = n // 4
        if q < MIN_N_TEST_PER_PAIR: continue
        Q1, Q2, Q3, Q4 = rows[:q], rows[q:2*q], rows[2*q:3*q], rows[3*q:]

        pairA = fit_pair(Q1 + Q2, Q3)
        pairB = fit_pair(Q2 + Q3, Q4)
        if pairA is None or pairB is None: continue

        verdict = classify(pairA, pairB)
        marker = "★" if verdict == "STABLE" else " "
        print(f"{regime:<14}{band:<8}{n:>5}  "
              f"{pairA['test_lift_pct']:>+8.2f}%{pairA['test_frac_nbm']*100:>6.1f}%  "
              f"{pairB['test_lift_pct']:>+8.2f}%{pairB['test_frac_nbm']*100:>6.1f}%  {marker} {verdict}")

        cell = dict(
            field=field, regime=regime, band=band, n=n,
            pairA={k: v for k, v in pairA.items() if k not in ("clf",)},
            pairB={k: v for k, v in pairB.items() if k not in ("clf",)},
            verdict=verdict,
        )

        if verdict == "STABLE":
            clf_final, best_final = fit_final(rows)
            if clf_final is not None:
                theta_final = _theta_for_final(clf_final, best_final, rows)
                cell["serialized"] = serialize_gbm(clf_final, best_final, theta_final)
                cell["n_trees_final"] = best_final

        results.append(cell)

    return results


def main():
    print(f"Loading pair-log ({PAIR_URL})...")
    by_field, vt_spread_by_field = load_rows_by_field()
    for f in FIELDS:
        print(f"  {f}: {len(by_field.get(f, [])):,} rows, "
              f"{len(vt_spread_by_field.get(f, {}))} VTs")

    all_results = []
    for f in FIELDS:
        rows_raw = by_field.get(f) or []
        vt_spread = vt_spread_by_field.get(f) or {}
        if not rows_raw or not vt_spread:
            continue
        cells = sweep_field(f, rows_raw, vt_spread)
        all_results.extend(cells)

    stable = [c for c in all_results if c["verdict"] == "STABLE"]

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)

    report_path = os.path.join(out_dir, "l1_selector_per_obs_classifier_stage1_v5.json")
    with open(report_path, "w") as fh:
        json.dump({
            "feature_names": FEATURE_NAMES,
            "gbm_params": GBM_PARAMS,
            "min_lift_pct": MIN_LIFT_PCT,
            "baseline": "error (top-level served)",
            "cells": [{k: v for k, v in c.items() if k != "serialized"} for c in all_results],
            "stable_summary": [
                {"field": c["field"], "regime": c["regime"], "band": c["band"],
                 "avg_test_lift_pct": (c["pairA"]["test_lift_pct"] + c["pairB"]["test_lift_pct"]) / 2,
                 "avg_fnbm_te": (c["pairA"]["test_frac_nbm"] + c["pairB"]["test_frac_nbm"]) / 2}
                for c in stable
            ],
        }, fh, indent=2)
    print(f"\nwrote report → {report_path}")

    candidate_path = os.path.join(out_dir, "l1_learned_selector_curated_v5_candidate.json")
    curated = {
        "fitted_at": None,
        "feature_names": FEATURE_NAMES,
        "note": (
            "Auto-generated by analysis/l1_selector_per_obs_classifier_stage1_v5.py. "
            "STABLE cells only, serialized as GBM trees. Runtime path: "
            "weather_collector/processors/l1_selector.py::_learned_predict (gbm branch). "
            "Baseline for lift = error_prod_real (what the selector actually served); "
            "gate is halves-stable ≥3% lift on both quartile pairs A and B, non-degenerate fNBM."
        ),
        "cells": [
            {**{"field": c["field"], "regime": c["regime"], "band": c["band"]},
             **c["serialized"]}
            for c in stable if "serialized" in c
        ],
    }
    with open(candidate_path, "w") as fh:
        json.dump(curated, fh, indent=2)
    print(f"wrote candidate curated JSON → {candidate_path}")
    print(f"  {len(curated['cells'])} STABLE cells serialized.")
    print(f"\nTo ship: copy {candidate_path} → "
          f"weather_collector/data/l1_learned_selector_curated.json, "
          f"set LEARNED_SELECTOR_SHADOW_ENABLED = True in l1_selector.py, deploy collector.")


if __name__ == "__main__":
    main()

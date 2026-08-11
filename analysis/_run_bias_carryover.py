"""Shared implementation for run-level bias carryover Stage 0 hypotheses.

Hypothesis: for field F, a run_time R's short-lead residuals predict its
long-lead residuals. If so, once R's short-lead forecasts have been scored
against fresh obs, we can nudge R's remaining long-lead forecasts by
alpha * short_lead_residual (OLS-fit alpha).

Baseline: whatever the pair log's `error` field already reflects (applied
layer) — [[feedback_measure_against_live_stack_baseline]].

Called from thin wrappers per-field so each shows up as its own row in the
digest. This file has no top-level side effects, so `python3 -m analysis
._run_bias_carryover` is a safe no-op if the digest picks it up.
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

SHORT_LEAD = (0, 3)
LONG_LEAD = (24, 48)
MIN_RUNS_TRAIN = 100
MIN_RUNS_TEST = 30
HELD_OUT_DAYS = 7
STAGE0_HIT_PCT = 1.0  # ≥ 1% long-lead MAE improvement to promote


def _hod(vt):
    try:
        return int(vt[11:13])
    except Exception:
        return None


def _bucket(lh):
    if lh is None:
        return None
    if SHORT_LEAD[0] <= lh <= SHORT_LEAD[1]:
        return "S"
    if LONG_LEAD[0] <= lh <= LONG_LEAD[1]:
        return "L"
    return None


def compute(field, window_days=45):
    """Load pair log rows for `field`, split by valid_time into train/test,
    fit OLS alpha on train (long_resid ~ alpha * short_resid, per-run means
    after de-mean by (hour, bucket)), apply held-out, return metrics."""
    # 1) Load window
    now_date = datetime.now(timezone.utc).date()
    lo_dt = datetime.combine(now_date - timedelta(days=window_days), datetime.min.time())
    lo = lo_dt.strftime("%Y-%m-%dT%H:%M")

    rows = []
    n_scanned = n_field = 0
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            n_scanned += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != field:
                continue
            n_field += 1
            vt = r.get("valid_time") or ""
            if vt < lo:
                continue
            lh = r.get("lead_h")
            b = _bucket(lh)
            if b is None:
                continue
            e = r.get("error")
            rt = r.get("run_time")
            h = _hod(vt)
            if e is None or rt is None or h is None:
                continue
            rows.append((vt, rt, h, b, float(e)))

    if not rows:
        return {"status": "NO_ROWS", "field": field, "n_scanned": n_scanned,
                "n_field": n_field}

    # 2) De-mean bias per (hour, bucket) — computed on TRAIN only to avoid leakage
    max_vt = max(r[0] for r in rows)
    max_date = datetime.strptime(max_vt[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    train_bias = defaultdict(lambda: [0.0, 0])
    for vt, rt, h, b, e in rows:
        if vt[:10] < test_start:
            train_bias[(h, b)][0] += e
            train_bias[(h, b)][1] += 1
    mean_bias = {k: v[0] / v[1] for k, v in train_bias.items() if v[1]}

    # 3) Aggregate to per-(run, bucket) residual means
    run_agg = defaultdict(lambda: {"S": [], "L": []})  # (train_or_test, run_time) -> {S:[], L:[]}
    for vt, rt, h, b, e in rows:
        split = "train" if vt[:10] < test_start else "test"
        resid = e - mean_bias.get((h, b), 0.0)
        run_agg[(split, rt)][b].append(resid)

    train_pairs = []  # (short_mean_resid, long_mean_resid)
    test_pairs = []   # (short_mean_resid, long_actual_errs [list])
    test_ntimes = 0
    test_long_abs_sum = 0.0
    for (split, rt), d in run_agg.items():
        if not d["S"] or not d["L"]:
            continue
        s = sum(d["S"]) / len(d["S"])
        if split == "train":
            l = sum(d["L"]) / len(d["L"])
            train_pairs.append((s, l))
        else:
            # per-row long errors so we can compute true MAE improvement
            test_pairs.append((s, d["L"]))
            test_ntimes += len(d["L"])
            test_long_abs_sum += sum(abs(x) for x in d["L"])

    result = {
        "field": field,
        "n_scanned": n_scanned,
        "n_field": n_field,
        "n_rows_in_window": len(rows),
        "test_start": test_start,
        "max_vt": max_vt,
        "n_train_runs": len(train_pairs),
        "n_test_runs": len(test_pairs),
        "n_test_long_obs": test_ntimes,
    }

    if len(train_pairs) < MIN_RUNS_TRAIN:
        result["status"] = "THIN_TRAIN"
        return result
    if len(test_pairs) < MIN_RUNS_TEST:
        result["status"] = "THIN_TEST"
        return result

    # 4) Fit OLS alpha: long_mean_resid ≈ alpha * short_mean_resid
    sx = sy = sxx = sxy = 0.0
    for x, y in train_pairs:
        sx += x
        sy += y
        sxx += x * x
        sxy += x * y
    n = len(train_pairs)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-12:
        result["status"] = "DEGENERATE"
        return result
    alpha = (n * sxy - sx * sy) / denom
    # Also intercept for reference
    beta = (sy - alpha * sx) / n

    # Pearson r on train (as an effect-size signal)
    mean_x = sx / n
    mean_y = sy / n
    var_x = sum((x - mean_x) ** 2 for x, _ in train_pairs) / n
    var_y = sum((y - mean_y) ** 2 for _, y in train_pairs) / n
    cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in train_pairs) / n
    r = cov_xy / (math.sqrt(var_x * var_y) + 1e-12)

    # 5) Score held-out: for each test run, subtract alpha*short_resid from each
    #    long-lead raw error and compute MAE change vs baseline.
    baseline_mae = test_long_abs_sum / test_ntimes if test_ntimes else 0.0
    corrected_abs_sum = 0.0
    for s, longs in test_pairs:
        nudge = alpha * s + beta
        for e in longs:
            corrected_abs_sum += abs(e - nudge)
    corrected_mae = corrected_abs_sum / test_ntimes if test_ntimes else 0.0
    improve_pct = 100.0 * (baseline_mae - corrected_mae) / baseline_mae if baseline_mae > 0 else 0.0

    result.update({
        "status": "SCORED",
        "alpha": round(alpha, 4),
        "beta": round(beta, 4),
        "train_pearson_r": round(r, 3),
        "baseline_long_mae": round(baseline_mae, 4),
        "corrected_long_mae": round(corrected_mae, 4),
        "mae_improve_pct": round(improve_pct, 2),
    })
    return result


def emit_and_write(res, out_txt, out_json, hypothesis_slug):
    """Format verdict text + write outputs. Returns exit code."""
    lines = []
    lines.append("=" * 88)
    lines.append(f"STAGE 0 — {hypothesis_slug}")
    lines.append("=" * 88)
    lines.append(f"Field: {res['field']}   Window: last 45d valid_time")
    lines.append(f"Short lead: {SHORT_LEAD[0]}-{SHORT_LEAD[1]}h   "
                 f"Long lead: {LONG_LEAD[0]}-{LONG_LEAD[1]}h")
    lines.append(f"Held-out: last {HELD_OUT_DAYS}d.  Gate: MAE improvement ≥ "
                 f"{STAGE0_HIT_PCT:.1f}% on long-lead |err|.")
    if "test_start" in res:
        lines.append(f"Train: valid_date <  {res['test_start']}   "
                     f"Test: valid_date >= {res['test_start']} (max {res.get('max_vt', '')[:10]}).")
    lines.append("")

    status = res.get("status")
    if status in ("NO_ROWS", "THIN_TRAIN", "THIN_TEST", "DEGENERATE"):
        lines.append(f"n_field={res.get('n_field', 0):,}   "
                     f"n_train_runs={res.get('n_train_runs', 0)}   "
                     f"n_test_runs={res.get('n_test_runs', 0)}")
        lines.append("")
        lines.append(f"VERDICT: INSUFFICIENT DATA ({status}).  "
                     f"Re-run when pair log deepens.")
    elif status == "SCORED":
        lines.append(f"n_train_runs={res['n_train_runs']}   "
                     f"n_test_runs={res['n_test_runs']}   "
                     f"n_test_long_obs={res['n_test_long_obs']:,}")
        lines.append(f"Train fit:     alpha={res['alpha']:+.4f}   "
                     f"beta={res['beta']:+.4f}   pearson_r={res['train_pearson_r']:+.3f}")
        lines.append(f"Baseline MAE (long-lead |err|): {res['baseline_long_mae']:.4f}")
        lines.append(f"Corrected MAE (long-lead |err|): {res['corrected_long_mae']:.4f}")
        lines.append(f"Improvement: {res['mae_improve_pct']:+.2f}%")
        lines.append("")
        if res["mae_improve_pct"] >= STAGE0_HIT_PCT:
            lines.append(f"VERDICT: STAGE 0 HIT — {res['mae_improve_pct']:+.2f}% long-lead MAE "
                         f"improvement clears +{STAGE0_HIT_PCT:.1f}% gate.")
            lines.append(f"Warrants Stage 1: per-(regime × lead_band) fit + orthogonality check "
                         f"vs current stack.")
        else:
            lines.append(f"VERDICT: NO STAGE 0 HIT — {res['mae_improve_pct']:+.2f}% falls short of "
                         f"+{STAGE0_HIT_PCT:.1f}% gate.  Do not proceed to Stage 1.")
    else:
        lines.append(f"VERDICT: UNKNOWN STATUS ({status}).")

    text = "\n".join(lines)
    print(text)
    os.makedirs(os.path.dirname(out_txt), exist_ok=True)
    with open(out_txt, "w") as fh:
        fh.write(text + "\n")
    payload = dict(res)
    payload["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload["hypothesis"] = hypothesis_slug
    with open(out_json, "w") as fh:
        json.dump(payload, fh, indent=2)
    return 0

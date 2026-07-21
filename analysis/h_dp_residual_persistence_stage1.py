"""
dp (dew point) residual-persistence Stage 1 preview — tune window + verify robustness.

Follow-on to h_daily_residual_persistence Stage 0 finding (07-21 digest):
rolling daily mean L2-residual at same clock hour reduces dp MAE by +19.06%
held-out — the largest of the 3 Stage 0 hits (dp +19.06%, h +9.76%, wg
+7.06%). Mirrors h_h_residual_persistence_stage1.py exactly (same template,
different field). Grid-searches window size, checks per-regime robustness,
applies to Production (post-L3/L4) as well as L2 alone, and halves-checks
stability on training.

Grid search:
  window ∈ {1, 2, 3, 5, 7, 14} days
  weighting: uniform mean (Stage 2 will explore exp-decay τ)
  applied to: baseline_L2 and baseline_Production

Robustness checks:
  1. Best window's per-regime MAE improvement (all state_fc.regime_synoptic).
  2. Halves stability: split training into two halves, best window must win
     in both halves.

Run:
    python3 analysis/h_dp_residual_persistence_stage1.py

Output:
    analysis/output/h_dp_residual_persistence_stage1.txt
    analysis/output/h_dp_residual_persistence_stage1.json
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_dp_residual_persistence_stage1.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_dp_residual_persistence_stage1.json")

FIELD = "dp"
WINDOW_GRID = [1, 2, 3, 5, 7, 14]
TEST_WINDOW_DAYS = 7
MIN_N_PER_REGIME = 300


def parse_local_date(vt):
    return vt[:10] if vt and len(vt) >= 10 else None


def parse_local_hour(vt):
    try:
        return int(vt[11:13])
    except (TypeError, ValueError, IndexError):
        return None


def load_rows():
    """Return list of dicts with: date, hour, obs, fc_l2, fc_prod, regime."""
    rows = []
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            vt = r.get("valid_time")
            ob = r.get("observed")
            fc_l2 = r.get("forecast_l2")
            fc_prod = r.get("forecast")
            if vt is None or ob is None or fc_l2 is None or fc_prod is None:
                continue
            date = parse_local_date(vt)
            hour = parse_local_hour(vt)
            if date is None or hour is None:
                continue
            fc_state = r.get("state_fc") or {}
            regime = fc_state.get("regime_synoptic") or "unknown"
            rows.append({
                "date": date,
                "hour": hour,
                "obs": float(ob),
                "fc_l2": float(fc_l2),
                "fc_prod": float(fc_prod),
                "regime": regime,
            })
    return rows


def build_daily_residual(rows, baseline_key):
    """daily_res[(date, hour)] = mean signed residual (obs - baseline) that day."""
    buckets = defaultdict(list)
    for r in rows:
        buckets[(r["date"], r["hour"])].append(r["obs"] - r[baseline_key])
    return {k: sum(v) / len(v) for k, v in buckets.items()}


def compute_correction(daily_res, date_str, hour, window_days):
    """Mean residual over prior window_days at same (hour). None if no data."""
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    vals = []
    for lag in range(1, window_days + 1):
        prev = (d - timedelta(days=lag)).isoformat()
        v = daily_res.get((prev, hour))
        if v is not None:
            vals.append(v)
    return sum(vals) / len(vals) if vals else 0.0


def score(rows, daily_res, baseline_key, window_days, filter_fn=None):
    """MAE + RMSE with correction applied, for rows passing filter_fn. Returns
    dict {n, mae_base, mae_corr, mae_pct, rmse_base, rmse_corr, rmse_pct}."""
    n = 0
    s_ae_base = s_ae_corr = 0.0
    s_se_base = s_se_corr = 0.0
    for r in rows:
        if filter_fn is not None and not filter_fn(r):
            continue
        corr = compute_correction(daily_res, r["date"], r["hour"], window_days)
        err_base = r[baseline_key] - r["obs"]
        err_corr = (r[baseline_key] + corr) - r["obs"]
        n += 1
        s_ae_base += abs(err_base)
        s_ae_corr += abs(err_corr)
        s_se_base += err_base * err_base
        s_se_corr += err_corr * err_corr
    if n == 0:
        return None
    mae_base = s_ae_base / n
    mae_corr = s_ae_corr / n
    rmse_base = (s_se_base / n) ** 0.5
    rmse_corr = (s_se_corr / n) ** 0.5
    return {
        "n": n,
        "mae_base": round(mae_base, 4),
        "mae_corr": round(mae_corr, 4),
        "mae_pct": round((mae_base - mae_corr) / mae_base * 100, 2) if mae_base > 0 else 0.0,
        "rmse_base": round(rmse_base, 4),
        "rmse_corr": round(rmse_corr, 4),
        "rmse_pct": round((rmse_base - rmse_corr) / rmse_base * 100, 2) if rmse_base > 0 else 0.0,
    }


def main():
    rows = load_rows()
    if not rows:
        print(f"No {FIELD} rows in pair log; aborting.", file=sys.stderr)
        return 1

    # Determine max date + test/train split
    dates = sorted({r["date"] for r in rows})
    max_date = datetime.strptime(dates[-1], "%Y-%m-%d").date()
    test_start = max_date - timedelta(days=TEST_WINDOW_DAYS)
    train_rows = [r for r in rows
                  if datetime.strptime(r["date"], "%Y-%m-%d").date() < test_start]
    test_rows = [r for r in rows
                 if datetime.strptime(r["date"], "%Y-%m-%d").date() >= test_start]

    # Build daily residual dicts against L2 and Production baselines
    daily_res_l2 = build_daily_residual(rows, "fc_l2")
    daily_res_prod = build_daily_residual(rows, "fc_prod")

    lines = []
    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 100)
    emit(f"{FIELD} RESIDUAL-PERSISTENCE — STAGE 1 PREVIEW")
    emit("=" * 100)
    emit(f"Total {FIELD} rows: {len(rows):,}  (train {len(train_rows):,} / test {len(test_rows):,})")
    emit(f"Dates: {dates[0]} → {dates[-1]}. Test window: last {TEST_WINDOW_DAYS} days ({test_start}+).")
    emit("")

    # [A] Grid search over window sizes on TEST window
    emit("-" * 100)
    emit("[A] Grid search — window ∈ {1, 2, 3, 5, 7, 14} days, held-out on last 7 days")
    emit("-" * 100)
    emit(f"{'window':<8}{'baseline':<12}{'n_test':>8}{'MAE base':>10}{'MAE corr':>10}"
         f"{'ΔMAE %':>10}{'RMSE base':>11}{'RMSE corr':>11}{'ΔRMSE %':>10}")
    grid = []
    for window in WINDOW_GRID:
        for baseline_key, baseline_lbl, daily_res in (
            ("fc_l2", "L2-alone", daily_res_l2),
            ("fc_prod", "Production", daily_res_prod),
        ):
            s = score(test_rows, daily_res, baseline_key, window)
            if s is None:
                continue
            grid.append({"window": window, "baseline": baseline_lbl, **s})
            mark = " ★" if s["mae_pct"] >= 1.0 else ("  ⚠" if s["mae_pct"] < -0.5 else "")
            emit(
                f"{window:<8}{baseline_lbl:<12}{s['n']:>8,}"
                f"{s['mae_base']:>10.4f}{s['mae_corr']:>10.4f}{s['mae_pct']:>+10.2f}"
                f"{s['rmse_base']:>11.4f}{s['rmse_corr']:>11.4f}{s['rmse_pct']:>+10.2f}{mark}"
            )
    emit("")

    # Find best (largest MAE improvement, must be positive)
    best = max(grid, key=lambda g: g["mae_pct"]) if grid else None
    if not best or best["mae_pct"] < 1.0:
        emit("Verdict: FAIL — no grid combo hits +1% MAE improvement on held-out.")
        _finalize(lines, grid, None, None, None)
        return 1
    emit(f"Best combo: window={best['window']}d on {best['baseline']} → "
         f"MAE {best['mae_pct']:+.2f}%, RMSE {best['rmse_pct']:+.2f}%")
    emit("")

    # [B] Per-regime cross-cut for best combo
    emit("-" * 100)
    emit(f"[B] Per-regime cross-cut — best combo (window={best['window']}d, {best['baseline']})")
    emit("-" * 100)
    daily_res = daily_res_l2 if best["baseline"] == "L2-alone" else daily_res_prod
    baseline_key = "fc_l2" if best["baseline"] == "L2-alone" else "fc_prod"
    regime_results = {}
    regimes = sorted({r["regime"] for r in test_rows})
    emit(f"{'regime':<14}{'n_test':>8}{'MAE base':>10}{'MAE corr':>10}{'ΔMAE %':>10}"
         f"{'RMSE base':>11}{'RMSE corr':>11}{'ΔRMSE %':>10}   verdict")
    for regime in regimes:
        s = score(test_rows, daily_res, baseline_key, best["window"],
                  filter_fn=lambda r, rg=regime: r["regime"] == rg)
        if s is None or s["n"] < MIN_N_PER_REGIME:
            continue
        regime_results[regime] = s
        if s["mae_pct"] >= 1.0:
            v = "WIN"
        elif s["mae_pct"] <= -1.0:
            v = "LOSE"
        else:
            v = "FLAT"
        mark = " ★" if v == "WIN" else ("  ⚠" if v == "LOSE" else "")
        emit(
            f"{regime:<14}{s['n']:>8,}"
            f"{s['mae_base']:>10.4f}{s['mae_corr']:>10.4f}{s['mae_pct']:>+10.2f}"
            f"{s['rmse_base']:>11.4f}{s['rmse_corr']:>11.4f}{s['rmse_pct']:>+10.2f}"
            f"   {v}{mark}"
        )
    n_win = sum(1 for r in regime_results.values() if r["mae_pct"] >= 1.0)
    n_lose = sum(1 for r in regime_results.values() if r["mae_pct"] <= -1.0)
    emit(f"\nRegime summary: {n_win} WIN, {len(regime_results) - n_win - n_lose} FLAT, {n_lose} LOSE")
    emit("")

    # [C] Halves-check on TRAINING window (excl test)
    emit("-" * 100)
    emit(f"[C] Halves check on training (excl. test) — best combo (window={best['window']}d)")
    emit("-" * 100)
    train_dates = sorted({r["date"] for r in train_rows})
    if len(train_dates) < 10:
        emit("  (training set too short for halves check)")
        halves = None
    else:
        mid = train_dates[len(train_dates) // 2]
        first_half = [r for r in train_rows if r["date"] < mid]
        second_half = [r for r in train_rows if r["date"] >= mid]
        h1 = score(first_half, daily_res, baseline_key, best["window"])
        h2 = score(second_half, daily_res, baseline_key, best["window"])
        halves = {"first": h1, "second": h2, "split_at": mid}
        emit(f"  first half   ({train_dates[0]} → {mid}, n={h1['n']:,}): "
             f"MAE {h1['mae_pct']:+.2f}%, RMSE {h1['rmse_pct']:+.2f}%")
        emit(f"  second half  ({mid} → {train_dates[-1]}, n={h2['n']:,}): "
             f"MAE {h2['mae_pct']:+.2f}%, RMSE {h2['rmse_pct']:+.2f}%")
        both_win = (h1["mae_pct"] >= 0.5 and h2["mae_pct"] >= 0.5)
        emit(f"  → Halves stability: {'✓ BOTH WIN' if both_win else '✗ SIGN FLIP or WEAK HALF'}")
    emit("")

    # Verdict
    emit("=" * 100)
    if best["mae_pct"] >= 1.0 and n_win > n_lose and halves and (
        halves["first"]["mae_pct"] >= 0.5 and halves["second"]["mae_pct"] >= 0.5):
        emit(f"Verdict: STAGE 1 PROMOTE — window={best['window']}d, {best['baseline']}. "
             f"Test MAE {best['mae_pct']:+.2f}%, per-regime {n_win}/{len(regime_results)} WIN, "
             f"halves both positive. Ready for Stage 2 preview.")
    elif n_lose > n_win:
        emit(f"Verdict: HOLD — best combo wins on aggregate ({best['mae_pct']:+.2f}%) but "
             f"loses in {n_lose} regime(s). Skip-table or regime-gated variant needed.")
    else:
        emit(f"Verdict: MARGINAL — best combo at {best['mae_pct']:+.2f}%. Re-run in 3 days.")
    emit("=" * 100)

    _finalize(lines, grid, best, regime_results, halves)
    return 0


def _finalize(lines, grid, best, regime_results, halves):
    text = "\n".join(lines)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    from datetime import datetime as _dt, timezone as _tz
    payload = {
        "generated_at": _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"forecast_error_log.jsonl (field={FIELD})",
        "test_window_days": TEST_WINDOW_DAYS,
        "window_grid": WINDOW_GRID,
        "grid_results": grid,
        "best": best,
        "per_regime": regime_results,
        "halves_check": halves,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    print(f"wrote {OUT_JSON}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

"""Shared Stage 1 harness for residual-persistence hypotheses.

Extracted 2026-08-30 v0.6.522 after `/code-review high` on h Stage 1 flagged
three copies of the same 317-line body (h, dp, wg) drifting in maintenance
(the v0.6.400a fc_prod-reconstruction patch was ported to dp only, not to
h/wg — the drift was rediscovered today when un-skipping h Stage 1).

Callers:
    from _residual_persistence_stage1 import run_stage1
    sys.exit(run_stage1(field="h"))

Bug fixes over the pre-refactor sibling scripts:
- fc_prod attribution is strict: require applied_layer stamp AND
  forecast_{applied} present. Never fall through to top-level `forecast`
  (which is L2 by design per [[feedback_top_level_forecast_is_l2]]) — that
  quietly contaminated the Production-baseline grid with L2 rows.
- halves check guards score() returning None (n==0) rather than dereferencing
  h1['n'] into an AttributeError.
- Test-window off-by-one: TEST_WINDOW_DAYS=7 now covers 7 dates, not 8.
- Halves label prints first-half end as (mid − 1 day) so the boundary reads
  correctly (mid is the first date of second_half).
- Removed the redundant _dt/_tz local re-import in _finalize.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"

DEFAULT_WINDOW_GRID = [1, 2, 3, 5, 7, 14]
DEFAULT_TEST_WINDOW_DAYS = 7
DEFAULT_MIN_N_PER_REGIME = 300


def _parse_date(vt):
    return vt[:10] if vt and len(vt) >= 10 else None


def _parse_hour(vt):
    try:
        return int(vt[11:13])
    except (TypeError, ValueError, IndexError):
        return None


def _load_rows(field):
    """Return list of dicts with: date, hour, obs, fc_l2, fc_prod, regime.

    Production attribution is strict — a row is skipped if applied_layer is
    missing or if forecast_{applied} is missing. That prevents silent
    L2 contamination when the top-level `forecast` field was the fallback."""
    rows = []
    skipped_no_applied = 0
    skipped_no_forecast_applied = 0
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != field:
                continue
            vt = r.get("valid_time")
            ob = r.get("observed")
            fc_l2 = r.get("forecast_l2")
            if vt is None or ob is None or fc_l2 is None:
                continue
            applied = r.get("applied_layer")
            if not applied:
                skipped_no_applied += 1
                continue
            fc_prod = r.get(f"forecast_{applied}")
            if fc_prod is None:
                skipped_no_forecast_applied += 1
                continue
            date = _parse_date(vt)
            hour = _parse_hour(vt)
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
    return rows, {"skipped_no_applied": skipped_no_applied,
                  "skipped_no_forecast_applied": skipped_no_forecast_applied}


def _build_daily_residual(rows, baseline_key):
    """daily_res[(date, hour)] = mean signed residual (obs - baseline) that day."""
    buckets = defaultdict(list)
    for r in rows:
        buckets[(r["date"], r["hour"])].append(r["obs"] - r[baseline_key])
    return {k: sum(v) / len(v) for k, v in buckets.items()}


def _compute_correction(daily_res, date_str, hour, window_days):
    """Mean residual over prior window_days at same (hour). Zero if no data."""
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    vals = []
    for lag in range(1, window_days + 1):
        prev = (d - timedelta(days=lag)).isoformat()
        v = daily_res.get((prev, hour))
        if v is not None:
            vals.append(v)
    return sum(vals) / len(vals) if vals else 0.0


def _score(rows, daily_res, baseline_key, window_days, filter_fn=None):
    n = 0
    s_ae_base = s_ae_corr = 0.0
    s_se_base = s_se_corr = 0.0
    for r in rows:
        if filter_fn is not None and not filter_fn(r):
            continue
        corr = _compute_correction(daily_res, r["date"], r["hour"], window_days)
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


def run_stage1(field,
               out_txt=None,
               out_json=None,
               window_grid=None,
               test_window_days=DEFAULT_TEST_WINDOW_DAYS,
               min_n_per_regime=DEFAULT_MIN_N_PER_REGIME):
    """Run Stage 1 preview for `field`. Returns 0 on success, 1 on FAIL/data-empty."""
    window_grid = window_grid or DEFAULT_WINDOW_GRID
    if out_txt is None:
        out_txt = os.path.join(SCRIPT_DIR, "output",
                               f"h_{field}_residual_persistence_stage1.txt")
    if out_json is None:
        out_json = os.path.join(SCRIPT_DIR, "output",
                                f"h_{field}_residual_persistence_stage1.json")

    rows, load_stats = _load_rows(field)
    if not rows:
        print(f"No {field} rows in pair log; aborting.", file=sys.stderr)
        return 1

    dates = sorted({r["date"] for r in rows})
    max_date = datetime.strptime(dates[-1], "%Y-%m-%d").date()
    # inclusive last-N-days window: max_date - (N-1) covers N distinct dates
    test_start = max_date - timedelta(days=test_window_days - 1)
    train_rows = [r for r in rows
                  if datetime.strptime(r["date"], "%Y-%m-%d").date() < test_start]
    test_rows = [r for r in rows
                 if datetime.strptime(r["date"], "%Y-%m-%d").date() >= test_start]

    daily_res_l2 = _build_daily_residual(rows, "fc_l2")
    daily_res_prod = _build_daily_residual(rows, "fc_prod")

    lines = []

    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 100)
    emit(f"{field} RESIDUAL-PERSISTENCE — STAGE 1 PREVIEW")
    emit("=" * 100)
    emit(f"Total {field} rows: {len(rows):,}  (train {len(train_rows):,} / test {len(test_rows):,})")
    emit(f"Dates: {dates[0]} → {dates[-1]}. Test window: last {test_window_days} days ({test_start}+).")
    if load_stats["skipped_no_applied"] or load_stats["skipped_no_forecast_applied"]:
        emit(f"Load-time strict-Production skips: "
             f"no applied_layer={load_stats['skipped_no_applied']:,}, "
             f"applied stamp but forecast_{{applied}} missing={load_stats['skipped_no_forecast_applied']:,}")
    emit("")

    emit("-" * 100)
    emit(f"[A] Grid search — window ∈ {window_grid} days, held-out on last {test_window_days} days")
    emit("-" * 100)
    emit(f"{'window':<8}{'baseline':<12}{'n_test':>8}{'MAE base':>10}{'MAE corr':>10}"
         f"{'ΔMAE %':>10}{'RMSE base':>11}{'RMSE corr':>11}{'ΔRMSE %':>10}")
    grid = []
    for window in window_grid:
        for baseline_key, baseline_lbl, daily_res in (
            ("fc_l2", "L2-alone", daily_res_l2),
            ("fc_prod", "Production", daily_res_prod),
        ):
            s = _score(test_rows, daily_res, baseline_key, window)
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

    train_dates_sorted = sorted({r["date"] for r in train_rows})
    have_halves = len(train_dates_sorted) >= 10
    mid = train_dates_sorted[len(train_dates_sorted) // 2] if have_halves else None
    first_half = [r for r in train_rows if r["date"] < mid] if have_halves else []
    second_half = [r for r in train_rows if r["date"] >= mid] if have_halves else []
    if have_halves:
        for g in grid:
            dr = daily_res_l2 if g["baseline"] == "L2-alone" else daily_res_prod
            key = "fc_l2" if g["baseline"] == "L2-alone" else "fc_prod"
            h1 = _score(first_half, dr, key, g["window"])
            h2 = _score(second_half, dr, key, g["window"])
            g["_halves"] = {"first": h1, "second": h2, "split_at": mid}
            g["halves_ok"] = bool(h1 and h2
                                  and h1["mae_pct"] >= 0.5
                                  and h2["mae_pct"] >= 0.5)

    raw_best = max(grid, key=lambda g: g["mae_pct"]) if grid else None
    stable = [g for g in grid if g.get("halves_ok")]
    best = max(stable, key=lambda g: g["mae_pct"]) if stable else raw_best
    if have_halves and best is not None and raw_best is not None and best is not raw_best:
        emit(f"Halves-preference override: raw-max window={raw_best['window']}d "
             f"{raw_best['baseline']} (test {raw_best['mae_pct']:+.2f}%) fails halves; "
             f"selecting halves-stable window={best['window']}d {best['baseline']} "
             f"(test {best['mae_pct']:+.2f}%).")
        emit("")
    if not best or best["mae_pct"] < 1.0:
        emit("Verdict: FAIL — no grid combo hits +1% MAE improvement on held-out.")
        _finalize(lines, grid, None, None, None, field, test_window_days,
                  window_grid, out_txt, out_json)
        return 1
    emit(f"Best combo: window={best['window']}d on {best['baseline']} → "
         f"MAE {best['mae_pct']:+.2f}%, RMSE {best['rmse_pct']:+.2f}%")
    emit("")

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
        s = _score(test_rows, daily_res, baseline_key, best["window"],
                   filter_fn=lambda r, rg=regime: r["regime"] == rg)
        if s is None or s["n"] < min_n_per_regime:
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

    emit("-" * 100)
    emit(f"[C] Halves check on training (excl. test) — best combo (window={best['window']}d)")
    emit("-" * 100)
    halves = None
    if not have_halves:
        emit("  (training set too short for halves check)")
    else:
        halves = best.get("_halves")
        h1 = halves["first"] if halves else None
        h2 = halves["second"] if halves else None
        mid_prev_iso = (datetime.strptime(mid, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()
        if h1 is None or h2 is None:
            emit(f"  halves check skipped — one half returned 0 rows "
                 f"(first={'None' if h1 is None else h1['n']}, "
                 f"second={'None' if h2 is None else h2['n']})")
        else:
            emit(f"  first half   ({train_dates_sorted[0]} → {mid_prev_iso}, n={h1['n']:,}): "
                 f"MAE {h1['mae_pct']:+.2f}%, RMSE {h1['rmse_pct']:+.2f}%")
            emit(f"  second half  ({mid} → {train_dates_sorted[-1]}, n={h2['n']:,}): "
                 f"MAE {h2['mae_pct']:+.2f}%, RMSE {h2['rmse_pct']:+.2f}%")
            emit(f"  → Halves stability: {'✓ BOTH WIN' if best.get('halves_ok') else '✗ SIGN FLIP or WEAK HALF'}")
    emit("")

    emit("=" * 100)
    halves_ok = (halves is not None
                 and halves["first"] is not None
                 and halves["second"] is not None
                 and halves["first"]["mae_pct"] >= 0.5
                 and halves["second"]["mae_pct"] >= 0.5)
    if best["mae_pct"] >= 1.0 and n_win > n_lose and halves_ok:
        emit(f"Verdict: STAGE 1 PROMOTE — window={best['window']}d, {best['baseline']}. "
             f"Test MAE {best['mae_pct']:+.2f}%, per-regime {n_win}/{len(regime_results)} WIN, "
             f"halves both positive. Ready for Stage 2 preview.")
    elif n_lose > n_win:
        emit(f"Verdict: HOLD — best combo wins on aggregate ({best['mae_pct']:+.2f}%) but "
             f"loses in {n_lose} regime(s). Skip-table or regime-gated variant needed.")
    else:
        emit(f"Verdict: MARGINAL — best combo at {best['mae_pct']:+.2f}%. Re-run in 3 days.")
    emit("=" * 100)

    _finalize(lines, grid, best, regime_results, halves, field, test_window_days,
              window_grid, out_txt, out_json)
    return 0


def _finalize(lines, grid, best, regime_results, halves, field, test_window_days,
              window_grid, out_txt, out_json):
    text = "\n".join(lines)
    os.makedirs(os.path.dirname(out_txt), exist_ok=True)
    with open(out_txt, "w") as fh:
        fh.write(text + "\n")
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"forecast_error_log.jsonl (field={field})",
        "test_window_days": test_window_days,
        "window_grid": window_grid,
        "grid_results": grid,
        "best": best,
        "per_regime": regime_results,
        "halves_check": halves,
    }
    with open(out_json, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {out_txt}", file=sys.stderr)
    print(f"wrote {out_json}", file=sys.stderr)

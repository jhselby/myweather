"""
Daily L2-residual persistence at same clock hour — untapped short-term drift.

Hypothesis: L4 (diurnal) averages hour-of-day bias over ~21 days. If the true
bias drifts on a 1-3 day timescale (weather regime shifts, air-mass changes),
L4's long window smooths it out and we leave signal on the table.

Test: for each field × obs_hour (0-23 local), aggregate L2 residual = obs − L2_forecast
by obs_date. Compute lag-1, lag-2, lag-3 day autocorrelation of this per-hour
time series. If ρ_1 > 0.3 for a hour, yesterday's residual at that hour predicts
today's — and we can add a recent-drift correction.

Then simulate the correction: for each pair row, subtract the mean signed L2
residual at same (field, hour) from the prior N days. Report MAE improvement
vs L2 alone, held-out.

Run:
    python3 analysis/h_daily_residual_persistence.py

Output:
    analysis/output/h_daily_residual_persistence.txt
    analysis/output/h_daily_residual_persistence.json
"""
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_daily_residual_persistence.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_daily_residual_persistence.json")

# Only additive-L2 fields where forecast_l2 is meaningful (Kalman-corrected)
FIELDS = ["t", "dp", "h", "ws", "wg", "pr", "cc", "cl", "cm", "ch", "sr"]

# Simulate correction using rolling mean of last N days
CORRECTION_WINDOW_DAYS = 2  # short-term: 2 days = catch 1-3 day regime drift
MIN_DAYS_PER_HOUR = 10       # need at least this many days per (field, hour) for autocorr


def parse_local_hour(vt):
    """valid_time is local ISO 'YYYY-MM-DDTHH:00'. Return int hour."""
    if not vt or len(vt) < 13:
        return None
    try:
        return int(vt[11:13])
    except ValueError:
        return None


def parse_local_date(vt):
    if not vt or len(vt) < 10:
        return None
    return vt[:10]


def autocorr(vals, lag):
    """Sample autocorrelation of vals at given lag. Returns None if too few pairs."""
    n = len(vals) - lag
    if n < 5:
        return None
    x = vals[:-lag] if lag > 0 else vals
    y = vals[lag:] if lag > 0 else vals
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    var_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
    var_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5
    if var_x == 0 or var_y == 0:
        return None
    return num / (var_x * var_y)


def compute():
    """Stream pair log; bucket by field × (obs_date, obs_hour)."""
    # per_bucket[(field, date, hour)] = list of L2 residuals across leads
    per_bucket = defaultdict(list)
    # also: per_field_lead_rows[(field, date, hour, lead)] for simulation later
    sim_rows = []  # (field, date, hour, obs_time, fc_l2, obs)
    n_scanned = n_kept = 0
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            n_scanned += 1
            f = r.get("field")
            if f not in FIELDS:
                continue
            vt = r.get("valid_time")
            ob = r.get("observed")
            fc_l2 = r.get("forecast_l2")
            if vt is None or ob is None or fc_l2 is None:
                continue
            date = parse_local_date(vt)
            hour = parse_local_hour(vt)
            if date is None or hour is None:
                continue
            res = float(ob) - float(fc_l2)
            per_bucket[(f, date, hour)].append(res)
            sim_rows.append((f, date, hour, vt, float(fc_l2), float(ob)))
            n_kept += 1

    # Reduce per_bucket to daily mean signed residual per (field, date, hour)
    daily_mean = {}  # (field, date, hour) -> mean signed residual
    daily_n = {}
    for k, vals in per_bucket.items():
        if len(vals) < 1:
            continue
        daily_mean[k] = sum(vals) / len(vals)
        daily_n[k] = len(vals)

    return daily_mean, daily_n, sim_rows, n_scanned, n_kept


def per_field_autocorr(daily_mean, daily_n):
    """For each (field, hour), build a date-sorted series of mean residuals,
    compute lag-1/2/3 autocorrelation. Return dict {(field, hour): {n, mean, std, ac1, ac2, ac3}}."""
    # Group by (field, hour) -> list of (date, mean)
    grouped = defaultdict(list)
    for (f, d, h), m in daily_mean.items():
        grouped[(f, h)].append((d, m))
    out = {}
    for (f, h), items in grouped.items():
        items.sort()  # by date string
        # Fill gaps: build a contiguous series over the actual date span
        if not items:
            continue
        dates = [datetime.strptime(d, "%Y-%m-%d").date() for d, _ in items]
        vals_by_date = {d: v for d, v in items}
        # Contiguous span
        start, end = dates[0], dates[-1]
        contiguous = []
        cur = start
        while cur <= end:
            s = cur.isoformat()
            contiguous.append(vals_by_date.get(s))
            cur = cur + timedelta(days=1)
        # Trim leading/trailing None
        # For autocorr, treat missing days as gaps — drop them from BOTH x and y
        # by keeping (val_t, val_t+lag) pairs where BOTH are non-None.
        def _autocorr_gap_safe(series, lag):
            pairs = [(series[i], series[i + lag]) for i in range(len(series) - lag)
                     if series[i] is not None and series[i + lag] is not None]
            if len(pairs) < 5:
                return None, len(pairs)
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            mx = sum(xs) / len(xs)
            my = sum(ys) / len(ys)
            num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            vx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
            vy = (sum((y - my) ** 2 for y in ys)) ** 0.5
            if vx == 0 or vy == 0:
                return None, len(pairs)
            return num / (vx * vy), len(pairs)

        present_vals = [v for v in contiguous if v is not None]
        if len(present_vals) < MIN_DAYS_PER_HOUR:
            continue
        ac1, n1 = _autocorr_gap_safe(contiguous, 1)
        ac2, n2 = _autocorr_gap_safe(contiguous, 2)
        ac3, n3 = _autocorr_gap_safe(contiguous, 3)
        mean = sum(present_vals) / len(present_vals)
        std = statistics.stdev(present_vals) if len(present_vals) > 1 else 0.0
        out[(f, h)] = {
            "n_days": len(present_vals),
            "mean_residual": round(mean, 4),
            "std_residual": round(std, 4),
            "ac1": round(ac1, 3) if ac1 is not None else None,
            "ac1_n_pairs": n1,
            "ac2": round(ac2, 3) if ac2 is not None else None,
            "ac3": round(ac3, 3) if ac3 is not None else None,
        }
    return out


def simulate_correction(sim_rows, daily_mean):
    """For each row, compute correction = mean of signed L2 residual over prior
    CORRECTION_WINDOW_DAYS at the same (field, hour). Compare MAE before/after
    on held-out (last 7 days as test; correction can only use days before that).
    """
    # Sort rows by valid_time
    sim_rows.sort(key=lambda r: r[3])
    if not sim_rows:
        return None
    # Determine test window
    max_vt = sim_rows[-1][3]
    max_date = datetime.strptime(max_vt[:10], "%Y-%m-%d").date()
    test_start = max_date - timedelta(days=7)

    per_field = defaultdict(lambda: {"n_test": 0, "sum_l2": 0.0, "sum_l2_sq": 0.0,
                                     "sum_corr": 0.0, "sum_corr_sq": 0.0,
                                     "n_applied": 0})
    for f, date_str, hour, vt, fc_l2, obs in sim_rows:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        if d < test_start:
            continue  # only score test window
        # Correction: mean residual at same (f, hour) over prior CORRECTION_WINDOW_DAYS
        prior_vals = []
        for lag in range(1, CORRECTION_WINDOW_DAYS + 1):
            prev = (d - timedelta(days=lag)).isoformat()
            v = daily_mean.get((f, prev, hour))
            if v is not None:
                prior_vals.append(v)
        correction = sum(prior_vals) / len(prior_vals) if prior_vals else 0.0
        err_l2 = fc_l2 - obs
        err_corr = (fc_l2 + correction) - obs
        p = per_field[f]
        p["n_test"] += 1
        p["sum_l2"] += abs(err_l2)
        p["sum_l2_sq"] += err_l2 * err_l2
        p["sum_corr"] += abs(err_corr)
        p["sum_corr_sq"] += err_corr * err_corr
        if prior_vals:
            p["n_applied"] += 1

    results = {}
    for f, p in per_field.items():
        n = p["n_test"]
        if n < 100:
            continue
        mae_l2 = p["sum_l2"] / n
        mae_corr = p["sum_corr"] / n
        rmse_l2 = (p["sum_l2_sq"] / n) ** 0.5
        rmse_corr = (p["sum_corr_sq"] / n) ** 0.5
        mae_pct = (mae_l2 - mae_corr) / mae_l2 * 100 if mae_l2 > 0 else 0.0
        rmse_pct = (rmse_l2 - rmse_corr) / rmse_l2 * 100 if rmse_l2 > 0 else 0.0
        results[f] = {
            "n_test": n,
            "n_applied": p["n_applied"],
            "mae_l2": round(mae_l2, 4),
            "mae_corr": round(mae_corr, 4),
            "mae_improve_pct": round(mae_pct, 2),
            "rmse_l2": round(rmse_l2, 4),
            "rmse_corr": round(rmse_corr, 4),
            "rmse_improve_pct": round(rmse_pct, 2),
        }
    return results


def emit(autocorr_data, sim_results, n_scanned, n_kept):
    lines = []
    lines.append("=" * 100)
    lines.append("L2-RESIDUAL DAILY PERSISTENCE — lag-1/2/3 day autocorr at same clock hour")
    lines.append("=" * 100)
    lines.append(f"Scanned {n_scanned:,} pair rows; kept {n_kept:,} with L2 forecast + obs.")
    lines.append("Question: does yesterday's mean (obs − L2_fc) at hour H predict today's at hour H?")
    lines.append(f"If yes (ρ_1 > 0.3), a rolling {CORRECTION_WINDOW_DAYS}-day correction at same hour")
    lines.append("could reduce MAE without needing full L4 refit.")
    lines.append("")

    # Per-field summary of autocorr — max/mean ρ_1 across hours, count of hours with ρ_1 > 0.3
    per_field_summary = defaultdict(lambda: {"hours": 0, "max_ac1": None, "mean_ac1_num": 0.0,
                                             "mean_ac1_den": 0, "n_hours_strong": 0})
    for (f, h), d in autocorr_data.items():
        s = per_field_summary[f]
        s["hours"] += 1
        if d["ac1"] is not None:
            s["mean_ac1_num"] += d["ac1"]
            s["mean_ac1_den"] += 1
            if s["max_ac1"] is None or d["ac1"] > s["max_ac1"]:
                s["max_ac1"] = d["ac1"]
            if d["ac1"] >= 0.3:
                s["n_hours_strong"] += 1

    lines.append("-" * 100)
    lines.append("PER-FIELD SUMMARY — lag-1 autocorrelation of daily residual per hour")
    lines.append("-" * 100)
    lines.append(f"{'field':<6}{'hours':>7}{'max_ρ1':>10}{'mean_ρ1':>10}{'hours ρ1≥0.3':>15}")
    lines.append("-" * 48)
    for f in FIELDS:
        s = per_field_summary.get(f)
        if s is None or s["hours"] == 0:
            continue
        mean_ac1 = s["mean_ac1_num"] / s["mean_ac1_den"] if s["mean_ac1_den"] else None
        lines.append(
            f"{f:<6}{s['hours']:>7}"
            f"{s['max_ac1']:>+10.3f}" if s['max_ac1'] is not None else f"{f:<6}{s['hours']:>7}{'--':>10}"
        )
        # (re-do with mean and strong count for correctness)
    # Rewrite properly since the f-string above broke on the ternary
    lines_ok = []
    for f in FIELDS:
        s = per_field_summary.get(f)
        if s is None or s["hours"] == 0:
            continue
        max_ac1 = s["max_ac1"]
        mean_ac1 = (s["mean_ac1_num"] / s["mean_ac1_den"]) if s["mean_ac1_den"] else None
        max_txt = f"{max_ac1:+.3f}" if max_ac1 is not None else "  --"
        mean_txt = f"{mean_ac1:+.3f}" if mean_ac1 is not None else "  --"
        strong = s["n_hours_strong"]
        mark = " ★" if strong >= 3 else ("  ⚠" if strong >= 1 else "  ")
        lines_ok.append(f"{f:<6}{s['hours']:>7}{max_txt:>10}{mean_txt:>10}{strong:>15}{mark}")
    # Replace the malformed table with the correct one
    # Find the last table entry we appended and truncate
    while lines and not lines[-1].startswith("-"):
        lines.pop()
    lines.extend(lines_ok)
    lines.append("")

    # Detailed hour-of-day breakdown for the top-3 fields by strong-hours count
    top_fields = sorted(per_field_summary.items(), key=lambda x: -x[1]["n_hours_strong"])[:3]
    if top_fields and top_fields[0][1]["n_hours_strong"] > 0:
        lines.append("-" * 100)
        lines.append(f"TOP 3 FIELDS BY # HOURS WITH STRONG LAG-1 AUTOCORR (ρ_1 ≥ 0.3)")
        lines.append("-" * 100)
        for f, s in top_fields:
            if s["n_hours_strong"] == 0:
                continue
            lines.append(f"\n{f}:")
            lines.append(f"  {'hour':<6}{'n_days':>8}{'mean_res':>12}{'std_res':>10}{'ρ_1':>8}{'ρ_2':>8}{'ρ_3':>8}")
            for h in range(24):
                d = autocorr_data.get((f, h))
                if d is None:
                    continue
                ac1 = f"{d['ac1']:+.2f}" if d['ac1'] is not None else "  --"
                ac2 = f"{d['ac2']:+.2f}" if d['ac2'] is not None else "  --"
                ac3 = f"{d['ac3']:+.2f}" if d['ac3'] is not None else "  --"
                mark = " ★" if d['ac1'] is not None and d['ac1'] >= 0.3 else ""
                lines.append(f"  {h:02d}:00 {d['n_days']:>8}"
                             f"{d['mean_residual']:>+12.3f}{d['std_residual']:>10.3f}"
                             f"{ac1:>8}{ac2:>8}{ac3:>8}{mark}")
        lines.append("")

    # Simulation results
    lines.append("=" * 100)
    lines.append(f"HELD-OUT SIMULATION — rolling {CORRECTION_WINDOW_DAYS}-day mean residual correction")
    lines.append("=" * 100)
    lines.append("Test window: last 7 days. Training: everything prior.")
    lines.append("Correction: for each row, subtract mean signed L2-residual over the same (field, hour)")
    lines.append(f"from the prior {CORRECTION_WINDOW_DAYS} days. Compare MAE + RMSE.")
    lines.append("")
    if sim_results:
        lines.append(f"{'field':<6}{'n_test':>8}{'n_applied':>10}"
                     f"{'MAE_L2':>10}{'MAE_corr':>10}{'Δ MAE %':>10}"
                     f"{'RMSE_L2':>10}{'RMSE_corr':>10}{'Δ RMSE %':>10}")
        lines.append("-" * 96)
        for f in FIELDS:
            r = sim_results.get(f)
            if r is None:
                continue
            mae_mark = " ★" if r['mae_improve_pct'] >= 1.0 else ("  ⚠" if r['mae_improve_pct'] < -0.5 else "")
            lines.append(
                f"{f:<6}{r['n_test']:>8,}{r['n_applied']:>10,}"
                f"{r['mae_l2']:>10.4f}{r['mae_corr']:>10.4f}{r['mae_improve_pct']:>+10.2f}"
                f"{r['rmse_l2']:>10.4f}{r['rmse_corr']:>10.4f}{r['rmse_improve_pct']:>+10.2f}"
                f"{mae_mark}"
            )
    lines.append("")

    # Verdict
    ship_fields = [f for f, r in (sim_results or {}).items() if r['mae_improve_pct'] >= 1.0]
    if ship_fields:
        lines.append(f"Verdict: STAGE 0 HIT — {len(ship_fields)} field(s) show ≥1% MAE improvement "
                     f"held-out: {', '.join(sorted(ship_fields))}. Warrants Stage 1 development.")
    else:
        lines.append("Verdict: NO STAGE 0 HIT — no field crosses +1% MAE improvement on held-out.")
        lines.append("Rolling-day residual persistence does not add value on top of L2.")
    return "\n".join(lines)


def main():
    daily_mean, daily_n, sim_rows, n_scanned, n_kept = compute()
    autocorr_data = per_field_autocorr(daily_mean, daily_n)
    sim_results = simulate_correction(sim_rows, daily_mean)

    text = emit(autocorr_data, sim_results, n_scanned, n_kept)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")

    from datetime import datetime as _dt, timezone as _tz
    payload = {
        "generated_at": _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "forecast_error_log.jsonl",
        "correction_window_days": CORRECTION_WINDOW_DAYS,
        "min_days_per_hour": MIN_DAYS_PER_HOUR,
        "autocorr_per_hour": {f"{f}/{h:02d}": v for (f, h), v in autocorr_data.items()},
        "simulation": sim_results,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())

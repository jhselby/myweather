
import sys, os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from _cache import cached_path
#!/usr/bin/env python3
"""
Decay τ tuning: is τ=14 days actually optimal? Maybe humidity wants a
shorter window (fast-varying) and pressure wants a longer one (slow).

Walk-forward validation:
  1. Pick a cutoff date (default: 3 days ago).
  2. For each τ in {7, 10, 14, 21, 28}:
       - Compute per-(field, lead_h) decay corrections using rows BEFORE the
         cutoff, weighted exp(-age_days/τ).
       - Apply those corrections to rows AFTER the cutoff.
       - Measure MAE on the held-out window.
  3. The τ with the lowest held-out MAE is optimal for that field.

If the optimum varies by field, per-field τ is worth implementing in
decay_fit.py. If everything wants ~14d, leave the global value alone.

Output:
  analysis/output/decay_tau_tuning_summary.txt

Run:
    python3 analysis/decay_tau_tuning.py
    python3 analysis/decay_tau_tuning.py --cutoff-days 5

Note: pair log retention is 30d, so the longest useful τ is bounded. τ=28
already weights the oldest row in the window at ~exp(-30/28) ≈ 0.34, which
is most of the available decay range.
"""
import argparse
import json
import math
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

FIELDS = ["t", "dp", "h", "ws", "wg", "cc", "sr", "pr", "pa"]
FIELD_LABELS = {
    "t": "Temperature", "dp": "Dew point", "h": "Humidity",
    "ws": "Wind speed", "wg": "Wind gust", "cc": "Cloud cover",
    "sr": "Solar rad.", "pr": "Pressure", "pa": "Precip amt",
}
TAUS = [7, 10, 14, 21, 28, 35, 42]
LEAD_BINS = 48


def _fetch_jsonl_lines(url):
    with open(cached_path(url), 'rb') as resp:
        for raw in resp:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff-days", type=float, default=3.0,
                    help="Days back from now for the train/test split (default 3.0)")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    now = datetime.utcnow()
    cutoff = now - timedelta(days=args.cutoff_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M")
    print(f"Fetching {ERROR_LOG_URL}…  (train < {cutoff_iso} < test)")

    # Load rows into memory grouped by field. For each: (obs_dt, lead_h, error, forecast, obs).
    # Use 'error' (L2 residual) as the signal — same as Fitter's decay aggregation.
    train_rows = defaultdict(list)  # field -> [(obs_dt, lead_h, error)]
    test_rows  = defaultdict(list)
    n_in = 0
    n_train = 0
    n_test = 0
    for row in _fetch_jsonl_lines(ERROR_LOG_URL):
        n_in += 1
        field = row.get("field")
        if field not in FIELDS:
            continue
        lead = row.get("lead_h")
        err = row.get("error")
        obs_t = row.get("obs_time", "")
        if lead is None or err is None or not obs_t:
            continue
        if not (0 <= lead < LEAD_BINS):
            continue
        try:
            obs_dt = datetime.strptime(obs_t, "%Y-%m-%dT%H:%M")
        except ValueError:
            continue
        if obs_dt < cutoff:
            train_rows[field].append((obs_dt, lead, float(err)))
            n_train += 1
        else:
            test_rows[field].append((obs_dt, lead, float(err)))
            n_test += 1
    print(f"  {n_in:,} rows scanned — {n_train:,} train / {n_test:,} test")

    # For each (field, τ), fit per-lead correction from train data, evaluate on test.
    results = {}  # (field, tau) -> mae
    n_used  = {}  # (field, tau) -> n test rows used
    fit_ref = cutoff  # weight reference: most recent train rows weighted ~1
    for field in FIELDS:
        tr = train_rows[field]
        te = test_rows[field]
        if len(tr) < 100 or len(te) < 20:
            continue
        for tau in TAUS:
            sums = defaultdict(float)
            wts  = defaultdict(float)
            for (obs_dt, lead, err) in tr:
                age_d = max(0.0, (fit_ref - obs_dt).total_seconds() / 86400.0)
                w = math.exp(-age_d / tau)
                sums[lead] += err * w
                wts[lead] += w
            correction = [
                (sums[lead] / wts[lead]) if wts[lead] > 0 else 0.0
                for lead in range(LEAD_BINS)
            ]
            abs_err_sum = 0.0
            n = 0
            for (obs_dt, lead, err) in te:
                # Apply correction: corrected_error = err − correction[lead]
                # (because forecast - correction - obs = err - correction)
                c_err = err - correction[lead]
                abs_err_sum += abs(c_err)
                n += 1
            if n:
                results[(field, tau)] = abs_err_sum / n
                n_used[(field, tau)] = n

    # Also compute UNCORRECTED MAE on test for baseline comparison.
    baseline_mae = {}
    for field in FIELDS:
        te = test_rows[field]
        if not te: continue
        baseline_mae[field] = sum(abs(e) for (_, _, e) in te) / len(te)

    # Build summary
    lines = [
        f"Decay τ tuning — generated {datetime.now().isoformat(timespec='seconds')}",
        f"Train cutoff: {cutoff_iso} UTC  ({args.cutoff_days:.1f}d back from now)",
        f"Train rows: {n_train:,}   Test rows: {n_test:,}",
        f"τ candidates: {TAUS}",
        "",
        f"Per-field held-out MAE (lower = better τ):",
        "",
    ]
    header = f"  {'field':<14} {'baseline':>10} " + " ".join(f"τ={t:>2}".rjust(9) for t in TAUS) + f"  {'best τ':>7}  {'win vs τ=14':>12}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    optimums = []
    for field in FIELDS:
        if field not in baseline_mae:
            continue
        base = baseline_mae[field]
        row_maes = []
        for tau in TAUS:
            m = results.get((field, tau))
            row_maes.append(m)
        if not any(m is not None for m in row_maes):
            continue
        best_tau = TAUS[min(range(len(TAUS)), key=lambda i: row_maes[i] if row_maes[i] is not None else 1e9)]
        best_mae = results[(field, best_tau)]
        t14_mae = results.get((field, 14))
        win_pct = ((t14_mae - best_mae) / t14_mae * 100) if t14_mae else 0
        optimums.append((field, best_tau, win_pct))
        mae_cells = "  ".join(f"{m:>7.3f}" if m is not None else "    -  " for m in row_maes)
        lines.append(f"  {FIELD_LABELS[field]:<14} {base:>10.3f}   {mae_cells}  {best_tau:>7}  {win_pct:>+11.1f}%")
    lines.append("")
    # Distribution of best-τ across fields
    from collections import Counter
    best_counter = Counter(t for _, t, _ in optimums)
    lines.append(f"Best-τ distribution across {len(optimums)} fields: " +
                 ", ".join(f"τ={t}: {n}" for t, n in sorted(best_counter.items())))
    # Verdict
    all_14 = all(bt == 14 for _, bt, _ in optimums)
    big_wins = sum(1 for _, _, w in optimums if w >= 5.0)
    if all_14:
        verdict = "KEEP τ=14 GLOBAL — every field's best τ is 14d. No reason to change."
    elif big_wins == 0:
        verdict = ("KEEP τ=14 GLOBAL — best-τ varies but no field gains ≥5% vs τ=14. "
                   "Per-field τ would add complexity for noise-level gains.")
    else:
        verdict = (f"IMPLEMENT PER-FIELD τ — {big_wins} field(s) gain ≥5% MAE vs τ=14. "
                   f"Worth ~30 min in decay_fit.py to make τ a per-field constant.")
    lines.append("")
    lines.append(f"Verdict: {verdict}")
    summary_path = os.path.join(OUT_DIR, "decay_tau_tuning_summary.txt")
    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  ✓ {summary_path}")
    print()
    print("\n".join(lines[-12:]))


if __name__ == "__main__":
    main()

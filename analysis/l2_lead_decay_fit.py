#!/usr/bin/env python3
"""
L2 lead-decay fit: does the L2 station-bias correction benefit from a
per-field decay-with-lead, instead of being applied flat across all 48 leads?

Premise:
  Current L2 takes the current Kalman-tracked station bias and adds it to
  every forecast hour 0-47 equally. That's optimal at lead 0 (the bias is
  measured right now) but the bias's signal-to-noise must degrade as the
  forecast moves into different atmospheric state. The audit showed
  temperature L1→L2 makes things slightly worse — consistent with bias
  being correct at short leads but over-applied at long leads.

Model:
  bias_to_apply(lead) = exp(-lead / τ_field) × current_bias

  τ_field is a single per-field scalar. τ → ∞ recovers the current flat
  behavior; small τ collapses L2 back toward L1 at far leads.

Fit:
  For each field, grid-search τ that minimizes weighted SSE of
    residual(τ) = error_l1 + exp(-lead/τ) × applied_bias
  on training rows. Then report held-out MAE on test rows for:
    raw_L1                 : |error_l1|
    L2_flat (current)      : |error_l1 + applied_bias|   = |error_l2|
    L2_decay (fitted τ)    : |error_l1 + exp(-lead/τ) × applied_bias|

Output:
  analysis/output/l2_lead_decay_summary.txt
"""
import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

FIELDS = ["t", "dp", "h", "ws", "wg", "cc", "sr", "pr", "pa", "ch", "cm", "cl"]
FIELD_LABELS = {
    "t": "Temperature", "dp": "Dew point", "h": "Humidity",
    "ws": "Wind speed", "wg": "Wind gust", "cc": "Cloud cover",
    "sr": "Solar rad.", "pr": "Pressure", "pa": "Precip amt",
    "ch": "Cloud high", "cm": "Cloud mid",  "cl": "Cloud low",
}

# τ grid in HOURS. ∞ = flat (current behavior); 0.5 = bias only useful at lead 0.
TAU_GRID = [0.5, 1, 2, 3, 4, 6, 8, 12, 18, 24, 36, 60, 120, 240, 1e9]

LEAD_BINS = 48
RECENCY_TAU_DAYS = 14.0  # match the existing decay fitter's recency weighting


def _fetch_lines(url):
    with open(cached_path(url), "rb") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff-days", type=float, default=2.0,
                    help="Hold out the last N days as test (default 2.0)")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    now = datetime.utcnow()
    cutoff = now - timedelta(days=args.cutoff_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M")
    print(f"Fetching {ERROR_LOG_URL}…")
    print(f"  train <  {cutoff_iso}  <= test")

    # Pull rows with forecast_l1 + forecast_l2.
    train = defaultdict(list)  # field -> [(obs_dt, lead, err_l1, applied_bias)]
    test  = defaultdict(list)
    n_in = n_use = 0
    for row in _fetch_lines(ERROR_LOG_URL):
        n_in += 1
        field = row.get("field")
        if field not in FIELDS:
            continue
        lead = row.get("lead_h")
        obs_t = row.get("obs_time", "")
        f_l1 = row.get("forecast_l1")
        f_l2 = row.get("forecast_l2")
        observed = row.get("observed")
        if lead is None or f_l1 is None or f_l2 is None or observed is None or not obs_t:
            continue
        if not (0 <= lead < LEAD_BINS):
            continue
        try:
            obs_dt = datetime.strptime(obs_t, "%Y-%m-%dT%H:%M")
        except ValueError:
            continue
        err_l1 = float(f_l1) - float(observed)
        applied_bias = float(f_l2) - float(f_l1)
        rec = (obs_dt, int(lead), err_l1, applied_bias)
        if obs_dt < cutoff:
            train[field].append(rec)
        else:
            test[field].append(rec)
        n_use += 1
    n_train = sum(len(v) for v in train.values())
    n_test  = sum(len(v) for v in test.values())
    print(f"  {n_in:,} rows scanned, {n_use:,} usable ({n_train:,} train / {n_test:,} test)")

    def w_of(obs_dt):
        age_d = max(0.0, (cutoff - obs_dt).total_seconds() / 86400.0)
        return math.exp(-age_d / RECENCY_TAU_DAYS)

    # Per-field τ fit
    results = {}  # field -> dict
    for field in FIELDS:
        tr = train[field]
        te = test[field]
        if len(tr) < 500 or len(te) < 100:
            continue

        # Grid search τ minimizing weighted SSE on train.
        best_tau, best_sse = None, float("inf")
        for tau in TAU_GRID:
            sse = 0.0
            wsum = 0.0
            for (obs_dt, lead, err_l1, bias) in tr:
                w = w_of(obs_dt)
                decay = math.exp(-lead / tau) if tau < 1e8 else 1.0
                r = err_l1 + decay * bias
                sse += w * r * r
                wsum += w
            if wsum > 0 and sse / wsum < best_sse:
                best_sse = sse / wsum
                best_tau = tau

        # Held-out MAE for three variants
        mae_l1 = 0.0
        mae_l2flat = 0.0
        mae_l2decay = 0.0
        n = 0
        for (obs_dt, lead, err_l1, bias) in te:
            decay = math.exp(-lead / best_tau) if best_tau < 1e8 else 1.0
            mae_l1     += abs(err_l1)
            mae_l2flat += abs(err_l1 + bias)
            mae_l2decay += abs(err_l1 + decay * bias)
            n += 1
        if not n:
            continue
        mae_l1 /= n; mae_l2flat /= n; mae_l2decay /= n

        # Also broken out by lead band
        bands = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
        band_rows = []
        for label, lo, hi in bands:
            n_b = 0; m1 = m2 = m3 = 0.0
            for (obs_dt, lead, err_l1, bias) in te:
                if not (lo <= lead < hi):
                    continue
                d = math.exp(-lead / best_tau) if best_tau < 1e8 else 1.0
                m1 += abs(err_l1); m2 += abs(err_l1 + bias); m3 += abs(err_l1 + d * bias)
                n_b += 1
            if n_b:
                band_rows.append((label, n_b, m1/n_b, m2/n_b, m3/n_b))

        results[field] = {
            "tau": best_tau,
            "n_train": len(tr),
            "n_test": n,
            "mae_l1": mae_l1,
            "mae_l2flat": mae_l2flat,
            "mae_l2decay": mae_l2decay,
            "bands": band_rows,
        }

    # Build summary
    lines = [
        f"L2 lead-decay fit — generated {datetime.now().isoformat(timespec='seconds')}",
        f"Train cutoff: {cutoff_iso} UTC  (test = last {args.cutoff_days:.1f}d)",
        f"Recency τ for fit weighting: {RECENCY_TAU_DAYS:.0f} days",
        f"τ grid (hours): {[t for t in TAU_GRID if t < 1e8]} + ∞ (flat)",
        "",
        "Model: bias_applied(lead) = exp(-lead/τ) × current_bias",
        "  τ = ∞  →  current behavior (bias applied flat across all 48 leads)",
        "  τ small →  bias only kept at short leads",
        "",
        "Per-field held-out MAE (lower = better):",
        "",
    ]
    hdr = f"  {'field':<14} {'n_test':>8} {'best τh':>9}  {'L1':>8}  {'L2-flat':>8}  {'L2-decay':>9}  {'flat vs L1':>11}  {'decay vs flat':>14}"
    lines.append(hdr)
    lines.append("  " + "-" * (len(hdr) - 2))
    big_wins = []
    for field in FIELDS:
        if field not in results:
            continue
        r = results[field]
        tau_disp = "∞" if r["tau"] >= 1e8 else f"{r['tau']:g}"
        flat_vs_l1 = (r["mae_l1"] - r["mae_l2flat"]) / r["mae_l1"] * 100 if r["mae_l1"] else 0.0
        decay_vs_flat = (r["mae_l2flat"] - r["mae_l2decay"]) / r["mae_l2flat"] * 100 if r["mae_l2flat"] else 0.0
        lines.append(
            f"  {FIELD_LABELS[field]:<14} {r['n_test']:>8,} {tau_disp:>9}  "
            f"{r['mae_l1']:>8.3f}  {r['mae_l2flat']:>8.3f}  {r['mae_l2decay']:>9.3f}  "
            f"{flat_vs_l1:>+10.1f}%  {decay_vs_flat:>+13.1f}%"
        )
        if decay_vs_flat >= 2.0:
            big_wins.append((field, decay_vs_flat, r["tau"]))

    lines.append("")
    lines.append("Per-field MAE by lead band:")
    for field in FIELDS:
        if field not in results:
            continue
        r = results[field]
        lines.append("")
        tau_disp = "∞" if r["tau"] >= 1e8 else f"{r['tau']:g}h"
        lines.append(f"  {FIELD_LABELS[field]} (τ={tau_disp}):")
        lines.append(f"    {'band':<8} {'n':>7}  {'L1':>8}  {'L2-flat':>8}  {'L2-decay':>9}")
        for label, n_b, m1, m2, m3 in r["bands"]:
            lines.append(f"    {label:<8} {n_b:>7,}  {m1:>8.3f}  {m2:>8.3f}  {m3:>9.3f}")

    lines.append("")
    # Per-cell verdict: aggregate win is only shippable if the decay helps in
    # EVERY lead band (or is flat) — not if it wins overall by helping 24-47h
    # a lot while hurting 0-11h. Aggregate wins that hide per-band damage are
    # exactly the failure mode we're trying to stop shipping.
    ship_wins = []      # win in aggregate AND net-non-negative per band
    mixed_wins = []     # aggregate win but at least one band gets worse
    BAND_LOSS_PCT = 2.0   # a band that gets ≥2% worse under decay is damage
    for field, agg_win, tau in big_wins:
        r = results[field]
        # Check each band's decay vs flat.
        bad_bands = []
        for label, n_b, m1, m2, m3 in r["bands"]:
            if m2 > 0:
                band_delta = (m2 - m3) / m2 * 100  # positive = decay helps
                if band_delta <= -BAND_LOSS_PCT:
                    bad_bands.append((label, band_delta))
        if bad_bands:
            mixed_wins.append((field, agg_win, tau, bad_bands))
        else:
            ship_wins.append((field, agg_win, tau))

    if not big_wins:
        verdict = ("KEEP L2 FLAT — no field gains ≥2% MAE from the lead-decay vs current "
                   "flat application. The L2 over-correction hypothesis isn't supported.")
    elif ship_wins:
        win_str = ", ".join(f"{f} (+{w:.1f}%, τ={'∞' if t>=1e8 else f'{t:g}h'})" for f, w, t in ship_wins)
        verdict = (f"IMPLEMENT L2 LEAD-DECAY — {len(ship_wins)} field(s) gain ≥2% MAE vs flat and don't "
                   f"lose in any lead band: {win_str}. Productionize as l2_decay.json with per-field τ.")
        if mixed_wins:
            mixed_str = "; ".join(
                f"{f} (+{w:.1f}% overall, but {', '.join(f'{lbl} {d:+.1f}%' for lbl,d in bb)})"
                for f, w, t, bb in mixed_wins)
            verdict += f"  MIXED (do NOT ship these — aggregate wins but per-band damage): {mixed_str}."
    else:
        # All big_wins were mixed. Downgrade to HOLD.
        mixed_str = "; ".join(
            f"{f} (+{w:.1f}% overall, but {', '.join(f'{lbl} {d:+.1f}%' for lbl,d in bb)})"
            for f, w, t, bb in mixed_wins)
        verdict = (f"HOLD — {len(mixed_wins)} field(s) gain ≥2% overall but LOSE materially in at least "
                   f"one lead band. Aggregate ship signal but per-band damage: {mixed_str}. "
                   f"Per-lead-band whitelist candidate, not a wholesale L2-decay ship.")
    lines.append(f"Verdict: {verdict}")

    summary_path = os.path.join(OUT_DIR, "l2_lead_decay_summary.txt")
    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  ✓ {summary_path}")
    print()
    # Echo the headline table
    for line in lines:
        if line.startswith("  ") or line.startswith("Verdict"):
            print(line)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Reliability check for the POP decay-correction scaling.

Question: when corrected POP says X%, does it actually rain X% of the time?
A well-calibrated forecast has observed rain frequency ≈ mid-bin POP.
This script measures it by replaying the pair log through three different
correction strategies and binning the resulting "corrected POP" values
against the observed rain outcomes, then plotting a reliability diagram.

Three strategies compared on the same pairs:
  1. RAW MODEL — no correction. Baseline.
  2. FLAT ADDITIVE — what v0.6.4 and earlier did: corrected = raw − C.
     Inflates clear-sky hours: raw 0% becomes 12%+ corrected.
  3. PIECEWISE SCALING — what v0.6.5+ does:
       applied = POP_NOISE_FLOOR + (C − POP_NOISE_FLOOR) × R/100
       corrected = clamp(R − applied, 0, 100)
     Preserves "model says 0% means 0%" while letting the full correction
     apply when raw is high.

Output:
  analysis/output/pop_calibration.png       — reliability diagram (3 curves)
  analysis/output/pop_calibration_summary.txt — bin counts, Brier scores

Run:
    python3 analysis/pop_calibration.py
    python3 analysis/pop_calibration.py --tau 3.5   # try a different noise floor

Note: results depend on whatever weather is in the current pair-log window.
After only a few days of data, the calibration curve is preliminary. Re-run
in 2–3 weeks with more diverse weather pairs for a confident read.
"""
import argparse
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime

SKIP_CHARTS = os.environ.get("ANALYSIS_NO_CHARTS") == "1"
if not SKIP_CHARTS:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
import numpy as np


ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
CORRECTIONS_URL = "https://data.wymancove.com/decay_corrections.json"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# Finer at the low end where we care most about the no-rain edge case.
BIN_EDGES = [0, 2, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100.0001]


def _fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "myweather-pop-calibration/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def _fetch_jsonl_lines(url):
    """Stream JSONL from a URL line by line — pair log is tens of MB."""
    req = urllib.request.Request(url, headers={"User-Agent": "myweather-pop-calibration/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw in resp:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def apply_flat(raw, correction):
    """v0.6.4 and earlier: clamp(raw − C, 0, 100)."""
    if correction is None:
        return raw
    return max(0.0, min(100.0, raw - correction))


def apply_scaled(raw, correction, T):
    """v0.6.5+: applied = T + (C − T) × R/100, then clamp(raw − applied, 0, 100)."""
    if correction is None:
        return raw
    r_frac = max(0.0, min(1.0, raw / 100.0))
    applied = T + (correction - T) * r_frac
    return max(0.0, min(100.0, raw - applied))


def bin_index(value):
    """Return the bin this value falls into (0..len(BIN_EDGES)-2)."""
    for i in range(len(BIN_EDGES) - 1):
        if BIN_EDGES[i] <= value < BIN_EDGES[i + 1]:
            return i
    return len(BIN_EDGES) - 2  # value == 100


def reliability_curve(forecasts, observed):
    """Return (bin_midpoints, observed_freq_per_bin, count_per_bin)."""
    sums = defaultdict(float)   # sum of "observed=100" outcomes in each bin
    counts = defaultdict(int)
    forecast_sum = defaultdict(float)  # sum of forecast values per bin (for actual midpoint)
    for f, o in zip(forecasts, observed):
        b = bin_index(f)
        sums[b] += (1.0 if o > 50 else 0.0)
        counts[b] += 1
        forecast_sum[b] += f
    n_bins = len(BIN_EDGES) - 1
    midpoints = [(BIN_EDGES[i] + BIN_EDGES[i + 1]) / 2 for i in range(n_bins)]
    actual_midpoints = [forecast_sum[i] / counts[i] if counts[i] else midpoints[i]
                        for i in range(n_bins)]
    observed_freq = [(sums[i] / counts[i] * 100) if counts[i] else None
                     for i in range(n_bins)]
    bin_counts = [counts[i] for i in range(n_bins)]
    return actual_midpoints, observed_freq, bin_counts


def brier_score(forecasts, observed):
    """Mean squared error between forecast probability and observed binary outcome.
    forecast in [0,100], observed in {0,100}. Returns scalar in [0, 10000] (lower is better)."""
    if not forecasts:
        return float("nan")
    return float(np.mean([(f - o) ** 2 for f, o in zip(forecasts, observed)]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tau", type=float, default=2.0,
                    help="POP_NOISE_FLOOR for the scaled strategy (default 2.0)")
    args = ap.parse_args()
    T = args.tau

    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"Fetching {CORRECTIONS_URL}…")
    corr_doc = _fetch_json(CORRECTIONS_URL)
    pp_correction_by_lead = (corr_doc.get("corrections", {}) or {}).get("pp", [])
    print(f"  POP corrections per lead: {len(pp_correction_by_lead)}")
    fitted_at = corr_doc.get("fitted_at", "?")

    print(f"Fetching {ERROR_LOG_URL}…  (this can take a minute)")
    raw_R = []
    obs = []
    flat_corrected = []
    scaled_corrected = []
    n_in = 0
    n_pp = 0
    for row in _fetch_jsonl_lines(ERROR_LOG_URL):
        n_in += 1
        if row.get("field") != "pp":
            continue
        lead = row.get("lead_h")
        forecast = row.get("forecast")
        observed = row.get("observed")
        if not isinstance(lead, int) or forecast is None or observed is None:
            continue
        if not (0 <= lead < len(pp_correction_by_lead)):
            continue
        c = pp_correction_by_lead[lead]
        if c is None:
            continue
        n_pp += 1
        raw_R.append(float(forecast))
        obs.append(float(observed))
        flat_corrected.append(apply_flat(float(forecast), float(c)))
        scaled_corrected.append(apply_scaled(float(forecast), float(c), T))
    print(f"  {n_in:,} rows scanned, {n_pp:,} pp pairs used")
    if not n_pp:
        print("No usable pairs.", file=sys.stderr)
        sys.exit(1)

    # ── Plot ───────────────────────────────────────────────────────────────
    if not SKIP_CHARTS:
        fig, ax = plt.subplots(figsize=(9, 7))
        ax.plot([0, 100], [0, 100], color="#555", linestyle="--", linewidth=1, label="perfect calibration")
        for label, vals, color in [
            ("RAW MODEL (no correction)",                raw_R,           "#8a93a3"),
            ("FLAT ADDITIVE (pre-v0.6.5)",               flat_corrected,  "#ef6450"),
            (f"PIECEWISE SCALED (v0.6.5+, T={T})",       scaled_corrected,"#4aa3ff"),
        ]:
            mids, freqs, counts = reliability_curve(vals, obs)
            xs = [m for m, f in zip(mids, freqs) if f is not None]
            ys = [f for f in freqs if f is not None]
            ax.plot(xs, ys, marker="o", linewidth=2, color=color, label=label)
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        ax.set_xlabel("Corrected POP forecast (%) — bin center")
        ax.set_ylabel("Observed rain frequency (%)")
        ax.set_title(f"POP reliability diagram  ·  n={n_pp:,} pp pairs  ·  corrections fitted {fitted_at}")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="lower right", fontsize=10)
        out_path = os.path.join(OUT_DIR, "pop_calibration.png")
        fig.tight_layout()
        fig.savefig(out_path, dpi=120)
        plt.close(fig)
        print(f"  ✓ {out_path}")

    # ── Summary text ───────────────────────────────────────────────────────
    summary = [
        f"POP calibration — generated {datetime.now().isoformat(timespec='seconds')}",
        f"Corrections file fitted at: {fitted_at}",
        f"Pairs used (field=pp): {n_pp:,}",
        f"POP_NOISE_FLOOR (T): {T}",
        "",
        f"Brier scores (lower is better — perfect = 0):",
        f"  RAW MODEL:        {brier_score(raw_R, obs):.1f}",
        f"  FLAT ADDITIVE:    {brier_score(flat_corrected, obs):.1f}",
        f"  PIECEWISE SCALED: {brier_score(scaled_corrected, obs):.1f}",
        "",
        f"Per-bin observed rain frequency:",
        f"  bin (corrected POP %)  | raw model       | flat additive   | piecewise scaled",
        f"  ---------------------- | --------------- | --------------- | ----------------",
    ]
    raw_mids, raw_freqs, raw_counts = reliability_curve(raw_R, obs)
    flat_mids, flat_freqs, flat_counts = reliability_curve(flat_corrected, obs)
    scl_mids, scl_freqs, scl_counts = reliability_curve(scaled_corrected, obs)
    for i in range(len(BIN_EDGES) - 1):
        lo, hi = BIN_EDGES[i], BIN_EDGES[i + 1]
        bin_label = f"  {lo:>4.0f}–{min(hi,100):>4.0f}            "
        def cell(freq, count):
            if freq is None:
                return f"  —    (n={count})"
            return f"  {freq:>5.1f}% (n={count})"
        summary.append(
            f"{bin_label} | {cell(raw_freqs[i], raw_counts[i])} | "
            f"{cell(flat_freqs[i], flat_counts[i])} | {cell(scl_freqs[i], scl_counts[i])}"
        )

    summary_path = os.path.join(OUT_DIR, "pop_calibration_summary.txt")
    with open(summary_path, "w") as f:
        f.write("\n".join(summary) + "\n")
    print(f"  ✓ {summary_path}")
    print()
    print("Done. Open the PNG to see the reliability diagram.")


if __name__ == "__main__":
    main()

"""R5 cove correction — held-out MAE audit (Step 2 of the R5 plan).

The R5 lookup table measures (waterfront_t_med - inland_t_med) per regime.
Step 1 (analysis/r5_cove_analysis.py) confirms the measurement is stable.
This Step 2 asks the actual ship question: does APPLYING the R5 delta
improve cove temperature forecast accuracy on held-out pairs?

Important caveat the script tests empirically:
  L2 (mesonet) already weights the two waterfront Tempests heavily for the
  cove location via 1/distance² × elevation. So L2-corrected temperature
  may ALREADY pull toward the waterfront signal that R5 measures. Adding
  R5 on top of L4 could double-count.

Three configs scored, all on the same held-out pairs:
  - baseline           = |error_l4|                         (production final)
  - r5_on_top_of_l4    = |error_l4 + R5_delta(obs_time)|    (R5 as a final layer)
  - r5_replaces_stack  = |error_l1 + R5_delta(obs_time)|    (R5 alone vs raw)

If baseline wins: don't ship R5.
If r5_on_top_of_l4 wins: ship R5 as the final layer.
If r5_replaces_stack wins: bigger architectural lift — L2's mesonet is
  hurting the cove and R5 is a better local model on its own.

Stratifies by (sb_active, hour band) so we can see WHERE R5 helps/hurts
even if the overall verdict is HOLD.

Sample size limited by cove_gradient_log retention window — capture started
2026-06-12, so first full read is ~2026-06-19 (7 days of paired data).
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

# Import the production R5 lookup directly so we audit the SAME math the
# Cloud Function would apply. Any future change to the lookup tables is
# reflected here automatically.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from weather_collector.processors.cove_correction import compute_cove_correction

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
COVE_LOG_URL  = "https://data.wymancove.com/cove_gradient_log.json"

# Pair log uses obs_time at hour boundaries (post-v0.6.77 dedup). Cove log
# ticks every 10 min. Match a pair to the cove-log entry whose ts shares the
# same YYYY-MM-DDTHH prefix (any 10-min tick within the obs hour is close
# enough — wind/sb don't change that fast in 10 min).
HOUR_KEY_LEN = 13  # len("2026-06-16T15")

# Lead bands match the walk-forward validator's bucketing.
BANDS = [
    ("0-5h",   0,  6),
    ("6-11h",  6,  12),
    ("12-23h", 12, 24),
    ("24-47h", 24, 48),
]
MIN_PAIRS_FOR_VERDICT = 200  # below this, audit is too noisy to ship on
SHIP_THRESHOLD_PCT = 1.0      # MAE must improve ≥1% over baseline to ship


def _load_cove_conditions():
    """Return dict: obs_hour_key → (wind_dir_deg, sb_active, hour_local).

    obs_hour_key = "YYYY-MM-DDTHH" (length 13). When multiple cove-log ticks
    fall in the same hour, we keep the LAST one — that's the condition closest
    to the boundary that aligns with the pair log's hour-resolution dedup.
    """
    sys.stderr.write(f"Loading cove conditions from {COVE_LOG_URL}...\n")
    doc = json.load(open(cached_path(COVE_LOG_URL)))
    entries = doc.get("entries") or []
    out = {}
    for e in entries:
        ts = e.get("ts") or ""
        if len(ts) < HOUR_KEY_LEN:
            continue
        key = ts[:HOUR_KEY_LEN]
        try:
            hour_local = int(ts[11:13])
        except (ValueError, IndexError):
            continue
        out[key] = (
            e.get("wind_dir"),
            bool(e.get("sb_active")),
            hour_local,
        )
    sys.stderr.write(f"  {len(out):,} unique obs hours with cove conditions\n")
    return out


def _band_for_lead(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return "other"


def main():
    cove_conds = _load_cove_conditions()
    if not cove_conds:
        sys.stderr.write("FATAL: no cove conditions loaded\n")
        sys.exit(1)

    # Per-bucket accumulators. Bucket key = (regime, band) where regime is
    # "sb_active" or "sb_inactive". Each bucket tallies sum-of-abs-error for
    # three configs plus pair count.
    abs_err = defaultdict(lambda: {"baseline": 0.0, "r5_l4": 0.0, "r5_l1": 0.0, "n": 0})

    # Diagnostic counters
    n_total = 0
    n_temp = 0
    n_matched = 0
    n_skipped_no_cove = 0
    n_skipped_no_layers = 0

    sys.stderr.write(f"Streaming pair log from {ERROR_LOG_URL}...\n")
    with open(cached_path(ERROR_LOG_URL), "rb") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            n_total += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("field") != "t":
                continue
            n_temp += 1
            obs_time = row.get("obs_time") or ""
            if len(obs_time) < HOUR_KEY_LEN:
                continue
            key = obs_time[:HOUR_KEY_LEN]
            cond = cove_conds.get(key)
            if cond is None:
                n_skipped_no_cove += 1
                continue
            wind_dir, sb_active, hour_local = cond
            e_l1 = row.get("error_l1")
            e_l4 = row.get("error_l4")
            lead_h = row.get("lead_h")
            if e_l1 is None or e_l4 is None or lead_h is None:
                n_skipped_no_layers += 1
                continue
            try:
                e_l1f = float(e_l1)
                e_l4f = float(e_l4)
            except (TypeError, ValueError):
                continue

            delta = compute_cove_correction(wind_dir, sb_active, hour_local)
            band = _band_for_lead(lead_h)
            regime = "sb_active" if sb_active else "sb_inactive"

            for bucket_key in [
                (regime, band),
                (regime, "all"),
                ("any", band),
                ("any", "all"),
            ]:
                bk = abs_err[bucket_key]
                bk["baseline"] += abs(e_l4f)
                bk["r5_l4"]    += abs(e_l4f + delta)
                bk["r5_l1"]    += abs(e_l1f + delta)
                bk["n"]        += 1
            n_matched += 1

    sys.stderr.write(
        f"\n  scanned {n_total:,} rows, {n_temp:,} temperature, "
        f"{n_matched:,} matched cove conditions "
        f"(skipped {n_skipped_no_cove:,} no-cove, {n_skipped_no_layers:,} no-layers)\n\n"
    )

    if n_matched < MIN_PAIRS_FOR_VERDICT:
        print(f"INSUFFICIENT DATA: only {n_matched:,} matched pairs "
              f"(need ≥{MIN_PAIRS_FOR_VERDICT:,} for a verdict)")
        return

    # Render table
    print(f"{'regime':<14}{'band':<10}{'n':>8}"
          f"{'MAE_base':>11}{'MAE_R5+L4':>12}{'MAE_R5alone':>13}"
          f"{'Δ R5+L4':>11}{'Δ R5alone':>12}")
    print("-" * 91)
    for regime in ["any", "sb_active", "sb_inactive"]:
        for band in ["all"] + [b[0] for b in BANDS]:
            bk = abs_err.get((regime, band))
            if not bk or bk["n"] == 0:
                continue
            n = bk["n"]
            mae_b = bk["baseline"] / n
            mae_r5_l4 = bk["r5_l4"] / n
            mae_r5_l1 = bk["r5_l1"] / n
            d_l4 = (100.0 * (mae_b - mae_r5_l4) / mae_b) if mae_b > 0 else 0.0
            d_l1 = (100.0 * (mae_b - mae_r5_l1) / mae_b) if mae_b > 0 else 0.0
            print(f"{regime:<14}{band:<10}{n:>8,}"
                  f"{mae_b:>11.3f}{mae_r5_l4:>12.3f}{mae_r5_l1:>13.3f}"
                  f"{d_l4:>+10.2f}%{d_l1:>+11.2f}%")
        print()

    # Verdict on overall "any/all" bucket
    overall = abs_err.get(("any", "all"))
    n = overall["n"]
    mae_b = overall["baseline"] / n
    mae_r5_l4 = overall["r5_l4"] / n
    mae_r5_l1 = overall["r5_l1"] / n
    d_l4 = 100.0 * (mae_b - mae_r5_l4) / mae_b if mae_b > 0 else 0.0
    d_l1 = 100.0 * (mae_b - mae_r5_l1) / mae_b if mae_b > 0 else 0.0

    print()
    print("=" * 91)
    print(f"VERDICT (n={n:,} held-out pairs, threshold ≥{SHIP_THRESHOLD_PCT}% MAE improvement):")
    print(f"  baseline MAE        = {mae_b:.3f}°F")
    print(f"  R5-on-top-of-L4 MAE = {mae_r5_l4:.3f}°F  (Δ {d_l4:+.2f}%)")
    print(f"  R5-replaces-stack   = {mae_r5_l1:.3f}°F  (Δ {d_l1:+.2f}%)")
    print()
    best = None
    best_delta = 0.0
    if d_l4 >= SHIP_THRESHOLD_PCT and d_l4 > best_delta:
        best = "r5_on_top_of_l4"; best_delta = d_l4
    if d_l1 >= SHIP_THRESHOLD_PCT and d_l1 > best_delta:
        best = "r5_replaces_stack"; best_delta = d_l1

    if best == "r5_on_top_of_l4":
        print(f"  → SHIP R5 as the final layer ({d_l4:+.2f}% MAE win)")
    elif best == "r5_replaces_stack":
        print(f"  → SHIP R5 replacing the L2-L4 stack for the cove ({d_l1:+.2f}% MAE win)")
    else:
        print(f"  → HOLD — neither variant beats baseline by ≥{SHIP_THRESHOLD_PCT}%")
        print(f"     Most likely: L2's station weighting already captures the waterfront signal.")
        print(f"     R5 stays as a confirmed-finding diagnostic; the candidate stamp can be retired.")


if __name__ == "__main__":
    main()

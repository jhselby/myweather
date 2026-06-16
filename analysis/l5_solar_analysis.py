#!/usr/bin/env python3
"""
L5 solar correction evaluation — 06-22 decision tool.

For each solar pair in the held-out window, computes:
  - Actual: |forecast_l1 - observed|        (baseline; no L5)
  - L5 forecast realistic:    forecast_l1 + correction(state_fc.regime_synoptic, forecast_l1)
  - L5 forecast ceiling:      forecast_l1 + correction(state_obs.regime_synoptic, forecast_l1)
  - |L5_realistic - observed|, |L5_ceiling - observed|

Reports per-regime n, MAE before / after / improvement %. Both views:
realistic (uses regime predicted by model at lead — what we'd actually
do in production) and ceiling (uses observed regime — theoretical
best case).

Verdict rule:
  - SHIP if the REALISTIC overall MAE drops by ≥ 5% AND at least 5 of
    the 8 regimes show ≥ 3% improvement (signal not driven by one
    regime carrying the day).
  - HOLD otherwise.

Run:
    python3 analysis/l5_solar_analysis.py
    python3 analysis/l5_solar_analysis.py --local-file /tmp/forecast_error_log.jsonl
    python3 analysis/l5_solar_analysis.py --days 7    # window in days
"""
import argparse
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weather_collector.processors.solar_correction import (
    compute_solar_correction, _BIAS_FALLBACK_BY_REGIME, SUN_UP_THRESHOLD,
)
_BIAS_BY_REGIME = _BIAS_FALLBACK_BY_REGIME  # name alias for downstream reporting

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "output", "l5_solar_summary.txt")

SHIP_OVERALL_MIN = 0.05    # 5% overall MAE drop
SHIP_PER_REGIME_MIN = 0.03 # 3% per-regime improvement to "count"
SHIP_MIN_REGIMES = 5       # ≥ this many of 8 regimes must show ≥ 3% improvement


def _stream(local_file, test_days):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=test_days)).strftime("%Y-%m-%dT%H:%M")
    if local_file:
        sys.stderr.write(f"  Reading from {local_file} (cutoff {cutoff})\n")
        with open(local_file) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (r.get("obs_time") or "") < cutoff:
                    continue
                yield r
        return
    sys.stderr.write(f"  Streaming pair log from local cache (cutoff {cutoff})...\n")
    with open(cached_path(ERROR_LOG_URL), "rb") as resp:
        for raw in resp:
            if not raw or not raw.strip():
                continue
            try:
                r = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if (r.get("obs_time") or "") < cutoff:
                continue
            yield r


def run_analysis(local_file=None, test_days=7):
    # Per-regime accumulators: {regime: {realistic: {n, sum_abs_base, sum_abs_l5},
    #                                    ceiling:   {n, sum_abs_base, sum_abs_l5}}}
    realistic = defaultdict(lambda: {"n": 0, "sum_abs_base": 0.0, "sum_abs_l5": 0.0})
    ceiling = defaultdict(lambda: {"n": 0, "sum_abs_base": 0.0, "sum_abs_l5": 0.0})
    n_total = 0
    n_solar = 0
    n_usable = 0

    for r in _stream(local_file, test_days):
        n_total += 1
        if r.get("field") != "sr":
            continue
        n_solar += 1
        lead_h = r.get("lead_h")
        if lead_h is None or lead_h < 1 or lead_h >= 48:
            continue
        l1 = r.get("forecast_l1")
        obs = r.get("observed")
        if l1 is None or obs is None:
            continue
        if l1 < SUN_UP_THRESHOLD:
            # Solar is essentially zero — correction is suppressed anyway
            continue
        state_fc = r.get("state_fc") or {}
        state_obs = r.get("state_obs") or {}
        regime_fc = state_fc.get("regime_synoptic")
        regime_obs = state_obs.get("regime_synoptic")
        if regime_fc is None and regime_obs is None:
            continue
        n_usable += 1

        base_err = abs(l1 - obs)
        # Extract hour from valid_time (forecast valid hour, local EDT)
        vt = r.get("valid_time") or ""
        hour_local = None
        if len(vt) >= 13:
            try:
                hour_local = int(vt[11:13])
            except ValueError:
                hour_local = None

        if regime_fc is not None:
            delta = compute_solar_correction(regime_fc, l1, hour_local=hour_local)
            l5_err = abs((l1 + delta) - obs)
            s = realistic[regime_fc]
            s["n"] += 1
            s["sum_abs_base"] += base_err
            s["sum_abs_l5"] += l5_err
        if regime_obs is not None:
            delta = compute_solar_correction(regime_obs, l1, hour_local=hour_local)
            l5_err = abs((l1 + delta) - obs)
            s = ceiling[regime_obs]
            s["n"] += 1
            s["sum_abs_base"] += base_err
            s["sum_abs_l5"] += l5_err

    def _aggregate(per_regime):
        results = {}
        total_n = 0
        total_base = 0.0
        total_l5 = 0.0
        for regime in _BIAS_BY_REGIME:
            if regime == "unknown":
                continue
            s = per_regime.get(regime)
            if not s or s["n"] == 0:
                results[regime] = {"n": 0, "mae_base": None, "mae_l5": None, "delta_pct": None}
                continue
            mae_base = s["sum_abs_base"] / s["n"]
            mae_l5 = s["sum_abs_l5"] / s["n"]
            delta_pct = (mae_l5 - mae_base) / mae_base if mae_base > 0 else None
            results[regime] = {
                "n": s["n"], "mae_base": mae_base, "mae_l5": mae_l5,
                "delta_pct": delta_pct,
            }
            total_n += s["n"]
            total_base += s["sum_abs_base"]
            total_l5 += s["sum_abs_l5"]
        overall = {
            "n": total_n,
            "mae_base": total_base / total_n if total_n else None,
            "mae_l5":   total_l5 / total_n if total_n else None,
        }
        if overall["mae_base"]:
            overall["delta_pct"] = (overall["mae_l5"] - overall["mae_base"]) / overall["mae_base"]
        else:
            overall["delta_pct"] = None
        return results, overall

    realistic_results, realistic_overall = _aggregate(realistic)
    ceiling_results, ceiling_overall = _aggregate(ceiling)

    # Realistic verdict
    overall_drop = (-realistic_overall["delta_pct"]) if realistic_overall["delta_pct"] is not None else 0
    n_regimes_improving = sum(
        1 for r, s in realistic_results.items()
        if s.get("delta_pct") is not None and s["delta_pct"] <= -SHIP_PER_REGIME_MIN
    )
    ship = (overall_drop >= SHIP_OVERALL_MIN) and (n_regimes_improving >= SHIP_MIN_REGIMES)

    return {
        "n_total_pairs": n_total,
        "n_solar_pairs": n_solar,
        "n_usable_pairs": n_usable,
        "realistic": realistic_results,
        "realistic_overall": realistic_overall,
        "ceiling": ceiling_results,
        "ceiling_overall": ceiling_overall,
        "overall_drop": overall_drop,
        "n_regimes_improving": n_regimes_improving,
        "ship": ship,
    }


def write_summary(result, path, test_days):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = []
    lines.append("L5 solar regime correction — evaluation")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append(f"Window: last {test_days:.1f} days")
    lines.append(f"Pairs scanned: {result['n_total_pairs']:,} total, {result['n_solar_pairs']:,} solar, {result['n_usable_pairs']:,} usable (≥{SUN_UP_THRESHOLD:.0f} W/m² with regime tag)")
    lines.append(f"Ship rule: realistic overall MAE drops ≥ {SHIP_OVERALL_MIN*100:.0f}% AND ≥ {SHIP_MIN_REGIMES} regimes improve by ≥ {SHIP_PER_REGIME_MIN*100:.0f}%")
    lines.append("")

    for title, results, overall in [
        ("Realistic (regime from model forecast — what we'd actually do)", result["realistic"], result["realistic_overall"]),
        ("Ceiling   (regime from observation — theoretical best case)",     result["ceiling"],   result["ceiling_overall"]),
    ]:
        lines.append(title)
        lines.append(f"  {'regime':<14} {'n':>7} {'MAE base':>10} {'MAE L5':>10} {'Δ%':>8}")
        for regime in _BIAS_BY_REGIME:
            if regime == "unknown":
                continue
            s = results.get(regime, {})
            if not s.get("n"):
                lines.append(f"  {regime:<14} {'0':>7} {'--':>10} {'--':>10} {'--':>8}")
                continue
            dpct = s["delta_pct"]
            dpct_str = f"{dpct*100:+.1f}%" if dpct is not None else "--"
            lines.append(f"  {regime:<14} {s['n']:>7} {s['mae_base']:>10.1f} {s['mae_l5']:>10.1f} {dpct_str:>8}")
        if overall["mae_base"]:
            dpct_str = f"{overall['delta_pct']*100:+.1f}%" if overall["delta_pct"] is not None else "--"
            lines.append(f"  {'OVERALL':<14} {overall['n']:>7} {overall['mae_base']:>10.1f} {overall['mae_l5']:>10.1f} {dpct_str:>8}")
        lines.append("")

    lines.append(f"Realistic overall MAE change: {result['realistic_overall']['delta_pct']*100:+.1f}%")
    lines.append(f"Regimes with realistic improvement ≥ {SHIP_PER_REGIME_MIN*100:.0f}%: {result['n_regimes_improving']} / 8 (need ≥ {SHIP_MIN_REGIMES})")
    lines.append("")
    if result["ship"]:
        lines.append("VERDICT: SHIP — flip solar_correction.ENABLED = True.")
        lines.append("  Realistic regime classification produces consistent improvement")
        lines.append("  across regimes, not driven by one regime carrying the day.")
    else:
        reasons = []
        if result["overall_drop"] < SHIP_OVERALL_MIN:
            reasons.append(f"overall drop only {result['overall_drop']*100:.1f}% (need ≥ {SHIP_OVERALL_MIN*100:.0f}%)")
        if result["n_regimes_improving"] < SHIP_MIN_REGIMES:
            reasons.append(f"only {result['n_regimes_improving']} regimes improving (need ≥ {SHIP_MIN_REGIMES})")
        lines.append("VERDICT: HOLD — " + "; ".join(reasons) + ".")
        lines.append("  Either accumulate more data and re-run, or refine the lookup")
        lines.append("  (e.g., add hour-of-day stratification within each regime).")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--local-file", default=None)
    p.add_argument("--days", type=float, default=7.0)
    args = p.parse_args()
    result = run_analysis(local_file=args.local_file, test_days=args.days)
    out_path = write_summary(result, OUT_PATH, args.days)
    sys.stderr.write(f"\nWrote {out_path}\n")
    with open(out_path) as f:
        sys.stdout.write(f.read())
    return 0 if result["ship"] else 1


if __name__ == "__main__":
    sys.exit(main())

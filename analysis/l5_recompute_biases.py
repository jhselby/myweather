#!/usr/bin/env python3
"""
Recompute L5 solar regime biases from DAYTIME-ONLY pair-log data.

The initial L5 lookup biases were copied from state_stratified_accuracy.json,
which averages signed error across ALL hours including night. Solar is zero
at night and ~600 W/m² at noon — averaging together means the "regime bias"
underweights the daytime signal that actually matters when the correction
fires (correction is gated to raw_solar >= 50 W/m²).

This script recomputes the biases using ONLY daytime pairs:
  - field == "sr"
  - lead 1-47
  - forecast_l1 >= SUN_UP_THRESHOLD (50 W/m²)
  - state_obs.regime_synoptic is present

Emits the updated `_BIAS_BY_REGIME` dict ready to drop into
`weather_collector/processors/solar_correction.py`.

Run:
    python3 analysis/l5_recompute_biases.py
    python3 analysis/l5_recompute_biases.py --local-file /tmp/forecast_error_log.jsonl
    python3 analysis/l5_recompute_biases.py --days 14    # window in days
"""
import argparse
import json
import os
import statistics
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from _cache import cached_path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "output", "l5_recompute_summary.txt")
SUN_UP_THRESHOLD = 50.0


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


def run(local_file=None, test_days=14):
    by_regime = defaultdict(list)  # regime → [signed_errors...]
    n_total = 0
    n_solar = 0
    n_kept = 0

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
            continue
        state_obs = r.get("state_obs") or {}
        regime = state_obs.get("regime_synoptic")
        if regime is None:
            continue
        n_kept += 1
        by_regime[regime].append(l1 - obs)  # signed (positive = forecast too high)

    sys.stderr.write(f"  Streamed {n_total:,} rows, {n_solar:,} solar, {n_kept:,} usable\n\n")

    # Per-regime stats
    rows = []
    for regime in ["frontal", "sw_flow", "pre_frontal", "sea_breeze",
                   "nw_flow", "calm", "se_flow", "ne_flow"]:
        errs = by_regime.get(regime, [])
        n = len(errs)
        if n < 50:
            rows.append({"regime": regime, "n": n, "mean": None,
                         "median": None, "std": None})
            continue
        mean = sum(errs) / n
        median = statistics.median(errs)
        std = statistics.stdev(errs)
        rows.append({"regime": regime, "n": n, "mean": mean,
                     "median": median, "std": std})

    return rows


def write_summary(rows, path, test_days):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = []
    lines.append("L5 solar bias recomputation — DAYTIME ONLY")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append(f"Window: last {test_days:.1f} days, raw_solar ≥ {SUN_UP_THRESHOLD:.0f} W/m²")
    lines.append("")
    lines.append(f"  {'regime':<14} {'n':>8} {'mean bias':>12} {'median':>10} {'std':>10}")
    for r in rows:
        if r["n"] < 50:
            lines.append(f"  {r['regime']:<14} {r['n']:>8} {'(too few)':>12} {'--':>10} {'--':>10}")
            continue
        lines.append(f"  {r['regime']:<14} {r['n']:>8} {r['mean']:>+12.1f} {r['median']:>+10.1f} {r['std']:>10.1f}")
    lines.append("")
    lines.append("Drop-in replacement for solar_correction._BIAS_BY_REGIME:")
    lines.append("")
    lines.append("_BIAS_BY_REGIME = {")
    for r in rows:
        if r["n"] < 50:
            lines.append(f'    \"{r["regime"]}\":      0.0,  # too few daytime samples (n={r["n"]})')
        else:
            lines.append(f'    \"{r["regime"]:<11}\": {r["mean"]:+8.1f},  # n={r["n"]:,}, median={r["median"]:+.1f}, σ={r["std"]:.1f}')
    lines.append('    "unknown":      0.0,')
    lines.append("}")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--local-file", default=None)
    p.add_argument("--days", type=float, default=14.0)
    args = p.parse_args()
    rows = run(local_file=args.local_file, test_days=args.days)
    out_path = write_summary(rows, OUT_PATH, args.days)
    sys.stderr.write(f"\nWrote {out_path}\n\n")
    with open(out_path) as f:
        sys.stdout.write(f.read())


if __name__ == "__main__":
    main()

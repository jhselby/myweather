#!/usr/bin/env python3
"""
L5 biases recomputed as (regime × hour) cells — hour-of-day refinement.

The day-15 first-pass evaluation showed L5 HOLDs because regime-only
indexing averages biases across daytime hours that may behave very
differently (e.g., ne_flow at noon vs ne_flow at 4pm could have opposite
biases). This script recomputes the lookup at (regime, hour_local) cells,
with a fallback: cells with n < MIN_CELL_N fall back to the regime-overall
mean (so we don't apply noisy corrections from undersampled regimes).

Emits a drop-in `_BIAS_BY_REGIME_HOUR` nested dict for
`solar_correction.py`.

Run:
    python3 analysis/l5_recompute_biases_hourly.py
    python3 analysis/l5_recompute_biases_hourly.py --local-file /tmp/forecast_error_log.jsonl
"""
import argparse
import json
import os
import statistics
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "output", "l5_recompute_hourly_summary.txt")
SUN_UP_THRESHOLD = 50.0
MIN_CELL_N = 30  # Below this, cell falls back to regime-overall bias

REGIMES = ["frontal", "sw_flow", "pre_frontal", "sea_breeze",
           "nw_flow", "calm", "se_flow", "ne_flow"]


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
    # Per (regime, hour) cell
    by_cell = defaultdict(list)
    # Per regime overall (for fallback)
    by_regime = defaultdict(list)
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
        # Extract local hour from obs_time (collector writes in America/New_York)
        ot = r.get("obs_time") or ""
        if len(ot) < 13:
            continue
        try:
            hour = int(ot[11:13])
        except ValueError:
            continue
        n_kept += 1
        err = l1 - obs  # signed bias
        by_cell[(regime, hour)].append(err)
        by_regime[regime].append(err)

    sys.stderr.write(f"  Streamed {n_total:,} rows, {n_solar:,} solar, {n_kept:,} usable daytime with regime\n\n")

    # Build the nested lookup
    lookup = {}
    fallbacks = {}
    for regime in REGIMES:
        regime_vals = by_regime.get(regime, [])
        if len(regime_vals) >= 50:
            fallbacks[regime] = sum(regime_vals) / len(regime_vals)
        else:
            fallbacks[regime] = 0.0
        lookup[regime] = {}
        for hour in range(0, 24):
            cell = by_cell.get((regime, hour), [])
            if len(cell) >= MIN_CELL_N:
                lookup[regime][hour] = sum(cell) / len(cell)
            # else: missing → caller falls back to regime mean

    return lookup, fallbacks, by_cell, by_regime


def write_summary(lookup, fallbacks, by_cell, by_regime, path, test_days):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = []
    lines.append("L5 solar biases — (regime × hour) cells")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append(f"Window: last {test_days:.1f} days, raw_solar ≥ {SUN_UP_THRESHOLD:.0f} W/m²")
    lines.append(f"Min cell n for hourly bias: {MIN_CELL_N} (else fall back to regime mean)")
    lines.append("")
    # Per-regime header + hourly grid
    for regime in REGIMES:
        regime_n = len(by_regime.get(regime, []))
        if regime_n < 50:
            lines.append(f"  {regime:<14} regime n={regime_n}  (insufficient for any bias)")
            continue
        regime_mean = fallbacks[regime]
        lines.append(f"  {regime:<14} regime n={regime_n}, overall bias = {regime_mean:+.1f}  W/m²")
        for hour in range(5, 21):  # daytime range
            cell = by_cell.get((regime, hour), [])
            n = len(cell)
            if n < MIN_CELL_N:
                lines.append(f"    {hour:02d}:00  n={n:<4}  (using regime fallback {regime_mean:+.1f})")
            else:
                m = sum(cell) / n
                std = statistics.stdev(cell) if n > 1 else 0
                lines.append(f"    {hour:02d}:00  n={n:<4}  bias={m:+7.1f}  σ={std:.1f}")
        lines.append("")

    # Emit code dict
    lines.append("Drop-in replacement for solar_correction:")
    lines.append("")
    lines.append("_BIAS_FALLBACK_BY_REGIME = {")
    for regime in REGIMES:
        lines.append(f'    "{regime}": {fallbacks[regime]:+.1f},')
    lines.append('    "unknown": 0.0,')
    lines.append("}")
    lines.append("")
    lines.append("_BIAS_BY_REGIME_HOUR = {")
    for regime in REGIMES:
        cells = lookup[regime]
        if not cells:
            lines.append(f'    "{regime}": {{}},')
            continue
        lines.append(f'    "{regime}": {{')
        for hour in sorted(cells):
            lines.append(f'        {hour:2d}: {cells[hour]:+.1f},')
        lines.append('    },')
    lines.append("}")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--local-file", default=None)
    p.add_argument("--days", type=float, default=14.0)
    args = p.parse_args()
    lookup, fallbacks, by_cell, by_regime = run(local_file=args.local_file, test_days=args.days)
    out_path = write_summary(lookup, fallbacks, by_cell, by_regime, OUT_PATH, args.days)
    sys.stderr.write(f"\nWrote {out_path}\n\n")
    with open(out_path) as f:
        sys.stdout.write(f.read())


if __name__ == "__main__":
    main()

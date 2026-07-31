#!/usr/bin/env python3
"""Reconstruct daily humid_bias (station consensus - HRRR model) trajectory
from the pair log. Same principle as h_lead_l2_ktaper_sim.py's back-solve:

    forecast_l2[lead=0] - forecast_l1[lead=0] = humid_bias × soft_ramp(0) = humid_bias × 1.0

Aggregate by day → per-day mean humid_bias. Look for magnitude spikes or
sign flips around 2026-07-25 when h L2 started hurting.

Also emit per-day trajectory for t and dp for context (t uses different τ,
dp is 100% derived from corrected_t + corrected_h).

Run:
    python3 -m analysis.h_humid_bias_trajectory
"""
import json
import os
import sys
import statistics
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = Path(__file__).resolve().parent / "output" / "h_humid_bias_trajectory.txt"

FIELDS = ("h", "t", "dp")


def main():
    # per_day[(field, day)] -> list of (l2 - l1) values at lead 0
    per_day = defaultdict(list)
    # also track per_day n
    n_by = defaultdict(int)
    n_rows = 0
    n_used = 0
    for line in open(cached_path(URL), "rb"):
        n_rows += 1
        try:
            r = json.loads(line)
        except Exception:
            continue
        f = r.get("field")
        if f not in FIELDS:
            continue
        if r.get("lead_h") != 0:
            continue
        l1 = r.get("forecast_l1")
        l2 = r.get("forecast_l2")
        if l1 is None or l2 is None:
            continue
        day = (r.get("obs_time") or "")[:10]
        if not day:
            continue
        per_day[(f, day)].append(float(l2) - float(l1))
        n_by[(f, day)] += 1
        n_used += 1

    out = []
    def p(*a):
        line = " ".join(str(x) for x in a)
        print(line); out.append(line)

    p(f"rows scanned {n_rows:,}   lead-0 rows used {n_used:,}")
    p()
    p("humid_bias reconstructed as (forecast_l2 - forecast_l1) at lead=0.")
    p("For h this equals the raw station-consensus bias (soft_ramp(0)=1.0).")
    p("Sign convention: positive = L2 pushed forecast UP vs raw (station said HRRR was too dry).")
    p("                 negative = L2 pushed forecast DOWN vs raw (station said HRRR was too wet).")
    p()

    days = sorted({d for (_, d) in per_day.keys()})
    if not days:
        p("NO DATA")
        return 1

    p("=" * 100)
    p("PER-DAY MEAN L2 BIAS APPLIED AT LEAD=0 (± std, n)")
    p("=" * 100)
    p(f"  {'day':<12}  "
      + "  ".join(f"{f:<28}" for f in FIELDS))
    for d in days:
        row = [f"  {d:<12} "]
        for f in FIELDS:
            vs = per_day.get((f, d), [])
            if not vs:
                row.append(f"{'—':<28}")
                continue
            m = sum(vs) / len(vs)
            s = statistics.stdev(vs) if len(vs) > 1 else 0.0
            row.append(f"{m:>+7.3f} ± {s:>5.3f}  (n={len(vs):>3})     ")
        p("".join(row))
    p()

    # Also print condensed "flip detector" — where did sign change day-to-day?
    p("=" * 100)
    p("SIGN + MAGNITUDE INFLECTION (day-over-day change in mean L2 bias)")
    p("=" * 100)
    for f in FIELDS:
        p(f"  === {f} ===")
        prior_mean = None
        for d in days:
            vs = per_day.get((f, d), [])
            if not vs:
                continue
            m = sum(vs) / len(vs)
            if prior_mean is None:
                p(f"    {d}  mean={m:+7.3f}")
            else:
                delta = m - prior_mean
                sign_flip = " ⚠ SIGN FLIP" if (prior_mean * m < 0) else ""
                big_change = " ⚠ LARGE Δ" if (abs(delta) > 1.0 and f != "t") or (abs(delta) > 0.5 and f == "t") else ""
                p(f"    {d}  mean={m:+7.3f}  Δ={delta:+7.3f}{sign_flip}{big_change}")
            prior_mean = m
        p()

    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(out) + "\n")
    print(f"\nwrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

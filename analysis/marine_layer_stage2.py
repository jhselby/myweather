"""Marine-layer / coastal-cloud Stage 2 verification.

Stage 1 finding (2026-06-21): NE-flow morning cloud-cover bias +25pp.

Stage 2 questions:
  1. Hold-out: split older/newer halves. Does the bias survive on the held-out
     newer half when bin definition is "fit" on the older half?
  2. Temporal stability: bias by calendar week. Stable or one anomalous patch?
  3. Lead-hour dependence: does bias vary by lead band (0-5/6-11/12-23/24-47)?
  4. Bin sensitivity: does ±15° wd / ±1h morning window preserve the signal?

Output is a single text block per question, schedulable for repeated reads.
"""

import json
import statistics
from collections import defaultdict
from datetime import datetime

from _cache import cached_path

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"


def in_bin(state_obs, obs_time, wd_lo=45, wd_hi=105, hr_lo=4, hr_hi=9):
    wd = state_obs.get("wind_dir")
    if wd is None:
        return False
    if not (wd_lo <= wd <= wd_hi):
        return False
    hr = datetime.fromisoformat(obs_time).hour
    return hr_lo <= hr <= hr_hi


def signed_bias(errs):
    if not errs:
        return None
    return (statistics.mean(errs), statistics.median(errs), len(errs))


def load_cc_rows():
    rows = []
    with open(cached_path(ERROR_LOG_URL)) as f:
        for line in f:
            r = json.loads(line)
            if r["field"] != "cc":
                continue
            st = r.get("state_obs")
            if not st:
                continue
            e = r.get("error_l4") if r.get("error_l4") is not None else r.get("error")
            if e is None:
                continue
            rows.append({
                "obs_time": r["obs_time"],
                "lead_h":   r.get("lead_h"),
                "wd":       st.get("wind_dir"),
                "error":    e,
            })
    rows.sort(key=lambda r: r["obs_time"])
    return rows


def q1_holdout(rows):
    """Split at temporal midpoint. Use older half to confirm bin, newer half
    to verify the bias still holds out-of-sample."""
    mid = len(rows) // 2
    older, newer = rows[:mid], rows[mid:]
    print("Q1. Hold-out by temporal split")
    print(f"  Older half: {older[0]['obs_time']}  →  {older[-1]['obs_time']}")
    print(f"  Newer half: {newer[0]['obs_time']}  →  {newer[-1]['obs_time']}")
    for name, sub in [("older (fit)", older), ("newer (held-out)", newer)]:
        in_e  = [r["error"] for r in sub if in_bin({"wind_dir": r["wd"]}, r["obs_time"])]
        out_e = [r["error"] for r in sub if not in_bin({"wind_dir": r["wd"]}, r["obs_time"])]
        ib = signed_bias(in_e); ob = signed_bias(out_e)
        print(f"  {name}")
        print(f"     in-bin:  n={ib[2]:>5,}  mean={ib[0]:+.2f}  median={ib[1]:+.2f}")
        print(f"     out-bin: n={ob[2]:>6,}  mean={ob[0]:+.2f}  median={ob[1]:+.2f}")


def q2_temporal_stability(rows):
    """Bin by ISO week. Report in-bin mean per week with n."""
    by_week = defaultdict(list)
    for r in rows:
        if not in_bin({"wind_dir": r["wd"]}, r["obs_time"]):
            continue
        wk = datetime.fromisoformat(r["obs_time"]).isocalendar()
        by_week[(wk.year, wk.week)].append(r["error"])
    print("\nQ2. Temporal stability — in-bin cc bias per ISO week")
    print(f"  {'year-wk':<10} {'n':>5} {'mean':>8} {'median':>8}")
    for k in sorted(by_week):
        xs = by_week[k]
        print(f"  {k[0]}-W{k[1]:02d}    {len(xs):>5}  {statistics.mean(xs):+7.2f}  {statistics.median(xs):+7.2f}")


def q3_lead_dependence(rows):
    """Lead-band split on in-bin only."""
    bands = [(0, 5), (6, 11), (12, 23), (24, 47)]
    print("\nQ3. Lead-hour dependence — in-bin cc bias")
    print(f"  {'band':<10} {'n':>5} {'mean':>8} {'median':>8}")
    in_rows = [r for r in rows if in_bin({"wind_dir": r["wd"]}, r["obs_time"])]
    for lo, hi in bands:
        xs = [r["error"] for r in in_rows if r["lead_h"] is not None and lo <= r["lead_h"] <= hi]
        if not xs:
            continue
        print(f"  {lo:>2}-{hi:<2}h    {len(xs):>5}  {statistics.mean(xs):+7.2f}  {statistics.median(xs):+7.2f}")


def q4_bin_sensitivity(rows):
    """Perturb wd ±15°, hour ±1h. Report bias for each variant."""
    variants = [
        ("baseline   (45-105, 4-9)",  45, 105, 4, 9),
        ("wd wider   (30-120, 4-9)",  30, 120, 4, 9),
        ("wd tighter (60-90, 4-9)",   60,  90, 4, 9),
        ("hr wider   (45-105, 3-10)", 45, 105, 3, 10),
        ("hr tighter (45-105, 5-8)",  45, 105, 5, 8),
    ]
    print("\nQ4. Bin sensitivity — in-bin cc bias under perturbations")
    print(f"  {'variant':<28} {'n':>5} {'mean':>8} {'median':>8}")
    for name, wlo, whi, hlo, hhi in variants:
        xs = [r["error"] for r in rows
              if in_bin({"wind_dir": r["wd"]}, r["obs_time"], wlo, whi, hlo, hhi)]
        if not xs:
            continue
        print(f"  {name:<28} {len(xs):>5}  {statistics.mean(xs):+7.2f}  {statistics.median(xs):+7.2f}")


def main():
    rows = load_cc_rows()
    print(f"Loaded {len(rows):,} cc rows with state_obs")
    print(f"Window: {rows[0]['obs_time']}  →  {rows[-1]['obs_time']}\n")
    q1_holdout(rows)
    q2_temporal_stability(rows)
    q3_lead_dependence(rows)
    q4_bin_sensitivity(rows)


if __name__ == "__main__":
    main()

"""Hour-of-day × field MAE — does overnight really run worse?

Motivating question (2026-08-18): Joe's "morning-red-evening-green" per-field
snapshot pattern. Two competing hypotheses:
  (A) prod is systematically worse at some hours (bias structure we could
      correct with an hour-conditional shift, or upstream-h/t fix).
  (B) prod tracks raw at every hour; morning-red is small-window variance
      and observer sampling bias.

Fields: h and t only. dp is excluded because dp = Magnus(t, h) — any dp
signal is a t/h signal in disguise (see project debug page line 3193 +
project_hypothesis_backlog).

Method: 30-day pair-log rollup. For each hour-of-day (LOCAL, EDT = UTC-4)
report n, mean|prod_error|, mean|error_l1| (near-raw proxy), and delta.
Verdict fires if there's ≥15% range in prod MAE across hours.

Run:
    python3 -m analysis.h_hour_of_day_mae
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path
from _prod import prod_error

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ("h", "t")
DAYS = 30
UTC_TO_LOCAL_OFFSET = -4  # EDT

now = datetime.utcnow()
cutoff = (now - timedelta(days=DAYS)).strftime("%Y-%m-%dT%H:%M")

# (field, local_hour) -> [n, sum_abs_prod, sum_abs_l1, sum_signed_prod, sum_signed_l1]
buckets = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0])

with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in FIELDS:
            continue
        ot = r.get("obs_time") or ""
        if len(ot) < 13 or ot < cutoff:
            continue
        try:
            utc_hour = int(ot[11:13])
        except ValueError:
            continue
        local_hour = (utc_hour + UTC_TO_LOCAL_OFFSET) % 24

        e_prod = prod_error(r)
        e_l1 = r.get("error_l1")
        if e_prod is None or e_l1 is None:
            continue
        ep, el = float(e_prod), float(e_l1)
        b = buckets[(f, local_hour)]
        b[0] += 1
        b[1] += abs(ep)
        b[2] += abs(el)
        b[3] += ep
        b[4] += el

print(f"h_hour_of_day_mae — {DAYS}d window, local hour (EDT)")
print(f"cutoff: {cutoff} UTC   fields: {list(FIELDS)}")
print()

for f in FIELDS:
    print(f"=== {f} ===")
    print(f"  {'hr':>3} {'n':>5}  {'|prod|':>7}  {'bias':>7}  {'|l1|':>7}  {'bias_l1':>8}  {'ratio':>6}")
    print("  " + "-" * 60)
    prod_maes = {}
    prod_biases = {}
    for h in range(24):
        n, s_prod, s_l1, sg_prod, sg_l1 = buckets.get((f, h), (0, 0.0, 0.0, 0.0, 0.0))
        if n < 50:
            print(f"  {h:>3} {n:>5}  {'thin':>7}")
            continue
        mp = s_prod / n
        ml = s_l1 / n
        bp = sg_prod / n
        bl = sg_l1 / n
        ratio = abs(bp) / mp if mp > 0 else 0.0  # bias/MAE: how much of the error is systematic
        prod_maes[h] = mp
        prod_biases[h] = bp
        marker = " ★" if (h < 6 or h >= 21) else ""
        print(f"  {h:>3} {n:>5}  {mp:>7.3f}  {bp:>+7.3f}  {ml:>7.3f}  {bl:>+8.3f}  {ratio:>5.2f}{marker}")
    if prod_maes:
        hi_h = max(prod_maes, key=prod_maes.get)
        lo_h = min(prod_maes, key=prod_maes.get)
        hi, lo = prod_maes[hi_h], prod_maes[lo_h]
        rng = (hi - lo) / lo * 100 if lo > 0 else 0.0
        night_hours = [h for h in prod_maes if h < 6 or h >= 21]
        day_hours = [h for h in prod_maes if 9 <= h <= 18]
        night_mae = sum(prod_maes[h] for h in night_hours) / len(night_hours) if night_hours else None
        day_mae = sum(prod_maes[h] for h in day_hours) / len(day_hours) if day_hours else None
        print()
        print(f"  worst hour: {hi_h:02d}:00 local  |prod|={hi:.3f}")
        print(f"  best hour:  {lo_h:02d}:00 local  |prod|={lo:.3f}")
        print(f"  range:      {rng:+.1f}%  (hi/lo)")
        if night_mae is not None and day_mae is not None:
            gap = (night_mae - day_mae) / day_mae * 100
            print(f"  night (21-05h) vs day (09-18h) prod MAE: {night_mae:.3f} vs {day_mae:.3f}  ({gap:+.1f}%)")
        if rng >= 15.0:
            print(f"  VERDICT: SIGNAL — hour-of-day range {rng:.1f}% ≥ 15%; hour-conditional structure exists.")
        else:
            print(f"  VERDICT: FLAT — hour-of-day range {rng:.1f}% < 15%; no systematic hour bias.")
        # Bias-vs-variance read: is the daytime peak SIGNED (bias, fixable with shift)
        # or unsigned (variance, only fixable by widening confidence)?
        hi_bias = prod_biases[hi_h]
        lo_bias = prod_biases[lo_h]
        hi_ratio = abs(hi_bias) / hi if hi > 0 else 0.0
        lo_ratio = abs(lo_bias) / lo if lo > 0 else 0.0
        print(f"  bias@worst_hr {hi_h:02d}: {hi_bias:+.3f}  (|bias|/MAE = {hi_ratio:.2f})")
        print(f"  bias@best_hr  {lo_h:02d}: {lo_bias:+.3f}  (|bias|/MAE = {lo_ratio:.2f})")
        if hi_ratio >= 0.30:
            print(f"  BIAS-DOMINANT at worst hour — hour-conditional L4/L5 shift table would help.")
        elif hi_ratio <= 0.15:
            print(f"  VARIANCE-DOMINANT at worst hour — no shift-based fix; only confidence-widening (C1 axis).")
        else:
            print(f"  MIXED bias/variance at worst hour — modest shift-fix upside; consider C1 axis first.")
    print()

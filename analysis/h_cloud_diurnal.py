"""Stage 0 — Cloud diurnal cycle.

cc/cl/cm/ch are NOT in L4_FIELDS. Test whether L1/L2 cloud forecasts show a
systematic hour-of-day bias the way temperature does — if yes, those fields
belong in L4.

Method: stratify signed error_l1 by hour-of-day (UTC, derived from obs_time).
For each cloud field, report mean bias + range across 24 hours. A spread of
≥5pp between best/worst hours is a strong signal that diurnal correction
would help.
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
CLOUD_FIELDS = {"cc", "cl", "cm", "ch"}

# (field, hour) -> [n, sum_err_signed, sum_abs_err]
sums = defaultdict(lambda: [0, 0.0, 0.0])
now = datetime.utcnow()
cutoff_iso = (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M")

with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in CLOUD_FIELDS:
            continue
        ot = r.get("obs_time") or ""
        if ot < cutoff_iso:
            continue
        if len(ot) < 13:
            continue
        try:
            hour = int(ot[11:13])
        except ValueError:
            continue
        e1 = r.get("error_l1")
        if e1 is None:
            continue
        s = sums[(f, hour)]
        s[0] += 1
        s[1] += e1
        s[2] += abs(e1)

print(f"{'field':<6} {'hour':>4} {'n':>7} {'mean_bias':>10} {'|err|':>8}")
print("-" * 45)
for f in sorted(CLOUD_FIELDS):
    biases = {}
    maes = {}
    for h in range(24):
        n, s_signed, s_abs = sums.get((f, h), (0, 0.0, 0.0))
        if n < 100:
            continue
        biases[h] = s_signed / n
        maes[h] = s_abs / n
        print(f"{f:<6} {h:>4} {n:>7,} {biases[h]:>+10.2f} {maes[h]:>8.2f}")
    if len(biases) >= 12:
        lo = min(biases.values()); hi = max(biases.values())
        spread = hi - lo
        verdict = "★ DIURNAL SIGNAL" if spread >= 5 else "flat"
        print(f"  → {f} bias spread across hours: {spread:.1f}pp  {verdict}")
    print()

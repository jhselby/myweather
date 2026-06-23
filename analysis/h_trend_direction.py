"""Stage 0 — Forecast trend direction (rising vs falling) × MAE.

When the model predicts a sharp change in cloud cover (rising or falling
significantly over the next 6 hours), is its forecast more or less accurate
than a stable forecast? Direction-of-change might carry different skill.

Method: for each (field, lead 0-h pair), compare forecast at lead 0 to
forecast at lead 6 (same run_time, same field). If |Δ| > threshold,
classify as rising / falling. Test forecast accuracy at the 6h lead per
class.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ["cc", "cl", "cm", "ch", "h", "t"]
TARGET_LEAD = 6

# (run_time, field, lead) -> forecast_l1
fc_by_key = {}
# also collect (run_time, field, lead=6) → observed
obs_target = {}
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try: r = json.loads(raw)
        except: continue
        f = r.get("field")
        if f not in FIELDS: continue
        lead = r.get("lead_h"); rt = r.get("run_time")
        if rt is None or lead is None: continue
        fc = r.get("forecast_l1")
        if fc is None: continue
        fc_by_key[(rt, f, int(lead))] = fc
        if int(lead) == TARGET_LEAD:
            obs = r.get("observed")
            if obs is not None:
                obs_target[(rt, f)] = (fc, obs)

# Now for each (run_time, field): we have fc[lead=0] and fc[lead=6] + obs[lead=6]
# Stratify the lead=6 MAE by sign of (fc[6] - fc[0])
sums = defaultdict(lambda: [0, 0.0])
THRESH = {"cc": 20, "cl": 15, "cm": 15, "ch": 15, "h": 10, "t": 3}
for (rt, f), (fc6, obs6) in obs_target.items():
    fc0 = fc_by_key.get((rt, f, 0))
    if fc0 is None: continue
    delta = fc6 - fc0
    thr = THRESH.get(f, 10)
    if delta > thr: cls = "rising"
    elif delta < -thr: cls = "falling"
    else: cls = "stable"
    err = abs(fc6 - obs6)
    s = sums[(f, cls)]
    s[0] += 1; s[1] += err

print(f"{'field':<5} {'class':<10} {'n':>7} {'|err|':>8} {'Δ vs stable':>13}")
print("-" * 50)
for f in FIELDS:
    base_n, base_e = sums.get((f, "stable"), (0, 0.0))
    if base_n < 100: continue
    base_mae = base_e/base_n
    for cls in ("rising", "falling", "stable"):
        n, e = sums.get((f, cls), (0, 0.0))
        if n < 50: continue
        m = e/n
        d = (m - base_mae)/base_mae*100 if base_mae else 0
        flag = "★" if abs(d) >= 30 else ("⚠" if abs(d) >= 15 else "")
        print(f"{f:<5} {cls:<10} {n:>7,} {m:>8.3f} {d:>+12.1f}% {flag}")
    print()

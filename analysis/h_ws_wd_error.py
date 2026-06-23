"""Stage 0 — wind speed × wind direction error.

At calm wind speeds, wind direction is essentially noise — there's no
sustained pressure gradient to give the wind a meaningful direction. At
strong wind, direction should be crisp. Does wd MAE scale with ws_obs?
If yes, low-wind cells flag for wider C1 confidence bands.

Method: stratify wd MAE by observed wind speed bin.
"""
import os, sys, json
import math
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

def circ_diff(a, b):
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d

# ws_bin -> [n, sum|wd_err|]
sums = defaultdict(lambda: [0, 0.0])
# Stream pair log; wd has its own field, ws has its own field — need to join
# at obs_time × lead × run_time
joined = defaultdict(dict)
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try: r = json.loads(raw)
        except: continue
        f = r.get("field")
        if f not in ("wd", "ws"): continue
        key = (r.get("obs_time"), r.get("lead_h"), r.get("run_time"))
        if None in key: continue
        joined[key][f] = (r.get("forecast_l1"), r.get("observed"))

for key, fs in joined.items():
    if "wd" not in fs or "ws" not in fs: continue
    wd_fc, wd_obs = fs["wd"]
    ws_fc, ws_obs = fs["ws"]
    if None in (wd_fc, wd_obs, ws_obs): continue
    if   ws_obs < 2:  b = "calm (<2)"
    elif ws_obs < 5:  b = "light (2-5)"
    elif ws_obs < 10: b = "moderate (5-10)"
    elif ws_obs < 15: b = "fresh (10-15)"
    else:             b = "strong (≥15)"
    err = circ_diff(wd_fc, wd_obs)
    s = sums[b]
    s[0] += 1; s[1] += err

ORDER = ["calm (<2)", "light (2-5)", "moderate (5-10)", "fresh (10-15)", "strong (≥15)"]
print(f"{'ws_bin':<18} {'n':>8} {'|wd_err|°':>10}")
print("-" * 40)
maes = {}
for b in ORDER:
    n, e = sums.get(b, (0, 0.0))
    if n < 100: continue
    maes[b] = e/n
    print(f"{b:<18} {n:>8,} {maes[b]:>10.1f}")
if "calm (<2)" in maes and "strong (≥15)" in maes:
    ratio = maes["calm (<2)"] / maes["strong (≥15)"]
    print(f"\n  → calm/strong ratio: {ratio:.2f}×")
    if ratio >= 2.0:
        print("  ★ WIND-SPEED-GATED wd ERROR — calm winds have effectively-meaningless direction.")
    elif ratio >= 1.3:
        print("  ⚠ Mild signal")
    else:
        print("  flat")

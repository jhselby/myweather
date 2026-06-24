"""Stage 0 — Naive persistence baseline.

For each (field, lead) pair, compare HRRR's forecast value vs "naive
persistence" (use the current observation as the forecast). If persistence
beats HRRR at very short leads, that's a real architectural finding: we
should fall back to persistence for lead 0-2h instead of trusting the model.

Pair log gives us forecast at lead-h relative to obs_time. For persistence
baseline: at run_time, the observation at that moment IS the lead-0 value
of persistence; the lead-h persistence forecast = that same value, unchanged.

Approximation: for each pair, we don't have the obs at run_time directly,
but we can look across all pairs that share obs_time = run_time + lead and
use the lead-0 pair's "observed" value as the persistence forecast for the
lead-h pair.

Simpler: just compare |forecast_l1 - observed| vs |0-lead_observed - observed|
where 0-lead_observed is from the matching (run_time, field, lead=0) pair.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ["t", "h", "ws", "wg", "cc"]
BANDS = [(0,2,"0-2h"), (2,5,"2-5h"), (5,12,"5-12h"), (12,24,"12-24h"), (24,48,"24-48h")]

def band_of(l):
    for lo, hi, lab in BANDS:
        if lo <= l < hi: return lab
    return None

# (run_time, field, lead=0) -> observed
persistence_baseline = {}
# (run_time, field, lead) -> (forecast_l1, observed)
pairs = []

with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try: r = json.loads(raw)
        except: continue
        f = r.get("field")
        if f not in FIELDS: continue
        rt = r.get("run_time"); lead = r.get("lead_h")
        if rt is None or lead is None: continue
        fc = r.get("forecast_l1"); obs = r.get("observed")
        if fc is None or obs is None: continue
        if int(lead) == 0:
            persistence_baseline[(rt, f)] = obs
        pairs.append((rt, f, int(lead), fc, obs))

# Compute model vs persistence MAE per band
# (field, band) -> [n, sum|err_model|, sum|err_persist|]
sums = defaultdict(lambda: [0, 0.0, 0.0])
for rt, f, lead, fc, obs in pairs:
    if lead == 0: continue
    persist_obs = persistence_baseline.get((rt, f))
    if persist_obs is None: continue
    band = band_of(lead)
    if not band: continue
    s = sums[(f, band)]
    s[0] += 1
    s[1] += abs(fc - obs)
    s[2] += abs(persist_obs - obs)

print(f"{'field':<5} {'band':<7} {'n':>8} {'|model|':>8} {'|persist|':>10} {'model-persist':>14}")
print("-" * 60)
for f in FIELDS:
    for lo, hi, lab in BANDS:
        n, em, ep = sums.get((f, lab), (0, 0.0, 0.0))
        if n < 200: continue
        mm = em/n; mp = ep/n
        delta = (mm - mp)/mp*100 if mp else 0
        flag = "★ PERSISTENCE WINS" if delta > 5 else ("⚠ tied" if abs(delta) < 5 else "")
        print(f"{f:<5} {lab:<7} {n:>8,} {mm:>8.3f} {mp:>10.3f} {delta:>+13.1f}% {flag}")
    print()

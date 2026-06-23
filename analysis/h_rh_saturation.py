"""Stage 0 — RH near saturation (fog onset regime).

When state_obs.humidity ≥ 95%, atmosphere is in fog/saturation regime.
Different microphysics, condensation begins, radiative transfer changes.
Does forecast accuracy on other fields drop in this regime?
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ["t", "dp", "ws", "wg", "cc", "cl", "cm", "ch", "pa"]

# (field, rh_bin) -> [n, sum|err|]
sums = defaultdict(lambda: [0, 0.0])
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try: r = json.loads(raw)
        except: continue
        f = r.get("field")
        if f not in FIELDS: continue
        rh = (r.get("state_obs") or {}).get("humidity")
        if rh is None: continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None: continue
        if   rh < 50: b = "dry (<50)"
        elif rh < 75: b = "moderate (50-75)"
        elif rh < 90: b = "humid (75-90)"
        elif rh < 95: b = "very humid (90-95)"
        else:         b = "saturating (≥95) ★"
        s = sums[(f, b)]
        s[0] += 1; s[1] += abs(err)

ORDER = ["dry (<50)", "moderate (50-75)", "humid (75-90)", "very humid (90-95)", "saturating (≥95) ★"]
print(f"{'field':<5} {'rh_bin':<22} {'n':>8} {'|err|':>8} {'Δ vs moderate':>15}")
print("-" * 60)
for f in FIELDS:
    base_n, base_e = sums.get((f, "moderate (50-75)"), (0, 0.0))
    if base_n < 200: continue
    base_mae = base_e / base_n
    for b in ORDER:
        n, e = sums.get((f, b), (0, 0.0))
        if n < 100: continue
        m = e/n
        d = (m - base_mae)/base_mae*100 if base_mae else 0
        flag = "★" if d >= 30 else ("⚠" if d >= 15 else "")
        print(f"{f:<5} {b:<22} {n:>8,} {m:>8.3f} {d:>+14.1f}% {flag}")
    print()

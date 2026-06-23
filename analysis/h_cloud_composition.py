"""Stage 0 — Cloud composition (layered vs single-layer).

When low+mid+high clouds are all present (layered sky), is forecast accuracy
worse than when only one layer is present? Layered skies are physically
harder to model — multiple radiative interactions, more stratification.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
TEST_FIELDS = ["t", "h", "ws", "wg", "cc", "ch"]  # excluding cloud subfields (would be circular)
PRES_THRESHOLD = 20  # % cloud cover to count as "present"

def composition(so):
    layers = sum(1 for k in ("cloud_low", "cloud_mid", "cloud_high")
                 if (so.get(k) or 0) >= PRES_THRESHOLD)
    if layers == 0: return "clear"
    if layers == 1: return "single layer"
    if layers == 2: return "two layers"
    return "three layers (full stack)"

sums = defaultdict(lambda: [0, 0.0])
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try: r = json.loads(raw)
        except: continue
        f = r.get("field")
        if f not in TEST_FIELDS: continue
        so = r.get("state_obs") or {}
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None: continue
        comp = composition(so)
        s = sums[(f, comp)]
        s[0] += 1; s[1] += abs(err)

ORDER = ["clear", "single layer", "two layers", "three layers (full stack)"]
print(f"{'field':<5} {'composition':<26} {'n':>8} {'|err|':>8} {'Δ vs clear':>11}")
print("-" * 65)
for f in TEST_FIELDS:
    base_n, base_e = sums.get((f, "clear"), (0, 0.0))
    if base_n < 200: continue
    base_mae = base_e/base_n
    for comp in ORDER:
        n, e = sums.get((f, comp), (0, 0.0))
        if n < 200: continue
        m = e/n
        d = (m - base_mae)/base_mae*100 if base_mae else 0
        flag = "★" if d >= 30 else ("⚠" if d >= 15 else "")
        print(f"{f:<5} {comp:<26} {n:>8,} {m:>8.3f} {d:>+10.1f}% {flag}")
    print()

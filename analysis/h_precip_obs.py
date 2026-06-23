"""Stage 0 — precip_obs > 0 as a confidence axis (mirror of C1f).

C1f (precip_fc>0) is forecast-keyed: "when model expects rain, widen bands."
This is the obs-keyed mirror: "when it's actually raining, how is forecast
skill affected on other fields?" If orthogonal to precip_fc, both ride
independent signals (model agrees rain coming AND model surprised by rain).
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ["t", "h", "ws", "wg", "cc", "cl", "cm", "ch"]

# (field, p_fc, p_obs) -> [n, sum|err|]
# Quadrants: (no/yes) × (no/yes)
sums = defaultdict(lambda: [0, 0.0])
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try: r = json.loads(raw)
        except: continue
        f = r.get("field")
        if f not in FIELDS: continue
        sf = r.get("state_fc") or {}
        so = r.get("state_obs") or {}
        pfc = sf.get("precip_in"); pob = so.get("precip_in")
        if pfc is None or pob is None: continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None: continue
        P_fc = pfc > 0.01
        P_ob = pob > 0.01
        s = sums[(f, P_fc, P_ob)]
        s[0] += 1; s[1] += abs(err)

LABELS = {
    (False, False): "neither (dry both)",
    (False, True):  "obs-only (model missed rain) ★",
    (True,  False): "fc-only (false alarm)",
    (True,  True):  "both (coherent rain)",
}
print(f"{'field':<5} {'cell':<32} {'n':>7} {'|err|':>8} {'Δ vs dry':>10}")
print("-" * 65)
for f in FIELDS:
    base_n, base_e = sums.get((f, False, False), (0, 0.0))
    if base_n < 200: continue
    base_mae = base_e/base_n
    for (P_fc, P_ob), label in LABELS.items():
        n, e = sums.get((f, P_fc, P_ob), (0, 0.0))
        if n < 50: continue
        m = e/n
        d = (m - base_mae)/base_mae*100 if base_mae else 0
        flag = "★" if d >= 50 else ("⚠" if d >= 20 else "")
        print(f"{f:<5} {label:<32} {n:>7,} {m:>8.3f} {d:>+9.1f}% {flag}")
    print()

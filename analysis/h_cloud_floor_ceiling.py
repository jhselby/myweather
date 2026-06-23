"""Stage 0 — Cloud cover floor/ceiling truncation.

When the model forecasts cc=0 or cc=100 (or near those bounds), the error
distribution is asymmetric — truncated by the physical [0, 100] interval.
A model that predicts cc=0 cannot under-predict (no negative observations);
a model that predicts cc=100 cannot over-predict. Stratify by forecast cc
bin to look for hidden bias near floor/ceiling.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
CLOUD_FIELDS = ["cc", "cl", "cm", "ch"]
BINS = [(0,5,"0-5"), (5,20,"5-20"), (20,50,"20-50"),
        (50,80,"50-80"), (80,95,"80-95"), (95,100.01,"95-100")]

def bin_of(v):
    for lo, hi, lab in BINS:
        if lo <= v < hi: return lab
    return None

# (field, fc_bin) -> [n, sum_err_signed, sum_abs_err]
sums = defaultdict(lambda: [0, 0.0, 0.0])
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try: r = json.loads(raw)
        except: continue
        f = r.get("field")
        if f not in CLOUD_FIELDS: continue
        fc = r.get("forecast_l4") or r.get("forecast_l3") or r.get("forecast_l2") or r.get("forecast_l1")
        obs = r.get("observed")
        if fc is None or obs is None: continue
        b = bin_of(fc)
        if not b: continue
        err = fc - obs  # signed
        s = sums[(f, b)]
        s[0] += 1; s[1] += err; s[2] += abs(err)

print(f"{'field':<5} {'fc_bin':<8} {'n':>7} {'mean_bias':>10} {'|err|':>8}")
print("-" * 50)
for f in CLOUD_FIELDS:
    rows = []
    for lo, hi, lab in BINS:
        n, sb, sa = sums.get((f, lab), (0, 0.0, 0.0))
        if n < 200: continue
        rows.append((lab, n, sb/n, sa/n))
    for lab, n, b, m in rows:
        flag = "★" if abs(b) >= 15 else ("⚠" if abs(b) >= 8 else "")
        print(f"{f:<5} {lab:<8} {n:>7,} {b:>+10.2f} {m:>8.2f} {flag}")
    if rows:
        # Floor (0-5) vs ceiling (95-100) asymmetry
        floor_b = next((b for lab,n,b,m in rows if lab=="0-5"), None)
        ceil_b  = next((b for lab,n,b,m in rows if lab=="95-100"), None)
        if floor_b is not None and ceil_b is not None:
            print(f"  → {f} floor bias {floor_b:+.1f}, ceiling bias {ceil_b:+.1f}")
    print()

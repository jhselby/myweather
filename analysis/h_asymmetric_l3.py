"""Stage 0 — Asymmetric over/under-call test.

Question: does L3 fix over-calls (forecast > observed) better than under-calls
(forecast < observed), or vice versa? Current L3 collapses both directions
into one signed mean per (field, lead). If the bias is asymmetric, splitting
by sign could expose untapped gains or expose harm hidden in the average.

Method: for each L3-applied field, partition test rows by sign of error_l1
(L1 over vs L1 under), measure |error_l1| vs |error_l3| in each partition,
compute the L3 win % for each partition independently.

Verdict rule: if one partition shows ≥10pp better L3 win than the other,
and both have ≥1000 rows, asymmetry is real → consider asymmetric L3.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
L3_FIELDS = {"ws", "wg", "ch", "cm", "pp"}

# field -> {"over": (n, sum|e1|, sum|e3|), "under": ...}
sums = defaultdict(lambda: {"over": [0, 0.0, 0.0], "under": [0, 0.0, 0.0]})

with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in L3_FIELDS:
            continue
        e1 = r.get("error_l1"); e3 = r.get("error_l3")
        if e1 is None or e3 is None:
            continue
        side = "over" if e1 > 0 else "under"
        s = sums[f][side]
        s[0] += 1
        s[1] += abs(e1)
        s[2] += abs(e3)

print(f"{'field':<8} {'side':<6} {'n':>9} {'|L1|':>8} {'|L3|':>8} {'Δ%':>7}")
print("-" * 50)
for f in sorted(sums):
    for side in ("over", "under"):
        n, e1, e3 = sums[f][side]
        if n < 200:
            continue
        m1 = e1/n; m3 = e3/n
        d = (m1 - m3) / m1 * 100 if m1 > 0 else 0
        print(f"{f:<8} {side:<6} {n:>9,} {m1:>8.3f} {m3:>8.3f} {d:>6.1f}%")
    # Asymmetry: |over_pct - under_pct|
    no, e1o, e3o = sums[f]["over"]; nu, e1u, e3u = sums[f]["under"]
    if no >= 1000 and nu >= 1000 and e1o > 0 and e1u > 0:
        po = (e1o/no - e3o/no)/(e1o/no)*100
        pu = (e1u/nu - e3u/nu)/(e1u/nu)*100
        print(f"  → asymmetry: over={po:.1f}%, under={pu:.1f}%, gap={abs(po-pu):.1f}pp"
              f"  {'★ REAL' if abs(po-pu) >= 10 else 'flat'}")
    print()

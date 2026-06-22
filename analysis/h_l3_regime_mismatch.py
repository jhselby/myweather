"""Stage 0 — L3 efficacy under regime mismatch.

When state_fc.regime_synoptic != state_obs.regime_synoptic, the model "thinks"
we're in a different weather regime than reality. R6 already shows MAE
penalty in this state. Different question here: does L3 still earn its keep
when the regime is mismatched, or should we gate L3 to regime-agreement
windows?

Method: split L3-applied pairs by (match) vs (mismatch). For each L3 field,
report L3 win % in each partition. A ≥10pp gap (e.g., L3 wins +50% on match,
+30% on mismatch) is interesting; if L3 loses outright on mismatch, it's a
clear gate candidate.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
L3_FIELDS = {"ws", "wg", "ch", "cm", "pp"}

# (field, status) -> [n, sum|e1|, sum|e3|]   status in {"match", "mismatch"}
sums = defaultdict(lambda: [0, 0.0, 0.0])

with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in L3_FIELDS:
            continue
        sf = r.get("state_fc") or {}
        so = r.get("state_obs") or {}
        rfc = sf.get("regime_synoptic")
        rob = so.get("regime_synoptic")
        if not rfc or not rob:
            continue
        e1 = r.get("error_l1"); e3 = r.get("error_l3")
        if e1 is None or e3 is None:
            continue
        status = "match" if rfc == rob else "mismatch"
        s = sums[(f, status)]
        s[0] += 1
        s[1] += abs(e1)
        s[2] += abs(e3)

print(f"{'field':<6} {'status':<10} {'n':>9} {'|L1|':>8} {'|L3|':>8} {'L3 win %':>10}")
print("-" * 60)
for f in sorted(L3_FIELDS):
    wins = {}
    for status in ("match", "mismatch"):
        n, e1, e3 = sums.get((f, status), (0, 0.0, 0.0))
        if n < 200:
            continue
        m1 = e1/n; m3 = e3/n
        d = (m1 - m3)/m1*100 if m1 > 0 else 0
        wins[status] = d
        print(f"{f:<6} {status:<10} {n:>9,} {m1:>8.3f} {m3:>8.3f} {d:>9.1f}%")
    if "match" in wins and "mismatch" in wins:
        gap = wins["match"] - wins["mismatch"]
        verdict = ("★ MISMATCH HURTS L3" if wins["mismatch"] < -3 else
                   "★ GATE CANDIDATE"     if abs(gap) >= 10 else
                   "flat")
        print(f"  → {f}: match wins +{wins['match']:.1f}%, mismatch +{wins['mismatch']:.1f}%, gap={gap:+.1f}pp  {verdict}")
    print()

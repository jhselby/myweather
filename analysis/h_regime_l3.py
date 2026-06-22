"""Stage 0 — Regime-conditional L3 efficacy.

Question: L3 is currently flat-applied to whitelist fields (ws, wg, ch, cm, pp)
across every regime. R0 says it wins overall on each. But could it be winning
big in some regimes and silently losing in others, with the wins canceling
the losses out in the global mean?

Method: per (field, regime_obs), measure |error_l1| vs |error_l3|. Compute
L3 improvement % per regime. Flag any regime where L3 loses by ≥3% with
n≥500 — that's a candidate for regime-gated L3 (apply only when regime
agrees, fall back to L2 otherwise).
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
L3_FIELDS = {"ws", "wg", "ch", "cm", "pp"}

# (field, regime) -> [n, sum|e1|, sum|e3|]
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
        so = r.get("state_obs") or {}
        regime = so.get("regime_synoptic")
        if not regime:
            continue
        e1 = r.get("error_l1"); e3 = r.get("error_l3")
        if e1 is None or e3 is None:
            continue
        s = sums[(f, regime)]
        s[0] += 1
        s[1] += abs(e1)
        s[2] += abs(e3)

print(f"{'field':<6} {'regime':<14} {'n':>8} {'|L1|':>8} {'|L3|':>8} {'Δ%':>7}  verdict")
print("-" * 70)
for f in sorted(L3_FIELDS):
    rows = []
    for (ff, regime), (n, e1, e3) in sums.items():
        if ff != f or n < 500:
            continue
        m1 = e1/n; m3 = e3/n
        d = (m1 - m3) / m1 * 100 if m1 > 0 else 0
        rows.append((regime, n, m1, m3, d))
    rows.sort(key=lambda r: -r[4])  # best gain first
    for regime, n, m1, m3, d in rows:
        verdict = "★ L3 LOSES" if d <= -3 else ("flat" if -3 < d < 3 else "WIN")
        print(f"{f:<6} {regime:<14} {n:>8,} {m1:>8.3f} {m3:>8.3f} {d:>6.1f}%  {verdict}")
    print()

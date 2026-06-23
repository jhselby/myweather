"""Stage 0 — Lead-hour × C1a transition penalty interaction.

C1a measures MAE penalty when state_fc.regime ≠ state_obs.regime. Hypothesis:
the penalty grows with lead. Short-lead regime predictions should be easy
(persist current regime). Long-lead predictions cross more synoptic
boundaries, so transition is both more common and harder to call exactly.

Method: per (field, lead band), MAE ratio (transition / stable). If ratios
grow monotonically with lead, lead-conditional C1a bands are warranted.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ["t", "h", "ws", "wg", "cc", "ch", "cm", "cl"]
BANDS  = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]

def lead_band(lh):
    for lab, lo, hi in BANDS:
        if lo <= lh < hi: return lab
    return None

# (field, band, transition) -> [n, sum|err|]
sums = defaultdict(lambda: [0, 0.0])
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try: r = json.loads(raw)
        except: continue
        f = r.get("field")
        if f not in FIELDS: continue
        lead = r.get("lead_h")
        if lead is None: continue
        band = lead_band(int(lead))
        if not band: continue
        sf = (r.get("state_fc") or {}).get("regime_synoptic")
        so = (r.get("state_obs") or {}).get("regime_synoptic")
        if not sf or not so: continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None: continue
        trans = (sf != so)
        s = sums[(f, band, trans)]
        s[0] += 1; s[1] += abs(err)

print(f"{'field':<5} {'band':<7} {'stable_MAE':>10} {'trans_MAE':>10} {'ratio':>7}")
print("-" * 50)
for f in FIELDS:
    ratios = []
    for lab, _, _ in BANDS:
        ns, es = sums.get((f, lab, False), (0, 0.0))
        nt, et = sums.get((f, lab, True),  (0, 0.0))
        if ns < 200 or nt < 200: continue
        ms = es/ns; mt = et/nt
        ratio = mt/ms if ms else 0
        ratios.append((lab, ratio))
        print(f"{f:<5} {lab:<7} {ms:>10.3f} {mt:>10.3f} {ratio:>6.2f}×")
    if len(ratios) >= 3:
        # check monotonicity
        r0, r1 = ratios[0][1], ratios[-1][1]
        diff = r1 - r0
        if diff >= 0.3:
            verdict = "★ LEAD-GROWING C1a penalty"
        elif diff >= 0.15:
            verdict = "⚠ mild growth"
        else:
            verdict = "flat"
        print(f"  → {f}: short→long Δ {diff:+.2f}  {verdict}")
    print()

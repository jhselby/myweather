"""Stage 0 — Mesonet confidence label × downstream MAE.

The Layer 2 mesonet emits a confidence label (High / Moderate / Low) per tick
based on octant-to-octant temperature scatter. Hypothesis: when scatter is
high (label = Moderate / Low), forecast accuracy on OTHER fields should also
be elevated — atmospheric conditions are noisier across the board, not just
for temperature.

The pair log doesn't carry the live confidence label directly, but it has
state_obs.regime_synoptic and adjacent fields. The cleanest proxy: use
state_obs.regime_synoptic transition + scatter-prone regimes (sea_breeze,
frontal) as a stand-in. But the more direct test = pull current confidence
label from live weather_data per recent tick + retrospective MAE on those
ticks.

Method: read recent weather_data.json snapshots from GCS where confidence
label is recorded. For pairs joining those ticks, compare MAE by label.

Note: weather_data is overwritten each tick, so historical labels aren't
in GCS. Instead, use the regime classifier output (state_obs.regime_synoptic)
and assume sea_breeze + frontal correspond to higher-scatter periods.
Verified by a quick test: does MAE differ between sea_breeze/frontal regimes
vs calm/nw_flow regimes for ALL fields?

This is a self-consistency / sanity-check more than a Stage 1 candidate.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ["t", "h", "ws", "wg", "cc", "cl", "cm", "ch", "pr"]
HIGH_SCATTER_REGIMES = {"sea_breeze", "frontal"}  # known noisy
LOW_SCATTER_REGIMES = {"calm", "nw_flow", "sw_flow"}  # known stable

# (field, scatter_class) -> [n, sum|err|]
sums = defaultdict(lambda: [0, 0.0])
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try: r = json.loads(raw)
        except: continue
        f = r.get("field")
        if f not in FIELDS: continue
        regime = (r.get("state_obs") or {}).get("regime_synoptic")
        if not regime: continue
        if regime in HIGH_SCATTER_REGIMES: sc = "high_scatter"
        elif regime in LOW_SCATTER_REGIMES: sc = "low_scatter"
        else: continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None: continue
        s = sums[(f, sc)]
        s[0] += 1; s[1] += abs(err)

print(f"{'field':<5} {'scatter':<14} {'n':>9} {'|err|':>8}")
print("-" * 45)
for f in FIELDS:
    rows = []
    for sc in ("low_scatter", "high_scatter"):
        n, e = sums.get((f, sc), (0, 0.0))
        if n < 200: continue
        rows.append((sc, n, e/n))
    if len(rows) == 2:
        for sc, n, m in rows:
            print(f"{f:<5} {sc:<14} {n:>9,} {m:>8.3f}")
        ratio = rows[1][2] / rows[0][2]
        flag = "★" if ratio >= 1.5 else ("⚠" if ratio >= 1.2 else "flat")
        print(f"  → {f}: high/low scatter ratio: {ratio:.2f}×  {flag}")
        print()

"""Stage 0 — Forecast self-coherence: precip ≠ cloud-cover sanity.

When `state_fc.precip_in > 0` but `state_obs.cloud_cover < 30%`, the model
is forecasting precipitation under a near-clear sky — internally incoherent.
The hypothesis: such incoherent pairs are downstream-degraded across many
fields, not just precip. If MAE in temp/wind/cloud is systematically higher
on incoherent pairs, that's a confidence-widening signal regardless of field.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ["t", "h", "ws", "wg", "cc", "ch", "cm", "cl", "pp", "pa"]

# (field, coherence_state) -> [n, sum|err|]
sums = defaultdict(lambda: [0, 0.0])
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in FIELDS:
            continue
        sf = r.get("state_fc") or {}
        so = r.get("state_obs") or {}
        fc_precip = sf.get("precip_in")
        obs_cc = so.get("cloud_cover")
        if fc_precip is None or obs_cc is None:
            continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None:
            continue
        # Classify
        if fc_precip > 0.01 and obs_cc < 30:
            state = "incoherent_dry_obs (precip_fc>0, cc_obs<30)"
        elif fc_precip > 0.01 and obs_cc >= 30:
            state = "coherent_wet (precip_fc>0, cc_obs≥30)"
        elif fc_precip <= 0.01 and obs_cc < 30:
            state = "coherent_clear (precip_fc=0, cc_obs<30)"
        else:
            state = "coherent_cloudy (precip_fc=0, cc_obs≥30)"
        s = sums[(f, state)]
        s[0] += 1; s[1] += abs(err)

STATES = ["coherent_clear (precip_fc=0, cc_obs<30)",
          "coherent_cloudy (precip_fc=0, cc_obs≥30)",
          "coherent_wet (precip_fc>0, cc_obs≥30)",
          "incoherent_dry_obs (precip_fc>0, cc_obs<30)"]
print(f"{'field':<5} {'coherence':<48} {'n':>7} {'|err|':>8}")
print("-" * 75)
for f in FIELDS:
    by = {}
    for state in STATES:
        n, e = sums.get((f, state), (0, 0.0))
        if n < 100:
            continue
        by[state] = (n, e/n)
    if "coherent_clear (precip_fc=0, cc_obs<30)" in by:
        base_mae = by["coherent_clear (precip_fc=0, cc_obs<30)"][1]
        for state in STATES:
            if state not in by:
                continue
            n, m = by[state]
            d = (m - base_mae)/base_mae*100 if base_mae else 0
            flag = ""
            if "incoherent" in state:
                flag = "★" if d >= 30 else ("⚠" if d >= 10 else "")
            print(f"{f:<5} {state:<48} {n:>7,} {m:>8.3f} ({d:+.1f}%) {flag}")
    print()

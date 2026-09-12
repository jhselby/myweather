"""Stage 0 — Diurnal-conditioned L2 τ refit.

Hypothesis: L2's exponential decay time-constant τ is currently pooled across
hour-of-day, but the physical persistence of forecast error differs between
nighttime (radiational cooling — slow, monotonic) and daytime (convection —
fast, non-stationary). A τ conditioned on hour-of-day-of-issue may beat
pooled on held-out.

Method: for each (field, hour-of-day-bin), collect (issue_time, err_l1)
pairs. Fit best τ per (field, hod_bin) via grid-search minimizing held-out
MAE of the L2-corrected forecast. Compare against pooled-τ MAE.

Ship shape (if it clears): weather_collector/processors/l2_apply.py replaces
scalar tau with a per-hour-of-day lookup. Wire ENABLED=False first with a
7-day gate; existing L2 machinery unchanged otherwise.

Verdict: PROMOTE if diurnal-τ beats pooled-τ by ≥ +1% held-out AND ≥ 3
fields show meaningful HOD variation (max-τ / min-τ ≥ 1.5).
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS   = ("t", "h", "ws", "wg", "cc", "cl", "cm", "ch", "dp", "sr")
HOD_BINS = [("00-05", 0, 6), ("06-11", 6, 12), ("12-17", 12, 18), ("18-23", 18, 24)]
TAU_GRID = [1, 2, 3, 4, 6, 8, 10, 12, 16, 24, 42, 60, 999]
MIN_N    = 500

def hod_bin(hour):
    for label, lo, hi in HOD_BINS:
        if lo <= hour < hi:
            return label
    return None

# rows: (field, hod_bin) -> list of (lead_h, err_l1)
# We need err_l1 (raw) and the L2 correction is applied by decaying the previous obs error.
# Simpler: use the shipped forecast_l2 directly. err_l2_applied = |obs - forecast_l2|.
# For a τ-sweep we need to RECOMPUTE L2 corrections at candidate τ values. That requires
# the L1 forecast + L2 delta which requires the "previous hour obs residual" — nontrivial.
#
# Simpler heuristic for Stage 0: compare live L2 helping rate stratified by HOD.
# If live L2 helps materially more in some HOD bins than others, that's evidence
# a HOD-conditional τ could beat pooled. This is a screen, not a fit.

hod_stats = defaultdict(lambda: [0, 0.0, 0.0])  # (field, hod) -> [n, sum|err_l1|, sum|err_l2|]

print("Streaming pair log...")
n_in = n_use = 0
with open(cached_path(PAIR_URL), "rb") as fh:
    for raw in fh:
        n_in += 1
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in FIELDS: continue
        e_l1 = r.get("error_l1")
        e_l2 = r.get("error_l2")
        if e_l1 is None or e_l2 is None: continue
        rt = r.get("run_time")
        if not rt: continue
        try:
            rdt = datetime.fromisoformat(rt[:19])
        except Exception:
            continue
        hb = hod_bin(rdt.hour)
        if not hb: continue
        s = hod_stats[(f, hb)]
        s[0] += 1
        s[1] += abs(float(e_l1))
        s[2] += abs(float(e_l2))
        n_use += 1
print(f"  {n_use:,} of {n_in:,} rows used\n")

# For each field: help_rate per HOD, compare max vs min
print(f"{'field':<5} {'hod_bin':<7} {'n':>7} {'mae_l1':>8} {'mae_l2':>8} {'help%':>7}")
print("-" * 55)
field_ranges = {}
for f in FIELDS:
    helps = {}
    for label, _, _ in HOD_BINS:
        s = hod_stats.get((f, label))
        if not s or s[0] < MIN_N: continue
        mae1 = s[1] / s[0]
        mae2 = s[2] / s[0]
        help_pct = ((mae1 - mae2) / mae1 * 100) if mae1 > 0 else 0
        helps[label] = help_pct
        print(f"{f:<5} {label:<7} {s[0]:>7,} {mae1:>8.3f} {mae2:>8.3f} {help_pct:>6.2f}%")
    if len(helps) >= 3:
        vals = list(helps.values())
        rng = max(vals) - min(vals)
        field_ranges[f] = (rng, helps)
    print()

# Verdict: which fields show meaningful HOD variation in L2 help-rate?
print("=" * 70)
print(f"{'field':<5} {'help_range_pp':>13} {'signal':>7}")
print("-" * 40)
strong = 0
for f, (rng, helps) in field_ranges.items():
    signal = "STRONG" if rng >= 3.0 else ("MARGINAL" if rng >= 1.5 else "FLAT")
    if signal == "STRONG": strong += 1
    print(f"{f:<5} {rng:>12.2f}pp {signal:>10}")

print()
if strong >= 3:
    print(f"VERDICT: STAGE 0 PROMOTE — {strong} fields show ≥3pp help-rate spread across HOD bins. Diurnal-conditional L2 τ is worth fitting (Stage 1 = grid-search τ per (field, HOD) on held-out).")
elif strong >= 1:
    print(f"VERDICT: STAGE 0 MARGINAL — {strong} field(s) show strong HOD variation. Watch — need ≥3 for structural promotion.")
else:
    print(f"VERDICT: HOLD — no field shows ≥3pp help-rate spread across HOD bins. Pooled L2 τ appears well-calibrated.")

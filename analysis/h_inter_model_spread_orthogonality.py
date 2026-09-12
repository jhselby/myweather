"""Stage 1 — Orthogonality of inter-model spread (HRRR-vs-NBM) vs existing C1 axes.

Candidate axis: inter_model_spread = |forecast_l1 − forecast_raw_nbm| per row.
Stage 0 result (v0.6.593): PROMOTE 35 of 36 (field, band) cells.

Test: for each existing per-row C1 axis A, does inter_model_spread's Q4/Q1
MAE ratio survive when A is HELD LOW (i.e., subtracting out A's signal)?

Existing axes tested (all per-row available in pair log):
  • C1a — transition (state_fc.regime_synoptic != state_obs.regime_synoptic)
  • cluster_spread (cloud_inter_source_sigma — cloud fields only)
  • pressure_tendency (state_fc.pressure_trend_hpa_3h magnitude)

Verdict per (candidate × axis):
  ORTHOGONAL — Q4/Q1 ratio ≥ 1.30 within A_low subset (candidate independent of A)
  REDUNDANT  — Q4/Q1 ratio ≤ 1.10 within A_low subset (A captures all elevation)
  PARTIAL    — ratio between 1.10 and 1.30 (some overlap)
  THIN       — insufficient sample in a subset

Overall PROMOTE if ORTHOGONAL vs all axes tested (candidate is a truly new axis).
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS   = ("t", "h", "ws", "wg", "wd", "cc", "cl", "cm", "ch", "dp", "sr")
BANDS    = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N_BIN = 100

def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None

def signed_delta(field, a, b):
    if field == "wd":
        d = (a - b) % 360
        if d > 180: d -= 360
        return abs(d)
    return abs(a - b)

# Pass 1: collect per-row (field, band, candidate, C1a, cluster_sigma, pt_mag, err)
print("Loading pair log...")
rows_by_cell = defaultdict(list)  # (field, band) -> list of tuples
with open(cached_path(PAIR_URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in FIELDS: continue
        lead = r.get("lead_h")
        if lead is None: continue
        band = lead_band(int(lead))
        if not band: continue
        f_h = r.get("forecast_l1")
        f_n = r.get("forecast_raw_nbm")
        if f_h is None or f_n is None: continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None: continue
        sf = (r.get("state_fc") or {})
        so = (r.get("state_obs") or {})
        sf_reg = sf.get("regime_synoptic")
        so_reg = so.get("regime_synoptic")
        if not sf_reg or not so_reg: continue
        c1a = int(sf_reg != so_reg)  # 1 = transition, 0 = stable
        clust = r.get("cloud_inter_source_sigma")  # cloud fields have this
        pt = sf.get("pressure_trend_hpa_3h")
        pt_mag = abs(float(pt)) if pt is not None else None
        cand = signed_delta(f, float(f_h), float(f_n))
        rows_by_cell[(f, band)].append((cand, c1a, clust, pt_mag, abs(float(err))))

# Quartile splits per (field, band) on candidate
def quartile_bin(sorted_arr, val):
    n = len(sorted_arr)
    q1 = sorted_arr[n // 4]
    q3 = sorted_arr[3 * n // 4]
    if val <= q1: return "Q1"
    if val >= q3: return "Q4"
    return "Q2Q3"

# For each (field, band, axis): compute Q4/Q1 within axis-LOW subset
AXES = [
    ("C1a_trans", lambda t: t[1] == 0, lambda t: t[1] == 1),  # axis_low = stable, axis_high = trans
    ("cluster",   None, None),  # populated below with per-cell quartile on t[2]
    ("pt_mag",    None, None),
]

print(f"\n{'candidate':<24} {'field':<5} {'band':<7} {'axis':<12} {'ratio_A_low':>11} {'n_Q1':>6} {'n_Q4':>6}  verdict")
print("-" * 100)
verdict_matrix = defaultdict(lambda: defaultdict(int))

for (f, band), rows in rows_by_cell.items():
    if len(rows) < 4 * MIN_N_BIN: continue
    cand_sorted = sorted(x[0] for x in rows)
    # Compute per-axis lookups (quartile-based for continuous)
    clust_vals = sorted(x[2] for x in rows if x[2] is not None)
    pt_vals    = sorted(x[3] for x in rows if x[3] is not None)
    clust_q1 = clust_vals[len(clust_vals)//4] if len(clust_vals) >= 4 * MIN_N_BIN else None
    pt_q1    = pt_vals[len(pt_vals)//4]       if len(pt_vals)    >= 4 * MIN_N_BIN else None

    def axis_low(name, r):
        cand, c1a, clust, pt_mag, err = r
        if name == "C1a_trans": return c1a == 0
        if name == "cluster":   return clust is not None and clust_q1 is not None and clust <= clust_q1
        if name == "pt_mag":    return pt_mag is not None and pt_q1 is not None and pt_mag <= pt_q1
        return False

    for axis_name in ("C1a_trans", "cluster", "pt_mag"):
        if axis_name == "cluster" and clust_q1 is None: continue
        if axis_name == "pt_mag"  and pt_q1    is None: continue
        # Filter to axis_low subset, then compute Q4/Q1 on candidate
        low_rows = [r for r in rows if axis_low(axis_name, r)]
        if len(low_rows) < 2 * MIN_N_BIN: continue
        low_cand_sorted = sorted(r[0] for r in low_rows)
        n_low = len(low_cand_sorted)
        q1_thresh = low_cand_sorted[n_low // 4]
        q4_thresh = low_cand_sorted[3 * n_low // 4]
        q1_rows = [r for r in low_rows if r[0] <= q1_thresh]
        q4_rows = [r for r in low_rows if r[0] >= q4_thresh]
        if len(q1_rows) < MIN_N_BIN or len(q4_rows) < MIN_N_BIN: continue
        mae_q1 = sum(r[4] for r in q1_rows) / len(q1_rows)
        mae_q4 = sum(r[4] for r in q4_rows) / len(q4_rows)
        if mae_q1 == 0: continue
        ratio = mae_q4 / mae_q1
        if ratio >= 1.30: verdict = "ORTHOGONAL"
        elif ratio <= 1.10: verdict = "REDUNDANT"
        else: verdict = "PARTIAL"
        verdict_matrix[axis_name][verdict] += 1
        print(f"{'inter_model_spread':<24} {f:<5} {band:<7} {axis_name:<12} {ratio:>10.2f}× {len(q1_rows):>6,} {len(q4_rows):>6,}  {verdict}")

print("\n" + "=" * 100)
print(f"{'axis':<15} {'ORTHOGONAL':>10} {'REDUNDANT':>10} {'PARTIAL':>10}")
for axis_name in ("C1a_trans", "cluster", "pt_mag"):
    v = verdict_matrix[axis_name]
    print(f"{axis_name:<15} {v['ORTHOGONAL']:>10} {v['REDUNDANT']:>10} {v['PARTIAL']:>10}")

# Overall: for each axis, PROMOTE if ORTHOGONAL count dominates (≥ 3× REDUNDANT)
overall = []
for axis_name in ("C1a_trans", "cluster", "pt_mag"):
    v = verdict_matrix[axis_name]
    o, r_ = v['ORTHOGONAL'], v['REDUNDANT']
    if o >= 3 and o >= 3 * max(r_, 1):
        overall.append((axis_name, "ORTHOGONAL"))
    elif r_ >= 3 and r_ >= 2 * o:
        overall.append((axis_name, "REDUNDANT"))
    else:
        overall.append((axis_name, "PARTIAL"))

ortho_axes = [n for n, v in overall if v == "ORTHOGONAL"]
redund_axes = [n for n, v in overall if v == "REDUNDANT"]

print()
if len(ortho_axes) == 3:
    print(f"VERDICT: STAGE 1 PROMOTE — inter_model_spread is independent of all three tested C1 axes ({', '.join(ortho_axes)}). New axis candidate.")
elif len(ortho_axes) >= 2 and len(redund_axes) == 0:
    print(f"VERDICT: STAGE 1 PARTIAL PROMOTE — orthogonal vs {', '.join(ortho_axes)}; unclear vs the rest. Advance to Stage 2 with per-cell narrow ship.")
elif len(redund_axes) >= 2:
    print(f"VERDICT: KILL — inter_model_spread is redundant with {', '.join(redund_axes)}. Fold into existing axes.")
else:
    print(f"VERDICT: HOLD — mixed orthogonality result. Orthogonal vs {ortho_axes}; redundant vs {redund_axes}.")

"""Stage 1 — Orthogonality of prior-day-error vs existing C1 axes.

Candidate axis: prior_day_err = |error| at (field, lead, valid_time − 24h).
Stage 0 result (v0.6.593): PROMOTE 14 of 40 cells (strong short-lead signal
across t/h/ws/wg/cc/dp; ch across all bands).

Test: for each existing per-row C1 axis A, does prior_day_err's Q4/Q1 MAE
ratio survive when A is HELD LOW?

Existing axes tested (all per-row available in pair log):
  • C1a — transition (state_fc.regime != state_obs.regime)
  • cluster_spread (cloud_inter_source_sigma)
  • pressure_tendency (state_fc.pressure_trend_hpa_3h magnitude)

Overall PROMOTE if ORTHOGONAL vs all axes tested.
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS   = ("t", "h", "ws", "wg", "cc", "cl", "cm", "ch", "dp", "sr")
BANDS    = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N_BIN = 100

def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None

# Pass 1: index by (field, lead, valid_hour) for prior-day join
print("Loading pair log + indexing...")
by_key = {}
all_rows = []
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
        vt = r.get("valid_time")
        if not vt: continue
        try:
            vdt = datetime.fromisoformat(vt[:19])
        except Exception:
            continue
        err = r.get("error")
        if err is None:
            err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None: continue
        sf = (r.get("state_fc") or {})
        so = (r.get("state_obs") or {})
        sf_reg = sf.get("regime_synoptic")
        so_reg = so.get("regime_synoptic")
        if not sf_reg or not so_reg: continue
        c1a = int(sf_reg != so_reg)
        clust = r.get("cloud_inter_source_sigma")
        pt = sf.get("pressure_trend_hpa_3h")
        pt_mag = abs(float(pt)) if pt is not None else None
        vdt_hr = vdt.replace(minute=0, second=0, microsecond=0)
        key = (f, int(lead), vdt_hr)
        abs_err = abs(float(err))
        by_key[key] = abs_err
        all_rows.append((f, int(lead), band, vdt_hr, abs_err, c1a, clust, pt_mag))
print(f"  {len(all_rows):,} rows indexed")

# Pass 2: for each row, look up prior-day analogue
print("Joining prior-day analogues...")
rows_by_cell = defaultdict(list)  # (field, band) -> list of (prior_err, c1a, clust, pt_mag, err)
for f, lead, band, vdt_hr, err, c1a, clust, pt_mag in all_rows:
    prior_key = (f, lead, vdt_hr - timedelta(hours=24))
    prior_err = by_key.get(prior_key)
    if prior_err is None: continue
    rows_by_cell[(f, band)].append((prior_err, c1a, clust, pt_mag, err))
n_joined = sum(len(v) for v in rows_by_cell.values())
print(f"  {n_joined:,} rows joined\n")

print(f"{'candidate':<20} {'field':<5} {'band':<7} {'axis':<12} {'ratio_A_low':>11} {'n_Q1':>6} {'n_Q4':>6}  verdict")
print("-" * 96)
verdict_matrix = defaultdict(lambda: defaultdict(int))

for (f, band), rows in rows_by_cell.items():
    if len(rows) < 4 * MIN_N_BIN: continue
    clust_vals = sorted(x[2] for x in rows if x[2] is not None)
    pt_vals    = sorted(x[3] for x in rows if x[3] is not None)
    clust_q1 = clust_vals[len(clust_vals)//4] if len(clust_vals) >= 4 * MIN_N_BIN else None
    pt_q1    = pt_vals[len(pt_vals)//4]       if len(pt_vals)    >= 4 * MIN_N_BIN else None

    def axis_low(name, r):
        prior_err, c1a, clust, pt_mag, err = r
        if name == "C1a_trans": return c1a == 0
        if name == "cluster":   return clust is not None and clust_q1 is not None and clust <= clust_q1
        if name == "pt_mag":    return pt_mag is not None and pt_q1 is not None and pt_mag <= pt_q1
        return False

    for axis_name in ("C1a_trans", "cluster", "pt_mag"):
        if axis_name == "cluster" and clust_q1 is None: continue
        if axis_name == "pt_mag"  and pt_q1    is None: continue
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
        print(f"{'prior_day_err':<20} {f:<5} {band:<7} {axis_name:<12} {ratio:>10.2f}× {len(q1_rows):>6,} {len(q4_rows):>6,}  {verdict}")

print("\n" + "=" * 96)
print(f"{'axis':<15} {'ORTHOGONAL':>10} {'REDUNDANT':>10} {'PARTIAL':>10}")
for axis_name in ("C1a_trans", "cluster", "pt_mag"):
    v = verdict_matrix[axis_name]
    print(f"{axis_name:<15} {v['ORTHOGONAL']:>10} {v['REDUNDANT']:>10} {v['PARTIAL']:>10}")

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
    print(f"VERDICT: STAGE 1 PROMOTE — prior_day_err is independent of all three tested C1 axes ({', '.join(ortho_axes)}). New axis candidate.")
elif len(ortho_axes) >= 2 and len(redund_axes) == 0:
    print(f"VERDICT: STAGE 1 PARTIAL PROMOTE — orthogonal vs {', '.join(ortho_axes)}; unclear vs the rest.")
elif len(redund_axes) >= 2:
    print(f"VERDICT: KILL — prior_day_err is redundant with {', '.join(redund_axes)}.")
else:
    print(f"VERDICT: HOLD — mixed orthogonality result. Orthogonal vs {ortho_axes}; redundant vs {redund_axes}.")

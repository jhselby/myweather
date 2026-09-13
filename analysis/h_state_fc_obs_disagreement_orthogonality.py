"""Stage 1 — Orthogonality of state_fc-vs-state_obs disagreement axes.

Candidate axes (from Stage 0 v0.6.596 — h_state_fc_obs_disagreement_stage0):
  • cloud_delta = |state_fc.cloud_cover − state_obs.cloud_cover|   (12 cells)
  • solar_delta = |state_fc.solar_wm2   − state_obs.solar_wm2|     (13 cells)

Test: for each existing per-row C1 axis A, does the candidate's Q4/Q1
MAE ratio survive when A is HELD LOW (i.e., subtracting out A's signal)?
Mirrors h_inter_model_spread_orthogonality.py (v0.6.594) directly — same
axes, same thresholds, same verdict rules.

Existing axes tested:
  • C1a — transition (state_fc.regime_synoptic != state_obs.regime_synoptic)
  • cluster_spread (cloud_inter_source_sigma — cloud fields only)
  • pt_mag         (state_fc.pressure_trend_hpa_3h magnitude)

Verdict per (candidate × axis):
  ORTHOGONAL — Q4/Q1 ratio ≥ 1.30 within A_low subset
  REDUNDANT  — Q4/Q1 ratio ≤ 1.10 within A_low subset
  PARTIAL    — ratio between 1.10 and 1.30
  THIN       — insufficient sample

Overall PROMOTE per candidate if ORTHOGONAL vs all three tested axes.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS   = ("t", "h", "ws", "wg", "wd", "cc", "cl", "cm", "ch", "dp", "sr")
BANDS    = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N_BIN = 100

CANDIDATES = ("cloud_delta", "solar_delta")


def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


# Pass 1: collect per-row (field, band, cloud_delta, solar_delta, C1a, cluster_sigma, pt_mag, err)
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

        cc_fc = sf.get("cloud_cover"); cc_ob = so.get("cloud_cover")
        sr_fc = sf.get("solar_wm2");   sr_ob = so.get("solar_wm2")
        cloud_delta = abs(float(cc_fc) - float(cc_ob)) if cc_fc is not None and cc_ob is not None else None
        solar_delta = abs(float(sr_fc) - float(sr_ob)) if sr_fc is not None and sr_ob is not None else None
        if cloud_delta is None and solar_delta is None: continue

        rows_by_cell[(f, band)].append((cloud_delta, solar_delta, c1a, clust, pt_mag, abs(float(err))))

# Per candidate × cell × axis: Q4/Q1 ratio within axis_low subset
per_cand_matrix = {c: defaultdict(lambda: defaultdict(int)) for c in CANDIDATES}

print(f"\n{'candidate':<14} {'field':<5} {'band':<7} {'axis':<12} {'ratio_A_low':>11} {'n_Q1':>6} {'n_Q4':>6}  verdict")
print("-" * 100)

for (f, band), rows in rows_by_cell.items():
    if len(rows) < 4 * MIN_N_BIN: continue
    clust_vals = sorted(x[3] for x in rows if x[3] is not None)
    pt_vals    = sorted(x[4] for x in rows if x[4] is not None)
    clust_q1 = clust_vals[len(clust_vals)//4] if len(clust_vals) >= 4 * MIN_N_BIN else None
    pt_q1    = pt_vals[len(pt_vals)//4]       if len(pt_vals)    >= 4 * MIN_N_BIN else None

    def axis_low(name, r):
        cd, sd, c1a, clust, pt_mag, err = r
        if name == "C1a_trans": return c1a == 0
        if name == "cluster":   return clust is not None and clust_q1 is not None and clust <= clust_q1
        if name == "pt_mag":    return pt_mag is not None and pt_q1 is not None and pt_mag <= pt_q1
        return False

    for cand_idx, cand_name in enumerate(CANDIDATES):
        # Filter rows where this candidate is available
        cand_rows = [r for r in rows if r[cand_idx] is not None]
        if len(cand_rows) < 4 * MIN_N_BIN: continue

        for axis_name in ("C1a_trans", "cluster", "pt_mag"):
            if axis_name == "cluster" and clust_q1 is None: continue
            if axis_name == "pt_mag"  and pt_q1    is None: continue
            low_rows = [r for r in cand_rows if axis_low(axis_name, r)]
            if len(low_rows) < 2 * MIN_N_BIN: continue
            low_cand_sorted = sorted(r[cand_idx] for r in low_rows)
            n_low = len(low_cand_sorted)
            q1_thresh = low_cand_sorted[n_low // 4]
            q4_thresh = low_cand_sorted[3 * n_low // 4]
            q1_rows = [r for r in low_rows if r[cand_idx] <= q1_thresh]
            q4_rows = [r for r in low_rows if r[cand_idx] >= q4_thresh]
            if len(q1_rows) < MIN_N_BIN or len(q4_rows) < MIN_N_BIN: continue
            mae_q1 = sum(r[5] for r in q1_rows) / len(q1_rows)
            mae_q4 = sum(r[5] for r in q4_rows) / len(q4_rows)
            if mae_q1 == 0: continue
            ratio = mae_q4 / mae_q1
            if ratio >= 1.30: verdict = "ORTHOGONAL"
            elif ratio <= 1.10: verdict = "REDUNDANT"
            else: verdict = "PARTIAL"
            per_cand_matrix[cand_name][axis_name][verdict] += 1
            print(f"{cand_name:<14} {f:<5} {band:<7} {axis_name:<12} {ratio:>10.2f}× {len(q1_rows):>6,} {len(q4_rows):>6,}  {verdict}")

# Per-candidate rollup
print("\n" + "=" * 100)
overall_by_cand = {}
for cand_name in CANDIDATES:
    print(f"\n{cand_name}:")
    print(f"  {'axis':<15} {'ORTHOGONAL':>10} {'REDUNDANT':>10} {'PARTIAL':>10}")
    axis_verdicts = []
    for axis_name in ("C1a_trans", "cluster", "pt_mag"):
        v = per_cand_matrix[cand_name][axis_name]
        print(f"  {axis_name:<15} {v['ORTHOGONAL']:>10} {v['REDUNDANT']:>10} {v['PARTIAL']:>10}")
        o, r_ = v['ORTHOGONAL'], v['REDUNDANT']
        if o >= 3 and o >= 3 * max(r_, 1):
            axis_verdicts.append((axis_name, "ORTHOGONAL"))
        elif r_ >= 3 and r_ >= 2 * o:
            axis_verdicts.append((axis_name, "REDUNDANT"))
        else:
            axis_verdicts.append((axis_name, "PARTIAL"))
    overall_by_cand[cand_name] = axis_verdicts

# Final verdicts
print("\n" + "=" * 100)
promote_ct = 0
for cand_name in CANDIDATES:
    axis_verdicts = overall_by_cand[cand_name]
    ortho = [n for n, v in axis_verdicts if v == "ORTHOGONAL"]
    redund = [n for n, v in axis_verdicts if v == "REDUNDANT"]
    if len(ortho) == 3:
        print(f"{cand_name}: STAGE 1 PROMOTE — independent of all three tested C1 axes ({', '.join(ortho)}). New axis candidate.")
        promote_ct += 1
    elif len(ortho) >= 2 and len(redund) == 0:
        print(f"{cand_name}: STAGE 1 PARTIAL PROMOTE — orthogonal vs {', '.join(ortho)}; unclear vs the rest.")
    elif len(redund) >= 2:
        print(f"{cand_name}: KILL — redundant with {', '.join(redund)}. Fold into existing axes.")
    else:
        print(f"{cand_name}: HOLD — mixed. Orthogonal vs {ortho}; redundant vs {redund}.")

print()
if promote_ct == 2:
    print("VERDICT: STAGE 1 PROMOTE (both) — cloud_delta and solar_delta are independent new axes.")
elif promote_ct == 1:
    print("VERDICT: STAGE 1 PROMOTE (partial) — one candidate cleared; the other needs review.")
else:
    print("VERDICT: HOLD / KILL — neither candidate clears the orthogonality bar.")

"""Stage 1.5 — inter_model_spread orthogonality vs xr_q (live incumbent axis).

Purpose: gate the Stage 2 SHIP cells from h_inter_model_spread_c1_stage2 against
double-widening with the live xr_q axis (cross_run_spread, wired v0.6.401g).

Both signals measure forecast difficulty of the current vt. Stage 1
tested ims orthogonality vs C1a_trans / cluster_spread / pt_mag; xr_q was
NOT in that gate.  Both signals promoted the SAME 6 fields (t/wd/wg/dp/pr/ws)
under separate Stage 2 halves-stable tests — high overlap risk.

Method (per Stage 2 SHIP cell):
  1. Load pair-log rows for (field, band).
  2. Compute ims = |forecast_l1 - forecast_raw_nbm| per row.
  3. Group by (field, vt) across the FIELD (not the cell) to build cross-run
     spread edges — matches xr_q axis scope which is field-level.
  4. Compute cell-level ims quartile edges (matches Stage 2 ims_q shape).
  5. Bin rows into 5 xr levels × 4 ims levels.
  6. Test: mean|err|(ims_Q4) / mean|err|(ims_Q1) ratio >= ORTHO_GATE inside
     both xr_Q1 and xr_Q5.  PASS = ims survives conditioning on xr_q.

Output: analysis/output/h_inter_model_spread_vs_xr_q_ortho.json  — per-cell
verdict list the curator uses to gate axis-6 SHIP entries.  Empty gate
verdict list (I/O failure or no SHIP cells) → curator must SKIP all ims
axis cells (safe default).
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path
from _prod import prod_error

PAIR_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
STAGE2_PATH = os.path.join(os.path.dirname(__file__), "output",
                           "h_inter_model_spread_c1_stage2.json")
OUT_PATH = os.path.join(os.path.dirname(__file__), "output",
                        "h_inter_model_spread_vs_xr_q_ortho.json")

BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
WINDOW_DAYS = 45
MIN_N_PER_QUADRANT = 40         # per (ims_bin × xr_bin) — matches xr_q Stage 2 floor
ORTHO_GATE = 1.15                # ims_Q4/Q1 ratio inside a fixed xr level to PASS
REDUNDANT_CEILING = 1.05         # below this → xr already captures the signal

FIELDS = ("t", "h", "ws", "wg", "wd", "cc", "cl", "cm", "ch", "dp", "sr", "pr")


def band_for(lead):
    for name, lo, hi in BANDS:
        if lo <= lead < hi:
            return name
    return None


def signed_delta(field, a, b):
    if field == "wd":
        d = (a - b) % 360
        if d > 180:
            d -= 360
        return abs(d)
    return abs(a - b)


def quintile_edges(sorted_vals):
    n = len(sorted_vals)
    return [sorted_vals[int(n * q)] for q in (0.2, 0.4, 0.6, 0.8)]


def quartile_edges(sorted_vals):
    n = len(sorted_vals)
    return [sorted_vals[int(n * q)] for q in (0.25, 0.5, 0.75)]


def bin_index(x, edges):
    for i, e in enumerate(edges):
        if x < e:
            return i
    return len(edges)


def load_stage2_ships():
    """Return {(field, band_label): stage2_entry} for SHIP cells only."""
    try:
        with open(STAGE2_PATH) as f:
            doc = json.load(f)
    except Exception as e:
        print(f"ERROR: could not load Stage 2 output {STAGE2_PATH}: {e}")
        return {}
    ships = {}
    for field, bands in (doc.get("cells") or {}).items():
        for band, entry in bands.items():
            if entry.get("verdict") == "SHIP":
                ships[(field, band)] = entry
    return ships


def load_pair_rows(field_set):
    """Return (rows_by_cell, forecasts_by_field_vt).

    rows_by_cell[(field, band)] = list of {vt, obs_dt, ims, err}
    forecasts_by_field_vt[(field, vt)] = list of forecast_l1 values (across runs)
    """
    rows_by_cell = defaultdict(list)
    forecasts_by_field_vt = defaultdict(list)
    cutoff_dt = None
    max_dt = None
    n_scanned = 0
    with open(cached_path(PAIR_URL), "rb") as fh:
        for raw in fh:
            n_scanned += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            f = r.get("field")
            if f not in field_set:
                continue
            lead = r.get("lead_h")
            if lead is None:
                continue
            band = band_for(int(lead))
            if band is None:
                continue
            fl1 = r.get("forecast_l1")
            fnbm = r.get("forecast_raw_nbm")
            if fl1 is None or fnbm is None:
                continue
            err = prod_error(r)
            if err is None:
                continue
            vt = r.get("valid_time") or ""
            if not vt:
                continue
            try:
                obs_dt = datetime.fromisoformat((r.get("obs_time") or "")[:19])
            except Exception:
                continue
            if max_dt is None or obs_dt > max_dt:
                max_dt = obs_dt
            ims = signed_delta(f, float(fl1), float(fnbm))
            rows_by_cell[(f, band)].append({
                "vt": vt,
                "obs_dt": obs_dt,
                "ims": ims,
                "err": abs(float(err)),
            })
            forecasts_by_field_vt[(f, vt)].append(float(fl1))
    if max_dt is not None:
        cutoff_dt = max_dt - timedelta(days=WINDOW_DAYS)
    return rows_by_cell, forecasts_by_field_vt, n_scanned, cutoff_dt


def xr_spread_by_field_vt(forecasts_by_field_vt):
    """Cross-run spread = max - min across L1 forecasts targeting the same vt.
    Only defined when >= 2 runs contributed; single-run vts stay None."""
    out = {}
    for key, arr in forecasts_by_field_vt.items():
        if len(arr) >= 2:
            out[key] = max(arr) - min(arr)
    return out


def analyze_cell(field, band, rows, xr_by_vt, xr_edges_field, cutoff_dt):
    """Return dict verdict for this (field, band) cell."""
    # Filter rows: obs_dt in window + xr_spread available
    scoped = []
    for r in rows:
        if cutoff_dt and r["obs_dt"] < cutoff_dt:
            continue
        xr = xr_by_vt.get((field, r["vt"]))
        if xr is None:
            continue
        scoped.append({"ims": r["ims"], "err": r["err"], "xr": xr})
    n_total = len(scoped)
    if n_total < 8 * MIN_N_PER_QUADRANT:
        return {"status": "THIN_TOTAL", "n_total": n_total}

    # Cell-level ims quartile edges
    ims_edges = quartile_edges(sorted(x["ims"] for x in scoped))
    # Field-level xr edges are already passed in (computed once per field)

    # Bin every row: (ims_bin ∈ {0..3}, xr_bin ∈ {0..4})
    by_quad = defaultdict(list)
    for r in scoped:
        ib = bin_index(r["ims"], ims_edges)
        xb = bin_index(r["xr"], xr_edges_field)
        by_quad[(ib, xb)].append(r["err"])

    # We test ratio ims_Q4 / ims_Q1 inside xr_Q1 (xb=0) and xr_Q5 (xb=4).
    quads = {}
    for (ib, xb), errs in by_quad.items():
        if ib in (0, 3) and xb in (0, 4):
            quads[(ib, xb)] = errs

    def stats(key):
        arr = quads.get(key) or []
        if len(arr) < MIN_N_PER_QUADRANT:
            return None
        return (mean(arr), len(arr))

    q1_low = stats((0, 0))     # ims Q1 × xr Q1
    q4_low = stats((3, 0))     # ims Q4 × xr Q1
    q1_hi = stats((0, 4))      # ims Q1 × xr Q5
    q4_hi = stats((3, 4))      # ims Q4 × xr Q5

    def level_verdict(low_stat, hi_stat, label):
        if not low_stat or not hi_stat:
            return {"level": label, "status": "THIN",
                    "n_ims_q1": (low_stat or (None, 0))[1],
                    "n_ims_q4": (hi_stat or (None, 0))[1]}
        m_low, n_low = low_stat
        m_hi, n_hi = hi_stat
        ratio = (m_hi / m_low) if m_low > 0 else 0
        if ratio >= ORTHO_GATE:
            status = "ORTHOGONAL"
        elif ratio <= REDUNDANT_CEILING:
            status = "REDUNDANT"
        else:
            status = "WEAK"
        return {"level": label, "status": status,
                "n_ims_q1": n_low, "n_ims_q4": n_hi,
                "mae_ims_q1": round(m_low, 4), "mae_ims_q4": round(m_hi, 4),
                "ratio": round(ratio, 3)}

    xr_lo = level_verdict(q1_low, q4_low, "xr_Q1")
    xr_hi = level_verdict(q1_hi, q4_hi, "xr_Q5")

    reals = [v["status"] for v in (xr_lo, xr_hi) if v["status"] != "THIN"]
    if not reals:
        overall = "THIN"
    elif all(v == "ORTHOGONAL" for v in reals):
        overall = "PASS"
    elif all(v == "REDUNDANT" for v in reals):
        overall = "REDUNDANT"
    elif "REDUNDANT" in reals:
        overall = "MIXED_REDUND"
    else:
        overall = "MIXED_WEAK"

    return {
        "status": overall,
        "n_total": n_total,
        "ims_q1_threshold": round(ims_edges[0], 4),
        "ims_q3_threshold": round(ims_edges[2], 4),
        "xr_q1_threshold_field": round(xr_edges_field[0], 4),
        "xr_q5_threshold_field": round(xr_edges_field[3], 4),
        "xr_Q1": xr_lo,
        "xr_Q5": xr_hi,
    }


def main():
    ships = load_stage2_ships()
    if not ships:
        print("VERDICT: NO SHIP CELLS — Stage 2 output missing or empty. "
              "Cannot gate; SKIP all ims axis wiring.")
        result = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source": "h_inter_model_spread_vs_xr_q_ortho.py",
            "window_days": WINDOW_DAYS,
            "ortho_gate": ORTHO_GATE,
            "redundant_ceiling": REDUNDANT_CEILING,
            "ortho_gate_pass": [],
            "ortho_gate_fail": [],
            "per_cell": {},
        }
        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        with open(OUT_PATH, "w") as w:
            json.dump(result, w, indent=2)
        return

    ship_fields = sorted({f for (f, _) in ships})
    print(f"Loaded {len(ships)} SHIP cell(s) across fields {ship_fields}")
    print(f"Loading pair log ...")
    rows_by_cell, forecasts_by_field_vt, n_scanned, cutoff_dt = load_pair_rows(set(ship_fields))
    print(f"  scanned {n_scanned:,} rows, cutoff {cutoff_dt}")

    xr_by_vt = xr_spread_by_field_vt(forecasts_by_field_vt)
    print(f"  built xr_spread for {len(xr_by_vt):,} (field, vt) pairs")

    # Per-field xr edges from all in-window multi-run vts.
    xr_edges_by_field = {}
    for f in ship_fields:
        vals = [sp for (ff, _), sp in xr_by_vt.items() if ff == f]
        if len(vals) < 200:
            print(f"  ⚠ {f}: only {len(vals)} xr samples; skipping")
            continue
        xr_edges_by_field[f] = quintile_edges(sorted(vals))

    per_cell = defaultdict(dict)
    pass_list = []
    fail_list = []
    thin_list = []
    print()
    print(f"{'field':<5} {'band':<7} {'verdict':<15}  {'xr_Q1':<28}  {'xr_Q5':<28}")
    print("-" * 96)
    for (field, band), _entry in sorted(ships.items()):
        edges = xr_edges_by_field.get(field)
        if edges is None:
            per_cell[field][band] = {"status": "THIN_XR_SAMPLES"}
            thin_list.append(f"{field}/{band}")
            print(f"{field:<5} {band:<7} {'THIN_XR':<15}  —")
            continue
        rows = rows_by_cell.get((field, band), [])
        verdict = analyze_cell(field, band, rows, xr_by_vt, edges, cutoff_dt)
        per_cell[field][band] = verdict
        st = verdict["status"]
        cell_id = f"{field}/{band}"
        if st == "PASS":
            pass_list.append(cell_id)
        elif st in ("REDUNDANT", "MIXED_REDUND"):
            fail_list.append(cell_id)
        else:
            thin_list.append(cell_id)

        def fmt_level(lv):
            if lv["status"] == "THIN":
                return f"{lv['status']} n1={lv['n_ims_q1']} n4={lv['n_ims_q4']}"
            return f"{lv['status']} ratio={lv['ratio']} n={lv['n_ims_q1']}/{lv['n_ims_q4']}"
        lo = fmt_level(verdict.get("xr_Q1", {"status": "?"}))
        hi = fmt_level(verdict.get("xr_Q5", {"status": "?"}))
        print(f"{field:<5} {band:<7} {st:<15}  {lo:<28}  {hi:<28}")

    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": "h_inter_model_spread_vs_xr_q_ortho.py",
        "window_days": WINDOW_DAYS,
        "ortho_gate": ORTHO_GATE,
        "redundant_ceiling": REDUNDANT_CEILING,
        "min_n_per_quadrant": MIN_N_PER_QUADRANT,
        "n_ship_cells_input": len(ships),
        "xr_edges_by_field": {f: [round(e, 4) for e in edges]
                              for f, edges in xr_edges_by_field.items()},
        "ortho_gate_pass": pass_list,
        "ortho_gate_fail": fail_list,
        "thin_or_missing": thin_list,
        "per_cell": per_cell,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as w:
        json.dump(result, w, indent=2)

    print()
    print("=" * 96)
    print(f"Totals: PASS {len(pass_list)}  FAIL_REDUND {len(fail_list)}  "
          f"THIN {len(thin_list)}   (of {len(ships)} SHIP cells)")
    if pass_list:
        print(f"VERDICT: STAGE 1.5 PROMOTE — {len(pass_list)} cell(s) survive xr_q conditioning:")
        for c in pass_list:
            print(f"    {c}")
        print("Curator gates axis_6 SHIP verdicts to these cells only. "
              "Repeat this run daily; wire only after a 7-day stability gate.")
    else:
        print("VERDICT: HOLD — no ims axis cell survived xr_q conditioning. "
              "ims signal is already captured by xr_q; do not wire axis_6.")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()

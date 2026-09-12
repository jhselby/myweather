"""Stage 2 — Inter-model spread C1 axis preview.

Candidate: inter_model_spread = |forecast_l1 − forecast_raw_nbm| per row.
Stage 0 (v0.6.593): PROMOTE 35 of 36 (field, band) cells.
Stage 1 (v0.6.594): ORTHOGONAL vs C1a (33/36), cluster (36/36), pt_mag (34/36).

This Stage 2 produces the per-cell curated table that would seed
c1_confidence_calibration_v2.py's `by_axes` for a future axis_6 wiring.
Analysis-only preview — no runtime change.

Method:
  1. Load pair log, join |forecast_l1 − forecast_raw_nbm| per row.
  2. Per (field, band), compute quartile thresholds on inter_model_spread.
  3. Per (field, band, quartile), compute:
     - MAE (test window: last TEST_DAYS days)
     - n
     - Chronological halves-stability (both halves have same Q4/Q1 ratio direction)
  4. Compute the C1 "premium" = MAE(Q4) − MAE(Q1) / MAE(Q1) — the widening
     factor a confidence layer would apply for a Q4 row vs a Q1 row.
  5. Per-cell verdict:
       SHIP     — |premium| ≥ MIN_PREMIUM_SHIP, n_low+n_high ≥ MIN_N_SHIP, halves-stable
       MARGINAL — |premium| ≥ MIN_PREMIUM_MARGIN OR n below SHIP floor but above MARGIN floor
       SKIP     — |premium| < magnitude threshold OR halves unstable
       THIN     — n below MARGIN floor

Output: analysis/output/h_inter_model_spread_c1_stage2.json (preview shape
compatible with the by_axes sub-table in c1_confidence_premium_v2.json).

If ≥3 SHIP cells clear a 7-day gate, wire axis_6 = inter_model_spread_q4
in c1_confidence_calibration_v2.py.
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS   = ("t", "h", "ws", "wg", "wd", "cc", "cl", "cm", "ch", "dp", "sr")
BANDS    = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
TEST_DAYS = 14
MIN_N_SHIP     = 500     # n_Q1 + n_Q4 combined
MIN_N_MARGIN   = 200
MIN_PREMIUM_SHIP    = 30.0  # percent — Q4 MAE at least 30% higher than Q1
MIN_PREMIUM_MARGIN  = 15.0
OUT_PATH = os.path.join(os.path.dirname(__file__), "output", "h_inter_model_spread_c1_stage2.json")

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

print("Loading pair log...")
rows_by_cell = defaultdict(list)  # (field, band) -> list of (obs_dt, spread, err)
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
        try:
            odt = datetime.fromisoformat((r.get("obs_time") or "")[:19])
        except Exception:
            continue
        spread = signed_delta(f, float(f_h), float(f_n))
        rows_by_cell[(f, band)].append((odt, spread, abs(float(err))))

# TEST window filter — use last TEST_DAYS days by obs_time
all_times = [t for rows in rows_by_cell.values() for t, _, _ in rows]
if not all_times:
    print("VERDICT: THIN — no data")
    sys.exit(0)
max_time = max(all_times)
test_cutoff = max_time - timedelta(days=TEST_DAYS)
print(f"  test window: {test_cutoff} → {max_time} ({TEST_DAYS} days)\n")

# Per-cell computation
print(f"{'field':<5} {'band':<7} {'n_Q1':>6} {'n_Q4':>6} {'MAE_Q1':>8} {'MAE_Q4':>8} {'prem%':>8} {'halves':>10}  verdict")
print("-" * 92)

output = {"generated_at": datetime.utcnow().isoformat() + "Z",
          "source": "h_inter_model_spread_c1_stage2.py",
          "test_window_days": TEST_DAYS,
          "min_premium_ship_pct": MIN_PREMIUM_SHIP,
          "cells": {}}
verdict_count = defaultdict(int)

for f in FIELDS:
    for label, _, _ in BANDS:
        rows = [(t, s, e) for t, s, e in rows_by_cell.get((f, label), []) if t >= test_cutoff]
        if len(rows) < 4 * MIN_N_MARGIN // 2:
            output["cells"].setdefault(f, {})[label] = {"verdict": "THIN", "n": len(rows)}
            verdict_count["THIN"] += 1
            continue
        spreads = sorted(x[1] for x in rows)
        n = len(spreads)
        q1_thresh = spreads[n // 4]
        q4_thresh = spreads[3 * n // 4]
        q1_rows = [(t, e) for t, s, e in rows if s <= q1_thresh]
        q4_rows = [(t, e) for t, s, e in rows if s >= q4_thresh]
        if not q1_rows or not q4_rows:
            continue
        mae_q1 = sum(e for _, e in q1_rows) / len(q1_rows)
        mae_q4 = sum(e for _, e in q4_rows) / len(q4_rows)
        if mae_q1 == 0:
            continue
        premium = (mae_q4 - mae_q1) / mae_q1 * 100
        # Halves check — chronological median of the (q1+q4) union
        union = sorted(q1_rows + q4_rows, key=lambda x: x[0])
        median_dt = union[len(union) // 2][0]
        def half_stats(sub, cutoff, before):
            if before:
                arr = [e for t, e in sub if t <= cutoff]
            else:
                arr = [e for t, e in sub if t > cutoff]
            if not arr: return None
            return sum(arr) / len(arr), len(arr)
        h1_q1 = half_stats(q1_rows, median_dt, True)
        h1_q4 = half_stats(q4_rows, median_dt, True)
        h2_q1 = half_stats(q1_rows, median_dt, False)
        h2_q4 = half_stats(q4_rows, median_dt, False)
        if not all([h1_q1, h1_q4, h2_q1, h2_q4]):
            halves_stable = False
            halves_tag = "n/a"
        else:
            r1 = (h1_q4[0] / h1_q1[0]) if h1_q1[0] > 0 else 0
            r2 = (h2_q4[0] / h2_q1[0]) if h2_q1[0] > 0 else 0
            halves_stable = (r1 >= 1.15 and r2 >= 1.15)
            halves_tag = f"{r1:.2f}/{r2:.2f}"
        n_combined = len(q1_rows) + len(q4_rows)
        if premium >= MIN_PREMIUM_SHIP and n_combined >= MIN_N_SHIP and halves_stable:
            verdict = "SHIP"
        elif premium >= MIN_PREMIUM_MARGIN and n_combined >= MIN_N_MARGIN and halves_stable:
            verdict = "MARGINAL"
        elif n_combined < MIN_N_MARGIN:
            verdict = "THIN"
        elif not halves_stable and premium >= MIN_PREMIUM_MARGIN:
            verdict = "UNSTABLE"
        else:
            verdict = "SKIP"
        verdict_count[verdict] += 1
        output["cells"].setdefault(f, {})[label] = {
            "verdict": verdict,
            "n_q1": len(q1_rows),
            "n_q4": len(q4_rows),
            "mae_q1": round(mae_q1, 4),
            "mae_q4": round(mae_q4, 4),
            "premium_pct": round(premium, 2),
            "halves_stable": halves_stable,
            "halves_tag": halves_tag,
            "q1_threshold": round(q1_thresh, 4),
            "q4_threshold": round(q4_thresh, 4),
        }
        print(f"{f:<5} {label:<7} {len(q1_rows):>6,} {len(q4_rows):>6,} {mae_q1:>8.3f} {mae_q4:>8.3f} {premium:>7.1f}% {halves_tag:>10}  {verdict}")
    print()

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, "w") as w:
    json.dump(output, w, indent=2)
print(f"wrote {OUT_PATH}")

print("=" * 92)
total_judged = sum(v for k, v in verdict_count.items() if k != "THIN")
print(f"Totals: SHIP {verdict_count['SHIP']} / MARGINAL {verdict_count['MARGINAL']} / "
      f"SKIP {verdict_count['SKIP']} / UNSTABLE {verdict_count['UNSTABLE']} / THIN {verdict_count['THIN']}")
if verdict_count["SHIP"] >= 3:
    print(f"VERDICT: STAGE 2 PROMOTE — {verdict_count['SHIP']} cells clear |premium| ≥ {MIN_PREMIUM_SHIP}% halves-stable. Advance to 7-day gate.")
elif verdict_count["SHIP"] + verdict_count["MARGINAL"] >= 3:
    print(f"VERDICT: STAGE 2 MARGINAL — {verdict_count['SHIP']} SHIP + {verdict_count['MARGINAL']} MARGINAL. Watch across 7d.")
else:
    print(f"VERDICT: HOLD — insufficient SHIP cells. Re-run with fresh test window.")

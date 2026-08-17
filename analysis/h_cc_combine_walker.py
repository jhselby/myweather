#!/usr/bin/env python3
"""Stage 0/1: dynamic per-cell combine-formula gate for Ccd.

Design intent [[project_cc_combine_walker]]: retire the hardcoded
`FORMULA = "max"` in cc_from_derivation.py by building a self-healing
per-(regime × lead-band) gate that picks the combine formula empirically
each day and holds on a 7-day stability rule.

Sibling design to [[project_chp_cell_skip_to_dynamic_gate]] (chp gate),
[[project_lc_regime_conditional]] (Lc gate), and [[project_lsr_recent_bias_gate]]
(Lsr gate), adapted for Ccd's shape: cc is a derived field with 3 candidate
combines, so the gate decision is "which formula wins this cell?" rather
than "apply/skip".

Source of truth: the pair log itself (all history in one place). We do a
fresh per-day recompute each run — no history cache needed — matching
[[feedback_fresh_per_day_recompute]]. Per (obs_day, regime, band) we compute
MAE for {prod, max, random}. Per cell (regime, band) the 7-day rule selects
a winning formula only if it strictly beats the current default `max` on
every seen day in the window AND at least MIN_DAYS_IN_WINDOW days have
n >= MIN_N_CELL_DAY.

Formulas evaluated:
  * max:    max(cl_l6, cm_l6, ch_l6) — Ccd's current hardcoded choice
  * random: 100 * (1 - Π(1 - x/100))
  * prod:   passthrough (what the collector actually served — used as fallback
            when both derivations lose to Pirate cc + Lc)

Emits:
  weather_collector/data/cc_combine_gate.json (runtime table for Stage 3)
  analysis/output/h_cc_combine_walker.txt (human-readable report)

Runtime consumer (Stage 3, not shipped by this script):
  cc_from_derivation.py adds CC_COMBINE_GATE_ENABLED flag + _load_gate() and
  per-lead formula selection inside _derive() — when ENABLED and
  per_cell[regime][band].formula is set, use it in place of the module-level
  FORMULA default.

Run:
    python3 -m analysis.h_cc_combine_walker
    python3 -m analysis.h_cc_combine_walker --min-obs-date 2026-07-01
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
REPO = Path(__file__).resolve().parent.parent
RUNTIME_TABLE_PATH = REPO / "weather_collector" / "data" / "cc_combine_gate.json"
OUT_TXT = Path(__file__).resolve().parent / "output" / "h_cc_combine_walker.txt"

CLOUD_FIELDS = {"cc", "cl", "cm", "ch"}
LEAD_BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]

GATE_WINDOW_DAYS = 7
MIN_N_CELL_DAY = 30      # a cell-day counts as "seen" only if n >= this
MIN_DAYS_IN_WINDOW = 7   # gate flips only if all 7 seen days agree
FORMULA_DEFAULT = "max"  # matches Ccd's FORMULA constant


def band_of(lead):
    for lab, lo, hi in LEAD_BANDS:
        if lo <= lead < hi:
            return lab
    return None


def deepest_available(r):
    for k in ("forecast_l6", "forecast_l4", "forecast_l3", "forecast_l2", "forecast_l1"):
        v = r.get(k)
        if v is not None:
            return float(v)
    return None


def clip(v):
    return max(0.0, min(100.0, v))


def derive_max(cl, cm, ch):
    return clip(max(cl, cm, ch))


def derive_random(cl, cm, ch):
    a = 1.0 - cl / 100.0
    b = 1.0 - cm / 100.0
    c = 1.0 - ch / 100.0
    return clip(100.0 * (1.0 - a * b * c))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-obs-date", default="2026-07-01")
    args = ap.parse_args()

    # Read pair log, group by (run_time, lead_h) → {field: row}
    groups = defaultdict(dict)
    print(f"reading {URL}")
    with open(cached_path(URL), "rb") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            f = r.get("field")
            if f not in CLOUD_FIELDS:
                continue
            obs_t = r.get("obs_time", "")
            if obs_t < args.min_obs_date:
                continue
            key = (r.get("run_time"), r.get("lead_h"))
            if key[0] is None or key[1] is None:
                continue
            groups[key][f] = r

    # Aggregate MAE per (day, regime, band, formula)
    # cell key = (day, regime, band); value = {'n', 'prod', 'max', 'random'}
    def new_agg():
        return {"n": 0, "prod": 0.0, "max": 0.0, "random": 0.0}
    per_day_cell = defaultdict(new_agg)

    complete = 0
    for (run_time, lead_h), fields in groups.items():
        if not (CLOUD_FIELDS <= set(fields.keys())):
            continue
        cc_row = fields["cc"]
        cl_row, cm_row, ch_row = fields["cl"], fields["cm"], fields["ch"]
        cc_obs = cc_row.get("observed")
        if cc_obs is None:
            continue
        prod_cc = deepest_available(cc_row)
        cl_c = deepest_available(cl_row)
        cm_c = deepest_available(cm_row)
        ch_c = deepest_available(ch_row)
        if None in (prod_cc, cl_c, cm_c, ch_c):
            continue

        d_max = derive_max(cl_c, cm_c, ch_c)
        d_rand = derive_random(cl_c, cm_c, ch_c)

        band = band_of(int(lead_h))
        regime = ((cc_row.get("state_fc") or {}).get("regime_synoptic")) or "unknown"
        day = (cc_row.get("obs_time") or "")[:10]
        if not day or not band:
            continue

        agg = per_day_cell[(day, regime, band)]
        agg["n"] += 1
        agg["prod"] += abs(prod_cc - cc_obs)
        agg["max"] += abs(d_max - cc_obs)
        agg["random"] += abs(d_rand - cc_obs)
        complete += 1

    print(f"  complete cc/cl/cm/ch quads with obs: {complete:,}")

    # Compute per-cell winner per day
    # per_cell_history[(regime, band)] = list of {'day', 'n', 'winner', 'maes': {...}}
    per_cell_history = defaultdict(list)
    all_days = sorted({d for (d, _, _) in per_day_cell.keys()})
    for (day, regime, band), agg in per_day_cell.items():
        if agg["n"] < MIN_N_CELL_DAY:
            continue
        maes = {k: agg[k] / agg["n"] for k in ("prod", "max", "random")}
        winner = min(maes, key=maes.get)
        per_cell_history[(regime, band)].append({
            "day": day,
            "n": agg["n"],
            "winner": winner,
            "maes": maes,
        })

    # Sort each cell's history chronologically
    for k in per_cell_history:
        per_cell_history[k].sort(key=lambda e: e["day"])

    # 7-day gate rule per cell:
    # window = last GATE_WINDOW_DAYS distinct seen days (already n >= MIN_N_CELL_DAY)
    # * if a non-default formula wins on ALL 7 days AND wins vs `max` by >= 1% on
    #   every day → gate applies that formula
    # * else → hold default (max)
    per_cell_runtime = defaultdict(dict)
    per_cell_report = []
    n_flipped = 0
    n_cells = 0
    for (regime, band), history in sorted(per_cell_history.items()):
        n_cells += 1
        window = history[-GATE_WINDOW_DAYS:]
        n_seen = len(window)
        winners = [e["winner"] for e in window]
        n_win_random = winners.count("random")
        n_win_max = winners.count("max")
        n_win_prod = winners.count("prod")

        # Strict rule: unanimous non-default across the full window
        cleared_formula = None
        margin_ok = False
        if n_seen >= MIN_DAYS_IN_WINDOW:
            for candidate in ("random", "prod"):
                if winners.count(candidate) == n_seen:
                    # require candidate to beat `max` by >= 1% MAE on every day
                    if all(
                        e["maes"][candidate] < e["maes"]["max"]
                        and (e["maes"]["max"] - e["maes"][candidate]) / max(1e-6, e["maes"]["max"]) >= 0.01
                        for e in window
                    ):
                        cleared_formula = candidate
                        margin_ok = True
                        break

        formula = cleared_formula or FORMULA_DEFAULT
        cleared = cleared_formula is not None

        # Today snapshot
        today = window[-1] if window else None
        per_cell_runtime[regime][band] = {
            "formula": formula,
            "cleared": bool(cleared),
            "days_seen": n_seen,
            "days_random_wins": n_win_random,
            "days_max_wins": n_win_max,
            "days_prod_wins": n_win_prod,
            "today_day": today["day"] if today else None,
            "today_n": today["n"] if today else None,
            "today_maes": today["maes"] if today else None,
            "today_winner": today["winner"] if today else None,
        }
        if cleared:
            n_flipped += 1
        per_cell_report.append({
            "regime": regime, "band": band, "series": winners,
            "n_seen": n_seen, "cleared": cleared, "formula": formula,
            "today": today,
        })

    # Report
    out = []
    def p(*a):
        line = " ".join(str(x) for x in a)
        print(line); out.append(line)

    today_str = all_days[-1] if all_days else "n/a"
    p("=" * 100)
    p(f"cc combine walker — today={today_str}")
    p(f"window: {GATE_WINDOW_DAYS}d  min-n-per-cell-day: {MIN_N_CELL_DAY}  "
      f"default formula: {FORMULA_DEFAULT}")
    p(f"days present: {len(all_days)}  cells with any history: {n_cells}  cells cleared: {n_flipped}")
    p(f"rule: non-default formula must win on ALL {MIN_DAYS_IN_WINDOW} days by ≥1% MAE vs max")
    p("=" * 100)

    header = (f"{'regime':<12} {'band':<7} {'series':<9} {'seen':>5} "
              f"{'R':>3} {'M':>3} {'P':>3} {'today prod':>11} {'max':>7} {'rand':>7}  formula")
    p(header)
    p("-" * len(header))
    series_map = {"random": "R", "max": "M", "prod": "P"}
    for row in sorted(per_cell_report, key=lambda x: (x["regime"], x["band"])):
        series_str = "".join(series_map.get(s, ".") for s in row["series"])
        maes = (row["today"] or {}).get("maes") or {}
        n_win_r = row["series"].count("random")
        n_win_m = row["series"].count("max")
        n_win_p = row["series"].count("prod")
        prod_s = f"{maes.get('prod', 0):>10.2f}" if maes else "       n/a"
        max_s  = f"{maes.get('max', 0):>7.2f}"  if maes else "    n/a"
        rand_s = f"{maes.get('random', 0):>7.2f}" if maes else "    n/a"
        marker = "→" if row["cleared"] else " "
        p(f"{row['regime']:<12} {row['band']:<7} {series_str:<9} {row['n_seen']:>5} "
          f"{n_win_r:>3} {n_win_m:>3} {n_win_p:>3} {prod_s} {max_s} {rand_s}  {marker}{row['formula']}")

    p()
    p("=" * 100)
    p("STAGE 0/1 VERDICT:")
    p("=" * 100)
    if n_cells == 0:
        v = "NULL — no cell has enough per-day sample yet."
    elif n_flipped == 0:
        v = (f"HOLD — no cell cleared the {GATE_WINDOW_DAYS}-day unanimous+margin gate today. "
             f"Walker will re-check daily.")
    else:
        v = (f"STAGE 1 PROMOTE — {n_flipped}/{n_cells} cell(s) cleared. "
             f"Ready for Stage 3 wire in cc_from_derivation.py (ship OFF, then flip).")
    p(f"  {v}")

    # Runtime table
    runtime = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "h_cc_combine_walker.py",
        "min_obs_date": args.min_obs_date,
        "gate_window_days": GATE_WINDOW_DAYS,
        "min_n_cell_day": MIN_N_CELL_DAY,
        "min_days_in_window": MIN_DAYS_IN_WINDOW,
        "default_formula": FORMULA_DEFAULT,
        "n_cells_total": n_cells,
        "n_cells_cleared": n_flipped,
        "days_present": len(all_days),
        "latest_day": today_str,
        "per_cell": {r: dict(bands) for r, bands in per_cell_runtime.items()},
        "notes": (
            "Stage 3 wire contract: when CC_COMBINE_GATE_ENABLED=True in "
            "cc_from_derivation.py, use per_cell[regime][band].formula in "
            "place of the module-level FORMULA default. Values: 'max' (Ccd's "
            "current hardcoded), 'random' (probabilistic overlap), 'prod' "
            "(passthrough — keep Pirate cc, skip derivation for this cell). "
            "When ENABLED=False, table is emitted for gate accounting only."
        ),
    }
    RUNTIME_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_TABLE_PATH.write_text(json.dumps(runtime, indent=2))
    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(out) + "\n")
    print(f"\nwrote {RUNTIME_TABLE_PATH}")
    print(f"wrote {OUT_TXT}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""L1 selector table fit (option-1 Phase 4, rewritten 2026-08-19).

Selector picks between HRRR-side cascade and NBM-side cascade per
(field, lead-band). This fit compares **fully-corrected Prod outputs**
per source — not raw source MAE — so the selector honestly picks the
cascade that delivers the lower MAE, accounting for HRRR-side depth
(Lc/chp/L3/L4/etc.) vs the shallower NBM-side stack (raw → l2_nbm →
l3_nbm today; more layers as we build NBM-side specialists).

Bug this fixes (v0.6.436 shipped raw-vs-raw): for fields like ch with
deep HRRR-side cascade (Lc + chp bring MAE 29.3 → 11.5), the raw
comparison said "NBM raw 19.4 < HRRR raw 29.3, pick NBM", which would
overwrite user-visible ch with l3_nbm (~19.4) and lose the 8-MAE-point
gain from HRRR-side corrections. Prod-per-source comparison picks HRRR
correctly: HRRR Prod 11.5 < NBM Prod 19.4.

Method:
  For each pair-log row within the window, per field:
    HRRR-Prod error = row["error_{deepest_hrrr_layer}"]  (walks
      specialists → decay layers → raw in priority order)
    NBM-Prod error  = row["error_l3_nbm"]  (Phase 3 stamp; identity to
      l2_nbm until per-lead bins warm up)
  Accumulate abs errors per (field, band). Compute MAE per side.
  Pick the source with lower MAE, subject to threshold gates:
    NBM iff n ≥ MIN_N AND lift_pct ≥ MIN_LIFT_PCT.
  Fall through to HRRR otherwise.

Writes weather_collector/data/l1_selector_table_curated.json with
per-(field, band) cell: {source, hrrr_prod_mae, nbm_prod_mae, lift_pct,
n}. Consumed by weather_collector/processors/l1_selector.py at collector
runtime.

Runtime:
    python3 -m analysis.l1_selector_fit
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import pair_log_paths

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"  # kept for compat; see pair_log_paths()
OUT_PATH = Path(__file__).resolve().parent.parent / "weather_collector" / "data" / "l1_selector_table_curated.json"

FIELDS = ("t", "ws", "wg", "wd", "h", "ch", "sr", "dp", "cc")
BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]
WINDOW_DAYS = 30
MIN_N = 200
MIN_LIFT_PCT = 3.0

# HRRR-side layer priority per field — deepest applied layer wins. Same
# shape as the debug page's _prodKey walker. Specialists first (dpbp,
# wdp, chp, clp), then decay layers (l6 Lc, l5 Lsr, l4 diurnal, l3
# lead-decay, l2 station-blend), then raw (l1).
HRRR_LAYER_PRIORITY_BY_FIELD = {
    "t":   ["l6", "l4", "l3", "l2", "l1"],
    "ws":  ["wsbp", "l4", "l3", "l2", "l1"],
    "wg":  ["l4", "l3", "l2", "l1"],
    "wd":  ["wdp", "l4", "l3", "l2", "l1"],
    "h":   ["l4", "l3", "l2", "l1"],
    "ch":  ["chp", "l6", "l4", "l3", "l2", "l1"],
    "cm":  ["l6", "l4", "l3", "l2", "l1"],
    "cl":  ["clp", "l6", "l4", "l3", "l2", "l1"],
    "cc":  ["l6", "l4", "l3", "l2", "l1"],
    "sr":  ["l5", "l1"],
    "dp":  ["dpbp", "l3", "l2", "l1"],
    "pa":  ["l1"],
    "pr":  ["l2", "l1"],
    "pp":  ["l1"],
}


def _band_for(lead_h):
    if lead_h is None:
        return None
    if lead_h < 6:  return "0-5"
    if lead_h < 12: return "6-11"
    if lead_h < 24: return "12-23"
    if lead_h < 48: return "24-47"
    return None


def _hrrr_prod_error(row, field):
    """Deepest applied HRRR-side layer's error for this row. Returns abs
    error, or None if no HRRR-side layer stamped."""
    for lyr in HRRR_LAYER_PRIORITY_BY_FIELD.get(field, ["l1"]):
        e = row.get(f"error_{lyr}")
        if e is not None:
            return abs(float(e))
    return None


def _nbm_prod_error(row):
    """Deepest NBM-side layer's error. Preference order (deepest first):
    error_l6_nbm (t) > error_l5_nbm (sr) > error_l4_nbm (cc/ch) >
    error_l3_nbm > (identity to l2_nbm until l3_nbm per-lead bins warm
    up). This is the NBM-side output the selector-substitution would
    deliver."""
    for k in ("error_l6_nbm", "error_l5_nbm", "error_l4_nbm", "error_l3_nbm"):
        e = row.get(k)
        if e is not None:
            return abs(float(e))
    return None


def fit():
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    window_start = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M")

    # Accumulator: {(field, band): {"hrrr_abs": Σ, "hrrr_n": N,
    #                                "nbm_abs": Σ, "nbm_n": N,
    #                                "paired_n": N (rows with both sides)}}
    acc = defaultdict(lambda: {"hrrr_abs": 0.0, "hrrr_n": 0,
                                "nbm_abs":  0.0, "nbm_n":  0,
                                "paired_n": 0})

    n_in = 0
    n_kept = 0
    for path in pair_log_paths():
        with open(path) as fin:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                n_in += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                field = row.get("field")
                if field not in FIELDS:
                    continue
                lead_h = row.get("lead_h")
                band = _band_for(lead_h)
                if band is None:
                    continue
                obs_time = row.get("obs_time", "")
                if obs_time < window_start:
                    continue
                n_kept += 1
                h = _hrrr_prod_error(row, field)
                n = _nbm_prod_error(row)
                key = (field, band)
                if h is not None:
                    acc[key]["hrrr_abs"] += h
                    acc[key]["hrrr_n"]   += 1
                if n is not None:
                    acc[key]["nbm_abs"] += n
                    acc[key]["nbm_n"]   += 1
                if h is not None and n is not None:
                    acc[key]["paired_n"] += 1

    # Emit per-(field, band) picks + shape the payload the runtime + fit-
    # status tile consume.
    table = {}
    router_nbm_lift_sum = 0.0
    router_hrrr_mae_sum = 0.0
    router_paired_n = 0
    ROUTER_FIELDS = {"t", "ws", "wd"}
    for field in FIELDS:
        cells = {}
        for band, lo, _ in BANDS:
            b = acc.get((field, band)) or {}
            paired = b.get("paired_n", 0)
            hrrr_n = b.get("hrrr_n", 0)
            nbm_n = b.get("nbm_n", 0)
            hrrr_mae = (b["hrrr_abs"] / hrrr_n) if hrrr_n else None
            nbm_mae  = (b["nbm_abs"]  / nbm_n)  if nbm_n  else None
            # Lift = HRRR-side MAE minus NBM-side MAE, as % of HRRR-side.
            # Positive = NBM Prod better; negative = HRRR Prod better.
            lift_pct = None
            if hrrr_mae is not None and nbm_mae is not None and hrrr_mae > 0:
                lift_pct = 100.0 * (hrrr_mae - nbm_mae) / hrrr_mae
            # Pick: NBM iff paired n ≥ MIN_N AND lift ≥ MIN_LIFT_PCT.
            # HRRR fall-through everywhere else (safe: equals current Prod).
            if (nbm_mae is not None and paired >= MIN_N
                    and lift_pct is not None and lift_pct >= MIN_LIFT_PCT):
                source = "nbm"
            else:
                source = "hrrr"
            cells[band] = {
                "source":        source,
                "hrrr_prod_mae": round(hrrr_mae, 3) if hrrr_mae is not None else None,
                "nbm_prod_mae":  round(nbm_mae,  3) if nbm_mae  is not None else None,
                "lift_pct":      round(lift_pct, 2) if lift_pct is not None else None,
                "n":             paired,
                "hrrr_n":        hrrr_n,
                "nbm_n":         nbm_n,
            }
            # Ship-gate aggregation across router-scope cells (t/ws/wd @
            # leads ≥6h) — matches v0.6.432 router's scope so we can prove
            # ≥90% of its lift is delivered.
            if field in ROUTER_FIELDS and lo >= 6 and hrrr_mae is not None and nbm_mae is not None:
                router_hrrr_mae_sum += b["hrrr_abs"]
                router_nbm_lift_sum += (b["hrrr_abs"] - b["nbm_abs"])
                router_paired_n += paired
        table[field] = cells

    selector_router_lift_pct = (
        100.0 * router_nbm_lift_sum / router_hrrr_mae_sum
        if router_hrrr_mae_sum > 0 else 0.0
    )

    output = {
        "fitted_at": now.strftime("%Y-%m-%dT%H:%M"),
        "window_days": WINDOW_DAYS,
        "min_n": MIN_N,
        "min_lift_pct": MIN_LIFT_PCT,
        "n_rows_scanned": n_in,
        "n_rows_kept":    n_kept,
        "compare_shape": "hrrr_prod_vs_nbm_prod",
        "hrrr_layer_priority_by_field": HRRR_LAYER_PRIORITY_BY_FIELD,
        "table": table,
        "ship_gate_router_scope": {
            "fields": sorted(list(ROUTER_FIELDS)),
            "leads": ">=6h",
            "aggregate_nbm_lift_pct": round(selector_router_lift_pct, 2),
            "aggregate_n": router_paired_n,
            "note": "Post-cascade NBM lift on the cells v0.6.432 router covered. Phase 4 ship gate: selector delivers ≥90% of router's live lift on t/ws/wd @ leads ≥6h.",
        },
        "notes": (
            "Selector compares fully-corrected Prod per source: HRRR-side deepest "
            "applied layer's error vs NBM-side error_l3_nbm. Picks NBM iff paired "
            "n ≥ min_n AND lift ≥ min_lift_pct; HRRR fall-through otherwise. Runtime "
            "l1_selector.pick_source(field, lead_h) reads this table; when 'nbm', "
            "forecast_snapshot replaces user-visible {field} with {field}_l3_nbm."
        ),
    }
    with open(OUT_PATH, "w") as fout:
        json.dump(output, fout, indent=2)
        fout.write("\n")

    print("\n" + "=" * 78)
    print(f"L1 selector table — window {WINDOW_DAYS}d · fitted_at {output['fitted_at']}")
    print(f"Compare: HRRR deepest-applied-layer Prod vs NBM l3_nbm Prod")
    print("=" * 78)
    print(f"{'field':<6} {'band':<8} {'pick':<6} {'HRRR Prod':>10} {'NBM Prod':>10} {'lift':>8} {'n':>8}")
    print("-" * 78)
    for field in FIELDS:
        for band, _, _ in BANDS:
            c = table[field].get(band) or {}
            hmae = c.get("hrrr_prod_mae")
            nmae = c.get("nbm_prod_mae")
            lft = c.get("lift_pct")
            print(f"{field:<6} {band:<8} {c.get('source','?'):<6} "
                  f"{(f'{hmae:.2f}' if hmae is not None else '—'):>10} "
                  f"{(f'{nmae:.2f}' if nmae is not None else '—'):>10} "
                  f"{(f'{lft:+.1f}%' if lft is not None else '—'):>8} "
                  f"{c.get('n',0):>8,}")
    print("=" * 78)
    print(f"Ship gate (router-scope): selector NBM lift = {selector_router_lift_pct:+.1f}% on n={router_paired_n:,}")
    print(f"  wrote {OUT_PATH}")


if __name__ == "__main__":
    fit()

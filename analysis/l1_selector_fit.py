#!/usr/bin/env python3
"""L1 selector table fit (option-1 Phase 4, 2026-08-19).

Produces `weather_collector/data/l1_selector_table_curated.json` — per
(field, lead-band), which source's L3-stack output should become the
user-facing forecast:

    {
      "fitted_at": "...", "window_days": 30, "min_n": 200, "min_lift_pct": 3.0,
      "table": {
        "t":  {"0-5": {"source": "hrrr", "hrrr_mae": 1.19, "nbm_mae": 1.35,
                       "lift_pct": -13.7, "n": 1140},
               "6-11": {"source": "nbm", ...}, ...},
        "ws": {...}, "wg": {...}, "wd": {...}, "h": {...}
      },
      "notes": "..."
    }

Scope = fields with L3_NBM stack: t / ws / wg / wd / h. Selector picks
NBM only when lift ≥ MIN_LIFT_PCT AND n ≥ MIN_N; else HRRR fall-through
(identity to current Prod stack). `wd` MAE via circular abs diff.

Method reuses `nbm_backfill_scoreboard.aggregate()` — same 30-day
backfill + pair-log join. Pair log's `error_l3_nbm` will supersede
raw-NBM-from-backfill as the primary signal once bins fill (currently
identity fall-through, so raw-NBM MAE ≈ l3_nbm MAE modulo the L2
station-bias delta). Refitting nightly will incorporate the pair-log
signal as it accumulates.

Ship-gate check (printed): for `t/ws/wd` at leads ≥6h, aggregate NBM
lift vs the v0.6.432 L1 router's live scope. If selector's lift on
those cells is ≥90% of the router's measured lift, the selector delivers
router-equivalent value and Phase 4 can arm. Otherwise flag before
deploy.

Runtime:
    python3 -m analysis.l1_selector_fit
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis.nbm_backfill_scoreboard import aggregate, BANDS, ROUTER_FIELDS

OUT_PATH = Path(__file__).resolve().parent.parent / "weather_collector" / "data" / "l1_selector_table_curated.json"

FIELDS = ("t", "ws", "wg", "wd", "h")  # fields with L3_NBM coverage
MIN_N = 200
MIN_LIFT_PCT = 3.0
WINDOW_DAYS = 30


def fit():
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    acc, matched, unmatched = aggregate(WINDOW_DAYS)
    print(f"\n  matched {matched:,} triplets; unmatched {unmatched:,}",
          file=sys.stderr)

    table = {}
    router_scope_nbm_lift_sum = 0.0
    router_scope_hrrr_mae_sum = 0.0
    router_scope_n_sum = 0
    for f in FIELDS:
        cells = {}
        for band, lo, _ in BANDS:
            b = acc.get((f, band))
            if not b or b["n"] < 1:
                continue
            hrrr_mae = b["hrrr_abs"] / b["n"]
            nbm_mae = b["nbm_abs"] / b["n"]
            lift_pct = 100.0 * (hrrr_mae - nbm_mae) / hrrr_mae if hrrr_mae > 0 else 0.0
            if b["n"] < MIN_N or abs(lift_pct) < MIN_LIFT_PCT:
                source = "hrrr"
            else:
                source = "nbm" if lift_pct > 0 else "hrrr"
            cells[band] = {
                "source": source,
                "hrrr_mae": round(hrrr_mae, 3),
                "nbm_mae": round(nbm_mae, 3),
                "lift_pct": round(lift_pct, 2),
                "n": b["n"],
            }
            # Ship-gate aggregation: router covers t/ws/wd @ leads ≥6h.
            if f in ROUTER_FIELDS and lo >= 6:
                router_scope_hrrr_mae_sum += b["hrrr_abs"]
                router_scope_nbm_lift_sum += (b["hrrr_abs"] - b["nbm_abs"])
                router_scope_n_sum += b["n"]
        table[f] = cells

    selector_router_lift_pct = (
        100.0 * router_scope_nbm_lift_sum / router_scope_hrrr_mae_sum
        if router_scope_hrrr_mae_sum > 0 else 0.0
    )

    output = {
        "fitted_at": now.strftime("%Y-%m-%dT%H:%M"),
        "window_days": WINDOW_DAYS,
        "min_n": MIN_N,
        "min_lift_pct": MIN_LIFT_PCT,
        "matched_triplets": matched,
        "table": table,
        "ship_gate_router_scope": {
            "fields": sorted(list(ROUTER_FIELDS)),
            "leads": ">=6h",
            "aggregate_nbm_lift_pct": round(selector_router_lift_pct, 2),
            "aggregate_n": router_scope_n_sum,
            "note": "Router-scope selector-lift vs HRRR raw. Phase 4 ship gate: ≥90% of v0.6.432 router's measured long-lead lift on t/ws/wd. Interpret against router's own last-24h lift on debug page.",
        },
        "notes": "Per-(field, lead-band) source picker. source='nbm' → user-facing {field} value is replaced with {field}_l3_nbm in forecast_snapshot. HRRR fall-through when n<min_n or |lift_pct|<min_lift_pct. Scope: t/ws/wg/wd/h (fields with L3_NBM coverage). Refits nightly.",
    }
    with open(OUT_PATH, "w") as fout:
        json.dump(output, fout, indent=2)
        fout.write("\n")

    print("\n" + "=" * 72)
    print(f"L1 selector table — window {WINDOW_DAYS}d, fitted_at {output['fitted_at']}")
    print("=" * 72)
    print(f"{'field':<6} {'band':<8} {'pick':<6} {'HRRR MAE':>10} {'NBM MAE':>10} {'lift':>8} {'n':>8}")
    print("-" * 72)
    for f in FIELDS:
        for band, _, _ in BANDS:
            c = table[f].get(band)
            if not c:
                continue
            print(f"{f:<6} {band:<8} {c['source']:<6} {c['hrrr_mae']:>10.2f} "
                  f"{c['nbm_mae']:>10.2f} {c['lift_pct']:>+7.1f}% {c['n']:>8,}")
    print("=" * 72)
    print(f"Ship gate (router-scope t/ws/wd @ leads≥6h): "
          f"selector NBM lift = {selector_router_lift_pct:+.1f}% on n={router_scope_n_sum:,}")
    print(f"  → v0.6.432 router shipped based on similar-shape 14d evidence; "
          f"selector-side ≥90% of router's live lift = ship-gate met.")
    print(f"\n  wrote {OUT_PATH}")


if __name__ == "__main__":
    fit()

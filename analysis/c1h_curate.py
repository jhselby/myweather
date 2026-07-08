"""
C1h confidence-layer — Stage 2 curated table.

Mirrors c1_curate_confidence_table.py. Reads c1h_confidence_premium.json
(Stage 1 output) and applies the standard curation rules to produce
weather_collector/data/c1h_curated.json for the runtime to consume.

Slot names: "flat" / "fires" (the C1h axis is trend-direction firing).

Run:
    python3 analysis/c1h_curate.py
"""
import json
import os
import sys
from datetime import datetime, timezone


SAMPLE_FLOOR = 1000
MAGNITUDE_FLOOR_PCT = 5.0

STAGE1_PATH = os.path.join(os.path.dirname(__file__), "output", "c1h_confidence_premium.json")
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "weather_collector", "data", "c1h_curated.json",
)


def classify(cell):
    n_flat = cell["n_flat"]
    n_fires = cell["n_fires"]
    pct = cell["premium_pct"]

    if n_flat < SAMPLE_FLOOR or n_fires < SAMPLE_FLOOR:
        return "SKIP", f"sample floor (n_flat={n_flat}, n_fires={n_fires})"
    if abs(pct) < MAGNITUDE_FLOOR_PCT:
        return "SKIP", f"magnitude floor (|{pct:+.2f}%| < {MAGNITUDE_FLOOR_PCT}%)"
    if abs(pct) < MAGNITUDE_FLOOR_PCT * 2:
        return "MARGINAL", f"premium {pct:+.2f}% in 5-10% band"
    return "SHIP", f"premium {pct:+.2f}%, n≥{SAMPLE_FLOOR}"


def find_outliers(field_cells):
    signs = []
    for band, entry in field_cells.items():
        if entry["status"] == "SKIP":
            continue
        signs.append((band, 1 if entry["premium_pct"] > 0 else -1))
    if len(signs) < 3:
        return
    pos = sum(1 for _, s in signs if s > 0)
    neg = sum(1 for _, s in signs if s < 0)
    if pos / len(signs) >= 0.75:
        dominant = 1
    elif neg / len(signs) >= 0.75:
        dominant = -1
    else:
        return
    for band, s in signs:
        if s != dominant:
            field_cells[band]["status"] = "REVIEW"
            field_cells[band]["rationale"] += (
                f" [contradicts field's dominant {'WIDEN' if dominant > 0 else 'NARROW'} pattern]"
            )


def curate():
    with open(STAGE1_PATH) as f:
        stage1 = json.load(f)
    cells = stage1.get("cells", {})

    curated = {}
    for field, bands in cells.items():
        curated[field] = {}
        for band, c in bands.items():
            status, reason = classify(c)
            if status == "SHIP" or status == "MARGINAL":
                direction = "WIDEN" if c["premium_pct"] > 0 else "NARROW"
            else:
                direction = None
            curated[field][band] = {
                "status":      status,
                "direction":   direction,
                "flat_mae":    c["flat_mae"],
                "fires_mae":   c["fires_mae"],
                "premium_abs": c["premium_abs"],
                "premium_pct": c["premium_pct"],
                "n_flat":      c["n_flat"],
                "n_fires":     c["n_fires"],
                "threshold":   c["threshold"],
                "rationale":   reason,
            }
        find_outliers(curated[field])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": os.path.basename(STAGE1_PATH),
        "axis": "c1h_trend_direction",
        "slots": ["flat", "fires"],
        "curation_rules": {
            "sample_floor":        SAMPLE_FLOOR,
            "magnitude_floor_pct": MAGNITUDE_FLOOR_PCT,
            "marginal_band_pct":   [MAGNITUDE_FLOOR_PCT, MAGNITUDE_FLOOR_PCT * 2],
            "outlier_rule":        "field-dominant direction ≥75% → contrarian cells tagged REVIEW",
        },
        "stage1_meta": {
            "test_days":  stage1.get("test_days"),
            "min_n":      stage1.get("min_n"),
            "thresholds": stage1.get("thresholds"),
        },
        "cells": curated,
    }


def print_summary(curated):
    field_order = ["cc", "cl", "cm", "ch", "t"]
    field_order = [f for f in field_order if f in curated["cells"]]
    print("C1h confidence-layer Stage 2 curated table")
    print(f"  sample_floor={SAMPLE_FLOOR}  magnitude_floor={MAGNITUDE_FLOOR_PCT}%")
    print("=" * 92)
    print(f"{'field':<6} {'band':<8} {'status':<9} {'direction':<8} "
          f"{'premium%':>9}  {'rationale':<50}")
    print("-" * 92)
    counts = {"SHIP": 0, "MARGINAL": 0, "REVIEW": 0, "SKIP": 0}
    for field in field_order:
        for band, entry in curated["cells"][field].items():
            status = entry["status"]
            counts[status] = counts.get(status, 0) + 1
            direction = entry["direction"] or "—"
            pct = entry["premium_pct"]
            rationale = entry["rationale"][:48]
            print(f"{field:<6} {band:<8} {status:<9} {direction:<8} "
                  f"{pct:>+8.2f}%  {rationale:<50}")
        print()
    print("=" * 92)
    total = sum(counts.values())
    print(f"Totals: {counts['SHIP']} SHIP, {counts['MARGINAL']} MARGINAL, "
          f"{counts['REVIEW']} REVIEW, {counts['SKIP']} SKIP   "
          f"(of {total} cells; {total - counts['SKIP']} wired)")


def main():
    if not os.path.exists(STAGE1_PATH):
        sys.exit(f"Missing Stage 1 input {STAGE1_PATH} — run c1h_calibration.py first")
    curated = curate()
    print_summary(curated)
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(curated, f, indent=2)
    print()
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

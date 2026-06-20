"""
L6 confidence-layer — Stage 2 curated table.

Takes the Stage 1 calibration output (`l6_confidence_premium.json`) and
applies documented curation rules to produce a production-ready lookup table
that `weather_collector/processors/confidence_layer.py` will consume.

Per the hypothesis promotion pipeline ([[feedback-hypothesis-promotion-pipeline]]),
Stage 2 is "curated text": automated filter rules + human-visible rationale
per cell. Re-runnable when the Stage 1 calibration refreshes.

Curation rules:
  • SAMPLE_FLOOR: drop cells where n_stable < SAMPLE_FLOOR OR n_transition <
    SAMPLE_FLOOR. Premium estimates below that are noise-dominated.
  • MAGNITUDE_FLOOR_PCT: drop cells where |premium_pct| < MAGNITUDE_FLOOR_PCT.
    Sub-5% adjustments are too small to justify the UX complexity of a
    regime-conditional band.
  • Direction tag: premium > MAGNITUDE_FLOOR_PCT → "WIDEN"; premium <
    -MAGNITUDE_FLOOR_PCT → "NARROW".
  • Outlier flag: cells whose direction contradicts the rest of the field's
    pattern get tagged "REVIEW" — manual judgment before wiring.

Run:
  python3 analysis/l6_curate_confidence_table.py
"""
import json
import os
import sys


# Curation thresholds. Tunable, but every change should be documented in the
# memory note + memo'd in the next deploy.
SAMPLE_FLOOR = 1000          # min n per side
MAGNITUDE_FLOOR_PCT = 5.0    # min |premium_pct| to wire

# Input: Stage 1 calibration (gitignored debug artifact in analysis/output/).
# Output: Stage 2 curated table — committed to the repo at
# weather_collector/data/ so it ships with the Cloud Function deploy. The
# analysis/output/ tree is in .gitignore (so it doesn't ship), which is why
# the production artifact lives in the collector tree instead.
STAGE1_PATH = os.path.join(os.path.dirname(__file__), "output", "l6_confidence_premium.json")
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "weather_collector", "data", "l6_confidence_curated.json",
)


def classify(cell):
    """Return (status, reason) for a single (field, band) cell.

    status ∈ {SHIP, MARGINAL, SKIP, REVIEW}
      • SHIP: passes both thresholds, direction unambiguous
      • MARGINAL: passes sample floor but premium is in 5-10% range
      • SKIP: fails sample or magnitude floor
      • REVIEW: outlier vs rest of the field (manual judgment caller)
    """
    n_st = cell["n_stable"]
    n_tr = cell["n_transition"]
    pct = cell["premium_pct"]

    if n_st < SAMPLE_FLOOR or n_tr < SAMPLE_FLOOR:
        return "SKIP", f"sample floor (n_st={n_st}, n_tr={n_tr})"
    if abs(pct) < MAGNITUDE_FLOOR_PCT:
        return "SKIP", f"magnitude floor (|{pct:+.2f}%| < {MAGNITUDE_FLOOR_PCT}%)"
    if abs(pct) < MAGNITUDE_FLOOR_PCT * 2:
        # Between 5% and 10% — wire it but flag as marginal so a reviewer
        # knows the signal is at the edge of the floor.
        return "MARGINAL", f"premium {pct:+.2f}% in 5-10% band"
    return "SHIP", f"premium {pct:+.2f}%, n≥{SAMPLE_FLOOR}"


def find_outliers(field_cells):
    """Detect cells whose direction contradicts the field's overall pattern.

    A field has a "dominant direction" if ≥75% of its non-SKIP cells agree
    on sign. Cells against that direction get tagged REVIEW.
    """
    signs = []
    for band, entry in field_cells.items():
        if entry["status"] == "SKIP":
            continue
        signs.append((band, 1 if entry["premium_pct"] > 0 else -1))
    if len(signs) < 3:
        return  # too few bands to call a dominant direction
    pos = sum(1 for _, s in signs if s > 0)
    neg = sum(1 for _, s in signs if s < 0)
    if pos / len(signs) >= 0.75:
        dominant = 1
    elif neg / len(signs) >= 0.75:
        dominant = -1
    else:
        return  # no clear dominant
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
                "status":         status,
                "direction":      direction,
                "stable_mae":     c["stable_mae"],
                "transition_mae": c["transition_mae"],
                "premium_abs":    c["premium_abs"],
                "premium_pct":    c["premium_pct"],
                "n_stable":       c["n_stable"],
                "n_transition":   c["n_transition"],
                "rationale":      reason,
            }
        find_outliers(curated[field])

    return {
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "source": os.path.basename(STAGE1_PATH),
        "curation_rules": {
            "sample_floor":         SAMPLE_FLOOR,
            "magnitude_floor_pct":  MAGNITUDE_FLOOR_PCT,
            "marginal_band_pct":    [MAGNITUDE_FLOOR_PCT, MAGNITUDE_FLOOR_PCT * 2],
            "outlier_rule":         "field-dominant direction ≥75% → contrarian cells tagged REVIEW",
        },
        "stage1_meta": {
            "test_days": stage1.get("test_days"),
            "min_n":     stage1.get("min_n"),
        },
        "cells": curated,
    }


def print_summary(curated):
    """Human-readable text table — what cells ship, what's marginal, what's skipped."""
    field_order = ["ws", "wg", "wd", "t", "dp", "h", "pa", "pr", "cc", "cl", "cm", "ch", "sr", "pp"]
    field_order = [f for f in field_order if f in curated["cells"]]
    print(f"L6 confidence-layer Stage 2 curated table")
    print(f"  sample_floor={SAMPLE_FLOOR}  magnitude_floor={MAGNITUDE_FLOOR_PCT}%")
    print("=" * 90)
    print(f"{'field':<6} {'band':<8} {'status':<9} {'direction':<8} "
          f"{'premium%':>9} {'rationale':<50}")
    print("-" * 90)
    counts = {"SHIP": 0, "MARGINAL": 0, "REVIEW": 0, "SKIP": 0}
    for field in field_order:
        for band, entry in curated["cells"][field].items():
            status = entry["status"]
            counts[status] = counts.get(status, 0) + 1
            direction = entry["direction"] or "—"
            pct = entry["premium_pct"]
            rationale = entry["rationale"][:48]
            print(f"{field:<6} {band:<8} {status:<9} {direction:<8} "
                  f"{pct:>+8.2f}% {rationale:<50}")
        print()
    print("=" * 90)
    total = sum(counts.values())
    print(f"Totals: {counts['SHIP']} SHIP, {counts['MARGINAL']} MARGINAL, "
          f"{counts['REVIEW']} REVIEW, {counts['SKIP']} SKIP   "
          f"(of {total} cells; {total - counts['SKIP']} wired)")


def main():
    if not os.path.exists(STAGE1_PATH):
        sys.exit(f"Missing Stage 1 input {STAGE1_PATH} — run l6_confidence_calibration.py first")
    curated = curate()
    print_summary(curated)
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(curated, f, indent=2)
    print()
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

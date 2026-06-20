"""
L6 confidence-layer Stage 2 v2 — multi-axis curated table.

Reads `analysis/output/l6_confidence_premium_v2.json` (multi-axis Stage 1)
and emits a curated table that BOTH the existing single-axis
`confidence_layer.py` (legacy `stable_mae`/`transition_mae` per (field, band))
AND a Stage 4-updated multi-axis lookup can consume.

Each (field, band) entry carries:
  - Legacy keys (status, direction, stable_mae, transition_mae, etc.) —
    classified exactly as v1 did, so unchanged confidence_layer.py keeps working.
  - by_axes: dict[axis_key -> {mae, n, status, rationale}] for the multi-axis
    cells. axis_key is "{spread_q}::{pt_bin}::{transition_flag}" (matches the
    v2 Stage 1 key shape).

The v2 curator uses the SAME thresholds as v1 (sample floor, magnitude floor)
but with a smaller absolute sample requirement for multi-axis cells, because
they're 8–24× sparser by construction. Magnitude floor is relative to the
legacy stable_mae for that (field, band), so "WIDEN by ≥5%" is consistent.

Run:
  python3 analysis/l6_curate_confidence_table_v2.py
"""
import json
import os
import sys
from datetime import datetime, timezone


# Legacy axis thresholds (match v1 exactly so the legacy half of the output
# is interchangeable with v1's output).
SAMPLE_FLOOR = 1000
MAGNITUDE_FLOOR_PCT = 5.0

# Multi-axis thresholds. Lower n because cells are by construction sparser.
# Magnitude floor stays at 5% — we don't widen displayed bands for tiny effects
# just because we have the axis resolution to claim them.
MULTI_SAMPLE_FLOOR = 200
MULTI_MAGNITUDE_FLOOR_PCT = 5.0

STAGE1_PATH = os.path.join(os.path.dirname(__file__), "output",
                           "l6_confidence_premium_v2.json")
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "weather_collector", "data", "l6_confidence_curated_v2.json",
)


def classify_legacy(cell):
    n_st = cell["n_stable"]
    n_tr = cell["n_transition"]
    pct = cell["premium_pct"]
    if n_st < SAMPLE_FLOOR or n_tr < SAMPLE_FLOOR:
        return "SKIP", f"sample floor (n_st={n_st}, n_tr={n_tr})"
    if abs(pct) < MAGNITUDE_FLOOR_PCT:
        return "SKIP", f"magnitude floor (|{pct:+.2f}%| < {MAGNITUDE_FLOOR_PCT}%)"
    if abs(pct) < MAGNITUDE_FLOOR_PCT * 2:
        return "MARGINAL", f"premium {pct:+.2f}% in 5-10% band"
    return "SHIP", f"premium {pct:+.2f}%, n≥{SAMPLE_FLOOR}"


def classify_axis_cell(legacy_stable_mae, cell_mae, cell_n):
    """Multi-axis cell classification: compare cell_mae to the legacy
    stable_mae for the same (field, band) to compute a magnitude (% delta),
    then apply sample + magnitude floors. Returns (status, direction, rationale).
    """
    if cell_n < MULTI_SAMPLE_FLOOR:
        return "SKIP", None, f"sample floor (n={cell_n})"
    if legacy_stable_mae is None or legacy_stable_mae <= 0:
        return "SKIP", None, "no legacy reference"
    pct = 100.0 * (cell_mae - legacy_stable_mae) / legacy_stable_mae
    if abs(pct) < MULTI_MAGNITUDE_FLOOR_PCT:
        return "SKIP", None, f"magnitude floor (|{pct:+.2f}%| < {MULTI_MAGNITUDE_FLOOR_PCT}%)"
    direction = "WIDEN" if pct > 0 else "NARROW"
    if abs(pct) < MULTI_MAGNITUDE_FLOOR_PCT * 2:
        return "MARGINAL", direction, f"delta {pct:+.2f}% in 5-10% band"
    return "SHIP", direction, f"delta {pct:+.2f}%, n≥{MULTI_SAMPLE_FLOOR}"


def find_outliers(field_cells):
    """v1 outlier rule applied to legacy half only — multi-axis cells already
    have full per-cell rationale and don't need the dominance check."""
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
                f" [contradicts field's dominant "
                f"{'WIDEN' if dominant > 0 else 'NARROW'} pattern]"
            )


def curate():
    with open(STAGE1_PATH) as f:
        stage1 = json.load(f)

    cells = stage1.get("cells", {})
    curated = {}

    for field, bands in cells.items():
        curated[field] = {}
        for band, c in bands.items():
            status, reason = classify_legacy(c)
            direction = ("WIDEN" if c["premium_pct"] > 0 else "NARROW") \
                if status in ("SHIP", "MARGINAL") else None

            # Multi-axis cells — keyed exactly as Stage 1 produced them.
            by_axes_out = {}
            for axis_key, ax in (c.get("by_axes") or {}).items():
                ax_status, ax_dir, ax_reason = classify_axis_cell(
                    c["stable_mae"], ax["mae"], ax["n"]
                )
                by_axes_out[axis_key] = {
                    "status":    ax_status,
                    "direction": ax_dir,
                    "mae":       ax["mae"],
                    "n":         ax["n"],
                    "rationale": ax_reason,
                }

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
                "by_axes":        by_axes_out,
            }
        find_outliers(curated[field])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source":       os.path.basename(STAGE1_PATH),
        "curation_rules": {
            "legacy_sample_floor":     SAMPLE_FLOOR,
            "legacy_magnitude_floor_pct": MAGNITUDE_FLOOR_PCT,
            "multi_sample_floor":      MULTI_SAMPLE_FLOOR,
            "multi_magnitude_floor_pct": MULTI_MAGNITUDE_FLOOR_PCT,
            "outlier_rule":           "field-dominant direction ≥75% on legacy cells → contrarians tagged REVIEW",
        },
        "stage1_meta": {
            "test_days":    stage1.get("test_days"),
            "min_n_legacy": stage1.get("min_n_legacy"),
            "min_n_multi":  stage1.get("min_n_multi"),
            "spread_field": stage1.get("spread_field"),
            "spread_cuts":  stage1.get("spread_cuts"),
            "pt_bins":      stage1.get("pt_bins"),
            "axes":         stage1.get("axes"),
        },
        "cells": curated,
    }


def print_summary(doc):
    field_order = ["ws", "wg", "wd", "t", "dp", "h", "pa", "pr",
                   "cc", "cl", "cm", "ch", "sr", "pp"]
    field_order = [f for f in field_order if f in doc["cells"]]
    print("L6 confidence-layer Stage 2 v2 curated table")
    print(f"  legacy: sample≥{SAMPLE_FLOOR}, |Δ|≥{MAGNITUDE_FLOOR_PCT}%")
    print(f"  multi:  sample≥{MULTI_SAMPLE_FLOOR}, |Δ|≥{MULTI_MAGNITUDE_FLOOR_PCT}%")
    print("=" * 92)
    legacy_counts = {"SHIP": 0, "MARGINAL": 0, "REVIEW": 0, "SKIP": 0}
    multi_counts = {"SHIP": 0, "MARGINAL": 0, "SKIP": 0}
    multi_total_cells = 0

    for field in field_order:
        for band, entry in doc["cells"][field].items():
            legacy_counts[entry["status"]] = legacy_counts.get(entry["status"], 0) + 1
            ba = entry.get("by_axes") or {}
            multi_total_cells += len(ba)
            for ax_entry in ba.values():
                multi_counts[ax_entry["status"]] = multi_counts.get(ax_entry["status"], 0) + 1

    print("Legacy axis:")
    total_legacy = sum(legacy_counts.values())
    print(f"  {legacy_counts['SHIP']} SHIP, {legacy_counts['MARGINAL']} MARGINAL, "
          f"{legacy_counts['REVIEW']} REVIEW, {legacy_counts['SKIP']} SKIP "
          f"(of {total_legacy})")
    print("Multi-axis cells:")
    print(f"  {multi_counts['SHIP']} SHIP, {multi_counts['MARGINAL']} MARGINAL, "
          f"{multi_counts['SKIP']} SKIP (of {multi_total_cells})")


def main():
    if not os.path.exists(STAGE1_PATH):
        sys.exit(f"Missing Stage 1 v2 input {STAGE1_PATH} — "
                 "run l6_confidence_calibration_v2.py first")
    doc = curate()
    print_summary(doc)
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(doc, f, indent=2)
    print()
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

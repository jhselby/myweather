#!/usr/bin/env python3
"""Curator — emit runtime table for the per-obs L1 blender.

Reads per-field Stage 1 blender outputs (β vectors + standardization moments)
and emits a single runtime-consumable JSON that l1_selector.py loads at
import time.

Only cells with verdict == STABLE from Stage 1 get emitted. Non-STABLE cells
fall through to the current selector at runtime.

Shape (runtime contract):
{
  "generated_at": iso,
  "source": "analysis/l1_blender_curate.py",
  "feature_names": [...],       # order of β[1:] and mu/sd
  "cells": [
    { "field": "dp",
      "regime": "nw_flow",
      "band": "12-23",           # stripped of "h" suffix; matches _band_for
      "beta": [intercept, β1, ...],  # length 1 + n_features
      "mu": [...],               # standardization means, length n_features
      "sd": [...],               # standardization stds, length n_features
      "omega_mean_train": 0.51,  # for runtime sanity assertions
      "test_lift_vs_best_A": 56.02,
      "test_lift_vs_best_B": 41.46,
      "n": 1037
    },
    ...
  ]
}

Runtime consumer (l1_selector._blender_omega): standardize features with mu/sd,
compute ω = clip(β·x, 0, 1). Caller applies forecast_l1 = ω·HRRR + (1-ω)·NBM.

Run:
    python3 analysis/l1_blender_curate.py
Emits:
    weather_collector/data/l1_blender_curated.json
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "weather_collector" / "data" / "l1_blender_curated.json"
FIELDS = ("dp", "h", "ch", "wg")   # extend as more fields clear Stage 1


def _band_key(band):
    # "0-5h" -> "0-5" (runtime keys drop the h suffix, matches _band_for pattern)
    return band[:-1] if band.endswith("h") else band


def curate():
    all_cells = []
    feature_names = None
    for field in FIELDS:
        src = HERE / "output" / f"l1_blender_stage1_{field}.json"
        if not src.exists():
            print(f"  skip {field}: {src.name} not found")
            continue
        data = json.load(open(src))
        if feature_names is None:
            feature_names = data["features"]
        elif feature_names != data["features"]:
            raise SystemExit(f"feature-name mismatch: {field} has {data['features']}, expected {feature_names}")

        n_ship = 0
        for cell in data["cells"]:
            if cell["verdict"] != "STABLE":
                continue
            coef = cell["coefficients"]
            all_cells.append({
                "field": field,
                "regime": cell["regime"],
                "band": _band_key(cell["band"]),
                "beta": coef["beta"],
                "mu": coef["mu"],
                "sd": coef["sd"],
                "omega_mean_train": cell["pair_B"]["omega_mean_te"],
                "test_lift_vs_best_A": cell["pair_A"]["test_lift_vs_best_pct"],
                "test_lift_vs_best_B": cell["pair_B"]["test_lift_vs_best_pct"],
                "hrrr_mae_te": cell["pair_B"]["hrrr_mae_te"],
                "nbm_mae_te":  cell["pair_B"]["nbm_mae_te"],
                "n": cell["n"],
            })
            n_ship += 1
        print(f"  {field}: {n_ship} STABLE cell(s) curated")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "analysis/l1_blender_curate.py",
        "feature_names": feature_names or [],
        "cells": all_cells,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {OUT}  ({len(all_cells)} cells)")
    if all_cells:
        print("  cells:")
        for c in all_cells:
            print(f"    {c['field']:<4} {c['regime']:<14} {c['band']:<7}  "
                  f"lift A={c['test_lift_vs_best_A']:+.1f}% / B={c['test_lift_vs_best_B']:+.1f}%  "
                  f"ω̄={c['omega_mean_train']:.2f}  n={c['n']}")


if __name__ == "__main__":
    curate()

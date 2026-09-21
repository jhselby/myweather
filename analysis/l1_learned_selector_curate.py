#!/usr/bin/env python3
"""Curator — emit runtime table for the learned per-obs L1 selector.

Reads per-field Stage 1 v2b classifier outputs (β vectors + standardization
moments + θ* per (regime, band)) and emits a single runtime-consumable JSON
that l1_selector.py loads at import time.

Only cells that PROMOTED (test_lift ≥ MIN_LIFT AND non-degenerate NBM fraction
AND test ≥ 0.5 × train, matching the Stage 1 v2b gate) get emitted.

Shape (runtime contract):
{
  "generated_at": iso,
  "source": "analysis/l1_learned_selector_curate.py",
  "feature_names": [...],       # order of β[1:] and mu/sd
  "cells": [
    { "field": "t",
      "regime": "ne_flow",
      "band": "12-23",           # stripped of "h" suffix, matches _band_for
      "theta": 0.75,
      "beta": [intercept, β1, ...],  # length 1 + n_features
      "mu": [...],               # standardization mean, length n_features
      "sd": [...],               # standardization std, length n_features
      "test_lift_pct": 6.08,
      "capture_pct": 23.2,
      "n_test": 251
    },
    ...
  ]
}

The runtime consumer (l1_selector._learned_override) standardizes the incoming
feature vector using mu/sd, dots with β, sigmoids, and picks NBM iff P > θ.

Run:
    python3 analysis/l1_learned_selector_curate.py
Emits:
    weather_collector/data/l1_learned_selector_curated.json
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "weather_collector" / "data" / "l1_learned_selector_curated.json"
FIELDS = ("t", "h")   # extend as more fields promote

MIN_LIFT_PCT = 3.0
MIN_N_TEST = 150


def curate():
    all_cells = []
    feature_names = None
    for field in FIELDS:
        src = HERE / "output" / f"l1_selector_per_obs_classifier_stage1_v2b_{field}.json"
        if not src.exists():
            print(f"  skip {field}: {src.name} not found")
            continue
        data = json.load(open(src))
        if feature_names is None:
            feature_names = data["features"]
        elif feature_names != data["features"]:
            raise SystemExit(f"feature-name mismatch: {field} has {data['features']}, expected {feature_names}")
        for cell in data["cells"]:
            lift_te = cell["test_lift_pct"]
            lift_tr = cell["train_lift_pct"]
            fnbm = cell["test_frac_nbm"]
            n_te = cell["n_test"]
            non_deg = 0.05 < fnbm < 0.60
            passes = (
                lift_te >= MIN_LIFT_PCT
                and lift_tr >= MIN_LIFT_PCT
                and lift_te >= 0.5 * lift_tr
                and n_te >= MIN_N_TEST
                and non_deg
            )
            if not passes:
                continue
            band = cell["band"].rstrip("h")   # "12-23h" → "12-23" to match _band_for
            all_cells.append({
                "field": field,
                "regime": cell["regime"],
                "band": band,
                "theta": cell["theta_star"],
                "beta": cell["beta_std"],
                "mu": cell["mu"],
                "sd": cell["sd"],
                "test_lift_pct": round(lift_te, 3),
                "capture_pct": round(cell["test_capture_pct"], 3),
                "n_test": n_te,
            })

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "analysis/l1_learned_selector_curate.py",
        "feature_names": feature_names or [],
        "min_lift_pct": MIN_LIFT_PCT,
        "min_n_test": MIN_N_TEST,
        "cells": all_cells,
        "notes": (
            "Runtime consumer: l1_selector._learned_override(field, regime, band, features). "
            "features is a dict keyed by feature_names entries; each value is standardized as "
            "(x - mu[i]) / sd[i], then P = sigmoid(beta[0] + sum(beta[i+1] * x_std[i])). "
            "Route NBM iff P > theta, else HRRR (or the fall-through pick). "
            "SHADOW guard lives in l1_selector.LEARNED_SELECTOR_SHADOW_ENABLED — the runtime "
            "table is loaded regardless; the flag controls whether picks are actually swapped."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}")
    print(f"  {len(all_cells)} cell(s) curated across fields={list(FIELDS)}")
    for c in all_cells:
        print(f"    {c['field']}/{c['regime']}/{c['band']}h  "
              f"θ={c['theta']}  test +{c['test_lift_pct']:.2f}%  capture {c['capture_pct']:.1f}%  n_te={c['n_test']}")


if __name__ == "__main__":
    curate()

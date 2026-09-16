"""wg residual-persistence gate — thin wrapper on the shared
`_residual_persistence` harness (extracted 2026-08-31 v0.6.532).

Field-specific config lives here; correction semantics live in
`_residual_persistence.py`. See that module for the full contract and
[[project_wg_residual_persistence]] for the Stage 0/1/2 lineage.

wg-specific: wind_gusts is physically bounded ≥ 0 (no upper bound —
gust magnitude has no hard ceiling in practice). Sanity clamp
_MAX_ABS_CORRECTION_MPH = 15.0 catches a runaway refit slot;
Stage 2 fit range is |≤5|mph.
"""
from pathlib import Path

from ._residual_persistence import (
    TABLE_ROOT,
    stamp_field,
    describe_field,
)

ENABLED = True   # Flipped 2026-09-16 v0.6.635. Stage 1 PROMOTE (Test MAE +17.83%, 3/5 regime WIN, halves both positive). Stage 2 curated table has 16 SHIP cells; residual_persistence_walker confirms 13 cleared the 7-day gate (all ⊂ Stage 2 SHIP set). Two months past the 07-27 earliest-flip target.

FIELD = "wg"
HOURLY_KEY = "wind_gusts"
L2_KEY = "wind_gusts_post_l2"
_MAX_ABS_CORRECTION_MPH = 15.0
_PRE_KEY_SUFFIX = "_post_l3_pre_wgrp"
_PHYSICAL_BOUNDS = (0.0, None)  # gust physical floor; no upper

_TABLE_PATH = TABLE_ROOT / "wg_residual_persistence_curated.json"


def stamp_wg_residual_persistence(weather_data):
    return stamp_field(
        weather_data,
        field=FIELD,
        hourly_key=HOURLY_KEY,
        l2_key=L2_KEY,
        table_path=_TABLE_PATH,
        max_abs_correction=_MAX_ABS_CORRECTION_MPH,
        pre_key_suffix=_PRE_KEY_SUFFIX,
        physical_bounds=_PHYSICAL_BOUNDS,
        enabled=ENABLED,
    )


def describe_applicability():
    return describe_field(field=FIELD, table_path=_TABLE_PATH, enabled=ENABLED)

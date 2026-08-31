"""dp residual-persistence gate — thin wrapper on the shared
`_residual_persistence` harness (extracted 2026-08-31 v0.6.532).

Field-specific config lives here; correction semantics live in
`_residual_persistence.py`. See that module for the full contract and
[[project_dp_residual_persistence]] for the Stage 0/1/2 lineage.

dp-specific: dew point has no physical bounds (both sides unclamped —
dp is unbounded °F in practice). Sanity clamp _MAX_ABS_CORRECTION_F = 10.0
catches a runaway refit slot; Stage 2 fit range is |≤3.15|°F.

Per [[project_dp_is_derived_no_dp_work]] this processor stays ENABLED=False
permanently — the h Stage 3 correction absorbs the dp signal via Magnus.
Wrapper retained so a future re-fit can pass through the same walker gate
as h and wg.
"""
from pathlib import Path

from ._residual_persistence import (
    TABLE_ROOT,
    stamp_field,
    describe_field,
)

ENABLED = False  # Do not flip — dp is derived downstream from h correction per [[project_dp_is_derived_no_dp_work]].

FIELD = "dp"
HOURLY_KEY = "corrected_dew_point"
L2_KEY = "corrected_dew_point_post_l2"
_MAX_ABS_CORRECTION_F = 10.0
_PRE_KEY_SUFFIX = "_post_l3_pre_dprp"
_PHYSICAL_BOUNDS = (None, None)  # dp is unbounded in practice

_TABLE_PATH = TABLE_ROOT / "dp_residual_persistence_curated.json"


def stamp_dp_residual_persistence(weather_data):
    return stamp_field(
        weather_data,
        field=FIELD,
        hourly_key=HOURLY_KEY,
        l2_key=L2_KEY,
        table_path=_TABLE_PATH,
        max_abs_correction=_MAX_ABS_CORRECTION_F,
        pre_key_suffix=_PRE_KEY_SUFFIX,
        physical_bounds=_PHYSICAL_BOUNDS,
        enabled=ENABLED,
    )


def describe_applicability():
    return describe_field(field=FIELD, table_path=_TABLE_PATH, enabled=ENABLED)

"""h residual-persistence gate — thin wrapper on the shared
`_residual_persistence` harness (extracted 2026-08-31 v0.6.532).

Pre-staged 2026-08-31 v0.6.530 ahead of the walker gate clearance
(earliest ~09-06 per [[project_h_residual_persistence_attribution_08_30]]).
Refactored same session as v0.6.532 alongside wg + dp.

Field-specific config lives here; correction semantics live in
`_residual_persistence.py`.

h-specific: relative humidity is physically bounded [0, 100]. Both-ends
clamp is the only field with an upper physical bound. Sanity clamp
_MAX_ABS_CORRECTION_PCT = 20.0 catches a runaway refit slot; Stage 2 fit
range as of walker day 1 is +1.44 to +7.58%.

Flip ENABLED=True only after
`.cache_h_residual_persistence_walker_history.json` reports
`n_cells_cleared >= 1` and 7 daily reads of shadow telemetry are stable.
"""
from pathlib import Path

from ._residual_persistence import (
    TABLE_ROOT,
    stamp_field,
    describe_field,
)

ENABLED = False  # Live-layer change gate: walker cell clearance + 7-day shadow-telemetry stability before flipping True. Ship-day earliest ~09-06.

FIELD = "h"
HOURLY_KEY = "corrected_humidity"
L2_KEY = "corrected_humidity_post_l2"
_MAX_ABS_CORRECTION_PCT = 20.0
_PRE_KEY_SUFFIX = "_post_l3_pre_hrp"
_PHYSICAL_BOUNDS = (0.0, 100.0)  # RH is bounded [0, 100]

_TABLE_PATH = TABLE_ROOT / "h_residual_persistence_curated.json"


def stamp_h_residual_persistence(weather_data):
    return stamp_field(
        weather_data,
        field=FIELD,
        hourly_key=HOURLY_KEY,
        l2_key=L2_KEY,
        table_path=_TABLE_PATH,
        max_abs_correction=_MAX_ABS_CORRECTION_PCT,
        pre_key_suffix=_PRE_KEY_SUFFIX,
        physical_bounds=_PHYSICAL_BOUNDS,
        enabled=ENABLED,
    )


def describe_applicability():
    return describe_field(field=FIELD, table_path=_TABLE_PATH, enabled=ENABLED)

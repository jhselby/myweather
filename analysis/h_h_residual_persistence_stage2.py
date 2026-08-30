"""h (humidity) residual-persistence Stage 2 preview.

Written 2026-08-30 v0.6.524 as a thin wrapper on
`_residual_persistence_stage2` — the architecturally-correct next step after
v0.6.522 Stage 1 refactor flipped h Stage 1 MARGINAL → STAGE 1 PROMOTE.
Feeds `weather_collector/data/h_residual_persistence_curated.json` (new
this ship — not yet read by any processor). When Stage 2 outputs a stable
per-cell SHIP set across a 7-day walker window, Stage 3 processor
`weather_collector/processors/h_residual_persistence.py` gets written on
the `wg_residual_persistence.py` template + 7-day live-layer flip gate.

Once h Stage 3 ships and clears, `dp_residual_persistence` stays
ENABLED=False permanently — fixing h routes to dp via Magnus. See
[[project_h_residual_persistence_attribution_08_30]] and
[[project_dp_is_derived_no_dp_work]].
"""
import sys

from _residual_persistence_stage2 import run_stage2


if __name__ == "__main__":
    sys.exit(run_stage2(field="h", units_label="%"))

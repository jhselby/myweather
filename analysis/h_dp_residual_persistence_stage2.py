"""dp residual-persistence Stage 2 preview.

Refactored 2026-08-30 v0.6.524 — logic lives in `_residual_persistence_stage2`.
Same architectural discipline as v0.6.522 Stage 1 refactor: three cloned
400-line siblings collapsed to one shared harness + thin wrappers so a
methodology fix happens in one place. See
[[project_h_residual_persistence_attribution_08_30]] and
[[project_dp_is_derived_no_dp_work]] — dp Stage 2 output feeds the collector
via `weather_collector/data/dp_residual_persistence_curated.json` but the
Stage 3 processor stays ENABLED=False permanently (h upstream owns the
signal via Magnus).
"""
import sys

from _residual_persistence_stage2 import run_stage2


if __name__ == "__main__":
    sys.exit(run_stage2(field="dp", units_label="°F"))

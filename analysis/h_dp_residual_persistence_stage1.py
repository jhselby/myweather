"""dp (dew point) residual-persistence Stage 1 preview.

Refactored 2026-08-30 v0.6.522 — logic lives in `_residual_persistence_stage1`.
Signal is now understood to be the downstream echo of an h bias observed via
Magnus (dp = f(t, h)); real Stage 2/3 ship path lives on h. See
[[project_h_residual_persistence_attribution_08_30]] and
[[project_dp_is_derived_no_dp_work]]. `dp_residual_persistence` processor
stays ENABLED=False permanently — fixing h routes to dp via Magnus.
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _residual_persistence_stage1 import run_stage1  # noqa: E402


if __name__ == "__main__":
    sys.exit(run_stage1(field="dp"))

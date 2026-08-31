"""wg residual-persistence Stage 2 preview.

Refactored 2026-08-30 v0.6.524 — logic lives in `_residual_persistence_stage2`.
Feeds `weather_collector/data/wg_residual_persistence_curated.json`, read by
the live `wg_residual_persistence.py` processor (Stage 3 shipped v0.6.380
2026-07-25 with a 7-day live-layer flip gate).
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _residual_persistence_stage2 import run_stage2  # noqa: E402


if __name__ == "__main__":
    sys.exit(run_stage2(field="wg", units_label="mph"))

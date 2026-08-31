"""wg (wind gust) residual-persistence Stage 1 preview.

Refactored 2026-08-30 v0.6.522 — logic lives in `_residual_persistence_stage1`.
Stage 2 shipped v0.6.372c 2026-07-22 (curated JSON per-cell verdicts); Stage 3
processor `wg_residual_persistence.py` shipped v0.6.380 2026-07-25 with a
7-day live-layer flip gate.
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _residual_persistence_stage1 import run_stage1  # noqa: E402


if __name__ == "__main__":
    sys.exit(run_stage1(field="wg"))

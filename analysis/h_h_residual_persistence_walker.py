"""h residual-persistence Stage 2 → Stage 3 walker.

Accumulates per-cell verdict history from h_residual_persistence_curated.json
and gates the h_residual_persistence.py Stage 3 write on 7 consecutive
SHIP-or-MARGIN days per cell. Written 2026-08-31 v0.6.529.
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _residual_persistence_walker import run_walker  # noqa: E402


if __name__ == "__main__":
    sys.exit(run_walker(field="h"))

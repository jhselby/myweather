"""wg residual-persistence Stage 2 → Stage 3 walker.

Written 2026-08-31 v0.6.529. wg Stage 3 (wg_residual_persistence.py) is
already live with ENABLED=False; walker exists for the same reason as the
dp sibling — future re-fits pass through the same 7/7-day cell gate.
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _residual_persistence_walker import run_walker  # noqa: E402


if __name__ == "__main__":
    sys.exit(run_walker(field="wg"))

"""dp residual-persistence Stage 2 → Stage 3 walker.

Written 2026-08-31 v0.6.529. dp Stage 3 (dp_residual_persistence.py) is
already live with ENABLED=False; this walker exists so a future re-fit that
re-enters the promotion path has the same 7/7-day cell gate as h and wg
rather than relying on manual review.
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _residual_persistence_walker import run_walker  # noqa: E402


if __name__ == "__main__":
    sys.exit(run_walker(field="dp"))

"""h (humidity) residual-persistence Stage 1 preview.

Refactored 2026-08-30 v0.6.522 — logic lives in `_residual_persistence_stage1`.
Un-skipped 2026-08-30 v0.6.520 after today's dp Stage 1 PROMOTE was attributed
to h upstream via Magnus (h Stage 1 +21.41% aggregate 5/5 WIN matches dp
+21.25% statistically). See [[project_h_residual_persistence_attribution_08_30]].
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _residual_persistence_stage1 import run_stage1  # noqa: E402


if __name__ == "__main__":
    sys.exit(run_stage1(field="h"))

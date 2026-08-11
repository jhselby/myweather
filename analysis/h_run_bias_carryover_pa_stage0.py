"""Stage 0 — pressure (pa) run-level bias carryover.

Motivated by smoke test in `analysis/h_smoke_C_deepdive.py` (08-10): after
de-meaning by (hour × lead-bucket), `pa` shows 75% same-sign agreement between
each run's short-lead (0-3h) and long-lead (24-48h) residual means, with 14%
of long-lead MAE explainable by short-lead sign alone.

Intervention:  per run_time R, once R's short-lead forecasts have been
scored against fresh obs, nudge R's long-lead forecasts by
    long_correction = alpha * mean_short_residual_of_R  +  beta
where alpha, beta are OLS fits on training runs.

Gate:  ≥ 1.0% long-lead |err| MAE improvement on the last 7d held-out.
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _run_bias_carryover import compute, emit_and_write  # noqa: E402

OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_run_bias_carryover_pa_stage0.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_run_bias_carryover_pa_stage0.json")


def main():
    res = compute(field="pa")
    return emit_and_write(res, OUT_TXT, OUT_JSON,
                          hypothesis_slug="run-bias carryover  (pa)")


if __name__ == "__main__":
    sys.exit(main())

"""L5_NBM apply-time processor (option-1 Phase 6, 2026-08-21).

Mirrors HRRR's L5 (regime × hour_of_day solar bias) on the NBM cascade.
Reads `weather_collector/data/lsr_nbm_bias_table_curated.json` once at
module load and exposes `l5_nbm_correction(regime, hour_of_day, raw_solar_wm2)`
returning the signed Δ (W/m²) to ADD to `sr_l3_nbm`. Returns 0.0 when
the table is missing, the regime is unknown / in skip list, the raw
solar is below sun-up threshold, or the cell is unfit.

Scope: sr only. sr is not in HRRR L4_FIELDS or L4_NBM_FIELDS, so on the
NBM cascade the sr layer stack is:
    sr_raw_nbm → sr_l2_nbm → sr_l3_nbm → sr_l5_nbm
Skips L4_NBM by design (mirrors HRRR sr, which also skips L4).

Sign convention (mirrors solar_correction.py::compute_solar_correction):
`bias = forecast - observed`, correction returned = `-bias`, applied as
`l5_nbm = l3_nbm + correction` (adds the negative of the bias, pushing
forecast toward observed).

Skip regimes start empty; L5-NBM analysis may promote regimes into the
skip list once we see per-regime performance in the pair log (same
pattern as HRRR L5's ne_flow / calm skips discovered 2026-07-02).

Applied inside `forecast_snapshot.stamp()` right after the L4_NBM block,
per hour, using each hour's local time (hour-of-day) and that lead's raw
NBM solar value for sun-up gating. Curated JSON updated by
`analysis/l5_nbm_recompute_biases_hourly.py`.
"""
import json
import logging
from pathlib import Path


CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "lsr_nbm_bias_table_curated.json"

SUN_UP_THRESHOLD = 50.0

_BIAS_BY_REGIME_HOUR = {}   # {regime: {hour_local: bias_wm2}}
_BIAS_FALLBACK_BY_REGIME = {}  # {regime: overall_bias_wm2}
_SKIP_REGIMES = set()
_MIN_CELL_N = 30


def _load():
    global _BIAS_BY_REGIME_HOUR, _BIAS_FALLBACK_BY_REGIME, _SKIP_REGIMES, _MIN_CELL_N
    try:
        with open(CURATED_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning(f"  ⚠  l5_nbm: curated JSON unavailable ({e}); apply is a no-op")
        return
    try:
        _MIN_CELL_N = int(data.get("min_cell_n", 30))
    except (TypeError, ValueError):
        _MIN_CELL_N = 30
    bbrh = data.get("bias_by_regime_hour") or {}
    _BIAS_BY_REGIME_HOUR = {
        regime: {int(h): float(v) for h, v in cells.items()}
        for regime, cells in bbrh.items()
    }
    fb = data.get("fallback_by_regime") or {}
    _BIAS_FALLBACK_BY_REGIME = {r: float(v) for r, v in fb.items()}
    _SKIP_REGIMES = set(data.get("skip_regimes") or [])


_load()


def l5_nbm_correction(regime_synoptic, hour_of_day, raw_solar_wm2):
    """Signed Δ (W/m²) to ADD to sr_l3_nbm. 0.0 when regime is unknown /
    in skip list, sun is down, or the (regime × hour) cell is unfit and
    the regime has no fallback."""
    if regime_synoptic is None or raw_solar_wm2 is None:
        return 0.0
    if raw_solar_wm2 < SUN_UP_THRESHOLD:
        return 0.0
    if regime_synoptic in _SKIP_REGIMES:
        return 0.0
    regime_cells = _BIAS_BY_REGIME_HOUR.get(regime_synoptic, {})
    if hour_of_day is not None and hour_of_day in regime_cells:
        bias = regime_cells[hour_of_day]
    else:
        bias = _BIAS_FALLBACK_BY_REGIME.get(regime_synoptic, 0.0)
    return round(-bias, 1)

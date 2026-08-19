"""
L3_NBM apply-time processor (option-1 Phase 3, 2026-08-19).

Reads `weather_collector/data/l3_nbm_curated.json` once at module load and
exposes `l3_nbm_bias(field, lead_h)` returning the per-lead signed bias to
subtract from `{field}_l2_nbm`. Returns 0.0 when the table is missing,
the field is not covered, the lead is out of range, the bin is unfit
(null), or the bin has fewer than `min_pairs_per_lead` samples.

Applied inside `forecast_snapshot.stamp()` right after the L2_NBM block,
per hour: `{f}_l3_nbm = {f}_l2_nbm - bias`. Same convention as the
existing HRRR L3 (decay_apply.apply_decay_corrections): correction is a
signed bias, subtracted from the layer below.

Scope: `L3_NBM_FIELDS = ("t", "ws", "wg", "h")` for scalar bias. `wd` is
handled through a separate circular branch — the fitter emits sin/cos
component arrays under `corrections.wd_components`, and this module
exposes `l3_nbm_wd_components(lead_h) -> (sin_corr, cos_corr)` for
`forecast_snapshot` to apply via atan2. Same convention as HRRR's
`decay_corrections.wd_components` fed from `error_sin`/`error_cos`.
Per-layer sin/cos errors are emitted by `forecast_error_log.py` for
every layer so future NBM cascades reuse the same signal.

Curated JSON is source-controlled and updated by `analysis/l3_nbm_fit.py`.
Shadow-only in Phase 3: stamps `{f}_l3_nbm` into the forecast log for
the Fitter's per-layer MAE aggregation and the debug chart. The
selector (Phase 4) is what will make L3_NBM user-visible.
"""
import json
import logging
from pathlib import Path


CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "l3_nbm_curated.json"

L3_NBM_FIELDS = ("t", "ws", "wg", "h", "ch", "sr", "dp", "cc")   # scalar-bias fields
L3_NBM_WD = "wd"                          # circular field (sin/cos components)
LEAD_BINS = 48

_TABLE = None      # {field: [(bias, n), ...]} for scalar fields
_WD_TABLE = None   # [(sin_corr, cos_corr, n), ...] length LEAD_BINS
_MIN_PAIRS = 20


def _load():
    global _TABLE, _WD_TABLE, _MIN_PAIRS
    try:
        with open(CURATED_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning(f"  ⚠  l3_nbm: curated JSON unavailable ({e}); apply is a no-op")
        _TABLE = {}
        _WD_TABLE = [(None, None, 0)] * LEAD_BINS
        return
    corrections = data.get("corrections", {}) or {}
    n_samples = data.get("n_samples", {}) or {}
    try:
        _MIN_PAIRS = int(data.get("min_pairs_per_lead", 20))
    except (TypeError, ValueError):
        _MIN_PAIRS = 20
    fused = {}
    for f in L3_NBM_FIELDS:
        corr = corrections.get(f) or [None] * LEAD_BINS
        nsam = n_samples.get(f) or [0] * LEAD_BINS
        fused[f] = list(zip(corr, nsam))
    _TABLE = fused
    wd_comp = corrections.get("wd_components") or {}
    wd_sin = wd_comp.get("sin") or [None] * LEAD_BINS
    wd_cos = wd_comp.get("cos") or [None] * LEAD_BINS
    wd_n   = n_samples.get(L3_NBM_WD) or [0] * LEAD_BINS
    _WD_TABLE = list(zip(wd_sin, wd_cos, wd_n))


_load()


def l3_nbm_bias(field, lead_h):
    """Signed per-lead bias to subtract from {field}_l2_nbm. 0.0 when the
    table lacks coverage, the bin is too thin, or the field is out of scope."""
    if field not in L3_NBM_FIELDS:
        return 0.0
    if _TABLE is None:
        return 0.0
    row = _TABLE.get(field)
    if not row or not (0 <= lead_h < LEAD_BINS):
        return 0.0
    bias, n = row[lead_h]
    if bias is None or n < _MIN_PAIRS:
        return 0.0
    return float(bias)


def l3_nbm_wd_components(lead_h):
    """Return (sin_corr, cos_corr) to subtract from (sin(wd_l2_nbm_rad),
    cos(wd_l2_nbm_rad)). Returns (0.0, 0.0) when the bin is too thin, out
    of range, or the curated table lacks wd data — leaves l3_nbm identical
    to l2_nbm in the identity fall-through case."""
    if _WD_TABLE is None or not (0 <= lead_h < LEAD_BINS):
        return (0.0, 0.0)
    sin_c, cos_c, n = _WD_TABLE[lead_h]
    if sin_c is None or cos_c is None or n < _MIN_PAIRS:
        return (0.0, 0.0)
    return (float(sin_c), float(cos_c))

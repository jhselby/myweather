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

from .nbm_common import cap_correction, is_stale


CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "l3_nbm_curated.json"

L3_NBM_FIELDS = ("wg", "h", "ch", "cc", "sr")   # scalar-bias fields
# 2026-08-25 v0.6.472: dropped sr, t, ws — 14d walkforward agg lift vs
# l2_nbm baseline: sr net loss (skip-cells -22% to -5%), t -2.2%, ws -2.5%,
# all with losses at every non-trivial band. wg kept despite walkforward
# proposal — mixed signal (0-5h +3.0%, 24-47h +8.2%, 6-11h -9.1%,
# 12-23h -3.4%); per-cell skip-table review scheduled 2026-08-28.
# dp dropped 2026-08-21 v0.6.465 — pooled per-lead bias (+1°F range at short
# leads) fights close-to-obs L2_NBM in every regime with enough data
# (pre_frontal/sw_flow/se_flow all at -96% to -125% lift 0-5h; per_field_scoring
# 24h showed Prod=2.895 vs L1sel=1.619, 79% worse than the raw NBM selector
# picked). NBM's dp is already well-calibrated at this coord (bias ~0, fc_std
# matches obs_std); no pooled bias should be subtracted. Matches HRRR's decision
# to exclude dp from L3_FIELDS. Selector's dp 6-47h NBM picks now score against
# l2_nbm (identity to raw_nbm since dp has no HRRR L2 delta); may re-evaluate
# on next fit.
L3_NBM_WD = "wd"                          # circular field (sin/cos components)
LEAD_BINS = 48

_TABLE = None      # {field: [(bias, n), ...]} for scalar fields
_WD_TABLE = None   # [(sin_corr, cos_corr, n), ...] length LEAD_BINS
_MIN_PAIRS = 20
_STALE = False
_FITTED_AT = None


def _load():
    global _TABLE, _WD_TABLE, _MIN_PAIRS, _STALE, _FITTED_AT
    try:
        with open(CURATED_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning(f"  ⚠  l3_nbm: curated JSON unavailable ({e}); apply is a no-op")
        _TABLE = {}
        _WD_TABLE = [(None, None, 0)] * LEAD_BINS
        _STALE = False
        _FITTED_AT = None
        return
    _FITTED_AT = data.get("fitted_at")
    _STALE = is_stale(_FITTED_AT)
    if _STALE:
        logging.warning(f"  ⚠  l3_nbm: curated JSON stale (fitted {_FITTED_AT}); apply is a no-op")
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
    return cap_correction(field, float(bias))


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


def describe_applicability():
    """F7 (2026-08-21) — applicability descriptors for L3_NBM. Consumed by
    collector's applicability_map aggregation; rendered on the debug page
    alongside the HRRR L3 descriptors."""
    scalar_fields = [
        {"field": f,
         "fires_when": f"L3_NBM_FIELDS contains {f}; every lead 0-47h when the curated bin has ≥{_MIN_PAIRS} pairs",
         "gated_by": "L3_NBM_FIELDS + curated bin coverage + NBM staleness gate",
         "current_state": ("stale — apply no-op" if _STALE
                           else "firing at every lead where the curated bin is fit")}
        for f in sorted(L3_NBM_FIELDS)
    ]
    wd_desc = {
        "field": L3_NBM_WD,
        "fires_when": f"Circular sin/cos correction from wd_components; every lead 0-47h when the bin has ≥{_MIN_PAIRS} pairs",
        "gated_by": "wd_components curated coverage + NBM staleness gate",
        "current_state": ("stale — apply no-op" if _STALE
                          else "firing at every lead where the wd_components bin is fit"),
    }
    return [{
        "layer_id": "L3_NBM",
        "name": "NBM lead-decay correction",
        "category": "nbm-cascade",
        "fitted_at": _FITTED_AT,
        "stale": _STALE,
        "fields": scalar_fields + [wd_desc],
    }]

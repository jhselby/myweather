"""L4_NBM apply-time processor (option-1 Phase 5, 2026-08-21).

Mirrors HRRR's L4 (hour-of-day diurnal residual) on the NBM cascade.
Reads `weather_collector/data/l4_nbm_curated.json` once at module load
and exposes `l4_nbm_correction(field, hour_of_day)` returning the
signed diurnal bias to subtract from `{field}_l3_nbm`. Returns 0.0
when the table is missing, the field is out of scope, the bin is null,
or the bin has fewer than `min_pairs_per_bin` samples.

Applied inside `forecast_snapshot.stamp()` right after the L3_NBM block,
per hour: `{f}_l4_nbm = {f}_l3_nbm - correction`. Same sign convention
as the HRRR L4 diurnal (decay_apply.py L4 branch).

Scope: `L4_NBM_FIELDS = ("ch",)` — cc dropped v0.6.563 (2026-09-08). Fields
outside this whitelist stay at L3_NBM as their deepest NBM-side layer.

Curated JSON is source-controlled and updated by `analysis/l4_nbm_fit.py`.
Shadow-only until the selector picks the deepest available NBM layer;
the selector currently substitutes `{f}_l3_nbm` (Phase 4), and the
selector's substitution will move to `{f}_l4_nbm` for cc/ch when the
selector fit and forecast_snapshot substitution reach L4-awareness.
"""
import json
import logging
from pathlib import Path

from .nbm_common import cap_correction, is_stale
from .. import runtime_tables


CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "l4_nbm_curated.json"
TABLE_NAME = "l4_nbm_curated.json"   # runtime_tables name (daily GCS refit, bundled fallback)

# 2026-09-08 v0.6.563: dropped cc. Walkforward flagged DROP cc for weeks;
# 30d prep analysis (n=27,313) confirmed layer's total marginal contribution
# is +0.79% pooled (best-possible skip-table +1.38%), not durable across
# cells or windows (verdicts flip week-to-week). Skip-table would be high-
# maintenance for marginal gain; DROP is the right shape. ch kept —
# sentry marginal help strongly positive. See [[l4-nbm-cc-drop-prep]].
L4_NBM_FIELDS = ("ch",)
HOD_BINS = 24

_TABLE = None      # {field: [(correction, n), ...]}, length HOD_BINS
_MIN_PAIRS = 20
_STALE = False
_FITTED_AT = None


def _load():
    global _TABLE, _MIN_PAIRS, _STALE, _FITTED_AT
    global _LOADED_FROM
    data = runtime_tables.get(TABLE_NAME, CURATED_PATH, validate_table)
    _LOADED_FROM = data
    if data is None:
        e = "no usable table (GCS or bundled)"
        logging.warning(f"  ⚠  l4_nbm: curated JSON unavailable ({e}); apply is a no-op")
        _TABLE = {}
        _STALE = False
        _FITTED_AT = None
        return
    _FITTED_AT = data.get("fitted_at")
    _STALE = is_stale(_FITTED_AT)
    if _STALE:
        logging.warning(f"  ⚠  l4_nbm: curated JSON stale (fitted {_FITTED_AT}); apply is a no-op")
        _TABLE = {}
        return
    corrections = data.get("corrections", {}) or {}
    n_samples = data.get("n_samples", {}) or {}
    try:
        _MIN_PAIRS = int(data.get("min_pairs_per_bin", 20))
    except (TypeError, ValueError):
        _MIN_PAIRS = 20
    fused = {}
    for f in L4_NBM_FIELDS:
        corr = corrections.get(f) or [None] * HOD_BINS
        nsam = n_samples.get(f) or [0] * HOD_BINS
        fused[f] = list(zip(corr, nsam))
    _TABLE = fused



def validate_table(data):
    """Structural check shared by the runtime loader and the refitter's
    publish guard. Returns None when usable, else a reason string."""
    if not isinstance(data, dict):
        return "not a JSON object"
    if not data.get("fitted_at"):
        return "missing fitted_at"
    corr = data.get("corrections")
    if not isinstance(corr, dict):
        return "missing corrections"
    for f in L4_NBM_FIELDS:
        row = corr.get(f)
        if not isinstance(row, list) or len(row) != HOD_BINS:
            return f"corrections[{f!r}] missing or not length {HOD_BINS}"
    return None


_LOADED_FROM = None   # identity of the table dict last parsed


def _maybe_reload():
    """Pick up a refit table from GCS without a deploy, and re-apply the
    stale rule on a long-lived instance (it used to run only at import)."""
    if (runtime_tables.get(TABLE_NAME, CURATED_PATH, validate_table) is not _LOADED_FROM
            or (not _STALE and is_stale(_FITTED_AT))):
        _load()


_load()


def l4_nbm_correction(field, hour_of_day):
    """Signed diurnal correction to subtract from {field}_l3_nbm. 0.0 when
    the table lacks coverage, the bin is too thin, or the field is out of
    scope."""
    _maybe_reload()
    if field not in L4_NBM_FIELDS:
        return 0.0
    if _TABLE is None:
        return 0.0
    row = _TABLE.get(field)
    if not row or not (0 <= hour_of_day < HOD_BINS):
        return 0.0
    corr, n = row[hour_of_day]
    if corr is None or n < _MIN_PAIRS:
        return 0.0
    return cap_correction(field, float(corr))


def describe_applicability():
    """F7 (2026-08-21) — applicability descriptors for L4_NBM."""
    fields = [
        {"field": f,
         "fires_when": f"L4_NBM_FIELDS contains {f}; every lead 0-47h when the (field × hour_of_day) bin has ≥{_MIN_PAIRS} pairs",
         "gated_by": "L4_NBM_FIELDS + curated bin coverage + NBM staleness gate",
         "current_state": ("stale — apply no-op" if _STALE
                           else "firing at every lead where the curated bin is fit")}
        for f in sorted(L4_NBM_FIELDS)
    ]
    return [{
        "layer_id": "L4_NBM",
        "name": "NBM diurnal (hour-of-day) correction",
        "category": "nbm-cascade",
        "fitted_at": _FITTED_AT,
        "stale": _STALE,
        "fields": fields,
    }]

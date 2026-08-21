"""Per-cell skip table for the NBM cascade (F5, 2026-08-21).

Mirrors decay_apply._should_skip / SKIP_TABLE for the HRRR side. Loads
`weather_collector/data/skip_table_nbm_curated.json` at import time (with
a lazy reload guard) and exposes `should_skip(field, layer, regime, lead_h)`.

Cell shape in the JSON: `[regime, lead_lo_inclusive, lead_hi_exclusive]`.
Curated from `analysis/nbm_walkforward_validator.py`'s per-band SKIP
proposals; ships with all layer buckets empty so no cell is skipped
until a real per-cell verdict lands.

Fail-safe: unknown regime → False (apply normally), missing file → False.
"""
import json
from pathlib import Path

CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "skip_table_nbm_curated.json"

# Module-level cache: {layer: {field: [(regime, lo, hi), ...]}}
_CELLS = None
_FITTED_AT = None


def _load():
    global _CELLS, _FITTED_AT
    try:
        doc = json.loads(CURATED_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        _CELLS = {}
        _FITTED_AT = None
        return
    _FITTED_AT = doc.get("fitted_at")
    cells = {}
    for layer, per_field in (doc.get("cells") or {}).items():
        cells[layer] = {}
        for field, rows in (per_field or {}).items():
            parsed = []
            for row in rows or []:
                if not isinstance(row, (list, tuple)) or len(row) != 3:
                    continue
                r, lo, hi = row
                try:
                    parsed.append((str(r), int(lo), int(hi)))
                except (TypeError, ValueError):
                    continue
            cells[layer][field] = parsed
    _CELLS = cells


def reload():
    """Force a re-read of the curated file. Called by tests / fit scripts."""
    _load()


def fitted_at():
    if _CELLS is None:
        _load()
    return _FITTED_AT


def describe_applicability():
    """F7 (2026-08-21) — applicability descriptor for the NBM skip table."""
    if _CELLS is None:
        _load()
    cells = _CELLS or {}
    per_layer_counts = {
        lyr: sum(len(rows) for rows in (per_field or {}).values())
        for lyr, per_field in cells.items()
    }
    total = sum(per_layer_counts.values())
    return [{
        "layer_id": "SKIP_TABLE_NBM",
        "name": "NBM per-cell skip table",
        "category": "nbm-cascade",
        "fitted_at": _FITTED_AT,
        "stale": False,
        "fields": [{
            "field": "*",
            "fires_when": (f"per-cell (field × layer × regime × lead-band) skip check "
                           f"called from each NBM apply block; total cells curated: {total}"),
            "gated_by": "curated skip_table_nbm_curated.json entries",
            "current_state": (
                "empty seed — no cells firing" if total == 0
                else "; ".join(f"{lyr}: {n}" for lyr, n in sorted(per_layer_counts.items()) if n)),
        }],
    }]


def should_skip(field, layer, regime, lead_h):
    """Return True if the (field, layer) skip table has a cell matching this
    (regime, lead_h). Fail-safe: unknown regime / lead → False."""
    if regime is None or lead_h is None:
        return False
    if _CELLS is None:
        _load()
    per_field = (_CELLS or {}).get(layer) or {}
    rows = per_field.get(field) or []
    for r, lo, hi in rows:
        if r == regime and lo <= lead_h < hi:
            return True
    return False

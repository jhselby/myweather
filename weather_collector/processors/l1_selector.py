"""L1 selector apply-time processor (option-1 Phase 4, 2026-08-19).

Loads `weather_collector/data/l1_selector_table_curated.json` at module
import; exposes `pick_source(field, lead_h) -> "hrrr" | "nbm"`. Table
schema and pick rule live in `analysis/l1_selector_fit.py`.

Fall-through to "hrrr" when the field or band is out of scope, the
table is unreadable, or the cell hasn't cleared its n/lift floors —
this is the safe default (equal to current Prod behavior pre-Phase-4).

Wired into `forecast_snapshot.stamp()`: for each hour × field, if
`pick_source(field, lead_h) == "nbm"`, replace the user-visible `{field}`
value with `{field}_l3_nbm`. The pair-log joiner stamps the pick as
`{field}_selector_source` so per-row Prod attribution stays correct.

Scope: fields listed in the table's `table` block. Currently t/ws/wg/wd/h.
Everything else falls through to HRRR unconditionally.

Naming note: the layer is called "L1 selector" per the option-1 plan
because it picks between two source cascades (HRRR-side, NBM-side) —
conceptually at L1 even though it applies at the top of the L3 output.
Ripping out the v0.6.432 L1 router happens after this ships and clears
its post-deploy watch.
"""
import json
import logging
from pathlib import Path


CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "l1_selector_table_curated.json"

BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]

_TABLE = {}       # {field: {band: "hrrr"|"nbm"}}
_META = {}        # fitted_at, ship-gate summary, etc.


def _band_for(lead_h):
    for name, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return name
    return None


def _load():
    global _TABLE, _META
    try:
        with open(CURATED_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning(f"  ⚠  l1_selector: curated JSON unavailable ({e}); "
                        f"selector is a no-op (HRRR fall-through)")
        _TABLE = {}
        return
    raw = data.get("table") or {}
    parsed = {}
    for field, cells in raw.items():
        parsed[field] = {band: (cell.get("source") or "hrrr")
                         for band, cell in (cells or {}).items()}
    _TABLE = parsed
    _META = {
        "fitted_at": data.get("fitted_at"),
        "window_days": data.get("window_days"),
        "ship_gate": data.get("ship_gate_router_scope") or {},
    }


_load()


def pick_source(field, lead_h):
    """Return "hrrr" or "nbm" for this (field, lead_h). HRRR fall-through
    on any missing lookup — always safe (equal to pre-Phase-4 Prod)."""
    cells = _TABLE.get(field)
    if not cells:
        return "hrrr"
    band = _band_for(lead_h)
    if band is None:
        return "hrrr"
    return cells.get(band, "hrrr")


def table_meta():
    """Selector table metadata for telemetry (fitted_at + ship-gate summary)."""
    return dict(_META)

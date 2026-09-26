"""L1 static blender — v0.7.6 (2026-09-26, shadow-only).

Universal ω per field applied at the L1 seat (raw HRRR L1 + raw NBM L1),
NO downstream cascade. On 90d pair-log, this beats the live production
stack on covered cells by +18% (h) and +30% (dp) at the halves-B floor
(most recent quartile of the fit corpus). See scratchpad analysis
`blend_final_batch.py`.

Key mechanic difference from the v0.7.0 blender (`l1_selector.blender_omega`):
- v0.7.0 blends the two TERMINAL forecasts (HRRR-l4/l6 vs NBM-l3_nbm),
  keeping the cascades' work.
- v0.7.6 blends the two L1 forecasts (raw_l1 vs raw_nbm) and BYPASSES
  the cascade. The analysis in scratchpad showed that on h/dp, cascade
  applied to a blended L1 input is worse than blend-L1-no-cascade — the
  L2/L3/L4 residual models are source-specific and miscorrect blended
  input. Terminal blending also loses to L1-blend-no-cascade.

Shadow-only initially: stamps `{f}_l1_blend_shadow` on every covered
row regardless of the ENABLED flag. `ENABLED = False` means the stamp
is telemetry, not applied. When ENABLED flips True, covered rows'
entry[f] and applied_layer switch to "l1_blend" for h/dp — replacing
whatever the cascade+selector produced.

Curated table shape (weather_collector/data/l1_static_blend_curated.json):
    {"fields": {
        "h":  {"omega": 0.44, "cells": [["ne_flow","12-23"], ...10 pairs]},
        "dp": {"omega": 0.27, "cells": [...10 pairs]}
    }}
"""
import json
import logging
from pathlib import Path

CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "l1_static_blend_curated.json"

# Shadow-only until 7-day pair-log retro confirms the fitted lift replicates
# on fresh live data. Flip to True in v0.7.7 (or later) after halves-stable
# validation on post-ship pair-log rows. Same discipline as v0.7.0 blender.
ENABLED = False

_OMEGA_BY_FIELD = {}            # {field: omega}
_COVERED_CELLS_BY_FIELD = {}    # {field: frozenset((regime, band))}


def _load():
    global _OMEGA_BY_FIELD, _COVERED_CELLS_BY_FIELD
    try:
        with open(CURATED_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning(f"  ⚠  l1_static_blend: curated JSON unavailable ({e}); apply is a no-op")
        _OMEGA_BY_FIELD = {}
        _COVERED_CELLS_BY_FIELD = {}
        return
    fields = data.get("fields") or {}
    for f, spec in fields.items():
        omega = spec.get("omega")
        cells = spec.get("cells") or []
        if omega is None or not cells:
            continue
        _OMEGA_BY_FIELD[f] = float(omega)
        _COVERED_CELLS_BY_FIELD[f] = frozenset((c[0], c[1]) for c in cells if len(c) == 2)


_load()


def lead_band(lead):
    if lead is None:
        return None
    if lead <= 5:  return "0-5"
    if lead <= 11: return "6-11"
    if lead <= 23: return "12-23"
    if lead <= 47: return "24-47"
    return None


def blend_l1(field, regime, band, fc_l1, fc_raw_nbm):
    """Return the L1 blend for this (field, regime, band) if covered, else None.

    Blend = ω * fc_l1 + (1 - ω) * fc_raw_nbm, with ω the field's universal weight.
    Returns None when: field not curated, cell not in covered set, or either
    forecast is missing. Safe to call unconditionally — no runtime cost outside
    the covered set beyond dict lookups.
    """
    if field not in _OMEGA_BY_FIELD:
        return None
    if regime is None or band is None:
        return None
    if (regime, band) not in _COVERED_CELLS_BY_FIELD[field]:
        return None
    if fc_l1 is None or fc_raw_nbm is None:
        return None
    omega = _OMEGA_BY_FIELD[field]
    return omega * float(fc_l1) + (1.0 - omega) * float(fc_raw_nbm)


def omega_for(field):
    return _OMEGA_BY_FIELD.get(field)


def covered_cells(field):
    return _COVERED_CELLS_BY_FIELD.get(field, frozenset())


def describe_applicability():
    return {
        "enabled": ENABLED,
        "fields": {
            f: {
                "omega": _OMEGA_BY_FIELD[f],
                "n_cells": len(_COVERED_CELLS_BY_FIELD[f]),
                "cells": sorted(list(_COVERED_CELLS_BY_FIELD[f])),
            }
            for f in _OMEGA_BY_FIELD
        },
    }

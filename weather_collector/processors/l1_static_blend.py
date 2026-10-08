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

Stamps `{f}_l1_blend_shadow` on every covered row regardless of the
apply gate, so telemetry accrues for cells that are not yet live.

Apply is gated by TWO things as of v0.7.20 (2026-10-02): the master
`ENABLED` switch and per-cell membership in `APPLIED_CELLS`. Use
`is_applied(field, regime, band)` rather than reading `ENABLED`
directly. For an applied cell, entry[f] / applied_layer / selector_source
switch to "l1_blend" — replacing whatever the cascade+selector produced
and bypassing L2/L3/L4 for that hour.

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

# Master switch. True since v0.7.20 (2026-10-02) — but apply is ALSO gated
# per-cell by APPLIED_CELLS below, so flipping this alone does not make all
# 20 curated cells live.
ENABLED = True

# v0.7.20 (2026-10-02) — narrow apply rollout. A cell applies only when
# ENABLED is True AND its (regime, band) is listed here for that field.
# Every other curated cell keeps stamping {f}_l1_blend_shadow as pure
# telemetry, exactly as it did while the module was shadow-only.
#
# First flip: h / nw_flow / 24-47 only. 10-02 shadow retro on live
# post-v0.7.8 rows: n=436 (curated gate min_n_rows=400), lift vs served
# +35.5%, halves 38.7% / 33.9% — the tightest halves spread of the nine
# SHIP-READY cells. dp / nw_flow / 24-47 cleared n (436) and lift (+17.5%)
# on the same day but its halves spread is 7.7% / 42.4%; held for the 10-03
# verdict rather than flipped on a wide spread.
#
# Second flip, v0.7.23 (2026-10-03) — h / sw_flow / 24-47. Only unflipped
# cell clearing the declared min_n_rows=400 gate: n=830, lift vs served
# +39.0%, halves 41.8% / 35.7% (6.1pt spread, tighter than the first flip's
# 38.7 / 33.9). h/sw_flow/12-23 is the next candidate at n=380 — 20 rows
# short of the gate, halves 50.6 / 40.9 — and should cross within a day or
# two. h/nw_flow/12-23 (n=210) and h/sw_flow/6-11 (n=173) have good lift but
# sit at half the gate or less; not taken. The 10-03 h SUSTAINED FIRE is an
# NBM source break, not a reason to lower the bar.
#
# Reversal: set APPLIED_CELLS = {} (or ENABLED = False) and redeploy.
APPLIED_CELLS = {
    "h": frozenset({("nw_flow", "24-47"), ("sw_flow", "24-47")}),
}

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


def is_applied(field, regime, band):
    """True when this (field, regime, band) is cleared for LIVE apply.

    The narrow-rollout gate: requires the master ENABLED switch AND
    membership in APPLIED_CELLS. Covered-but-not-applied cells still get
    their shadow stamp from the caller — this governs only whether the
    blend replaces the served forecast. Callers must use this instead of
    reading ENABLED, or they will apply every curated cell.
    """
    if not ENABLED:
        return False
    cells = APPLIED_CELLS.get(field)
    if not cells:
        return False
    return (regime, band) in cells


def applied_cells(field):
    return APPLIED_CELLS.get(field, frozenset())


def omega_for(field):
    return _OMEGA_BY_FIELD.get(field)


def covered_cells(field):
    return _COVERED_CELLS_BY_FIELD.get(field, frozenset())


def describe_applicability():
    """Applicability descriptor for L1b (L1 static blender). Returns a list of
    layer dicts matching applicability_map_schema.json; one per-field entry
    per curated field."""
    fields = []
    for f in sorted(_OMEGA_BY_FIELD):
        covered = sorted(_COVERED_CELLS_BY_FIELD.get(f, frozenset()))
        applied = sorted(APPLIED_CELLS.get(f, frozenset())) if ENABLED else []
        fmt = lambda cells: ", ".join(f"{r}/{b}" for r, b in cells) or "none"
        fields.append({
            "field": f,
            "fires_when": (
                f"ENABLED AND (regime, lead band) in APPLIED_CELLS[{f!r}]: serves "
                f"ω·raw_l1 + (1−ω)·raw_nbm with ω={_OMEGA_BY_FIELD[f]}, bypassing L2/L3/L4"
            ),
            "gated_by": "ENABLED + APPLIED_CELLS",
            "current_state": (
                f"Applied on {len(applied)} of {len(covered)} curated cells ({fmt(applied)}); "
                f"the rest stamp {f}_l1_blend_shadow only."
                if ENABLED else
                f"ENABLED False; all {len(covered)} curated cells stamp {f}_l1_blend_shadow only."
            ),
        })
    return [
        {
            "layer_id": "L1b",
            "name": "L1 static blender (HRRR/NBM raw blend)",
            "category": "general-purpose",
            "fields": fields,
        }
    ]

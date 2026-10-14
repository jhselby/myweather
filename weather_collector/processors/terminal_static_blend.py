"""Terminal static blend (v0.7.57).

served = w * HRRR_terminal + (1 - w) * NBM_terminal, per (field, regime, band),
with w from weather_collector/data/terminal_static_blend_curated.json (written
by analysis/terminal_blend_fit.py). Terminals are the same ones the v0.7.0
learned blender uses in forecast_snapshot (HRRR l6/l5/l4 by field, NBM
l3_nbm > l2_nbm > raw_nbm), so the blend sits on top of both correction
cascades instead of choosing one.

Why: 10-14 retro (30d, prod-vs-prod) — the binary selector captures under
10% of the oracle routing gap and picks the better cascade ~55% of rows.
A 50/50 average of the two corrected terminals beat the better fixed routing
by t +10.7%, sr +14.6%, h +20.9% (both halves). The fit keeps only cells
whose weight, fit on one half of the month, still lifts >= 5% vs the served
forecast on the other half (both directions), n >= 400, 0.05 < w < 0.95.

Every covered cell stamps {f}_tblend_shadow (+ _w_shadow) for verification.
A cell replaces the served forecast only when listed in APPLIED_CELLS.
Reversal: APPLIED_CELLS = {} and redeploy.
"""
import json
import logging
from pathlib import Path

CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "terminal_static_blend_curated.json"

ENABLED = True

# v0.7.57 — apply every passing cell for t, sr, ws. h stays shadow-only:
# its L1 static blend (l1_static_blend.APPLIED_CELLS) owns h until the two
# blends are compared on fresh shadow rows. wg: no cell passed.
APPLIED_FIELDS = frozenset({"t", "sr", "ws"})

_W = {}  # {field: {(regime, band): w}}


def _load():
    global _W
    try:
        doc = json.loads(CURATED_PATH.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logging.warning(f"  ⚠  terminal_static_blend: curated JSON unavailable ({e}); no-op")
        _W = {}
        return
    out = {}
    for f, spec in (doc.get("fields") or {}).items():
        cells = {}
        for c in spec.get("cells") or []:
            w = c.get("w")
            if c.get("regime") and c.get("band") and w is not None and 0.0 < float(w) < 1.0:
                cells[(c["regime"], c["band"])] = float(w)
        if cells:
            out[f] = cells
    _W = out


_load()


def weight(field, regime, band):
    """Curated w for this cell, or None when not covered."""
    if regime is None or band is None:
        return None
    return (_W.get(field) or {}).get((regime, band))


def blend(field, regime, band, hrrr_term, nbm_term):
    w = weight(field, regime, band)
    if w is None or hrrr_term is None or nbm_term is None:
        return None
    return w * float(hrrr_term) + (1.0 - w) * float(nbm_term)


def is_applied(field, regime, band):
    return bool(ENABLED and field in APPLIED_FIELDS and weight(field, regime, band) is not None)


def covered_cells(field):
    return frozenset((_W.get(field) or {}).keys())

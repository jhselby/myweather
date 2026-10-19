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

# v0.7.57 — apply every passing cell for t, sr, ws. wg: no cell passed.
# v0.7.58 — h: the 5 passing terminal cells the L1 static blend does NOT
# apply. 30d head-to-head on L1-blend-stamped rows: on the 6 L1-applied
# cells the two blends tie (keep L1); where L1 is not applied the terminal
# blend wins (sw_flow/12-23 +31.1% vs L1 +20.9%, nw_flow/12-23 +17.0% vs
# +4.3%, ne_flow/12-23 +44.7% vs +36.0%). frontal/24-47 and nw_flow/0-5
# have no L1 cell. L1 apply runs first in forecast_snapshot, so these never
# overlap an L1-applied hour.
# v0.7.69 — ws 6-11 dropped: live 10-14..10-19 the blend lost to the NBM it
# pre-empts (nw_flow -8.8% n=277, pre_frontal -47% n=48). ws 24-47 kept
# (frontal +2.2% n=168, pre_frontal +4.7% n=166).
ALL = "all"
APPLIED = {
    "t": ALL, "sr": ALL,
    "ws": frozenset({("frontal", "24-47"), ("pre_frontal", "24-47")}),
    "h": frozenset({("frontal", "24-47"), ("ne_flow", "12-23"), ("nw_flow", "0-5"),
                    ("nw_flow", "12-23"), ("sw_flow", "12-23")}),
}

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
    if not ENABLED or weight(field, regime, band) is None:
        return False
    cells = APPLIED.get(field)
    return cells == ALL or (cells is not None and (regime, band) in cells)


def covered_cells(field):
    return frozenset((_W.get(field) or {}).keys())


def describe_applicability():
    """Applicability descriptor for the terminal static blend (v0.7.62)."""
    fields = []
    for f in sorted(_W):
        cells = sorted(_W[f])
        ap = APPLIED.get(f)
        applied = cells if ap == ALL else sorted(c for c in cells if ap and c in ap)
        fmt = lambda cs: ", ".join(f"{r}/{b} w={_W[f][(r, b)]:.2f}" for r, b in cs) or "none"
        fields.append({
            "field": f,
            "fires_when": ("ENABLED AND (regime_runtime, lead band) is an applied curated cell: serves "
                           "w·HRRR terminal + (1−w)·NBM terminal (pre-empts the selector's pick)"),
            "gated_by": "ENABLED + APPLIED",
            "current_state": (f"Applied on {len(applied)} of {len(cells)} curated cells ({fmt(applied)}); "
                              f"the rest stamp {f}_tblend_shadow only." if ENABLED else
                              f"ENABLED False; {len(cells)} curated cells stamp {f}_tblend_shadow only."),
        })
    return [{
        "layer_id": "TB",
        "name": "Terminal static blend (HRRR/NBM corrected-output blend)",
        "category": "general-purpose",
        "fields": fields,
    }]


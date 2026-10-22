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

# v0.7.71 — field-level blend: one w per field, served on EVERY row of these
# fields ahead of the per-cell blend, the L1 static blend and the selector
# pick. 10-20 walk-forward (w fit on the prior 14d, next day scored vs what
# shipped, 17 days): h +12.2%, sr +11.2%, t +4.2%, wg +3.3%. w is refit daily
# by myweather-refitter (analysis/terminal_blend_field_fit.py) into
# runtime_tables/; a table older than FIELD_STALE_DAYS goes no-op and the
# per-cell path below takes over again. Reversal: FIELD_APPLIED = frozenset().
FIELD_APPLIED = frozenset({"t", "h", "sr", "wg"})
FIELD_TABLE_NAME = "terminal_blend_field_curated.json"
FIELD_PATH = Path(__file__).resolve().parent.parent / "data" / FIELD_TABLE_NAME
FIELD_STALE_DAYS = 3


def validate_field_table(data):
    """Structural check shared by the runtime loader and the refitter guard."""
    if not isinstance(data, dict):
        return "not a JSON object"
    if not data.get("fitted_at"):
        return "missing fitted_at"
    fields = data.get("fields")
    if not isinstance(fields, dict) or not fields:
        return "missing fields"
    for f, spec in fields.items():
        w = (spec or {}).get("w")
        if not isinstance(w, (int, float)) or not 0.0 <= float(w) <= 1.0:
            return f"fields[{f!r}].w missing or outside [0, 1]"
        for key in ("w_by_block", "w_by_band"):
            for h, bw in ((spec or {}).get(key) or {}).items():
                if not isinstance(bw, (int, float)) or not 0.0 <= float(bw) <= 1.0:
                    return f"fields[{f!r}].{key}[{h!r}] outside [0, 1]"
        w3s = [("w3", (spec or {}).get("w3"))] if (spec or {}).get("w3") is not None else []
        for key in ("w3_by_band", "w3_by_block"):
            w3s += [(f"{key}[{k!r}]", v) for k, v in ((spec or {}).get(key) or {}).items()]
        for name, w3 in w3s:
            if not _valid_w3(w3):
                return f"fields[{f!r}].{name} not three weights in [0, 1] summing to 1"
    return None


def _valid_w3(w3):
    return (isinstance(w3, list) and len(w3) == 3
            and all(isinstance(x, (int, float)) and 0.0 <= float(x) <= 1.0 for x in w3)
            and abs(sum(float(x) for x in w3) - 1.0) < 1e-6)


# v0.7.75 — ECMWF IFS raw as the third input on t and h. 10-22 walk-forward
# (fit prior 14d, next day scored, 17 days) vs the shipped 2-way rule:
# t +19.1% (halves +14.4/+23.0, 13/17 days), h +11.5% (+7.3/+16.2, 13/17).
# Reversal: FIELD3_APPLIED = frozenset() and redeploy (2-way serves again).
FIELD3_APPLIED = frozenset({"t", "h"})


def _field_spec(field):
    from datetime import datetime, timedelta
    from .. import runtime_tables
    doc = runtime_tables.get(FIELD_TABLE_NAME, FIELD_PATH, validate_field_table)
    if not doc:
        return None
    try:
        fitted = datetime.strptime(doc["fitted_at"][:16], "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    if datetime.utcnow() - fitted > timedelta(days=FIELD_STALE_DAYS):
        return None
    return (doc.get("fields") or {}).get(field) or None


def field_weight3(field, hour=None, band=None):
    """[w_hrrr, w_nbm, w_ecmwf] for the 3-way field blend, or None when the
    field is not in FIELD3_APPLIED or the table has no w3 (the 2-way
    field_weight then serves). t keys on lead band, h on 4h block."""
    if field not in FIELD3_APPLIED or field not in FIELD_APPLIED:
        return None
    spec = _field_spec(field)
    if not spec or spec.get("w3") is None:
        return None
    w3 = (spec.get("w3_by_band") or {}).get(band) if band else None
    if w3 is None and hour is not None and spec.get("w3_by_block"):
        step = int(spec.get("block_hours") or 4)
        w3 = spec["w3_by_block"].get(str(int(hour) // step * step))
    return [float(x) for x in (w3 or spec["w3"])]


def field_weight(field, hour=None, band=None):
    """HRRR weight for the field-level blend, or None when the field is not
    applied, the table is missing, or it is stale. v0.7.73: with `hour`
    (local valid hour), h and sr use the w of that hour's block when the
    table has one (`w_by_block`), else the field w. v0.7.74: with `band`
    (lead band name), t uses the w of that band (`w_by_band`)."""
    if field not in FIELD_APPLIED:
        return None
    spec = _field_spec(field)
    if not spec:
        return None
    bw = (spec.get("w_by_band") or {}).get(band) if band else None
    if bw is not None:
        return float(bw)
    blocks = spec.get("w_by_block") or {}
    if hour is not None and blocks:
        step = int(spec.get("block_hours") or 4)
        bw = blocks.get(str(int(hour) // step * step))
        if bw is not None:
            return float(bw)
    return float(spec["w"])


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
    for f in sorted(FIELD_APPLIED):
        w = field_weight(f)
        fields.append({
            "field": f,
            "fires_when": ("every row (v0.7.71 field-level blend): serves w·HRRR terminal + "
                           "(1−w)·NBM terminal ahead of the selector pick, L1 blend and cell blends"),
            "gated_by": "FIELD_APPLIED + daily refit ≤ 3 days old",
            "current_state": (f"Live, w_hrrr={w:.2f}" + (
                f"; 3-way with ECMWF w3={field_weight3(f)}" if field_weight3(f) else "")
                if w is not None else
                              "No-op: field table missing or stale; per-cell path below serves"),
        })
    for f in sorted(_W):
        if f in FIELD_APPLIED and field_weight(f) is not None:
            continue
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


"""URMA-truth bias-then-blend for t (v0.8.0 rebuild branch). Stamps `t_urmab`; SERVED since v0.7.114.

For t at leads 6-47h: per source (HRRR L1, NBM raw, ECMWF raw) subtract its trailing bias against
URMA (independent truth, not built from our forecast), then blend with weights fit on those
bias-corrected errors. Written by analysis/urma_blend_table_fit.py into
weather_collector/data/urma_blend_shadow_curated.json (refit daily by myweather-refitter once
registered). Walk-forward on 67 days: +11.4% (6-11h), +17.7% (12-23h), +16.6% (24-47h) vs served on
URMA truth, both halves positive; holdout (9 days) intervals still span zero, so this stamps
`t_urmab` for the pair log and changes NOTHING served. Pair log emits forecast_urmab / error_urmab.

Ship tiers (fixed 11-12): forward shadow days only; >= 5 of 7 days beating served with a positive
median, 6-47h only, auto-revert tripwire, then analysis/ship_rule.py at >= 14 holdout days.
Reversal: ENABLED = False (stamps nothing) or serving off. Serving is gated by SERVE and by the
runtime doc urma_blend_serve.json {"serve": bool} (gs://myweather-data/runtime_tables/, bundled copy
in data/), so a revert needs no deploy: gsutil cp a {"serve": false} doc. When served, the old served
t is kept as `t_pre_urmab` (pair log error_pre_urmab) so analysis/urma_shadow_score.py keeps scoring
the blend against what users would have seen without it.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

ENABLED = True
TABLE_NAME = "urma_blend_shadow_curated.json"
TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / TABLE_NAME
SERVE = True
SERVE_TABLE = "urma_blend_serve.json"
SERVE_PATH = Path(__file__).resolve().parent.parent / "data" / SERVE_TABLE
STALE_DAYS = 4
BANDS = (("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48))
WG_BANDS = (("0-5", 0, 6),) + BANDS   # v0.7.125: the wg shadow also covers 0-5h


def validate_table(doc):
    """None when usable, else the reason. fields.t is required; fields.ws (v0.7.123) is optional."""
    try:
        fields = doc["fields"]
        cells = fields["t"]["bands"]
    except (KeyError, TypeError):
        return "missing fields.t.bands"
    if not cells:
        return "no bands"
    for f in ("t", "ws", "wg"):
        if f not in fields:
            continue
        for b, c in (fields[f].get("bands") or {}).items():
            w, bias = c.get("w"), c.get("bias")
            if not (isinstance(w, list) and len(w) == 3 and isinstance(bias, list) and len(bias) == 3):
                return f"{f} band {b}: w/bias must be length-3 lists"
            if abs(sum(w) - 1.0) > 0.01 or min(w) < -1e-9:
                return f"{f} band {b}: weights not on the simplex"
            if any(abs(x) > 15 for x in bias):
                return f"{f} band {b}: |bias| > 15"
    return None


def _band(lead_h, bands=BANDS):
    return next((b for b, lo, hi in bands if lo <= lead_h < hi), None)


def _fresh(doc):
    try:
        t = datetime.strptime(doc["fitted_at"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    except (KeyError, ValueError, TypeError):
        return False
    return (datetime.now(timezone.utc) - t).days <= STALE_DAYS


def stamp(entry, lead_h):
    """Stamp entry['t_urmab'] at 6-47h, and the shadows entry['ws_urmab'] (6-47h, v0.7.123) and
    entry['wg_urmab'] (0-47h, v0.7.125; HRRR/NBM only, ECMWF weight 0) when the inputs and a fresh
    table exist. Only t is ever served; the pair log scores the others as forecast_urmab."""
    if not ENABLED or _band(lead_h, WG_BANDS) is None:
        return
    try:
        from .. import runtime_tables
        doc = runtime_tables.get(TABLE_NAME, TABLE_PATH, validate_table)
    except Exception as e:  # noqa: BLE001
        logging.warning(f"  ⚠  urma_blend_shadow: table load failed ({e})")
        return
    if not doc or not _fresh(doc):
        return
    for f, floor, bands in (("t", None, BANDS), ("ws", 0.0, BANDS), ("wg", 0.0, WG_BANDS)):
        band = _band(lead_h, bands)
        cell = ((doc["fields"].get(f) or {}).get("bands") or {}).get(band) if band else None
        if not cell:
            continue
        w, bias = cell["w"], cell["bias"]
        xs = (entry.get(f"{f}_l1"), entry.get(f"{f}_raw_nbm"), entry.get(f"{f}_ecmwf"))
        if any(x is None and wi > 0 for x, wi in zip(xs, w)):
            continue
        v = sum(wi * (float(x) - bi) for wi, x, bi in zip(w, xs, bias) if wi > 0)
        entry[f"{f}_urmab"] = round(v if floor is None else max(floor, v), 1)


def _valid_serve(doc):
    return None if isinstance(doc, dict) and isinstance(doc.get("serve"), bool) else "serve must be a bool"


def serving():
    """True when t_urmab replaces served t. Fails closed (False) if the switch doc cannot be read."""
    if not (ENABLED and SERVE):
        return False
    try:
        from .. import runtime_tables
        doc = runtime_tables.get(SERVE_TABLE, SERVE_PATH, _valid_serve)
    except Exception as e:  # noqa: BLE001
        logging.warning(f"  ⚠  urma_blend_shadow: serve switch unreadable ({e}); not serving")
        return False
    return bool(doc and doc.get("serve"))


def apply(entry):
    """Serve t_urmab in place of t. Keeps the replaced value as t_pre_urmab. True when it fired."""
    tu, told = entry.get("t_urmab"), entry.get("t")
    if tu is None or told is None or not serving():
        return False
    entry["t_pre_urmab"] = told
    entry["t_preempted_source_shadow"] = entry.get("t_selector_source")
    entry["t"] = tu
    entry["t_applied"] = "urmab"
    entry["t_selector_source"] = "urmab"
    return True

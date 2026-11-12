"""URMA-truth bias-then-blend, SHADOW ONLY (v0.8.0 rebuild branch).

For t at leads 6-47h: per source (HRRR L1, NBM raw, ECMWF raw) subtract its trailing bias against
URMA (independent truth, not built from our forecast), then blend with weights fit on those
bias-corrected errors. Written by analysis/urma_blend_table_fit.py into
weather_collector/data/urma_blend_shadow_curated.json (refit daily by myweather-refitter once
registered). Walk-forward on 67 days: +11.4% (6-11h), +17.7% (12-23h), +16.6% (24-47h) vs served on
URMA truth, both halves positive; holdout (9 days) intervals still span zero, so this stamps
`t_urmab` for the pair log and changes NOTHING served. Pair log emits forecast_urmab / error_urmab.

Ship tiers (fixed 11-12): forward shadow days only; >= 5 of 7 days beating served with a positive
median, 6-47h only, auto-revert tripwire, then analysis/ship_rule.py at >= 14 holdout days.
Reversal: ENABLED = False.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

ENABLED = True
TABLE_NAME = "urma_blend_shadow_curated.json"
TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / TABLE_NAME
STALE_DAYS = 4
BANDS = (("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48))


def validate_table(doc):
    """None when usable, else the reason."""
    try:
        cells = doc["fields"]["t"]["bands"]
    except (KeyError, TypeError):
        return "missing fields.t.bands"
    if not cells:
        return "no bands"
    for b, c in cells.items():
        w, bias = c.get("w"), c.get("bias")
        if not (isinstance(w, list) and len(w) == 3 and isinstance(bias, list) and len(bias) == 3):
            return f"band {b}: w/bias must be length-3 lists"
        if abs(sum(w) - 1.0) > 0.01 or min(w) < -1e-9:
            return f"band {b}: weights not on the simplex"
        if any(abs(x) > 15 for x in bias):
            return f"band {b}: |bias| > 15 F"
    return None


def _band(lead_h):
    return next((b for b, lo, hi in BANDS if lo <= lead_h < hi), None)


def _fresh(doc):
    try:
        t = datetime.strptime(doc["fitted_at"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    except (KeyError, ValueError, TypeError):
        return False
    return (datetime.now(timezone.utc) - t).days <= STALE_DAYS


def stamp(entry, lead_h):
    """Stamp entry['t_urmab'] for t at 6-47h when all three inputs and a fresh table exist."""
    if not ENABLED:
        return
    band = _band(lead_h)
    if band is None:
        return
    hr, nb, ec = entry.get("t_l1"), entry.get("t_raw_nbm"), entry.get("t_ecmwf")
    if hr is None or nb is None or ec is None:
        return
    try:
        from .. import runtime_tables
        doc = runtime_tables.get(TABLE_NAME, TABLE_PATH, validate_table)
    except Exception as e:  # noqa: BLE001
        logging.warning(f"  ⚠  urma_blend_shadow: table load failed ({e})")
        return
    if not doc or not _fresh(doc):
        return
    cell = doc["fields"]["t"]["bands"].get(band)
    if not cell:
        return
    w, bias = cell["w"], cell["bias"]
    entry["t_urmab"] = round(sum(wi * (float(x) - bi) for wi, x, bi in zip(w, (hr, nb, ec), bias)), 1)

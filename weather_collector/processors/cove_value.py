"""Cove value (v0.7.138, SHADOW): the Mesonet reading plus an adjustment learned from the Cove-side station.

The Mesonet cannot show the Cove's damped daily swing (warmer nights, cooler days), so a table refit daily by
myweather-refitter (analysis/mesonet_cove_adjust_fit.py) gives, per ET hour, how far Neptune Rd runs from the
Mesonet. Stamps hyperlocal.cove_temp / cove_humidity / cove_dew_point and the adjustments used. Nothing served or
scored reads these; they are logged next to the Mesonet value in the station archive for the Cove-side test
(plan 1.8). Fails closed: no fresh table, no stamp.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ENABLED = True
TABLE_NAME = "mesonet_cove_adjust_curated.json"
TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / TABLE_NAME
STALE_DAYS = 4
_ET = ZoneInfo("America/New_York")


def validate_table(doc):
    try:
        fields = doc["fields"]
    except (KeyError, TypeError):
        return "missing fields"
    if not isinstance(fields, dict) or "t" not in fields:
        return "fields.t required"
    for f, v in fields.items():
        hr = (v or {}).get("hourly")
        if not isinstance(hr, dict) or not hr:
            return f"{f}: no hourly values"
        for h, a in hr.items():
            if not (h.isdigit() and 0 <= int(h) <= 23) or not isinstance(a, (int, float)):
                return f"{f}: bad hour entry {h!r}"
            if abs(a) > (15 if f == "t" else 40):
                return f"{f}: |adjustment| too large at hour {h}"
    return None


def _fresh(doc, now):
    try:
        t = datetime.strptime(doc["fitted_at"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    except (KeyError, ValueError, TypeError):
        return False
    return (now - t).days <= STALE_DAYS


def apply(hyperlocal, now_utc=None):
    """Stamp the Cove value on the hyperlocal dict. Never raises."""
    if not ENABLED or not isinstance(hyperlocal, dict):
        return
    now_utc = now_utc or datetime.now(timezone.utc)
    try:
        from .. import runtime_tables
        doc = runtime_tables.get(TABLE_NAME, TABLE_PATH, validate_table)
        if not doc or not _fresh(doc, now_utc):
            return
        hr = str(now_utc.astimezone(_ET).hour)
        t_adj = (doc["fields"].get("t") or {}).get("hourly", {}).get(hr)
        mt = hyperlocal.get("station_temp")
        if t_adj is not None and mt is not None:
            hyperlocal["cove_temp"] = round(float(mt) + t_adj, 1)
            hyperlocal["cove_adjust_t"] = round(t_adj, 2)
        h_adj = (doc["fields"].get("h") or {}).get("hourly", {}).get(hr)
        mh = hyperlocal.get("station_humidity")
        if h_adj is not None and mh is not None:
            hyperlocal["cove_humidity"] = round(max(0.0, min(100.0, float(mh) + h_adj)), 1)
            hyperlocal["cove_adjust_h"] = round(h_adj, 2)
        if hyperlocal.get("cove_temp") is not None and hyperlocal.get("cove_humidity") is not None:
            from ..utils import magnus_dew_point_f
            dp = magnus_dew_point_f(hyperlocal["cove_temp"], hyperlocal["cove_humidity"])
            if dp is not None:
                hyperlocal["cove_dew_point"] = round(dp, 1)
        hyperlocal["cove_table_fitted"] = doc.get("fitted_at")
    except Exception as e:  # noqa: BLE001
        logging.warning(f"  ⚠  cove_value failed ({e})")

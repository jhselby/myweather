"""
Long-retention water-temperature log: GoMOFS (Cove cell) beside the two
Mass Bay buoys, one row per hour, never pruned. Exists because
cove_gradient_log.json keeps only 14 days and the GoMOFS-vs-buoy bias
moves with conditions (11-25: +1.7 F on 11-11..13, ~0 on 11-16..22).

ts is America/New_York local, same as cove_gradient_log. First run seeds
from cove_gradient_log's :0x ticks so the first 14 days are not lost.
"""
from datetime import datetime

import pytz

from ..fetchers.salem_water import fetch_buoy_44029_water_f
from ..gcs_io import load_json, upload_json


GCS_PATH = "water_temp_log.json"
TZ = pytz.timezone("America/New_York")


def _seed():
    old = load_json("cove_gradient_log.json", default={"entries": []}) or {}
    rows = []
    for e in old.get("entries", []):
        ts = e.get("ts", "")
        if len(ts) == 16 and ts[14:16] < "10":
            rows.append({"ts": ts[:13] + ":00", "gomofs_f": e.get("salem_water_t"),
                         "b44013_f": e.get("buoy_water_t"), "b44029_f": None})
    return rows


def append_water_temp(weather_data):
    """Append one hourly row (called every tick; acts only on the first tick of the hour)."""
    now = datetime.now(TZ)
    if now.minute >= 10:
        return
    ts = now.strftime("%Y-%m-%dT%H:00")
    log = load_json(GCS_PATH, default=None)
    entries = log.get("entries") if log else _seed()
    if entries and entries[-1]["ts"] >= ts:
        return
    entries.append({
        "ts": ts,
        "gomofs_f": weather_data.get("salem_water_temp_f"),
        "b44013_f": (weather_data.get("buoy_44013") or {}).get("water_temp_f"),
        "b44029_f": fetch_buoy_44029_water_f(),
    })
    upload_json({"entries": entries}, GCS_PATH, "water_temp_log.json")

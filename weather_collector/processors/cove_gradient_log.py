"""
Rolling log for the cove-gradient hypothesis: is the temperature
differential (waterfront stations − inland stations) correlated with
the land-water thermal gap (air T − Salem Channel water T)?

Per-tick capture of:
  - Waterfront-tagged Tempest temps (Neptune Rd, Willow Rd, etc)
  - Inland Tempest median temp (everything not waterfront)
  - GoMOFS Salem Channel water temp
  - Current ambient temp + wind direction + sea-breeze active flag

Analysis (after ~5-7 days):
  Y = waterfront_median - inland_median
  X = ambient_T - water_T
  Stratify by wind regime and sea-breeze active state.

Append-only, 14-day retention.
"""
from datetime import datetime, timedelta
from statistics import median

import pytz

from ..gcs_io import load_json, upload_json


GCS_PATH = "cove_gradient_log.json"
RETENTION_DAYS = 14
TZ = pytz.timezone("America/New_York")


def _med(xs):
    xs = [x for x in xs if x is not None]
    return round(median(xs), 2) if xs else None


def append_cove_snapshot(weather_data):
    """Capture one tick of the cove-gradient measurement."""
    tempest_stations = (weather_data.get("tempest") or {}).get("stations") or []
    if not tempest_stations:
        return

    waterfront_temps = []
    waterfront_names = []
    inland_temps = []
    for s in tempest_stations:
        t = s.get("temperature_f")
        if t is None or not s.get("valid"):
            continue
        if s.get("waterfront"):
            waterfront_temps.append(t)
            waterfront_names.append(s.get("station_name"))
        else:
            inland_temps.append(t)

    if not waterfront_temps or not inland_temps:
        return

    cur = weather_data.get("current") or {}
    sb = weather_data.get("sea_breeze") or {}

    now_local = datetime.now(TZ)
    ts = now_local.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    cutoff = (now_local - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")

    entry = {
        "ts": ts,
        "waterfront_t_med": _med(waterfront_temps),
        "waterfront_n": len(waterfront_temps),
        "waterfront_names": waterfront_names,
        "inland_t_med": _med(inland_temps),
        "inland_n": len(inland_temps),
        "ambient_t": cur.get("temperature"),
        "wind_dir": cur.get("wind_direction"),
        "wind_speed": cur.get("wind_speed"),
        "salem_water_t": weather_data.get("salem_water_temp_f"),
        "buoy_water_t": (weather_data.get("buoy_44013") or {}).get("water_temp_f"),
        "sb_active": sb.get("active"),
        "sb_likelihood": sb.get("likelihood"),
    }

    # Drop the diff for convenience
    if entry["waterfront_t_med"] is not None and entry["inland_t_med"] is not None:
        entry["delta_wf_inland"] = round(entry["waterfront_t_med"] - entry["inland_t_med"], 2)
    if entry["ambient_t"] is not None and entry["salem_water_t"] is not None:
        entry["land_water_gap"] = round(entry["ambient_t"] - entry["salem_water_t"], 2)

    log = load_json(GCS_PATH, default={"entries": []})
    entries = [e for e in log.get("entries", []) if e.get("ts", "") >= cutoff]
    entries.append(entry)
    upload_json({"entries": entries}, GCS_PATH, "cove_gradient_log.json")

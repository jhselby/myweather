"""
Per-station reading archive (v0.7.94). Logging only: nothing served or scored
reads it.

Why: L2 is graded on the same station network that feeds it, so a score
cannot tell real skill at the Cove from the network agreeing with itself.
The clean test splits the network (half feeds L2, half is truth), which
needs every station's reading on every tick. Nothing else keeps them:
station_history.json holds 48 h and the pair log holds only the aggregate.

One GCS file per UTC day, `station_readings/YYYY-MM-DD.json`, kept
permanently (no lifecycle rule on the bucket; the weekly backup copies it).
Each tick stores the raw Tempest readings, the per-station offsets L2 applied
that tick, and the L2 anchors (model value, network bias, gain), so the
octant aggregate can be rebuilt for any subset of stations. Station location
metadata is stored once per file under "stations".
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..gcs_io import load_json, upload_json
from ..utils import redact_secrets

GCS_PREFIX = "station_readings/"
_EASTERN = ZoneInfo("America/New_York")

# Tempest key -> short archive key
_READING_KEYS = {
    "temperature_f": "t",
    "dew_point_f": "dp",
    "relative_humidity": "rh",
    "sea_level_pressure_mb": "p_mb",
    "wind_avg_mph": "ws",
    "wind_gust_mph": "wg",
    "wind_lull_mph": "wl",
    "wind_direction": "wd",
    "solar_radiation_wm2": "sr",
    "precip_rate_in": "pr",
    "precip_accum_1hr_in": "pa1h",
}
_META_KEYS = ("station_name", "waterfront", "latitude", "longitude", "elevation_ft", "distance_mi")
_ANCHOR_KEYS = ("model_temp", "weighted_bias", "kalman_gain", "station_temp", "bias_std",
                "model_humidity", "weighted_bias_humidity", "kalman_gain_humidity", "station_humidity",
                "aggregation", "octants_used", "stations_used")


def _applied_offsets(station_offsets, now_utc):
    """Same merge hyperlocal.build_hyperlocal_data uses: day/night temp split
    overrides the combined table."""
    offs = station_offsets or {}
    is_day = 7 <= now_utc.astimezone(_EASTERN).hour < 19
    temp = {**offs.get("temp", {}), **offs.get("temp_day" if is_day else "temp_night", {})}
    return temp, offs.get("humidity", {}), offs.get("pressure", {})


def build_entry(weather_data, tempest_data, station_offsets, now_utc):
    stations = (tempest_data or {}).get("stations") or []
    if not stations:
        return None, {}
    temp_o, hum_o, pres_o = _applied_offsets(station_offsets, now_utc)
    readings, meta = {}, {}
    for s in stations:
        sid = str(s.get("station_id") or s.get("station_name") or "")
        if not sid:
            continue
        row = {"valid": bool(s.get("valid")), "age_min": s.get("age_minutes")}
        for src, dst in _READING_KEYS.items():
            v = s.get(src)
            if v is not None:
                row[dst] = v
        for dst, table in (("off_t", temp_o), ("off_rh", hum_o), ("off_p", pres_o)):
            if sid in table:
                row[dst] = table[sid]
        readings[sid] = row
        meta[sid] = {k: s.get(k) for k in _META_KEYS}
    hyp = weather_data.get("hyperlocal") or {}
    entry = {
        "ts": now_utc.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%MZ"),
        "l2": {k: hyp.get(k) for k in _ANCHOR_KEYS if hyp.get(k) is not None},
        "readings": readings,
    }
    return entry, meta


def append_station_readings(weather_data, tempest_data, station_offsets, now_utc=None):
    """Append this tick's per-station readings to today's archive file.
    Best-effort: failures log a warning and never affect the run."""
    now_utc = now_utc or datetime.now(timezone.utc)
    try:
        entry, meta = build_entry(weather_data, tempest_data, station_offsets, now_utc)
        if entry is None:
            return
        path = f"{GCS_PREFIX}{now_utc.strftime('%Y-%m-%d')}.json"
        doc = load_json(path, default=None) or {"schema": 1, "stations": {}, "ticks": []}
        doc["stations"].update(meta)
        if doc["ticks"] and doc["ticks"][-1].get("ts") == entry["ts"]:
            doc["ticks"][-1] = entry  # rerun of the same tick
        else:
            doc["ticks"].append(entry)
        upload_json(doc, path, path)
        logging.info(f"  ✓ station_readings: {len(entry['readings'])} stations, "
                     f"{len(doc['ticks'])} ticks today")
    except Exception as e:
        logging.warning(f"  ⚠  station_readings log failed: {redact_secrets(e)}")

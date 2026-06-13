"""
Per-tick snapshot of the inputs to the correction stack. Captures raw L1
model forecast arrays (lead 0-47h) and current station observations so
the backtest framework can replay any tick under any config.

Storage: one file per day at gs://myweather-data/backtest_snapshots/YYYY-MM-DD.json,
shape {"entries": [...]}. Per-day separation makes 14-day retention a
simple delete-old-files loop and keeps any single file under ~5 MB.

Snapshot schema is versioned (snapshot_schema_version) so the backtest
replay can detect incompatible older entries.
"""
import math
from datetime import datetime, timedelta

import pytz

from ..gcs_io import load_json, upload_json, get_client, BUCKET


SNAPSHOT_DIR = "backtest_snapshots"
RETENTION_DAYS = 14
SCHEMA_VERSION = 1
TZ = pytz.timezone("America/New_York")

# Raw L1 source keys in weather_data["hourly"]. The corrected_* siblings
# are downstream and not captured here — backtest replays produce them.
_L1_FIELD_MAP = {
    "t":  "temperature",
    "dp": "dew_point",
    "h":  "humidity",
    "ws": "raw_wind_speed",
    "wg": "raw_wind_gusts",
    "pr": "raw_pressure_in",
    "pp": "raw_precipitation_probability",
    "cc": "raw_cloud_cover",
    "sr": "raw_direct_radiation",
    "pa": "raw_precipitation",
    "cl": "raw_cloud_cover_low",
    "cm": "raw_cloud_cover_mid",
    "ch": "raw_cloud_cover_high",
    "wd": "raw_wind_direction",
}

# Lead horizon we capture. Matches the production correction window.
LEAD_HOURS = 48


def _slim_l1(hourly):
    out = {}
    for short, source_key in _L1_FIELD_MAP.items():
        arr = hourly.get(source_key)
        if isinstance(arr, list):
            out[short] = arr[:LEAD_HOURS]
    return out


def _slim_tempest_obs(tempest):
    """Per-station Tempest observations relevant to backtest fitting."""
    stations = (tempest or {}).get("stations") or []
    out = []
    for s in stations:
        if not s.get("valid"):
            continue
        entry = {
            "id":    s.get("station_id"),
            "name":  s.get("station_name"),
            "t":    s.get("temperature_f"),
            "dp":   s.get("dew_point_f"),
            "h":    s.get("relative_humidity"),
            "ws":   s.get("wind_avg_mph"),
            "wg":   s.get("wind_gust_mph"),
            "wd":   s.get("wind_direction"),
            "p_mb": s.get("sea_level_pressure_mb"),
            "sr":   s.get("solar_radiation_wm2"),
            "waterfront": s.get("waterfront"),
        }
        out.append(entry)
    return out


def _slim_wu_obs(wu):
    """WU station network medians + count."""
    if not wu:
        return None
    return {
        "t_med":  wu.get("temperature_f"),
        "h_med":  wu.get("humidity_pct"),
        "p_med":  wu.get("pressure_in"),
        "ws_med": wu.get("wind_speed_mph"),
        "wg_med": wu.get("wind_gust_mph"),
        "n_stations": len((wu.get("stations") or [])),
    }


def _slim_kbvy(kbvy):
    if not kbvy:
        return None
    return {
        "t":  kbvy.get("temp_f"),
        "dp": kbvy.get("dew_point_f"),
        "h":  kbvy.get("humidity_pct"),
        "ws": kbvy.get("wind_speed_mph"),
        "wg": kbvy.get("wind_gust_mph"),
        "wd": kbvy.get("wind_dir"),
        "p":  kbvy.get("pressure_in"),
    }


def _state_meta(weather_data):
    """Regime stamps used downstream for stratified analysis."""
    derived = weather_data.get("derived") or {}
    state = (derived.get("state") or {})
    return {
        "regime_flow":     state.get("regime_flow"),
        "regime_synoptic": state.get("regime_synoptic"),
        "wind_octant":     state.get("wind_octant"),
        "cloud_cover":     state.get("cloud_cover"),
        "wind_speed":      state.get("wind_speed"),
    }


def write_snapshot(weather_data):
    """Capture one tick of L1 inputs + station obs to today's snapshot file."""
    hourly = weather_data.get("hourly") or {}
    if not hourly.get("times"):
        return

    now_local = datetime.now(TZ)
    ts = now_local.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    day = now_local.strftime("%Y-%m-%d")

    entry = {
        "ts": ts,
        "schema_version": SCHEMA_VERSION,
        "lead_times": hourly["times"][:LEAD_HOURS],
        "l1": _slim_l1(hourly),
        "obs": {
            "tempest": _slim_tempest_obs(weather_data.get("tempest")),
            "wu":      _slim_wu_obs(weather_data.get("wu_stations")),
            "kbvy":    _slim_kbvy(weather_data.get("kbvy")),
        },
        "state_meta": _state_meta(weather_data),
    }

    gcs_path = f"{SNAPSHOT_DIR}/{day}.json"
    log = load_json(gcs_path, default={"entries": []})
    entries = log.get("entries", [])
    entries.append(entry)
    upload_json({"entries": entries}, gcs_path, gcs_path)

    # Prune day-files older than retention. Cheap — just deletes a few objects.
    _prune_old_days(now_local)


def _prune_old_days(now_local):
    """Delete snapshot day-files older than RETENTION_DAYS."""
    cutoff = (now_local - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    try:
        client = get_client()
        bucket = client.bucket(BUCKET)
        blobs = bucket.list_blobs(prefix=f"{SNAPSHOT_DIR}/")
        for blob in blobs:
            # Filename like "backtest_snapshots/2026-05-30.json"
            name = blob.name.rsplit("/", 1)[-1].replace(".json", "")
            if len(name) == 10 and name < cutoff:
                blob.delete()
    except Exception:
        pass  # Pruning is best-effort; never crash the collector

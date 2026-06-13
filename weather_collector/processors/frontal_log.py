"""
Rolling observation log for frontal-passage detection.

Captures per-tick T / Td / P / ws / wd from the best-available Tempest
station (typically Willow Rd, 0.21 mi from the cove). 14-day retention.

The detector (frontal_detection.py) reads this log to compute rate-of-change
features across rolling windows and emit passage events.

Append-only, 14-day retention.
"""
import math
from datetime import datetime, timedelta

import pytz

from ..gcs_io import load_json, upload_json


GCS_PATH = "frontal_obs_log.json"
RETENTION_DAYS = 14
TZ = pytz.timezone("America/New_York")


def _mb_to_inhg(mb):
    return round(mb * 0.02953, 3) if mb is not None else None


def append_frontal_snapshot(weather_data):
    """Capture one tick of cove obs for frontal-passage detection."""
    best = (weather_data.get("tempest") or {}).get("best") or {}
    if not best or not best.get("valid"):
        return

    wd_deg = best.get("wind_direction")
    wd_sin = round(math.sin(math.radians(wd_deg)), 4) if wd_deg is not None else None
    wd_cos = round(math.cos(math.radians(wd_deg)), 4) if wd_deg is not None else None

    now_local = datetime.now(TZ)
    ts = now_local.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    cutoff = (now_local - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")

    entry = {
        "ts": ts,
        "station": best.get("station_name"),
        "t": best.get("temperature_f"),
        "dp": best.get("dew_point_f"),
        "p_inhg": _mb_to_inhg(best.get("sea_level_pressure_mb")),
        "ws": best.get("wind_avg_mph"),
        "wg": best.get("wind_gust_mph"),
        "wd": wd_deg,
        "wd_sin": wd_sin,
        "wd_cos": wd_cos,
    }

    # Skip if essential fields missing (would just clutter the log)
    if entry["t"] is None or entry["dp"] is None or entry["wd"] is None:
        return

    log = load_json(GCS_PATH, default={"entries": []})
    entries = [e for e in log.get("entries", []) if e.get("ts", "") >= cutoff]
    entries.append(entry)
    upload_json({"entries": entries}, GCS_PATH, "frontal_obs_log.json")

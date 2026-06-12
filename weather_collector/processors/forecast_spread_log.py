"""
Rolling log of raw GFS forecast values for the 0-48h window, for joining
against the HRRR L1 values already in forecast_log.json.

Both sources are fetched every tick — HRRR for the live forecast (0-48h)
and GFS for the 7-day extension. forecast_log.json already records HRRR
L1 under `*_l1` keys; this log adds the matching GFS values so we can
later compute |HRRR - GFS| per hour and test whether model spread predicts
actual forecast error.

Append-only with 14-day retention, same as forecast_log.json. Joined
downstream by (run, v).
"""
from datetime import datetime, timedelta

import pytz

from ..gcs_io import load_json, upload_json


GCS_PATH = "gfs_l1_log.json"
RETENTION_DAYS = 14
SNAPSHOT_HOURS = 48
TZ = pytz.timezone("America/New_York")

# Internal-name → Open-Meteo native key. The collector calls this BEFORE
# normalize_for_forecast_generation rewrites the dict in place, so we read
# native Open-Meteo keys directly off the fetched response.
_FIELDS = {
    "t":  "temperature_2m",
    "h":  "relative_humidity_2m",
    "ws": "wind_speed_10m",
    "wg": "wind_gusts_10m",
    "pp": "precipitation_probability",
    "cc": "cloud_cover",
}


def _round_for(field, val):
    if val is None:
        return None
    if field in ("pp", "cc"):
        return round(val)
    return round(val, 1)


def append_gfs_snapshot(gfs_hourly):
    """Log raw GFS values for the next 48 hours so we can later compute
    the HRRR-vs-GFS spread by joining against forecast_log.json on
    (run, v).
    """
    if not gfs_hourly:
        return

    times = gfs_hourly.get("time", [])
    if not times:
        return

    now_local = datetime.now(TZ)
    run_stamp = now_local.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    cutoff = (now_local - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")

    hours = []
    for i, t in enumerate(times[:SNAPSHOT_HOURS]):
        if not t:
            continue
        entry = {"v": t}
        any_value = False
        for field, src_key in _FIELDS.items():
            arr = gfs_hourly.get(src_key, [])
            if i < len(arr) and arr[i] is not None:
                entry[field] = _round_for(field, arr[i])
                any_value = True
        if any_value:
            hours.append(entry)

    if not hours:
        return

    log = load_json(GCS_PATH, default={"snapshots": []})
    snapshots = [s for s in log.get("snapshots", []) if s.get("run", "") >= cutoff]
    snapshots.append({"run": run_stamp, "hours": hours})
    upload_json({"snapshots": snapshots}, GCS_PATH, "gfs_l1_log.json")

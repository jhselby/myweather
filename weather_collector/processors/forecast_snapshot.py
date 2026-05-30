"""
Rolling log of corrected 48h forecast snapshots, stored in GCS.

Every collector run writes one compact snapshot of what we think the next
48 hours will look like. Kept for RETENTION_DAYS days for downstream
forecast-vs-observed calibration (decay curves, POP accuracy, dew point
drift, etc.). One entry per hour, fields use short keys to keep file
size manageable across two weeks of 10-minute runs.
"""
from datetime import datetime, timedelta

import pytz

from ..gcs_io import load_json, upload_json
from ..utils import magnus_dew_point_f


GCS_PATH = "forecast_log.json"
RETENTION_DAYS = 14
SNAPSHOT_HOURS = 48
TZ = pytz.timezone("America/New_York")


def append_forecast_snapshot(hourly):
    """Append a snapshot of the corrected 48h forecast for later validation.
    Prunes snapshots older than RETENTION_DAYS on each write. No-op if the
    hourly data has no usable hours.
    """
    now_local = datetime.now(TZ)
    run_stamp = now_local.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    cutoff = (now_local - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")

    times = hourly.get("times", [])
    temps = hourly.get("corrected_temperature", hourly.get("temperature", []))
    winds = hourly.get("wind_speed", [])
    gusts = hourly.get("wind_gusts", [])
    humid = hourly.get("corrected_humidity", hourly.get("humidity", []))
    pop   = hourly.get("precipitation_probability", [])

    hours = []
    for i, t in enumerate(times[:SNAPSHOT_HOURS]):
        if not t:
            continue
        entry = {"v": t}
        if i < len(temps) and temps[i] is not None:
            entry["t"] = round(temps[i], 1)
        if i < len(winds) and winds[i] is not None:
            entry["ws"] = round(winds[i], 1)
        if i < len(gusts) and gusts[i] is not None:
            entry["wg"] = round(gusts[i], 1)
        if i < len(humid) and humid[i] is not None:
            entry["h"] = round(humid[i], 1)
            if i < len(temps) and temps[i] is not None:
                dp = magnus_dew_point_f(temps[i], humid[i])
                if dp is not None:
                    entry["dp"] = dp
        if i < len(pop) and pop[i] is not None:
            entry["pp"] = round(pop[i])
        hours.append(entry)

    if not hours:
        return

    log = load_json(GCS_PATH, default={"snapshots": []})
    snapshots = [s for s in log.get("snapshots", []) if s.get("run", "") >= cutoff]
    snapshots.append({"run": run_stamp, "hours": hours})
    upload_json({"snapshots": snapshots}, GCS_PATH, "forecast_log.json")

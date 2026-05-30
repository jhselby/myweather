"""
Rolling 10-minute observed-conditions log, stored in GCS.

Each collector run appends one entry with the current corrected temp plus
whatever side-channel observations were available (precip rate, gust,
wind, dew point, pressure, cloud, humidity). Entries older than the
retention window are dropped on every write.

Used downstream for: daily high/low (mixing observed with forecast),
yesterday peak stats, and the observed-history chart.
"""
from datetime import datetime, timedelta

import pytz

from ..gcs_io import load_json, upload_json
from ..utils import magnus_dew_point_f


GCS_PATH = "obs_temp_log.json"
RETENTION_HOURS = 24
TZ = pytz.timezone("America/New_York")


def _load():
    """Read the current obs log from GCS. Empty default on missing or error."""
    return load_json(GCS_PATH, default={"entries": []})


def _save(log):
    upload_json(log, GCS_PATH, "obs_temp_log.json")


def update_obs_temp_log(
    corrected_temp,
    precip_in=None,
    peak_gust_mph=None,
    wind_mph=None,
    wind_dir=None,
    dew_point_f=None,
    pressure_in=None,
    cloud_cover=None,
    humidity=None,
):
    """Append one 10-min observed snapshot. Returns the post-write log dict.

    If corrected_temp is None there's nothing meaningful to log, but we
    still return the existing log so callers can read past entries.
    """
    if corrected_temp is None:
        return _load()

    now_local = datetime.now(TZ)
    cutoff = (now_local - timedelta(hours=RETENTION_HOURS)).strftime("%Y-%m-%dT%H:%M")

    log = _load()
    entries = [e for e in log.get("entries", []) if e.get("time", "") >= cutoff]

    stamp = now_local.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    entry = {"time": stamp, "temp": round(corrected_temp, 1)}
    if precip_in is not None:
        entry["precip_in"] = round(precip_in, 3)
    if peak_gust_mph is not None:
        entry["gust_mph"] = round(peak_gust_mph, 1)
    if wind_mph is not None:
        entry["wind_mph"] = round(wind_mph, 1)
    if wind_dir is not None:
        entry["wind_dir"] = round(wind_dir)
    if dew_point_f is not None:
        entry["dew_point_f"] = round(dew_point_f, 1)
    if pressure_in is not None:
        entry["pressure_in"] = round(pressure_in, 2)
    if cloud_cover is not None:
        entry["cloud_cover"] = round(cloud_cover)
    if humidity is not None:
        entry["humidity"] = round(humidity, 1)
        # Re-derive dew point from corrected temp + humidity; overrides any
        # dew_point_f the caller passed in (this is the canonical value).
        dp = magnus_dew_point_f(corrected_temp, humidity)
        if dp is not None:
            entry["dew_point_f"] = dp

    entries.append(entry)
    entries.sort(key=lambda e: e.get("time", ""))
    log = {"entries": entries}
    _save(log)
    return log

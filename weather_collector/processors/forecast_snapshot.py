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
    # Per-layer forecast arrays. The Fitter (decay_fit) computes per-layer MAE
    # by comparing each layer's forecast against the same observation, so we
    # snapshot all 4 layers' values per hour. Mapping:
    #   L1 (raw)        = raw_* or the unprocessed model array
    #   L2 (mesonet)    = *_post_l2 (added by decay_apply.py)
    #   L3 (post-decay) = *_post_l3 (added by decay_apply.py)
    #   L4 (final)      = the live corrected_* / _post_diurnal array
    # Fields with no L2 (wind/POP/cloud) have L1 == L2.
    layers = {
        "t":  {"l1": hourly.get("temperature", []),
               "l2": hourly.get("corrected_temperature_post_l2", []),
               "l3": hourly.get("corrected_temperature_post_l3", []),
               "l4": hourly.get("corrected_temperature", [])},
        "h":  {"l1": hourly.get("humidity", []),
               "l2": hourly.get("corrected_humidity_post_l2", []),
               "l3": hourly.get("corrected_humidity_post_l3", []),
               "l4": hourly.get("corrected_humidity", [])},
        "ws": {"l1": hourly.get("raw_wind_speed", hourly.get("wind_speed", [])),
               "l2": hourly.get("wind_speed_post_l2", []),
               "l3": hourly.get("wind_speed_post_l3", []),
               "l4": hourly.get("wind_speed", [])},
        "wg": {"l1": hourly.get("raw_wind_gusts", hourly.get("wind_gusts", [])),
               "l2": hourly.get("wind_gusts_post_l2", []),
               "l3": hourly.get("wind_gusts_post_l3", []),
               "l4": hourly.get("wind_gusts", [])},
        "pp": {"l1": hourly.get("raw_precipitation_probability",
                                 hourly.get("precipitation_probability", [])),
               "l2": hourly.get("precipitation_probability_post_l2", []),
               "l3": hourly.get("precipitation_probability_post_l3", []),
               "l4": hourly.get("precipitation_probability", [])},
        "pr": {"l1": hourly.get("raw_pressure_in", []),
               "l2": hourly.get("corrected_pressure_in_post_l2", []),
               "l3": hourly.get("corrected_pressure_in_post_l3", []),
               "l4": hourly.get("corrected_pressure_in", [])},
        "cc": {"l1": hourly.get("raw_cloud_cover", hourly.get("cloud_cover", [])),
               "l2": hourly.get("cloud_cover_post_l2", []),
               "l3": hourly.get("cloud_cover_post_l3", []),
               "l4": hourly.get("cloud_cover", [])},
    }
    # Dew point is derived from t + h via Magnus at each layer (no separate model array).
    # Backward-compat top-level keys (t / h / ws / wg / pp / pr / cc) kept = L4 final.

    def _round_for(field, val):
        if val is None:
            return None
        if field == "pr":  return round(val, 3)
        if field in ("pp", "cc"): return round(val)
        return round(val, 1)

    hours = []
    for i, t in enumerate(times[:SNAPSHOT_HOURS]):
        if not t:
            continue
        entry = {"v": t}
        # Per-layer values per field
        for field, lyrs in layers.items():
            for lyr_key, arr in lyrs.items():
                if i < len(arr) and arr[i] is not None:
                    entry[f"{field}_{lyr_key}"] = _round_for(field, arr[i])
        # Backward-compat top-level keys (= L4 final). Joiner pre-v0.6.25 reads these.
        for field in ("t","h","ws","wg","pp","pr","cc"):
            l4 = entry.get(f"{field}_l4")
            if l4 is not None:
                entry[field] = l4
        # Dew point per layer (derived from t/h at each layer via Magnus)
        for lyr_key in ("l1","l2","l3","l4"):
            tv = entry.get(f"t_{lyr_key}")
            hv = entry.get(f"h_{lyr_key}")
            if tv is not None and hv is not None:
                dp = magnus_dew_point_f(tv, hv)
                if dp is not None:
                    entry[f"dp_{lyr_key}"] = dp
        # Backward-compat dp = dp_l4
        if entry.get("dp_l4") is not None:
            entry["dp"] = entry["dp_l4"]
        hours.append(entry)

    if not hours:
        return

    log = load_json(GCS_PATH, default={"snapshots": []})
    snapshots = [s for s in log.get("snapshots", []) if s.get("run", "") >= cutoff]
    snapshots.append({"run": run_stamp, "hours": hours})
    upload_json({"snapshots": snapshots}, GCS_PATH, "forecast_log.json")

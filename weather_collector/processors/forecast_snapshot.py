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
        "sr": {"l1": hourly.get("raw_direct_radiation", hourly.get("direct_radiation", [])),
               "l2": hourly.get("direct_radiation_post_l2", []),
               "l3": hourly.get("direct_radiation_post_l3", []),
               "l4": hourly.get("direct_radiation", [])},
        "pa": {"l1": hourly.get("raw_precipitation", hourly.get("precipitation", [])),
               "l2": hourly.get("precipitation_post_l2", []),
               "l3": hourly.get("precipitation_post_l3", []),
               "l4": hourly.get("precipitation", [])},
        "cl": {"l1": hourly.get("raw_cloud_cover_low", hourly.get("cloud_cover_low", [])),
               "l2": hourly.get("cloud_cover_low_post_l2", []),
               "l3": hourly.get("cloud_cover_low_post_l3", []),
               "l4": hourly.get("cloud_cover_low", [])},
        "cm": {"l1": hourly.get("raw_cloud_cover_mid", hourly.get("cloud_cover_mid", [])),
               "l2": hourly.get("cloud_cover_mid_post_l2", []),
               "l3": hourly.get("cloud_cover_mid_post_l3", []),
               "l4": hourly.get("cloud_cover_mid", [])},
        "ch": {"l1": hourly.get("raw_cloud_cover_high", hourly.get("cloud_cover_high", [])),
               "l2": hourly.get("cloud_cover_high_post_l2", []),
               "l3": hourly.get("cloud_cover_high_post_l3", []),
               "l4": hourly.get("cloud_cover_high", [])},
        # Wind direction is circular — needs special sin/cos math in Fitter
        # and Apply. No Layer 2 (no mesonet aggregation for direction yet) and
        # no Layer 4 (no diurnal yet) — Layer 3 decay correction only in v0.6.27.
        # l2 = l1, l4 = l3 by construction; kept in layers dict for snapshot
        # consistency with the rest of the fields.
        "wd": {"l1": hourly.get("raw_wind_direction", hourly.get("wind_direction", [])),
               "l2": hourly.get("raw_wind_direction", hourly.get("wind_direction", [])),
               "l3": hourly.get("wind_direction", []),
               "l4": hourly.get("wind_direction", [])},
    }
    # Dew point is derived from t + h via Magnus at each layer (no separate model array).
    # Backward-compat top-level keys (t / h / ws / wg / pp / pr / cc) kept = L4 final.

    def _round_for(field, val):
        if val is None:
            return None
        if field == "pr":  return round(val, 3)
        if field == "pa":  return round(val, 3)
        if field in ("pp", "cc", "cl", "cm", "ch", "sr", "wd"): return round(val)
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
        # Backward-compat top-level keys. CRITICAL: these must equal the L2
        # (pre-decay) value, NOT L4. The Fitter reads the top-level key as
        # "the forecast" and calibrates decay corrections from (forecast - obs).
        # If top-level = L4 (post-decay), the calibration would see ~0 error
        # and decay corrections would shrink to zero. Pre-v0.6.25b the snapshot
        # was taken BEFORE decay_apply so the legacy key was naturally L2. We
        # now snapshot AFTER decay_apply to capture all 4 layers — preserving
        # legacy semantics requires explicitly using the _l2 value here.
        for field in ("t","h","ws","wg","pp","pr","cc","sr","pa","cl","cm","ch","wd"):
            l2 = entry.get(f"{field}_l2")
            if l2 is not None:
                entry[field] = l2
        # Dew point per layer (derived from t/h at each layer via Magnus)
        for lyr_key in ("l1","l2","l3","l4"):
            tv = entry.get(f"t_{lyr_key}")
            hv = entry.get(f"h_{lyr_key}")
            if tv is not None and hv is not None:
                dp = magnus_dew_point_f(tv, hv)
                if dp is not None:
                    entry[f"dp_{lyr_key}"] = dp
        # Legacy dp = dp_l2 for the same Fitter-calibration reason as above.
        if entry.get("dp_l2") is not None:
            entry["dp"] = entry["dp_l2"]
        hours.append(entry)

    if not hours:
        return

    log = load_json(GCS_PATH, default={"snapshots": []})
    snapshots = [s for s in log.get("snapshots", []) if s.get("run", "") >= cutoff]
    snapshots.append({"run": run_stamp, "hours": hours})
    upload_json({"snapshots": snapshots}, GCS_PATH, "forecast_log.json")

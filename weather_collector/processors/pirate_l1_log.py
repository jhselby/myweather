"""
Rolling log of raw Pirate Weather forecast values for the 0-48h window,
joinable to the HRRR L1 values in forecast_log.json + GFS L1 in
gfs_l1_log.json by (run_hour, valid_time).

Booked 2026-07-27 v0.6.382q after `h_pp_source_blend.py` Stage 0 HOLD
showed HRRR + GFS pp are near-collinear at 0-48h (both post-process from
the same NCEP soup + share recent-obs assimilation). Pirate is IBM/GFS-
adjacent but adds an independent model-post-processing layer. The pp
source-blend can be retested at 3 sources once this log has ≥14 days
of coverage — earliest retest 2026-08-10.

Field scope: `pp` only for now — that's the booked need. The processor
is easy to extend if a future analysis needs Pirate cloud cover / solar
historically (both fields are already fetched); add the internal-name →
data-key mapping in _FIELDS.

Append-only with 14-day retention, same as gfs_l1_log.json.
"""
from datetime import datetime, timedelta

import pytz

from ..gcs_io import load_json, upload_json


GCS_PATH = "pirate_l1_log.json"
RETENTION_DAYS = 14
SNAPSHOT_HOURS = 48
TZ = pytz.timezone("America/New_York")


def append_pirate_snapshot(pirate_data):
    """Log raw Pirate pp for the next 48 hours so we can later join
    (run_hour, valid_time) against HRRR + GFS for a 3-source pp blend.

    pirate_data is the fetched Pirate Weather dict (see fetchers/pirate_weather.py):
    contains `hourly_times` (UNIX seconds) + `hourly_precip_probability` (0-100)."""
    if not pirate_data:
        return

    hourly_times = pirate_data.get("hourly_times") or []
    hourly_pp = pirate_data.get("hourly_precip_probability") or []
    if not hourly_times or not hourly_pp:
        return

    now_local = datetime.now(TZ)
    run_stamp = now_local.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    cutoff = (now_local - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")

    hours = []
    n = min(len(hourly_times), len(hourly_pp), SNAPSHOT_HOURS)
    for i in range(n):
        ts_unix = hourly_times[i]
        pp = hourly_pp[i]
        if ts_unix is None or pp is None:
            continue
        # Convert UNIX seconds → local-TZ hour string matching gfs_l1_log's
        # `v` convention ("YYYY-MM-DDTHH:MM"), so joins across the three
        # sources use identical keys. Pirate returns UTC unix — anchor to
        # TZ to match the collector's frame of reference.
        try:
            v_iso = datetime.fromtimestamp(int(ts_unix), tz=pytz.UTC).astimezone(TZ).strftime("%Y-%m-%dT%H:%M")
        except (TypeError, ValueError, OverflowError):
            continue
        hours.append({"v": v_iso, "pp": pp})

    if not hours:
        return

    log = load_json(GCS_PATH, default={"snapshots": []})
    snapshots = [s for s in log.get("snapshots", []) if s.get("run", "") >= cutoff]
    snapshots.append({"run": run_stamp, "hours": hours})
    upload_json({"snapshots": snapshots}, GCS_PATH, "pirate_l1_log.json")

"""L1 router — override cascade output with NWS-gridpoint (NBM-derived) for
long-lead (≥6h) t/dp/ws/wd forecasts.

Empirical basis (2026-08-18, 14-day head-to-head against production):

  field  lead1  lead3  lead6  lead12  lead18  lead24
  t      Prod   HRRR   NBM    NBM     NBM     NBM
  dp     Prod   Prod   NBM    NBM     NBM     NBM
  ws     Prod   NBM    NBM    NBM     NBM     NBM
  wd     Prod   Prod   NBM    NBM     NBM     NBM
  wg     Prod   NBM    NBM    NBM     NBM     NBM      ← awaits NBM grib ingester
  sr     HRRR   NBM    NBM    NBM     HRRR    NBM      ← awaits NBM/HRRR ingester

At leads ≥6h, NBM (via NWS-gridpoint API, live-fetched by v0.6.431) beats the
current production cascade by +6% to +24% MAE for t/dp/ws/wd. This module
mutates hourly[<field>] to the NWS-gridpoint value at those slots. Fields
without an NWS-gridpoint counterpart (wg, sr) are untouched — those need a
direct NBM/HRRR grib ingester (phase 2).

At leads 1-5h, production still wins for most fields (station-blend + wdp +
short-lead corrections). Router leaves cascade output intact there.

Rollback: set _ROUTER_ENABLED=False.
"""
import logging
from datetime import datetime, timedelta, timezone

import pytz

from .forecast_text import _extract_nws_value


_ROUTER_ENABLED = True
_MIN_LEAD_H = 6  # first hour at which we override cascade

# (short field, hourly array key we MUTATE, NWS-gridpoint key,
#  converter obs → our units).
#
# Array-key notes (per frontend + snapshot conventions):
#   - t: mutate `corrected_temperature` — the L4/L6 array the frontend renders.
#     hourly["temperature"] stays as raw model so snapshot's L1 slot still
#     reflects the Open-Meteo baseline.
#   - ws / wd: cascade mutates hourly["wind_*"] in place; raw_wind_* backups
#     already preserve L1 for the pair log. Router mutates the same live key.
#   - dp: derived via Magnus from t + humidity. Not routed tonight (would
#     require overriding corrected_dew_point independently and keeping units
#     consistent with a routed t). Phase 2.
#   - wg / sr: no NWS-gridpoint counterpart. Phase 2 (NBM grib ingester).
_ROUTER_FIELDS = (
    ("t",  "corrected_temperature", "temperature",   lambda v: v * 9 / 5 + 32),
    ("ws", "wind_speed",            "windSpeed",     lambda v: v * 0.621371),
    ("wd", "wind_direction",        "windDirection", lambda v: v),
)

_TZ = pytz.timezone("America/New_York")


def _hour_utc(iso_local):
    """Parse the collector's local-naive 'YYYY-MM-DDTHH:MM' hourly-time string
    into a UTC-aware datetime pinned to the top of the hour."""
    try:
        naive = datetime.strptime(iso_local[:16], "%Y-%m-%dT%H:%M")
    except (ValueError, TypeError):
        return None
    return _TZ.localize(naive).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def apply_l1_router(weather_data):
    """Mutate weather_data['hourly'][<field>] for at-lead ≥_MIN_LEAD_H slots
    using NWS-gridpoint values when available. Leaves cascade output intact at
    short lead and when the NWS value is missing.

    Preserves the pre-router array as hourly['<field>_pre_router'] for debug
    and rollback. Adds hourly['<field>_router_source'] as a per-hour list of
    'prod' or 'nws' labels so the snapshot / debug page can attribute cells.
    """
    if not _ROUTER_ENABLED:
        return

    hourly = weather_data.get("hourly") or {}
    times = hourly.get("times") or []
    if not times:
        return

    nws = weather_data.get("nws_gridpoints") or {}
    if not nws:
        return

    # Router keys off the first hour in the hourly array as the run's t=0.
    # Same convention as forecast_error_log's lead calculation.
    t0_utc = _hour_utc(times[0])
    if t0_utc is None:
        return

    override_counts = {}
    for short, arr_key, nws_key, conv in _ROUTER_FIELDS:
        arr = hourly.get(arr_key)
        if not arr:
            continue
        prop = nws.get(nws_key)
        if not prop:
            continue
        pre_arr = list(arr)
        source_labels = ["prod"] * len(arr)
        n_swapped = 0

        for i, iso in enumerate(times):
            hour_utc = _hour_utc(iso)
            if hour_utc is None:
                continue
            lead_h = int(round((hour_utc - t0_utc).total_seconds() / 3600))
            if lead_h < _MIN_LEAD_H:
                continue
            raw = _extract_nws_value(prop, hour_utc)
            if raw is None:
                continue
            try:
                val = conv(float(raw))
            except (TypeError, ValueError):
                continue
            arr[i] = val
            source_labels[i] = "nws"
            n_swapped += 1

        hourly[f"{arr_key}_pre_router"] = pre_arr
        hourly[f"{arr_key}_router_source"] = source_labels
        override_counts[short] = n_swapped

    if override_counts:
        summary = " ".join(f"{k}={v}" for k, v in override_counts.items())
        # Cloud Run's root logger sits at WARNING and drops logging.info() —
        # use print(..., flush=True) so the router's activity is visible in
        # logs. Same pattern as MEMPROBE lines in collector.py (v0.6.414).
        print(f"  ✓ L1 router (NWS/NBM) overrode long-lead slots: {summary}", flush=True)

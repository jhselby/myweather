"""
Orchestrate every data fetch the collector needs.

`fetch_all_sources()` runs the rate-limit-sensitive Open-Meteo calls
sequentially, then fans out everything else in parallel via
`fetch_parallel_sources()`, and returns a single `FetchResults` dataclass
that bundles all the data + the `sources` meta dict + a `failed_fetches`
set flagging sequential calls that returned None.

What's NOT here: side-effect setup that bookends the fetch in collector.main()
— previous-run cache load, frost-log GCS download, frost-log update/upload,
and sunset-directional computation. Those stay in main() because their order
relative to other main()-level steps is what matters.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .fetch_parallel import fetch_parallel_sources
from .open_meteo import (
    fetch_current_gfs,
    fetch_daily_ecmwf,
    fetch_hourly_gfs_7day,
    fetch_hourly_hrrr,
    fetch_hrrr_daily_temps,
)


@dataclass
class FetchResults:
    # Sequential Open-Meteo
    current_data: Any = None
    hourly_data: Any = None
    daily_data: Any = None
    daily_temps_data: Any = None
    hourly_7day_data: Any = None
    # Parallel sources
    pws_data: Any = None
    tide_data: Any = None
    kbos_data: Any = None
    kbvy_data: Any = None
    buoy_data: Any = None
    wu_data: Any = None
    alert_data: Any = None
    pirate_data: Any = None
    birds_data: Any = None
    tempest_data: Any = None
    nws_gridpoints_data: Any = None
    salem_water_temp: Any = None
    # Meta
    sources: dict = field(default_factory=dict)
    failed_fetches: set = field(default_factory=set)


def _timed(name, fn, *args, **kwargs):
    t0 = time.time()
    result = fn(*args, **kwargs)
    logging.info(f"  ⏱  {name}: {time.time() - t0:.1f}s")
    return result


# Error placeholder used when a parallel source returns None for both data
# AND meta — i.e. when its dict entry was never populated. The unpacking
# below preserves the same behavior the old inline code had.
_ERROR_TUPLE = (None, {"status": "error"})


def fetch_all_sources():
    """Run all weather data fetchers — Open-Meteo sequential (rate-limit
    sensitive), everything else parallel — and return a `FetchResults`
    dataclass. The `sources` dict mirrors what gets written to the payload's
    top-level `sources` field; `failed_fetches` is the set used by
    apply_stale_fallbacks to decide which top-level keys need patching from
    the previous run."""

    out = FetchResults()

    # ── Open-Meteo calls: SEQUENTIAL (rate-limit sensitive) ──
    out.current_data, current_meta = _timed("GFS current", fetch_current_gfs)
    out.hourly_data, hourly_meta = _timed("HRRR hourly", fetch_hourly_hrrr)
    out.daily_temps_data, daily_temps_meta = _timed("HRRR daily temps", fetch_hrrr_daily_temps)
    out.hourly_7day_data, hourly_7day_meta = _timed("GFS 7-day hourly", fetch_hourly_gfs_7day)
    out.daily_data, daily_meta = _timed("ECMWF daily", fetch_daily_ecmwf)

    # Track which sequential fetches returned None (used by stale fallback)
    if out.current_data is None: out.failed_fetches.add("current")
    if out.hourly_data is None:  out.failed_fetches.add("hourly")
    if out.daily_data is None:   out.failed_fetches.add("daily")

    # ── Everything else: PARALLEL ──
    parallel_results = fetch_parallel_sources()

    out.nws_gridpoints_data, nws_gridpoints_meta = parallel_results.get("NWS gridpoints", _ERROR_TUPLE)
    out.pws_data, pws_meta                       = parallel_results.get("PWS current",    _ERROR_TUPLE)
    out.tide_data, tides_meta                    = parallel_results.get("Tides",          _ERROR_TUPLE)
    out.salem_water_temp                         = parallel_results.get("Salem water temp")
    out.kbos_data, kbos_meta                     = parallel_results.get("KBOS obs",       _ERROR_TUPLE)
    out.kbvy_data, kbvy_meta                     = parallel_results.get("KBVY obs",       _ERROR_TUPLE)
    out.buoy_data, buoy_meta                     = parallel_results.get("Buoy 44013",     _ERROR_TUPLE)
    out.wu_data, wu_meta                         = parallel_results.get("WU stations",    _ERROR_TUPLE)
    out.alert_data, alerts_meta                  = parallel_results.get("NWS alerts",     _ERROR_TUPLE)
    out.pirate_data, pirate_meta                 = parallel_results.get("Pirate Weather", _ERROR_TUPLE)
    out.birds_data, birds_meta                   = parallel_results.get("eBird",          _ERROR_TUPLE)
    out.tempest_data, tempest_meta               = parallel_results.get("Tempest",        _ERROR_TUPLE)

    out.sources = {
        "gfs_current": current_meta,
        "hrrr_hourly": hourly_meta,
        "ecmwf_daily": daily_meta,
        "pws": pws_meta,
        "tides": tides_meta,
        "kbos": kbos_meta,
        "kbvy": kbvy_meta,
        "buoy_44013": buoy_meta,
        "wu_stations": wu_meta,
        "nws_alerts": alerts_meta,
        "pirate_weather": pirate_meta,
        "ebird": birds_meta,
        "tempest": tempest_meta,
    }

    return out

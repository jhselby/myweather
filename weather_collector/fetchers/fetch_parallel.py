"""
Run all non-rate-limited weather data fetchers in parallel via ThreadPoolExecutor.
Open-Meteo calls stay sequential in collector.main() because they share a rate
limit; everything in here is independent and safe to fan out.

Each fetcher returns either a (data, meta) tuple or a single value (Salem water
temp is the lone single-value source). On timeout or exception, we substitute
the matching shape so downstream unpacking in collector.main() never KeyErrors.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .ebird import fetch_ebird
from .noaa import fetch_buoy_44013, fetch_kbos_obs, fetch_kbvy_obs
from .nws import fetch_nws_alerts, fetch_nws_gridpoints
from .pirate_weather import fetch_pirate_weather
from .pws import fetch_pws_current
from .salem_water import fetch_salem_water_temp
from .tempest import fetch_tempest
from .tides import fetch_tides
from .wu import fetch_wu_stations
from ..utils import redact_secrets

MAX_WORKERS = 6
AS_COMPLETED_TIMEOUT = 60
TASK_TIMEOUT = 45

# Single-value fetchers return just the data (not a (data, meta) tuple), so
# their error placeholder is None instead of (None, {...}).
_SINGLE_VALUE_TASKS = {"Salem water temp"}


def fetch_parallel_sources():
    """Fan out all non-rate-limited fetchers via ThreadPool. Returns a dict
    keyed by display name with each fetcher's (data, meta) result — or None
    for single-value sources (Salem water temp). Timeouts and exceptions are
    logged and replaced with the matching error placeholder so callers can
    unpack without checking each key."""

    parallel_tasks = {
        "NWS gridpoints": (fetch_nws_gridpoints, [], {}),
        "PWS current": (fetch_pws_current, [], {}),
        "Tides": (fetch_tides, [], {}),
        "Salem water temp": (fetch_salem_water_temp, [], {}),
        "KBOS obs": (fetch_kbos_obs, [], {}),
        "KBVY obs": (fetch_kbvy_obs, [], {}),
        "Buoy 44013": (fetch_buoy_44013, [], {}),
        "WU stations": (fetch_wu_stations, [], {}),
        "NWS alerts": (fetch_nws_alerts, [], {}),
        "Pirate Weather": (fetch_pirate_weather, [], {}),
        "eBird": (fetch_ebird, [], {}),
        "Tempest": (fetch_tempest, [], {}),
    }

    def _error_placeholder(name, err_payload):
        if name in _SINGLE_VALUE_TASKS:
            return None
        return (None, err_payload)

    parallel_t0 = time.time()
    parallel_results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_name = {
            executor.submit(fn, *args, **kwargs): name
            for name, (fn, args, kwargs) in parallel_tasks.items()
        }
        for future in as_completed(future_to_name, timeout=AS_COMPLETED_TIMEOUT):
            name = future_to_name[future]
            try:
                parallel_results[name] = future.result(timeout=TASK_TIMEOUT)
            except TimeoutError:
                logging.warning(f"  ⚠️  {name} timed out ({TASK_TIMEOUT}s)")
                parallel_results[name] = _error_placeholder(name, {"status": "error", "error": "timeout"})
            except Exception as e:
                logging.error(f"  ⚠️  {name} failed: {redact_secrets(e)}")
                parallel_results[name] = _error_placeholder(name, {"status": "error", "error": redact_secrets(e)})
    logging.info(f"  ✓ Parallel fetches complete: {time.time() - parallel_t0:.1f}s")

    return parallel_results

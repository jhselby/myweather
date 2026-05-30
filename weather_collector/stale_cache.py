"""
Previous-run cache: load the last weather_data.json from GCS and patch in
any top-level keys whose source failed this run, so a transient API outage
shows stale data rather than no data.
"""
import logging

from .gcs_io import BUCKET, get_client, load_json
from .utils import redact_secrets


PREV_GCS_PATH = "weather_data.json"

# Top-level payload keys that get patched from the previous run when their
# source fetch failed. New top-level sources need to be added here.
STALE_FALLBACK_KEYS = [
    "pirate_weather", "kbos", "kbvy", "wu_stations",
    "nws_gridpoints", "tides", "buoy", "sunset_directional",
]


def load_prev_weather_data():
    """Read the most recent weather_data.json from GCS. Returns {} if it
    doesn't exist (first run) or if the load failed. Logs at WARNING level
    on success so the fallback usage is visible in monitoring."""
    try:
        client = get_client()
        blob = client.bucket(BUCKET).blob(PREV_GCS_PATH)
        if blob.exists():
            import json
            prev = json.loads(blob.download_as_text())
            logging.warning(f"  ✓ Loaded previous weather_data.json from GCS for fallback cache")
            return prev
        else:
            logging.info(f"  ℹ  No previous weather_data.json in GCS (first run)")
    except Exception as e:
        logging.warning(f"  ⚠  Could not load previous weather_data.json: {redact_secrets(e)}")
    return {}


def apply_stale_fallbacks(weather_data, prev, failed_fetches):
    """For any source that failed this run, copy its key from the previous
    run's payload into `weather_data`. Mutates `weather_data` in place and
    returns the list of patched key names.

    `failed_fetches` is the set of fetch labels that returned None this
    run — used to detect failure for current/hourly/daily, since those
    dicts get built (possibly empty) even when their source fails.
    """
    if not prev:
        return []

    stale = []

    # Top-level keys: present in weather_data only when their fetch succeeded.
    for key in STALE_FALLBACK_KEYS:
        if key not in weather_data and key in prev:
            weather_data[key] = prev[key]
            stale.append(key)
            logging.error(f"  ⚠  {key}: using previous run's data (source failed)")

    # current/hourly/daily: built even when GFS fails (silently wrong).
    # Use explicit None-tracking instead of inspecting the built dict.
    for fetch_name, data_key in [("current", "current"), ("hourly", "hourly"), ("daily", "daily")]:
        if fetch_name in failed_fetches and data_key in prev:
            weather_data[data_key] = prev[data_key]
            stale.append(data_key)
            logging.error(f"  ⚠  {data_key}: using previous run's data (fetch failed)")

    return stale

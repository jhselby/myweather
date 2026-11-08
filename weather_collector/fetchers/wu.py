"""
Fetch Weather Underground multi-station data
"""
import json
from . import wu_scraper_realtime
from ..utils import iso_utc_now, redact_secrets
import logging




# v0.7.95: Weather Underground retired. The key has been refused (401) since
# 2026-10-07 and no station has reported since 2026-10-21; the scraper still made
# ~41 refused calls per run. Tempest is the mesonet. Off = return the scraper's own
# empty aggregate (what every run produced since 10-21) with no network call, so
# hyperlocal, daily_extremes and the Sources card see exactly what they saw.
WU_ENABLED = False


def fetch_wu_stations():
    """
    Fetch multi-station WU data using the scraper module.
    This is optional and fails gracefully if the scraper is unavailable.
    """
    if not WU_ENABLED:
        return wu_scraper_realtime.filter_and_aggregate([]), {
            "status": "ok", "updated_at": iso_utc_now(), "error": None,
            "note": "Weather Underground retired 2026-11-08 (no readings since 2026-10-21); mesonet = Tempest"}
    logging.info("📡 Fetching WU stations (optional)...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        # Run the scraper (it writes to wu_stations_realtime.json)
        wu_scraper_realtime.main()

        # Load the output file
        with open("wu_stations_realtime.json", "r") as f:
            wu_data = json.load(f)

        meta["status"] = "ok"
        stations_count = wu_data.get("quality", {}).get("stations_used_temp", 0)
        logging.info(f"  ✓ WU stations: {stations_count} stations")
        return wu_data, meta

    except Exception as e:
        meta["error"] = redact_secrets(e)
        logging.error(f"  ✗ WU stations (optional): {redact_secrets(e)}")
        return None, meta
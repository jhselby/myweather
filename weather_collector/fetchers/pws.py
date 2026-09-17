"""
Fetch current conditions from Weather Underground Personal Weather Station.

Uses the WU PWS observations API (same endpoint as wu_scraper_realtime),
not the browser page — the SPA HTML is unreliable from Cloud Function IPs.
"""
import os
import requests
from datetime import datetime

from ..config import PWS_STATION, PWS_CACHE_FILE
from ..utils import iso_utc_now, load_json, save_json, redact_secrets
import logging


WU_API_URL = "https://api.weather.com/v2/pws/observations/current"


def fetch_pws_current():
    """
    Fetch Castle Hill PWS current observation via the WU API.
    Falls back to cached value if the API call fails.
    """
    logging.info("📡 Fetching Castle Hill PWS...")

    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}
    cache_path = PWS_CACHE_FILE
    last = load_json(cache_path)

    try:
        api_key = os.environ["WU_API_KEY"]
        params = {
            "apiKey": api_key,
            "stationId": PWS_STATION,
            "numericPrecision": "decimal",
            "format": "json",
            "units": "e",
        }
        r = requests.get(WU_API_URL, params=params, timeout=15)
        r.raise_for_status()
        obs = (r.json().get("observations") or [None])[-1]
        temp = (obs or {}).get("imperial", {}).get("temp") if obs else None

        if temp is None:
            raise RuntimeError("PWS API returned no temperature")

        pws_data = {
            "station": PWS_STATION,
            "name": "Castle Hill",
            "updated": datetime.now().isoformat(),
            "temperature": float(temp),
            "stale": False,
        }
        save_json(cache_path, pws_data)

        meta["status"] = "ok"
        logging.info(f"✓ PWS: {pws_data['temperature']}°F")
        return pws_data, meta

    except Exception as e:
        meta["error"] = redact_secrets(e)
        logging.error(f"✗ PWS error: {redact_secrets(e)}")

        if last and isinstance(last, dict) and last.get("temperature") is not None:
            last_copy = dict(last)
            last_copy["stale"] = True
            return last_copy, meta

        return {
            "station": PWS_STATION,
            "name": "Castle Hill",
            "updated": None,
            "temperature": None,
            "stale": True,
        }, meta

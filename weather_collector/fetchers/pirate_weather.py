"""
Pirate Weather API fetcher
Provides minutely precip, solar irradiance, CAPE, and cloud cover
https://pirateweather.net
"""
import os
import requests
from ..utils import redact_secrets

API_KEY = os.environ["PIRATE_WEATHER_API_KEY"]
LAT = 42.5014
LON = -70.8750
BASE_URL = "https://api.pirateweather.net/forecast"




def fetch_pirate_weather():
    """
    Fetch minutely precip, hourly solar/CAPE from Pirate Weather.
    Returns (data, meta) tuple matching collector convention.
    """
    url = f"{BASE_URL}/{API_KEY}/{LAT},{LON}"
    params = {
        "units": "us",           # Fahrenheit, mph, inches
        "exclude": "daily,alerts,flags",
        "version": 2,            # Enables solar, cape, liquidAccumulation etc.
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        raw = resp.json()

        # --- Minutely block (next 60 minutes) ---
        minutely_raw = raw.get("minutely", {}).get("data", [])
        minutely = [
            {
                "time": pt.get("time"),                        # UNIX timestamp
                "precip_intensity": pt.get("precipIntensity", 0),   # inches/hr
                "precip_probability": pt.get("precipProbability", 0),
                "precip_type": pt.get("precipType"),           # "rain", "snow", "sleet" or None
            }
            for pt in minutely_raw
        ]

        # --- Currently block (solar, CAPE, cloud cover) ---
        currently = raw.get("currently", {})
        solar = currently.get("solar")        # W/m²
        cape = currently.get("cape")          # J/kg
        current_cloud_cover_raw = currently.get("cloudCover")  # 0-1 fraction
        current_cloud_cover = round(current_cloud_cover_raw * 100) if current_cloud_cover_raw is not None else None

        # --- Hourly solar/CAPE/cloud cover (48h) ---
        hourly_raw = raw.get("hourly", {}).get("data", [])[:48]
        hourly_solar = [pt.get("solar") for pt in hourly_raw]
        hourly_cape = [pt.get("cape") for pt in hourly_raw]
        hourly_times = [pt.get("time") for pt in hourly_raw]
        # cloudCover is 0-1; convert to 0-100 to match Open-Meteo format
        hourly_cloud_cover = [
            round(pt["cloudCover"] * 100) if pt.get("cloudCover") is not None else None
            for pt in hourly_raw
        ]

        data = {
            "minutely": minutely,
            "current_solar": solar,
            "current_cape": cape,
            "current_cloud_cover": current_cloud_cover,
            "hourly_times": hourly_times,
            "hourly_solar": hourly_solar,
            "hourly_cape": hourly_cape,
            "hourly_cloud_cover": hourly_cloud_cover,
        }

        meta = {
            "status": "ok",
            "source": "Pirate Weather",
            "minutely_count": len(minutely),
            "has_solar": solar is not None,
            "has_cape": cape is not None,
        }
        return data, meta

    except requests.exceptions.Timeout:
        return None, {"status": "error", "error": "timeout"}
    except requests.exceptions.RequestException as e:
        return None, {"status": "error", "error": redact_secrets(e)}
    except Exception as e:
        return None, {"status": "error", "error": f"unexpected: {redact_secrets(e)}"}

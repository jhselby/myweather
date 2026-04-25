"""
Pirate Weather API fetcher
Provides minutely precip, solar irradiance, and CAPE
https://pirateweather.net
"""
import os
import requests

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

        # --- Currently block (solar, CAPE) ---
        currently = raw.get("currently", {})
        solar = currently.get("solar")        # W/m²
        cape = currently.get("cape")          # J/kg

        # --- Hourly solar/CAPE (first 24h) ---
        hourly_raw = raw.get("hourly", {}).get("data", [])[:24]
        hourly_solar = [pt.get("solar") for pt in hourly_raw]
        hourly_cape = [pt.get("cape") for pt in hourly_raw]
        hourly_times = [pt.get("time") for pt in hourly_raw]

        data = {
            "minutely": minutely,
            "current_solar": solar,
            "current_cape": cape,
            "hourly_times": hourly_times,
            "hourly_solar": hourly_solar,
            "hourly_cape": hourly_cape,
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
        return None, {"status": "error", "error": str(e)}
    except Exception as e:
        return None, {"status": "error", "error": f"unexpected: {e}"}

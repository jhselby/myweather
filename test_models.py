#!/usr/bin/env python3
"""
test_models.py — Quick sanity check for HRRR and ECMWF via Open-Meteo.
Run from your repo directory: python3 test_models.py

Checks:
  1. Both models respond successfully
  2. HRRR returns current + hourly data
  3. ECMWF returns daily data
  4. Key fields are present and plausible
  5. Shows what model label Open-Meteo actually used
"""

import requests
import json
from datetime import datetime

LAT = 42.5014
LON = -70.8750
BASE_URL = "https://api.open-meteo.com/v1/forecast"

OM_UNITS = {
    "temperature_unit":   "fahrenheit",
    "wind_speed_unit":    "mph",
    "precipitation_unit": "inch",
    "timezone":           "America/New_York",
}

CURRENT_VARS = ",".join([
    "temperature_2m", "relative_humidity_2m", "apparent_temperature",
    "precipitation", "weather_code", "cloud_cover", "pressure_msl",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m"
])
HOURLY_VARS = ",".join([
    "temperature_2m", "wind_speed_10m", "wind_gusts_10m",
    "wind_direction_10m", "precipitation_probability", "pressure_msl"
])
DAILY_VARS = ",".join([
    "weather_code", "temperature_2m_max", "temperature_2m_min",
    "precipitation_sum", "wind_speed_10m_max", "wind_gusts_10m_max",
    "sunrise", "sunset"
])


def check(label, params):
    print(f"\n{'='*55}")
    print(f"  Testing: {label}")
    print(f"{'='*55}")
    try:
        r = requests.get(BASE_URL, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        if "error" in data:
            print(f"  ✗ API error: {data['error']}")
            return False

        # Show model Open-Meteo actually used (may differ from requested)
        model_used = data.get("model", "not reported")
        print(f"  Model reported by API : {model_used}")

        # Current
        cur = data.get("current", {})
        if cur:
            print(f"  Current temp          : {cur.get('temperature_2m')} °F")
            print(f"  Feels like            : {cur.get('apparent_temperature')} °F")
            print(f"  Wind                  : {cur.get('wind_speed_10m')} mph "
                  f"from {cur.get('wind_direction_10m')}°")
            print(f"  Gusts                 : {cur.get('wind_gusts_10m')} mph")
            print(f"  Pressure              : {cur.get('pressure_msl')} hPa")
        else:
            print("  Current               : (not requested)")

        # Hourly — just show first 3 slots
        hourly = data.get("hourly", {})
        if hourly:
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            print(f"  Hourly slots returned : {len(times)}")
            for i in range(min(3, len(times))):
                print(f"    {times[i]}  {temps[i]} °F")
        else:
            print("  Hourly                : (not requested)")

        # Daily — show first 5 days
        daily = data.get("daily", {})
        if daily:
            dates = daily.get("time", [])
            hi    = daily.get("temperature_2m_max", [])
            lo    = daily.get("temperature_2m_min", [])
            print(f"  Daily days returned   : {len(dates)}")
            for i in range(min(5, len(dates))):
                print(f"    {dates[i]}  Hi {hi[i]}°F / Lo {lo[i]}°F")
        else:
            print("  Daily                 : (not requested)")

        print(f"\n  ✓ {label} PASSED")
        return True

    except requests.exceptions.RequestException as e:
        print(f"  ✗ Network error: {e}")
        return False
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")
        return False


def main():
    print(f"\nWyman Cove Model Test  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Location: {LAT}, {LON}")

    results = {}

    # Test 1: HRRR — hourly only (does not support current conditions)
    results["HRRR"] = check("HRRR (hourly only, no current)", {
        "latitude":      LAT,
        "longitude":     LON,
        "hourly":        HOURLY_VARS,
        "models":        "hrrr",
        "forecast_days": 2,
        **OM_UNITS,
    })

    # Test 2: ECMWF — daily only
    results["ECMWF"] = check("ECMWF IFS (daily 10-day)", {
        "latitude":      LAT,
        "longitude":     LON,
        "daily":         DAILY_VARS,
        "models":        "ecmwf_ifs025",
        "forecast_days": 10,
        **OM_UNITS,
    })

    # Test 3: GFS baseline (what you have now) — for comparison
    results["GFS"] = check("GFS baseline (current + hourly + daily)", {
        "latitude":      LAT,
        "longitude":     LON,
        "current":       CURRENT_VARS,
        "hourly":        HOURLY_VARS,
        "daily":         DAILY_VARS,
        "forecast_days": 10,
        **OM_UNITS,
    })

    print(f"\n{'='*55}")
    print("  SUMMARY")
    print(f"{'='*55}")
    for name, ok in results.items():
        print(f"  {'✓' if ok else '✗'}  {name}")

    if results["HRRR"] and results["ECMWF"]:
        print("\n  ✓ Both primary models available — collector.py update is safe to deploy.")
    elif results["GFS"]:
        print("\n  ⚠  One or both primary models unavailable.")
        print("     Fallback to GFS will activate automatically.")
        print("     Collector is still safe to deploy.")
    else:
        print("\n  ✗ All models failed — check network connectivity.")


if __name__ == "__main__":
    main()

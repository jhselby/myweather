"""
Fetch NOAA observations: KBOS, KBVY, Buoy 44013
"""
import requests
from pathlib import Path

from ..config import KBOS_CACHE_FILE, KBVY_CACHE_FILE, BUOY_CACHE_FILE, HEADERS_DEFAULT
from ..utils import iso_utc_now, safe_float, load_json, save_json


def fetch_kbos_obs():
    """
    Fetch Boston Logan (KBOS) METAR via Aviation Weather Center.
    Caches rolling 3-hour pressure history for trend calculation.
    """
    print("📡 Fetching KBOS obs...")
    url = "https://aviationweather.gov/cgi-bin/data/metar.php?ids=KBOS&format=json"
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        r = requests.get(url, headers=HEADERS_DEFAULT, timeout=30)
        r.raise_for_status()
        data = r.json()

        if not data:
            raise ValueError("Empty METAR response")

        obs = data[0]
        obs_time = obs.get("obsTime")
        altim = safe_float(obs.get("altim"))

        if altim is None:
            raise ValueError("No altimeter reading")

        # Convert inHg to hPa
        pressure_hpa = round(altim * 33.8639, 1)

        # Load cache and update rolling history
        cache = load_json(KBOS_CACHE_FILE) or {"history": []}
        history = cache.get("history", [])
        history.append({"time": obs_time, "pressure_hpa": pressure_hpa})

        # Keep only last 3 hours of readings (12 readings at 15min intervals)
        history = history[-12:]

        # Compute 3h trend if we have old enough data
        pressure_tend = None
        if len(history) >= 2:
            oldest = history[0]["pressure_hpa"]
            newest = history[-1]["pressure_hpa"]
            pressure_tend = round(newest - oldest, 1)

        result = {
            "station": "KBOS",
            "obs_time": obs_time,
            "pressure_hpa": pressure_hpa,
            "pressure_tend_hpa": pressure_tend,
        }

        # Save updated cache
        save_json(KBOS_CACHE_FILE, {"history": history, "latest": result})

        meta["status"] = "ok"
        print(f"  ✓ KBOS: {pressure_hpa} hPa" + (f" ({pressure_tend:+.1f})" if pressure_tend else ""))
        return result, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ KBOS: {e}")
        return None, meta


def fetch_kbvy_obs():
    """Fetch Beverly Airport (KBVY) METAR."""
    print("📡 Fetching KBVY obs...")
    url = "https://aviationweather.gov/cgi-bin/data/metar.php?ids=KBVY&format=json"
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        r = requests.get(url, headers=HEADERS_DEFAULT, timeout=30)
        r.raise_for_status()
        data = r.json()

        if not data:
            raise ValueError("Empty METAR response")

        obs = data[0]
        result = {
            "station": "KBVY",
            "obs_time": obs.get("obsTime"),
            "temp_f": safe_float(obs.get("temp")),
            "dewpoint_f": safe_float(obs.get("dewp")),
            "wind_speed_kt": safe_float(obs.get("wspd")),
            "wind_dir": safe_float(obs.get("wdir")),
            "visibility_sm": safe_float(obs.get("visib")),
        }

        save_json(KBVY_CACHE_FILE, result)

        meta["status"] = "ok"
        print(f"  ✓ KBVY: {result['temp_f']}°F")
        return result, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ KBVY: {e}")
        return None, meta


def fetch_buoy_44013():
    """
    Fetch Boston buoy 44013 observations.
    Caches rolling pressure history for trend calculation.
    """
    print("📡 Fetching Buoy 44013...")
    url = "https://www.ndbc.noaa.gov/data/realtime2/44013.txt"
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        r = requests.get(url, headers=HEADERS_DEFAULT, timeout=30)
        r.raise_for_status()

        lines = r.text.strip().split('\n')
        if len(lines) < 3:
            raise ValueError("Insufficient data lines")

        # Skip header lines, parse most recent observation
        data_line = lines[2].split()
        if len(data_line) < 13:
            raise ValueError("Malformed data line")

        pressure_hpa = safe_float(data_line[12])
        water_temp_c = safe_float(data_line[14]) if len(data_line) > 14 else None

        if pressure_hpa is None:
            raise ValueError("No pressure reading")

        # Convert water temp to F
        water_temp_f = round(water_temp_c * 9/5 + 32, 1) if water_temp_c else None

        # Load cache and compute trend
        cache = load_json(BUOY_CACHE_FILE) or {"history": []}
        history = cache.get("history", [])
        
        obs_time = iso_utc_now()
        history.append({"time": obs_time, "pressure_hpa": pressure_hpa})
        history = history[-12:]  # Keep last 3 hours

        pressure_tend = None
        if len(history) >= 2:
            pressure_tend = round(history[-1]["pressure_hpa"] - history[0]["pressure_hpa"], 1)

        result = {
            "station": "44013",
            "pressure_hpa": pressure_hpa,
            "pressure_tend_hpa": pressure_tend,
            "water_temp_f": water_temp_f,
        }

        save_json(BUOY_CACHE_FILE, {"history": history, "latest": result})

        meta["status"] = "ok"
        print(f"  ✓ Buoy: {pressure_hpa} hPa, {water_temp_f}°F")
        return result, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ Buoy: {e}")
        return None, meta
"""
Fetch NOAA observations (KBOS, KBVY, Buoy 44013)
"""
import requests
from ..utils import iso_utc_now


def fetch_kbos_obs():
    """Fetch KBOS METAR from Aviation Weather new API."""
    print("📡 Fetching KBOS obs...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}
    
    try:
        url = "https://aviationweather.gov/api/data/metar"
        r = requests.get(url, params={"ids": "KBOS", "format": "json"}, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        if not data or len(data) == 0:
            raise ValueError("No data returned")
        
        obs = data[0]  # First result
        temp_c = obs.get("temp")
        
        result = {
            "station": obs.get("icaoId"),
            "temp_f": round(temp_c * 9/5 + 32, 1) if temp_c is not None else None,
            "dewpoint_c": obs.get("dewp"),
            "pressure_hpa": obs.get("altim"),
            "pressure_tend_hpa": obs.get("presTend"),
            "wind_speed_kt": obs.get("wspd"),
            "wind_dir": obs.get("wdir"),
        }
        
        meta["status"] = "ok"
        print(f"  ✓ KBOS: {result.get('temp_f')}°F, {result.get('pressure_hpa')} hPa")
        return result, meta
        
    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ KBOS: {e}")
        return None, meta


def fetch_kbvy_obs():
    """Fetch KBVY METAR from Aviation Weather new API."""
    print("📡 Fetching KBVY obs...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}
    
    try:
        url = "https://aviationweather.gov/api/data/metar"
        r = requests.get(url, params={"ids": "KBVY", "format": "json"}, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        if not data or len(data) == 0:
            raise ValueError("No data returned")
        
        obs = data[0]
        temp_c = obs.get("temp")
        
        result = {
            "station": obs.get("icaoId"),
            "temp_f": round(temp_c * 9/5 + 32, 1) if temp_c is not None else None,
            "dewpoint_c": obs.get("dewp"),
            "pressure_hpa": obs.get("altim"),
            "wind_speed_kt": obs.get("wspd"),
            "wind_dir": obs.get("wdir"),
        }
        
        meta["status"] = "ok"
        print(f"  ✓ KBVY: {result.get('temp_f')}°F")
        return result, meta
        
    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ KBVY: {e}")
        return None, meta


def fetch_buoy_44013():
    """Fetch Buoy 44013 latest observation from NDBC."""
    print("📡 Fetching Buoy 44013...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}
    
    try:
        url = "https://www.ndbc.noaa.gov/data/latest_obs/44013.rss"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        
        # Parse RSS (simple text extraction)
        text = r.text
        
        # Extract data between tags
        def extract(tag):
            start = text.find(f"<{tag}>")
            end = text.find(f"</{tag}>")
            if start == -1 or end == -1:
                return None
            return text[start + len(tag) + 2:end].strip()
        
        pressure_mb = extract("pressure")
        water_temp_c = extract("water_temp")
        wind_speed_kt = extract("wind_speed")
        wave_height_ft = extract("wave_height")
        
        result = {
            "station": "44013",
            "pressure_hpa": float(pressure_mb) if pressure_mb else None,
            "pressure_tend_hpa": None,
            "water_temp_f": round(float(water_temp_c) * 9/5 + 32, 1) if water_temp_c else None,
            "wind_speed_kt": float(wind_speed_kt) if wind_speed_kt else None,
            "wave_height_ft": float(wave_height_ft) if wave_height_ft else None,
        }
        
        meta["status"] = "ok"
        print(f"  ✓ Buoy: {result.get('pressure_hpa')} hPa, {result.get('water_temp_f')}°F")
        return result, meta
        
    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ Buoy: {e}")
        return None, meta
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
        
        obs = data[0]
        temp_c = obs.get("temp")
        
        result = {
            "station": obs.get("icaoId"),
            "temp_f": round(temp_c * 9/5 + 32, 1) if temp_c is not None else None,
            "dewpoint_c": obs.get("dewp"),
            "pressure_hpa": obs.get("altim"),
            "pressure_tend_hpa": obs.get("presTend"),
            "wind_speed_kt": obs.get("wspd"),
            "wind_dir": obs.get("wdir"),
            "present_weather": obs.get("wxString")
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
            "present_weather": obs.get("wxString"),
        }
        
        meta["status"] = "ok"
        print(f"  ✓ KBVY: {result.get('temp_f')}°F")
        return result, meta
        
    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ KBVY: {e}")
        return None, meta


def fetch_buoy_44013():
    """Fetch Buoy 44013 latest observation from NDBC RSS feed."""
    print("📡 Fetching Buoy 44013...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}
    
    try:
        url = "https://www.ndbc.noaa.gov/data/latest_obs/44013.rss"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        text = r.text
        
        # Find the item description (second CDATA block)
        first = text.find("<description><![CDATA[")
        first_end = text.find("]]></description>", first)
        second = text.find("<description><![CDATA[", first_end)
        second_end = text.find("]]></description>", second)
        
        if second == -1:
            raise ValueError("Could not find item description")
        
        desc = text[second + 22:second_end]
        
        # Extract numeric values from HTML description
        import re
        
        def get_num(label):
            """Extract first number after a label."""
            match = re.search(f"<strong>{label}:</strong>\\s*([\\d.]+)", desc)
            return match.group(1) if match else None
        
        # Wind direction special case: "SE (130°)"
        wind_dir = None
        wind_match = re.search(r"<strong>Wind Direction:</strong>\s*\w+\s*\((\d+)", desc)
        if wind_match:
            wind_dir = int(wind_match.group(1))
        
        wind_speed = get_num("Wind Speed")
        wind_gust = get_num("Wind Gust")
        pressure = get_num("Atmospheric Pressure")
        water_temp = get_num("Water Temperature")
        
        result = {
            "station": "44013",
            "pressure_hpa": round(float(pressure) * 33.8639, 1) if pressure else None,
            "pressure_tend_hpa": None,
            "water_temp_f": float(water_temp) if water_temp else None,
            "wind_speed_kt": float(wind_speed) if wind_speed else None,
            "wind_gust_kt": float(wind_gust) if wind_gust else None,
            "wind_dir": wind_dir,
            "wave_height_ft": None,
            "wave_period_sec": None,
            "wind_mph": round(float(wind_speed) * 1.15078, 1) if wind_speed else None,
        }
        
        meta["status"] = "ok"
        print(f"  ✓ Buoy: {result.get('wind_speed_kt')} kt, {result.get('water_temp_f')}°F")
        return result, meta
        
    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ Buoy: {e}")
        return None, meta
"""
Fetch NWS gridpoint data (NBM hourly forecasts)
Provides high-quality surface forecasts from National Blend of Models
"""
import requests
from ..utils import iso_utc_now

HEADERS = {"User-Agent": "MyWeatherApp/1.0"}
GRIDPOINT_URL = "https://api.weather.gov/gridpoints/BOX/76,97"


def fetch_nws_gridpoints():
    """Fetch NWS gridpoint hourly data (temperature, precip, wind)."""
    print("📡 Fetching NWS gridpoint data...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}
    
    try:
        r = requests.get(GRIDPOINT_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        properties = data.get("properties", {})
        
        # Extract hourly time series we need
        result = {
            "temperature": properties.get("temperature", {}),
            "dewpoint": properties.get("dewpoint", {}),
            "probabilityOfPrecipitation": properties.get("probabilityOfPrecipitation", {}),
            "quantitativePrecipitation": properties.get("quantitativePrecipitation", {}),
            "weather": properties.get("weather", {}),
            "windSpeed": properties.get("windSpeed", {}),
            "windDirection": properties.get("windDirection", {}),
        }
        
        meta["status"] = "ok"
        print(f"  ✓ NWS gridpoints fetched")
        return result, meta
        
    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ NWS gridpoints failed: {e}")
        return {}, meta

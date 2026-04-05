"""
Fetch weather data from Open-Meteo API (GFS, HRRR, ECMWF models)
"""
import requests

from ..config import (
    LAT, LON, OM_BASE_URL, OM_UNITS, HEADERS_DEFAULT,
    HRRR_HOURLY_VARS, GFS_ADDITIONAL_HOURLY_VARS, CURRENT_VARS, DAILY_VARS
)
from ..utils import iso_utc_now


def _om_get(params, label):
    """GET from Open-Meteo with standard error handling."""
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None, "model": label}
    try:
        r = requests.get(OM_BASE_URL, params=params, headers=HEADERS_DEFAULT, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise ValueError(data.get("reason", str(data["error"])))
        meta["status"] = "ok"
        if label == "GFS 7-day hourly":
            if "hourly" in data and "temperature_850hPa" in data["hourly"]:
                print(f"    DEBUG: GFS returned temperature_850hPa: {len(data.get('hourly', {}).get('temperature_850hPa', []))} values")
            else:
                print(f"    DEBUG: GFS did NOT return temperature_850hPa")
        print(f"  ✓ {label}")
        return data, meta
    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ {label}: {e}")
        return None, meta


def fetch_current_gfs():
    """Fetch current conditions from GFS."""
    print("📡 Fetching current conditions (GFS)...")
    params = {
        "latitude": LAT,
        "longitude": LON,
        "current": ",".join(CURRENT_VARS),
        **OM_UNITS,
    }
    return _om_get(params, "GFS current")


def fetch_hourly_hrrr():
    """Fetch 48h hourly forecast from HRRR, fallback to GFS."""
    print("📡 Fetching 48h hourly (HRRR)...")
    hrrr_hourly = ",".join(HRRR_HOURLY_VARS)
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": hrrr_hourly,
        "forecast_hours": 48,
        "past_hours": 0,
        **OM_UNITS,
    }
    data, meta = _om_get(params, "HRRR hourly")
    if data is None:
        print("  ⚠️  HRRR unavailable — falling back to GFS seamless")
        gfs_hourly = ",".join(HRRR_HOURLY_VARS + GFS_ADDITIONAL_HOURLY_VARS)
        fb = {k: v for k, v in params.items() if k != "models"}
        fb["hourly"] = gfs_hourly
        data, meta = _om_get(fb, "GFS seamless (HRRR fallback)")
    return data, meta


def fetch_daily_ecmwf():
    """Fetch 10-day daily forecast from ECMWF, fallback to GFS."""
    print("📡 Fetching 10-day daily (ECMWF)...")
    params = {
        "latitude": LAT,
        "longitude": LON,
        "daily": ",".join(DAILY_VARS),
        "models": "ecmwf_ifs025",
        "forecast_days": 10,
        **OM_UNITS,
    }
    data, meta = _om_get(params, "ECMWF daily")
    if data is None:
        print("  ⚠️  ECMWF unavailable — falling back to GFS seamless")
        fb = {k: v for k, v in params.items() if k != "models"}
        print("  ⏳ Attempting GFS fallback...")
        data, meta = _om_get(fb, "GFS seamless (ECMWF fallback)")
        if data is None:
            print("  ✗ GFS fallback also failed - no daily forecast available")
    return data, meta

def fetch_directional_clouds(lat, lon, bearing_deg, distances_miles):
    """
    Fetch cloud cover at multiple points along a bearing.
    distances_miles: list of distances (e.g., [10, 25, 50])
    Returns: dict with cloud data at each distance
    """
    from ..config import OM_BASE_URL, OM_UNITS, HEADERS_DEFAULT
    from ..processors.sunset_directional import calculate_offset_lat_lon
    from ..utils import iso_utc_now
    import requests
    import time
    
    print(f"  📡 Fetching clouds at {bearing_deg}° bearing: {distances_miles} miles...")
    
    results = {}
    for dist in distances_miles:
        new_lat, new_lon = calculate_offset_lat_lon(lat, lon, bearing_deg, dist)
        
        params = {
            "latitude": new_lat,
            "longitude": new_lon,
            "hourly": "cloud_cover_low,cloud_cover_mid,cloud_cover_high,relative_humidity_2m",
            "forecast_days": 5,
            **OM_UNITS,
        }
        
        # Try request with one retry on timeout
        for attempt in range(2):
            try:
                r = requests.get(OM_BASE_URL, params=params, headers=HEADERS_DEFAULT, timeout=60)
                r.raise_for_status()
                data = r.json()
                
                if data.get("hourly"):
                    results[f"{dist}mi"] = {
                        "latitude": new_lat,
                        "longitude": new_lon,
                        "times": data["hourly"].get("time", []),
                        "cloud_low": data["hourly"].get("cloud_cover_low", []),
                        "cloud_mid": data["hourly"].get("cloud_cover_mid", []),
                        "cloud_high": data["hourly"].get("cloud_cover_high", []),
                        "humidity": data["hourly"].get("relative_humidity_2m", []),
                    }
                    print(f"    ✓ {dist}mi ({new_lat}, {new_lon})")
                    break  # Success - exit retry loop
                else:
                    print(f"    ✗ {dist}mi - no data")
                    results[f"{dist}mi"] = None
                    break  # No retry for "no data" response
                    
            except requests.exceptions.Timeout as e:
                if attempt == 0:
                    # First attempt timed out - wait and retry
                    print(f"    ⚠️ {dist}mi - timeout, retrying in 10s...")
                    time.sleep(10)
                else:
                    # Second attempt also timed out - give up
                    print(f"    ✗ {dist}mi - timeout after retry")
                    results[f"{dist}mi"] = None
                    
            except Exception as e:
                # Other errors - don't retry
                print(f"    ✗ {dist}mi - {e}")
                results[f"{dist}mi"] = None
                break
    
    return results


def fetch_hourly_gfs_7day():
    """Fetch 7-day hourly forecast from GFS for detailed forecast text."""
    print("📡 Fetching 7-day hourly (GFS)...")
    gfs_hourly = ",".join(HRRR_HOURLY_VARS + GFS_ADDITIONAL_HOURLY_VARS)
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": gfs_hourly,
        "forecast_days": 7,
        **OM_UNITS,
    }
    return _om_get(params, "GFS 7-day hourly")

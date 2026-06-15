"""
Fetch weather data from Open-Meteo API (GFS, HRRR, ECMWF models)
"""
import requests

from ..config import (
    LAT, LON, OM_BASE_URL, OM_UNITS, HEADERS_DEFAULT,
    HRRR_HOURLY_VARS, GFS_ADDITIONAL_HOURLY_VARS, CURRENT_VARS, DAILY_VARS
)
from ..utils import iso_utc_now, redact_secrets
import logging




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
        logging.info(f"  ✓ {label}")
        return data, meta
    except Exception as e:
        meta["error"] = redact_secrets(e)
        logging.error(f"  ✗ {label}: {redact_secrets(e)}")
        return None, meta


def fetch_current_gfs():
    """Fetch current conditions from GFS."""
    logging.info("📡 Fetching current conditions (GFS)...")
    params = {
        "latitude": LAT,
        "longitude": LON,
        "current": ",".join(CURRENT_VARS),
        **OM_UNITS,
    }
    return _om_get(params, "GFS current")


def fetch_hourly_hrrr():
    """Fetch 48h hourly forecast from HRRR, fallback to GFS."""
    logging.info("📡 Fetching 48h hourly (HRRR)...")
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
        logging.warning("  ⚠️  HRRR unavailable — falling back to GFS seamless")
        gfs_hourly = ",".join(HRRR_HOURLY_VARS + GFS_ADDITIONAL_HOURLY_VARS)
        fb = {k: v for k, v in params.items() if k != "models"}
        fb["hourly"] = gfs_hourly
        data, meta = _om_get(fb, "GFS seamless (HRRR fallback)")
    return data, meta


def fetch_daily_ecmwf():
    """Fetch 10-day daily forecast from ECMWF, fallback to GFS."""
    logging.info("📡 Fetching 10-day daily (ECMWF)...")
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
        logging.warning("  ⚠️  ECMWF unavailable — falling back to GFS seamless")
        fb = {k: v for k, v in params.items() if k != "models"}
        logging.warning("  ⏳ Attempting GFS fallback...")
        data, meta = _om_get(fb, "GFS seamless (ECMWF fallback)")
        if data is None:
            logging.error("  ✗ GFS fallback also failed - no daily forecast available")
    return data, meta

def fetch_directional_clouds(lat, lon, bearing_deg, distances_miles, skip_retry=False):
    """
    Fetch cloud cover at multiple points along a bearing.
    distances_miles: list of distances (e.g., [10, 25, 50])
    skip_retry: if True, don't retry on timeout (used for warmup calls)
    Returns: dict with cloud data at each distance
    """
    from ..config import OM_BASE_URL, OM_UNITS, HEADERS_DEFAULT
    from ..processors.sunset_directional import calculate_offset_lat_lon
    from ..utils import iso_utc_now
    import requests
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    logging.info(f"  📡 Fetching clouds at {bearing_deg}° bearing: {distances_miles} miles...")
    
    def fetch_one(dist):
        new_lat, new_lon = calculate_offset_lat_lon(lat, lon, bearing_deg, dist)
        params = {
            "latitude": new_lat,
            "longitude": new_lon,
            "hourly": "cloud_cover_low,cloud_cover_mid,cloud_cover_high,relative_humidity_2m,total_column_integrated_water_vapour",
            "forecast_days": 5,
            **OM_UNITS,
        }
        max_attempts = 1 if skip_retry else 2
        for attempt in range(max_attempts):
            try:
                r = requests.get(OM_BASE_URL, params=params, headers=HEADERS_DEFAULT, timeout=10)
                r.raise_for_status()
                data = r.json()
                if data.get("hourly"):
                    logging.info(f"    ✓ {dist}mi ({new_lat}, {new_lon})")
                    return f"{dist}mi", {
                        "latitude": new_lat,
                        "longitude": new_lon,
                        "times": data["hourly"].get("time", []),
                        "cloud_low": data["hourly"].get("cloud_cover_low", []),
                        "cloud_mid": data["hourly"].get("cloud_cover_mid", []),
                        "cloud_high": data["hourly"].get("cloud_cover_high", []),
                        "humidity": data["hourly"].get("relative_humidity_2m", []),
                        "precip_water_mm": data["hourly"].get("total_column_integrated_water_vapour", []),
                    }
                else:
                    logging.error(f"    ✗ {dist}mi - no data")
                    return f"{dist}mi", None
            except requests.exceptions.Timeout:
                if attempt == 0 and not skip_retry:
                    logging.warning(f"    ⚠️ {dist}mi - timeout, retrying in 1s...")
                    time.sleep(1)
                else:
                    label = "(warmup)" if skip_retry else "after retry"
                    logging.error(f"    ✗ {dist}mi - timeout {label}")
                    return f"{dist}mi", None
            except Exception as e:
                logging.error(f"    ✗ {dist}mi - {redact_secrets(e)}")
                return f"{dist}mi", None
        return f"{dist}mi", None
    
    results = {}
    with ThreadPoolExecutor(max_workers=len(distances_miles)) as executor:
        futures = {executor.submit(fetch_one, d): d for d in distances_miles}
        for future in as_completed(futures):
            key, val = future.result()
            results[key] = val
    
    return results


def fetch_hourly_gfs_7day():
    """Fetch 7-day hourly forecast from GFS for detailed forecast text.

    Must specify models=gfs_seamless explicitly. Without it, Open-Meteo's
    default is "best available," which is HRRR for the first 48 hours.
    For the forecast text that's fine (HRRR + GFS day 3-7 is what we want
    visually), but for R4 (HRRR vs GFS spread) we need actual GFS in the
    0-48h window so the comparison is meaningful.
    """
    logging.info("📡 Fetching 7-day hourly (GFS)...")
    gfs_hourly = ",".join(HRRR_HOURLY_VARS + GFS_ADDITIONAL_HOURLY_VARS)
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": gfs_hourly,
        "forecast_days": 7,
        "models": "gfs_seamless",
        **OM_UNITS,
    }
    return _om_get(params, "GFS 7-day hourly")


def fetch_hrrr_daily_temps():
    """Fetch today's full hourly temps (past+forward) for daily high/low computation."""
    logging.info("📡 Fetching HRRR daily temps (past+forward)...")
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": "temperature_2m",
        "forecast_hours": 48,
        "past_hours": 24,
        **OM_UNITS,
    }
    data, meta = _om_get(params, "HRRR daily temps")
    return data, meta

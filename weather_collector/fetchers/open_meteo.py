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
        "models": "ncep_hrrr_conus",
        "forecast_days": 2,
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
        data, meta = _om_get(fb, "GFS seamless (ECMWF fallback)")
    return data, meta
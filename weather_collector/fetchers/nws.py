"""
Fetch NWS forecast and alerts
"""
import requests

from ..config import LAT, LON, HEADERS_DEFAULT
from ..utils import iso_utc_now


def fetch_nws_forecast():
    """Fetch NWS forecast discussion and text forecast."""
    print("📡 Fetching NWS forecast...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        # Get grid point
        point_url = f"https://api.weather.gov/points/{LAT},{LON}"
        r = requests.get(point_url, headers=HEADERS_DEFAULT, timeout=30)
        r.raise_for_status()
        point_data = r.json()

        forecast_url = point_data["properties"]["forecast"]
        
        # Get forecast
        r2 = requests.get(forecast_url, headers=HEADERS_DEFAULT, timeout=30)
        r2.raise_for_status()
        forecast_data = r2.json()

        periods = forecast_data["properties"]["periods"][:6]  # Next 3 days (6 periods)

        result = {
            "office": point_data["properties"]["gridId"],
            "periods": periods,
        }

        meta["status"] = "ok"
        print(f"  ✓ NWS forecast: {len(periods)} periods")
        return result, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ NWS forecast: {e}")
        return None, meta


def fetch_nws_alerts():
    """Fetch active NWS alerts for the area."""
    print("📡 Fetching NWS alerts...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        url = f"https://api.weather.gov/alerts/active?point={LAT},{LON}"
        r = requests.get(url, headers=HEADERS_DEFAULT, timeout=30)
        r.raise_for_status()
        data = r.json()

        alerts = data.get("features", [])

        result = {
            "count": len(alerts),
            "alerts": alerts,
        }

        meta["status"] = "ok"
        print(f"  ✓ NWS alerts: {len(alerts)} active")
        return result, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ NWS alerts: {e}")
        return None, meta
"""
Fetch tide predictions from NOAA
"""
import requests
from datetime import datetime, timedelta

from ..config import TIDE_STATION
from ..utils import iso_utc_now


def fetch_tides():
    """
    Fetch tide predictions from NOAA.
    Makes two calls:
      1. High/low events (hilo product) — capped at 8, used for tile display
      2. 6-minute interval curve (predictions product) — 48h, used for chart
    """
    print("📡 Fetching NOAA tides...")

    url = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    today = datetime.now()
    begin = today.strftime("%Y%m%d")
    end = (today + timedelta(days=2)).strftime("%Y%m%d")
    base = {
        "station": TIDE_STATION,
        "datum": "MLLW",
        "time_zone": "lst_ldt",
        "units": "english",
        "format": "json",
    }

    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        # Call 1: High/low events
        r1 = requests.get(url, params={**base, "product": "predictions", 
                                        "interval": "hilo", 
                                        "begin_date": begin, 
                                        "end_date": end}, timeout=30)
        r1.raise_for_status()
        hilo_data = r1.json()

        # Call 2: 6-minute curve (48h)
        begin_curve = today.strftime("%Y%m%d %H:%M")
        end_curve = (today + timedelta(hours=48)).strftime("%Y%m%d %H:%M")
        r2 = requests.get(url, params={**base, "product": "predictions",
                                        "interval": "6",
                                        "begin_date": begin_curve,
                                        "end_date": end_curve}, timeout=30)
        r2.raise_for_status()
        curve_data = r2.json()

        # Build result
        events = hilo_data.get("predictions", [])[:8]  # Cap at 8 events
        curve = curve_data.get("predictions", [])

        tide_result = {
            "station": TIDE_STATION,
            "events": events,
            "curve": curve,
        }

        meta["status"] = "ok"
        print(f"  ✓ Tides: {len(events)} events, {len(curve)} curve points")
        return tide_result, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ Tides: {e}")
        return None, meta
"""
Fetch tide predictions from NOAA
"""
import re
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..config import TIDE_STATION
from ..utils import iso_utc_now



def _redact_secrets(value):
    s = str(value)
    s = re.sub(r'([?&]key=)[^&\s]+', r'\1REDACTED', s)
    s = re.sub(r'(AIza[0-9A-Za-z\-_]{20,})', 'REDACTED', s)
    s = re.sub(r"((?:x-goog-api-key|api[_-]?key)[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+", r"\1REDACTED", s, flags=re.IGNORECASE)
    return s

def fetch_tides():
    """
    Fetch tide predictions from NOAA.
    Makes two calls:
      1. High/low events (hilo product) — capped at 8, used for tile display
      2. 6-minute interval curve (predictions product) — 48h, used for chart
    """
    print("📡 Fetching NOAA tides...")

    url = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    today = datetime.now(ZoneInfo("America/New_York"))
    begin = today.strftime("%Y%m%d")
    end = (today + timedelta(days=3)).strftime("%Y%m%d")
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
        begin_curve = today.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y%m%d %H:%M")
        end_curve = (today + timedelta(hours=72)).strftime("%Y%m%d %H:%M")
        r2 = requests.get(url, params={**base, "product": "predictions",
                                        "interval": "6",
                                        "begin_date": begin_curve,
                                        "end_date": end_curve}, timeout=30)
        r2.raise_for_status()
        curve_data = r2.json()

        # Build result - reformat events for UI
        raw_events = hilo_data.get("predictions", [])[:12]
        events = []
        for event in raw_events:
            # NOAA format: {t: "2026-03-15 02:54", v: "1.957", type: "L"}
            # UI expects: {date: "2026-03-15", time: "02:54", height: "1.957", type: "L"}
            timestamp = event.get("t", "")
            if " " in timestamp:
                date_part, time_part = timestamp.split(" ", 1)
            else:
                date_part, time_part = timestamp, "00:00"
            
            events.append({
                "date": date_part,
                "time": time_part,
                "height": event.get("v"),
                "type": event.get("type"),
            })

        # Curve for chart - reformat times and heights
        raw_curve = curve_data.get("predictions", [])
        curve = {
            "times": [c.get("t") for c in raw_curve],
            "heights": [float(c.get("v", 0)) for c in raw_curve],
        }

        tide_result = {
            "station": TIDE_STATION,
            "events": events,
            "curve": curve,
        }

        meta["status"] = "ok"
        print(f"  ✓ Tides: {len(events)} events, {len(curve['times'])} curve points")
        return tide_result, meta

    except Exception as e:
        meta["error"] = _redact_secrets(e)
        print(f"  ✗ Tides: {_redact_secrets(e)}")
        return None, meta
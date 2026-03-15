"""
Frost/freeze tracking and last frost date calculations
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from ..config import FROST_LOG_FILE
from ..utils import load_json, save_json


def update_frost_log(daily_data):
    """
    Update frost log with freeze/frost events from daily forecast.
    Tracks last spring frost and first fall frost.
    
    Args:
        daily_data: Daily forecast data from Open-Meteo
        
    Returns:
        dict: Updated frost log
    """
    if not daily_data:
        return load_json(FROST_LOG_FILE) or {}

    daily = daily_data.get("daily", {})
    times = daily.get("time", [])
    mins = daily.get("temperature_2m_min", [])

    if not times or not mins:
        return load_json(FROST_LOG_FILE) or {}

    # Load existing log
    frost_log = load_json(FROST_LOG_FILE) or {
        "last_spring_frost": None,
        "first_fall_frost": None,
        "events": []
    }

    eastern = ZoneInfo("America/New_York")
    now = datetime.now(eastern)
    current_year = now.year

    # Determine if we're in spring or fall season
    spring_start = datetime(current_year, 3, 1, tzinfo=eastern)
    fall_start = datetime(current_year, 9, 1, tzinfo=eastern)

    # Process forecast days for frost events
    for date_str, temp_min in zip(times, mins):
        if temp_min is None:
            continue

        forecast_date = datetime.fromisoformat(date_str).replace(tzinfo=eastern)

        # Check for freeze (<=32°F) or frost (<=36°F)
        if temp_min <= 32:
            event_type = "freeze"
        elif temp_min <= 36:
            event_type = "frost"
        else:
            continue

        # Update spring or fall frost tracking
        if spring_start <= forecast_date < fall_start:
            # Spring season
            frost_log["last_spring_frost"] = {
                "date": date_str,
                "temp_min": temp_min,
                "type": event_type
            }
        elif forecast_date >= fall_start:
            # Fall season
            if frost_log.get("first_fall_frost") is None:
                frost_log["first_fall_frost"] = {
                    "date": date_str,
                    "temp_min": temp_min,
                    "type": event_type
                }

    # Save updated log
    save_json(FROST_LOG_FILE, frost_log)
    return frost_log
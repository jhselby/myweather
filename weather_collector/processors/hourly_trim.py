"""
Trim hourly arrays so they start at the current local hour.

The Open-Meteo hourly forecast returns timestamps starting at midnight UTC,
which means at fetch time the first ~N entries are already in the past.
This trim keeps the payload focused on what's still ahead.
"""
from datetime import datetime

import pytz


LOCAL_TZ = pytz.timezone("America/New_York")


def trim_hourly_to_current_hour(weather_data):
    """Slice every array under weather_data['hourly'] to start at the current
    local hour. No-op if the hourly block is missing or already starts at the
    current hour. Mutates weather_data in place."""
    now_local = datetime.now(LOCAL_TZ)
    current_hour_iso = now_local.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    hourly_times = weather_data.get("hourly", {}).get("times", [])
    trim_idx = next((i for i, t in enumerate(hourly_times) if t >= current_hour_iso), 0)
    if trim_idx > 0 and "hourly" in weather_data:
        for key in weather_data["hourly"]:
            weather_data["hourly"][key] = weather_data["hourly"][key][trim_idx:]

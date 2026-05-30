"""
Utility functions for weather data collection and processing
"""
import math
import re
import json
from datetime import datetime, timezone
from pathlib import Path


def redact_secrets(value):
    s = str(value)
    s = re.sub(r'([?&]key=)[^&\s]+', r'\1REDACTED', s)
    s = re.sub(r'(AIza[0-9A-Za-z\-_]{20,})', 'REDACTED', s)
    s = re.sub(r'((?:x-goog-api-key|api[_-]?key)["\']?\s*[:=]\s*["\']?)[^"\'\\s,}]+', r'\1REDACTED', s, flags=re.IGNORECASE)
    return s



def iso_utc_now() -> str:
    """Return current UTC time as ISO string with 'Z' suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_float(x):
    """Convert x to float, return None on failure."""
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def load_json(path: Path):
    """Load JSON from file path, return None on any error."""
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return None


def save_json(path: Path, obj):
    """Save object as JSON to file path with 2-space indent."""
    path.write_text(json.dumps(obj, indent=2))


def compute_age_minutes(updated_at_iso: str, now_utc: datetime):
    """
    Compute age in minutes between ISO timestamp and now_utc.
    Returns None if parsing fails.
    """
    try:
        s = updated_at_iso.replace("Z", "+00:00")
        t = datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        delta = now_utc - t.astimezone(timezone.utc)
        return round(delta.total_seconds() / 60.0, 1)
    except Exception:
        return None


def magnus_dew_point_f(temp_f, rh_pct):
    """Magnus formula: dew point in °F from temperature °F and relative humidity %.
    Returns None if either input is missing or humidity is non-positive."""
    if temp_f is None or rh_pct is None or rh_pct <= 0:
        return None
    t_c = (temp_f - 32) * 5 / 9
    gamma = math.log(rh_pct / 100.0) + (17.625 * t_c) / (243.04 + t_c)
    dp_c = 243.04 * gamma / (17.625 - gamma)
    return round(dp_c * 9 / 5 + 32, 1)


def steadman_feels_like_f(temp_f, rh_pct=None, wind_mph=None, solar_wm2=None):
    """Steadman apparent temperature in °F.

    Uses the solar variant when solar_wm2 is a positive number, otherwise the
    shade variant. Missing humidity defaults to 50%; missing wind defaults to 0.
    Returns None if temp_f is None.
    """
    if temp_f is None:
        return None
    rh = rh_pct if rh_pct is not None else 50
    ws_ms = (wind_mph if wind_mph is not None else 0) * 0.44704
    t_c = (temp_f - 32) * 5 / 9
    e = (rh / 100) * 6.105 * math.exp((17.27 * t_c) / (237.7 + t_c))
    if solar_wm2 is not None and solar_wm2 > 0:
        q = solar_wm2 * 0.17
        at_c = t_c + 0.348 * e - 0.70 * ws_ms + 0.70 * q / (ws_ms + 10) - 4.25
    else:
        at_c = t_c + 0.33 * e - 0.70 * ws_ms - 4.00
    return round(at_c * 9 / 5 + 32, 1)


def get_weather_description(code: int) -> str:
    """Convert WMO weather code to human-readable description."""
    codes = {
        0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Overcast",
        45: "Fog", 48: "Freezing Fog",
        51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
        61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
        71: "Light Snow", 73: "Snow", 75: "Heavy Snow",
        77: "Snow Grains", 80: "Light Showers", 81: "Showers", 82: "Heavy Showers",
        85: "Light Snow Showers", 86: "Snow Showers",
        95: "Thunderstorm", 96: "Thunderstorm with Hail", 99: "Severe Thunderstorm"
    }
    return codes.get(code, f"Code {code}")


def get_weather_emoji(code: int) -> str:
    """Convert WMO weather code to emoji."""
    emojis = {
        0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
        45: "🌫️", 48: "🌫️",
        51: "🌦️", 53: "🌧️", 55: "🌧️",
        61: "🌧️", 63: "🌧️", 65: "🌧️",
        71: "🌨️", 73: "🌨️", 75: "🌨️",
        77: "🌨️", 80: "🌦️", 81: "🌦️", 82: "🌧️",
        85: "🌨️", 86: "🌨️",
        95: "⛈️", 96: "⛈️", 99: "⛈️"
    }
    return emojis.get(code, "🌡️")
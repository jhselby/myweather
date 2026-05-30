"""
Map raw Open-Meteo API responses to the canonical key naming used
throughout the payload (no `_2m` / `_10m` / `_msl` suffixes; arrays
default to [] when absent).
"""
from ..utils import get_weather_description, get_weather_emoji


_HOURLY_KEY_MAP = {
    "times": "time",
    "temperature": "temperature_2m",
    "apparent_temperature": "apparent_temperature",
    "humidity": "relative_humidity_2m",
    "dew_point": "dew_point_2m",
    "precipitation_probability": "precipitation_probability",
    "precipitation": "precipitation",
    "weather_code": "weather_code",
    "cloud_cover": "cloud_cover",
    "cloud_cover_low": "cloud_cover_low",
    "cloud_cover_mid": "cloud_cover_mid",
    "cloud_cover_high": "cloud_cover_high",
    "direct_radiation": "direct_radiation",
    "uv_index": "uv_index",
    "wind_speed": "wind_speed_10m",
    "wind_direction": "wind_direction_10m",
    "wind_gusts": "wind_gusts_10m",
    "pressure": "pressure_msl",
    "temperature_850hPa": "temperature_850hPa",
    "temperature_700hPa": "temperature_700hPa",
    "geopotential_height_850hPa": "geopotential_height_850hPa",
    "col_precip_type_850mb": "col_precip_type_850mb",
    "freezing_level_ft": "freezinglevel_height",
    "precip_water_mm": "total_column_integrated_water_vapour",
}

_DAILY_KEY_MAP = {
    "time": "time",
    "weather_code": "weather_code",
    "temperature_max": "temperature_2m_max",
    "temperature_min": "temperature_2m_min",
    "apparent_temperature_max": "apparent_temperature_max",
    "apparent_temperature_min": "apparent_temperature_min",
    "sunrise": "sunrise",
    "sunset": "sunset",
    "uv_index_max": "uv_index_max",
    "precipitation_sum": "precipitation_sum",
    "precipitation_probability_max": "precipitation_probability_max",
    "wind_speed_max": "wind_speed_10m_max",
    "wind_gusts_max": "wind_gusts_10m_max",
}


def normalize_current(current_data):
    """Map raw GFS current response to canonical keys.
    Returns None if `current_data` is falsy (so callers can detect missing GFS)."""
    if not current_data:
        return None
    cur = current_data.get("current", {})
    code = cur.get("weather_code", 0)
    return {
        "temperature": cur.get("temperature_2m"),
        "apparent_temperature": cur.get("apparent_temperature"),
        "humidity": cur.get("relative_humidity_2m"),
        "dew_point": cur.get("dew_point_2m"),
        "precipitation": cur.get("precipitation"),
        "weather_code": cur.get("weather_code"),
        "weather_description": get_weather_description(code),
        "weather_emoji": get_weather_emoji(code),
        "cloud_cover": cur.get("cloud_cover"),
        "pressure": cur.get("pressure_msl"),
        "wind_speed": cur.get("wind_speed_10m"),
        "wind_direction": cur.get("wind_direction_10m"),
        "wind_gusts": cur.get("wind_gusts_10m"),
        "uv_index": cur.get("uv_index"),
        "visibility": cur.get("visibility"),
    }


def normalize_hourly(hourly_data):
    """Map raw HRRR hourly response to canonical keys.
    Returns None if `hourly_data` is falsy."""
    if not hourly_data:
        return None
    h = hourly_data.get("hourly", {})
    return {canonical: h.get(raw_key, []) for canonical, raw_key in _HOURLY_KEY_MAP.items()}


def empty_hourly():
    """All hourly fields as empty arrays. Used by the Pirate Weather
    cloud-cover fallback to seed a minimal hourly block when HRRR is gone."""
    return {canonical: [] for canonical in _HOURLY_KEY_MAP}


def normalize_daily(daily_data):
    """Map raw ECMWF daily response to canonical keys.
    Returns None if `daily_data` is falsy."""
    if not daily_data:
        return None
    d = daily_data.get("daily", {})
    return {canonical: d.get(raw_key, []) for canonical, raw_key in _DAILY_KEY_MAP.items()}

"""
Normalize the 7-day GFS hourly response into the canonical key naming
used elsewhere in the payload (no `_2m` / `_10m` / `_msl` suffixes).

Two flavors:
  - `normalize_for_payload`: 9-field projection shipped as
    weather_data["hourly_7day"]
  - `normalize_for_forecast_generation`: 17-field full version, enriched
    with 850mb precip types, wet bulb temps, and surface precip types.
    Used internally by generate_forecast_text via the `gfs` arm of the
    {hrrr, gfs} forecast_hourly dict — not shipped to the frontend.
"""
from .precip_850mb import add_850mb_precip_type
from .precip_surface import add_corrected_precip_types
from .wet_bulb import add_wet_bulb_temps


# Common 9 fields — shipped to the frontend
_PAYLOAD_KEY_MAP = {
    "times": "time",
    "temperature": "temperature_2m",
    "apparent_temperature": "apparent_temperature",
    "precipitation_probability": "precipitation_probability",
    "weather_code": "weather_code",
    "cloud_cover": "cloud_cover",
    "wind_speed": "wind_speed_10m",
    "wind_direction": "wind_direction_10m",
    "wind_gusts": "wind_gusts_10m",
}

# Full 20-field set used internally — adds humidity, dew point, low/mid/high
# clouds, precipitation accumulation, and the upper-air thermal fields the
# precip-type processors need.
_FULL_KEY_MAP = {
    **_PAYLOAD_KEY_MAP,
    "humidity": "relative_humidity_2m",
    "dew_point": "dew_point_2m",
    "precipitation": "precipitation",
    "cloud_cover_low": "cloud_cover_low",
    "cloud_cover_mid": "cloud_cover_mid",
    "cloud_cover_high": "cloud_cover_high",
    "pressure": "pressure_msl",
    "temperature_850hPa": "temperature_850hPa",
    "temperature_700hPa": "temperature_700hPa",
    "geopotential_height_850hPa": "geopotential_height_850hPa",
    "col_precip_type_850mb": "col_precip_type_850mb",
}


def _normalize(raw_hourly, key_map):
    """Map raw Open-Meteo hourly keys to the canonical names."""
    return {canonical: raw_hourly.get(raw_key, []) for canonical, raw_key in key_map.items()}


def normalize_for_payload(raw_hourly):
    """9-field projection shipped as weather_data["hourly_7day"]."""
    return _normalize(raw_hourly, _PAYLOAD_KEY_MAP)


def normalize_for_forecast_generation(hourly_7day_data, weather_data):
    """Replace hourly_7day_data["hourly"] with a fully normalized version
    enriched with 850mb precip types, wet bulb temps, and surface precip
    types. The result feeds generate_forecast_text via the `gfs` arm of
    the {hrrr, gfs} forecast_hourly dict. Mutates the input in place.
    """
    normalized = _normalize(hourly_7day_data["hourly"], _FULL_KEY_MAP)
    temp_data = {"hourly": normalized, "current": weather_data.get("current", {})}
    add_850mb_precip_type(temp_data)
    add_wet_bulb_temps(temp_data)
    add_corrected_precip_types(temp_data, weather_data.get("hyperlocal", {}))
    hourly_7day_data["hourly"] = temp_data["hourly"]

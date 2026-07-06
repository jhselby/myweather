"""
Configuration constants for Wyman Cove Weather Station  
"""
from pathlib import Path
import os

# Location & Station IDs
LAT, LON = 42.5014, -70.8750
LOCATION_NAME = "Wyman Cove, Marblehead MA"
ELEVATION_FT = 30.0

TIDE_STATION = "8442645"
PWS_STATION = "KMAMARBL63"

# Schema & Cache
SCHEMA_VERSION = "1.2"
PWS_CACHE_FILE = Path("/tmp/last_pws.json")
KBOS_CACHE_FILE = Path("/tmp/last_kbos.json")
KBVY_CACHE_FILE = Path("/tmp/last_kbvy.json")
BUOY_CACHE_FILE = Path("/tmp/last_buoy.json")
FROST_LOG_FILE = Path("/tmp/frost_log.json")

# Wind Exposure Model

WIND_EXPOSURE_TABLE = [
    # Joe's direct-exposure window (2026-06-20): 270° (W) through just past
    # 0° (N) is open to the wind. Shelter builds from there going either
    # direction — gradient zones bracket the direct band.
    [  0,  15, 1.00],  # N - still direct ("just past 0")
    [ 15,  45, 0.70],  # NNE-NE - shelter starts building CW
    [ 45, 100, 0.25],  # E-ESE - 39-68ft Westlot/Ridge terrain close
    [100, 200, 0.08],  # SE-S - Marblehead + local terrain, max shelter
    [200, 245, 0.10],  # SSW-WSW - 39-78ft Crestwood/Pinecliff close
    [245, 270, 0.55],  # W-edge - shelter releasing toward direct band
    [270, 360, 1.00],  # W through N - direct exposure
]
WORRY_NOTICEABLE, WORRY_NOTABLE, WORRY_SIGNIFICANT, WORRY_SEVERE = 5, 12, 20, 30

# HTTP
HEADERS_DEFAULT = {"User-Agent": "MyWeather/1.0 (github.com/jhselby/myweather)"}

# Open-Meteo
OM_BASE_URL = "https://api.open-meteo.com/v1/forecast"
OM_UNITS = {
    "temperature_unit": "fahrenheit",
    "wind_speed_unit": "mph",
    "precipitation_unit": "inch",
    "timezone": "America/New_York",
}

HRRR_HOURLY_VARS = [
    "temperature_2m", "relative_humidity_2m", "dew_point_2m",
    "apparent_temperature", "precipitation_probability", "precipitation",
    "weather_code", "pressure_msl", "cloud_cover",
    "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
    "temperature_850hPa", "temperature_700hPa", "geopotential_height_850hPa",
    "direct_radiation", "diffuse_radiation", "shortwave_radiation", "uv_index",
    "freezinglevel_height", "total_column_integrated_water_vapour",
]

GFS_ADDITIONAL_HOURLY_VARS = ["visibility"]

CURRENT_VARS = [
    "temperature_2m", "relative_humidity_2m", "apparent_temperature",
    "precipitation", "weather_code", "cloud_cover", "pressure_msl",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", 
    "uv_index", "dew_point_2m", "visibility",
]

DAILY_VARS = [
    "weather_code", "temperature_2m_max", "temperature_2m_min",
    "apparent_temperature_max", "apparent_temperature_min",
    "sunrise", "sunset", "uv_index_max", "precipitation_sum",
    "precipitation_probability_max", "wind_speed_10m_max", "wind_gusts_10m_max",
]

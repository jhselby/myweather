"""
Configuration constants for Wyman Cove Weather Station  
"""
from pathlib import Path

# Location & Station IDs
LAT, LON = 42.5014, -70.8750
LOCATION_NAME = "Wyman Cove, Marblehead MA"
ELEVATION_FT = 30.0

TIDE_STATION = "8442645"
PWS_STATION = "KMAMARBL63"

# Schema & Cache
SCHEMA_VERSION = "1.2"
PWS_CACHE_FILE = Path("last_pws.json")
KBOS_CACHE_FILE = Path("last_kbos.json")
KBVY_CACHE_FILE = Path("last_kbvy.json")
BUOY_CACHE_FILE = Path("last_buoy.json")
FROST_LOG_FILE = Path("frost_log.json")

# Wind Exposure Model

WIND_EXPOSURE_TABLE = [
    [  0,  25, 1.00],  # N-NNE - open harbor, max exposure
    [ 25,  45, 0.70],  # NE - 39ft terrain ~200ft away, partial blocking
    [ 45, 100, 0.25],  # E-ESE - 39-68ft Westlot/Ridge terrain close, heavy blocking
    [100, 200, 0.08],  # SE-S - Marblehead + local terrain, maximum shelter
    [200, 260, 0.10],  # SSW-WSW - 39-78ft Crestwood/Pinecliff close, heavy blocking
    [260, 290, 0.40],  # W - 39ft close but harbor opens beyond, moderate
    [290, 320, 0.75],  # WNW-NW - harbor opening, high exposure
    [320, 360, 1.00],  # NW-N - open harbor, max exposure
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
]

GFS_ADDITIONAL_HOURLY_VARS = ["visibility", "uv_index"]

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
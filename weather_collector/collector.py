#!/usr/bin/env python3
"""
Wyman Cove Weather Station - Main Collector
Orchestrates all data fetching and processing
"""
import json
import os
from datetime import datetime
from pathlib import Path

from .config import SCHEMA_VERSION, LOCATION_NAME
from .utils import iso_utc_now, get_weather_description, get_weather_emoji, compute_age_minutes

# Import all fetchers
from .fetchers.open_meteo import fetch_current_gfs, fetch_hourly_hrrr, fetch_daily_ecmwf, fetch_hourly_gfs_7day, fetch_hrrr_daily_temps
from .fetchers.pws import fetch_pws_current
from .fetchers.tides import fetch_tides
from .fetchers.noaa import fetch_kbos_obs, fetch_kbvy_obs, fetch_buoy_44013
from .fetchers.nws import fetch_nws_forecast, fetch_nws_alerts
from .fetchers.salem_water import fetch_salem_water_temp
from .fetchers.nws_gridpoints import fetch_nws_gridpoints
from .fetchers.wu import fetch_wu_stations
from .fetchers.pirate_weather import fetch_pirate_weather
from .fetchers.ebird import fetch_ebird
from .fetchers.briefing_ai import generate_briefing
from .processors.wet_bulb import add_wet_bulb_temps
from .processors.sea_breeze import detect_sea_breeze
from .processors.hyperlocal import build_hyperlocal_data, compute_dew_point_spread
from .processors.precip_850mb import add_850mb_precip_type
from .processors.precip_surface import add_corrected_precip_types
from .processors.sunset_directional import build_sunset_directional_data
from .fetchers.open_meteo import fetch_directional_clouds

# Import all processors
from .processors.frost import update_frost_log
from .processors.pressure import compute_pressure_trend_hpa, get_best_pressure_trend, classify_pressure_alarm
from .processors.wind_risk import compute_wind_risk
from .processors.fog import calculate_fog_risk
from .processors.trough import compute_trough_signal
from .processors.forecast_text import generate_forecast_text
import re

GCS_BUCKET = "myweather-data"
FROST_LOG_GCS_PATH = "frost_log.json"
WEATHER_DATA_GCS_PATH = "weather_data.json"
OBS_TEMP_LOG_GCS_PATH = "obs_temp_log.json"
FROST_LOG_TMP = Path("/tmp/frost_log.json")



def _redact_secrets(value):
    s = str(value)
    s = re.sub(r'([?&]key=)[^&\s]+', r'\1REDACTED', s)
    s = re.sub(r'(AIza[0-9A-Za-z\-_]{20,})', 'REDACTED', s)
    s = re.sub(r"((?:x-goog-api-key|api[_-]?key)[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+", r"\1REDACTED", s, flags=re.IGNORECASE)
    return s

def _gcs_client():
    from google.cloud import storage
    return storage.Client()


def _download_frost_log_from_gcs():
    """Download frost_log.json from GCS to /tmp. Silently skips if not found."""
    try:
        client = _gcs_client()
        blob = client.bucket(GCS_BUCKET).blob(FROST_LOG_GCS_PATH)
        if blob.exists():
            blob.download_to_filename(str(FROST_LOG_TMP))
            print(f"  ✓ Downloaded frost_log.json from GCS")
        else:
            print(f"  ℹ  No frost_log.json in GCS yet (first run)")
    except Exception as e:
        print(f"  ⚠  Could not download frost_log.json from GCS: {_redact_secrets(e)}")


def _upload_to_gcs(data, gcs_path, label):
    """Upload a dict as JSON to GCS."""
    try:
        client = _gcs_client()
        blob = client.bucket(GCS_BUCKET).blob(gcs_path)
        payload = json.dumps(data, indent=2)
        blob.upload_from_string(payload, content_type="application/json")
        blob.cache_control = "no-cache, max-age=0"
        blob.patch()
        print(f"  ✓ Uploaded {label} to GCS ({len(payload):,} bytes)")
    except Exception as e:
        print(f"  ✗ Failed to upload {label} to GCS: {_redact_secrets(e)}")
        raise


def _load_obs_temp_log():
    """Load observed corrected temperature log from GCS."""
    try:
        client = _gcs_client()
        blob = client.bucket(GCS_BUCKET).blob(OBS_TEMP_LOG_GCS_PATH)
        if blob.exists():
            return json.loads(blob.download_as_text())
    except Exception as e:
        print(f"  ⚠  Could not load obs_temp_log.json from GCS: {_redact_secrets(e)}")
    return {"entries": []}


def _save_obs_temp_log(data):
    """Save observed corrected temperature log to GCS."""
    _upload_to_gcs(data, OBS_TEMP_LOG_GCS_PATH, "obs_temp_log.json")


def _update_obs_temp_log(corrected_temp):
    """Append current corrected temp with local timestamp; keep only today and yesterday."""
    if corrected_temp is None:
        return _load_obs_temp_log()

    import pytz
    from datetime import datetime, timedelta
    eastern = pytz.timezone("America/New_York")
    now_local = datetime.now(eastern)
    today_str = now_local.strftime("%Y-%m-%d")
    yesterday_str = (now_local - timedelta(days=1)).strftime("%Y-%m-%d")

    log = _load_obs_temp_log()
    entries = log.get("entries", [])

    entries = [e for e in entries if e.get("time", "").startswith(today_str) or e.get("time", "").startswith(yesterday_str)]

    hour_stamp = now_local.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    if not any(e.get("time") == hour_stamp for e in entries):
        entries.append({"time": hour_stamp, "temp": round(corrected_temp, 1)})

    entries.sort(key=lambda e: e.get("time", ""))
    log = {"entries": entries}
    _save_obs_temp_log(log)
    return log


def build_weather_data(current_data, hourly_data, daily_data, pws_data, tide_data,
                       kbos_data, kbvy_data, buoy_data, forecast_data, alert_data,
                       sources, wu_data=None, frost_log=None, salem_water_temp=None, sunset_directional=None, nws_gridpoints=None, hourly_7day_data=None, pirate_data=None, birds_data=None, daily_temps_data=None):
    """
    Build the complete weather data structure from all sources.
    This is the main processing function that combines all fetched data.
    """
    weather_data = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_utc_now(),
        "location": LOCATION_NAME,
        "sources": sources,
    }

    # Current conditions
    if current_data:
        current = current_data.get("current", {})
        current_units = current_data.get("current_units", {})
        weather_data["current"] = {
            "temperature": current.get("temperature_2m"),
            "apparent_temperature": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "dew_point": current.get("dew_point_2m"),
            "precipitation": current.get("precipitation"),
            "weather_code": current.get("weather_code"),
            "weather_description": get_weather_description(current.get("weather_code", 0)),
            "weather_emoji": get_weather_emoji(current.get("weather_code", 0)),
            "cloud_cover": current.get("cloud_cover"),
            "pressure": current.get("pressure_msl"),
            "wind_speed": current.get("wind_speed_10m"),
            "wind_direction": current.get("wind_direction_10m"),
            "wind_gusts": current.get("wind_gusts_10m"),
            "uv_index": current.get("uv_index"),
            "visibility": current.get("visibility")
        }
    
    # Ensure current dict exists even if GFS failed
    if "current" not in weather_data:
        weather_data["current"] = {}

    # ASOS condition override - prefer observed conditions over model
    if kbvy_data and kbvy_data.get("present_weather"):
        weather_data["current"]["condition_override"] = kbvy_data["present_weather"]
        weather_data["current"]["condition_source"] = "KBVY observed"
    
    
    # Wind override - use max of KBVY and WU stations for exposed coastal location
    wind_candidates = []
    # Save original model values for corrections display
    weather_data["current"]["model_wind_speed"] = weather_data["current"].get("wind_speed", 0)
    weather_data["current"]["model_wind_gusts"] = weather_data["current"].get("wind_gusts", 0)
    
    # Include model as a candidate so we never undercount
    wind_candidates.append({
        "source": "model",
        "gust": weather_data["current"].get("wind_gusts", 0),
        "speed": weather_data["current"].get("wind_speed", 0),
        "direction": weather_data["current"].get("wind_direction")
    })
    if kbvy_data and kbvy_data.get("wind_gust_kt"):
        wind_candidates.append({
            "source": "KBVY",
            "gust": kbvy_data["wind_gust_kt"] * 1.15078,
            "speed": kbvy_data["wind_speed_kt"] * 1.15078 if kbvy_data.get("wind_speed_kt") else 0,
            "direction": kbvy_data.get("wind_dir")
        })
    if wu_data and wu_data.get("stations"):
        for station in wu_data["stations"]:
            if station.get("wind_gust_mph"):
                wind_candidates.append({
                    "source": f"WU_{station.get('station_id', 'unknown')}",
                    "gust": station["wind_gust_mph"],
                    "speed": station.get("wind_speed_mph", 0),
                    "direction": station.get("wind_direction")
                })
    
    if wind_candidates:
        # Max gust independently
        max_gust_entry = max(wind_candidates, key=lambda x: x['gust'])
        weather_data["current"]["wind_gusts"] = max_gust_entry['gust']
        
        # Max sustained independently
        max_speed_entry = max(wind_candidates, key=lambda x: x['speed'])
        weather_data["current"]["wind_speed"] = max_speed_entry['speed']
        
        # Direction from highest gust source
        if max_gust_entry['direction']:
            weather_data["current"]["wind_direction"] = max_gust_entry['direction']
        weather_data["current"]["condition_source"] = f"{max_gust_entry['source']} observed"

    # Hourly forecast
    if hourly_data:
        hourly = hourly_data.get("hourly", {})
        weather_data["hourly"] = {
            "times": hourly.get("time", []),
            "temperature": hourly.get("temperature_2m", []),
            "apparent_temperature": hourly.get("apparent_temperature", []),
            "humidity": hourly.get("relative_humidity_2m", []),
            "dew_point": hourly.get("dew_point_2m", []),
            "precipitation_probability": hourly.get("precipitation_probability", []),
            "precipitation": hourly.get("precipitation", []),
            "weather_code": hourly.get("weather_code", []),
            "cloud_cover": hourly.get("cloud_cover", []),
            "cloud_cover_low": hourly.get("cloud_cover_low", []),
            "cloud_cover_mid": hourly.get("cloud_cover_mid", []),
            "cloud_cover_high": hourly.get("cloud_cover_high", []),
            "wind_speed": hourly.get("wind_speed_10m", []),
            "wind_direction": hourly.get("wind_direction_10m", []),
            "wind_gusts": hourly.get("wind_gusts_10m", []),
            "pressure": hourly.get("pressure_msl", []),
            "temperature_850hPa": hourly.get("temperature_850hPa", []),
            "temperature_700hPa": hourly.get("temperature_700hPa", []),
            "geopotential_height_850hPa": hourly.get("geopotential_height_850hPa", []),
            "col_precip_type_850mb": hourly.get("col_precip_type_850mb", []),
        }


    # Blend observed wind into hourly forecast for exposed coastal location
    if wind_candidates and "hourly" in weather_data and "wind_gusts" in weather_data["hourly"]:
        from datetime import datetime, timezone
        observed_gust = weather_data["current"]["wind_gusts"]
        observed_speed = weather_data["current"]["wind_speed"]
        
        # Find current hour index (times are in UTC)
        now_utc = datetime.now(timezone.utc)
        import pytz; eastern = pytz.timezone("America/New_York"); now_local = datetime.now(eastern); current_hour_iso = now_local.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
        
        try:
            current_idx = weather_data["hourly"]["times"].index(current_hour_iso)
        except ValueError:
            current_idx = 0
        
        
        # Blend from current hour forward for next 24 hours
        for i in range(current_idx, min(current_idx + 24, len(weather_data["hourly"]["wind_gusts"]))):
            hours_ahead = i - current_idx
            blend_weight = max(0, 1 - (hours_ahead / 24))
            
            model_gust = weather_data["hourly"]["wind_gusts"][i]
            weather_data["hourly"]["wind_gusts"][i] = (observed_gust * blend_weight) + (model_gust * (1 - blend_weight))
            
            
            if observed_speed and "wind_speed" in weather_data["hourly"]:
                model_speed = weather_data["hourly"]["wind_speed"][i]
                weather_data["hourly"]["wind_speed"][i] = (observed_speed * blend_weight) + (model_speed * (1 - blend_weight))
    # 7-day hourly forecast (GFS)
    if hourly_7day_data:
        hourly_7day = hourly_7day_data.get("hourly", {})
        weather_data["hourly_7day"] = {
            "times": hourly_7day.get("time", []),
            "temperature": hourly_7day.get("temperature_2m", []),
            "apparent_temperature": hourly_7day.get("apparent_temperature", []),
            "precipitation_probability": hourly_7day.get("precipitation_probability", []),
            "weather_code": hourly_7day.get("weather_code", []),
            "cloud_cover": hourly_7day.get("cloud_cover", []),
            "wind_speed": hourly_7day.get("wind_speed_10m", []),
            "wind_direction": hourly_7day.get("wind_direction_10m", []),
            "wind_gusts": hourly_7day.get("wind_gusts_10m", []),
        }

    # Daily forecast
    if daily_data:
        daily = daily_data.get("daily", {})
        weather_data["daily"] = {
            "time": daily.get("time", []),
            "weather_code": daily.get("weather_code", []),
            "temperature_max": daily.get("temperature_2m_max", []),
            "temperature_min": daily.get("temperature_2m_min", []),
            "apparent_temperature_max": daily.get("apparent_temperature_max", []),
            "apparent_temperature_min": daily.get("apparent_temperature_min", []),
            "sunrise": daily.get("sunrise", []),
            "sunset": daily.get("sunset", []),
            "uv_index_max": daily.get("uv_index_max", []),
            "precipitation_sum": daily.get("precipitation_sum", []),
            "precipitation_probability_max": daily.get("precipitation_probability_max", []),
            "wind_speed_max": daily.get("wind_speed_10m_max", []),
            "wind_gusts_max": daily.get("wind_gusts_10m_max", [])
        }

    # PWS data
    if pws_data:
        weather_data["pws"] = pws_data

    # Tide data
    if tide_data:
        weather_data["tides"] = tide_data
        # Dock Day Score needs tide_curve at top level
        weather_data["tide_curve"] = tide_data.get("curve", {"times": [], "heights": []})

    # NOAA observations
    if kbos_data:
        weather_data["kbos"] = kbos_data
    if kbvy_data:
        weather_data["kbvy"] = kbvy_data
    if buoy_data:
        weather_data["buoy_44013"] = buoy_data

    # NWS forecast and alerts
    if forecast_data:
        weather_data["nws_forecast"] = forecast_data

    if alert_data:
        weather_data["alerts"] = alert_data

    # Salem water temp

    if nws_gridpoints:
        weather_data["nws_gridpoints"] = nws_gridpoints
    if salem_water_temp is not None:
        weather_data["salem_water_temp_f"] = salem_water_temp

    # WU stations (optional)
    if wu_data:
        weather_data["wu_stations"] = wu_data

    # Frost log
    if frost_log:
        weather_data["frost_log"] = frost_log

    # Pirate Weather (minutely precip, solar, CAPE)
    if pirate_data:
        weather_data["pirate_weather"] = pirate_data

    # --- Derived calculations ---
    derived = {}

    # Pressure trend
    model_trend = compute_pressure_trend_hpa(hourly_data)
    if model_trend is not None:
        derived["pressure_trend_hpa_3h"] = model_trend

    best_tend, tend_src = get_best_pressure_trend(kbos_data, buoy_data, model_trend)
    if best_tend is not None:
        derived["best_pressure_tend"] = round(best_tend, 1)
        derived["best_pressure_tend_src"] = tend_src
        
        alarm = classify_pressure_alarm(best_tend)
        derived["pressure_alarm"] = alarm["alarm"]
        derived["pressure_alarm_label"] = alarm["alarm_label"]

    # Hyperlocal corrections
    build_hyperlocal_data(weather_data, wu_data, pws_data, kbos_data)

    # Add corrected hourly arrays (bias pre-applied)
    _hyp = weather_data.get("hyperlocal", {})
    _bias = _hyp.get("weighted_bias", 0)
    _hbias = _hyp.get("bias_humidity", 0)
    if "hourly" in weather_data:
        _raw_temps = weather_data["hourly"].get("temperature", [])
        weather_data["hourly"]["corrected_temperature"] = [
            round(t + _bias, 1) if t is not None else None for t in _raw_temps
        ]
        _raw_humid = weather_data["hourly"].get("humidity", [])
        weather_data["hourly"]["corrected_humidity"] = [
            round(h + _hbias, 1) if h is not None else None for h in _raw_humid
        ]

    # Compute daily high/low using Joe's observed corrected temp so far today
    # plus Joe's remaining corrected forecast for today; tomorrow stays forecast-only.
    if "hourly" in weather_data:
        _ct_times = weather_data["hourly"].get("times", [])
        _ct_temps = weather_data["hourly"].get("corrected_temperature", [])
        from datetime import datetime, timedelta
        import pytz
        eastern = pytz.timezone("America/New_York")
        _now = datetime.now(eastern)
        _today_str = _now.strftime("%Y-%m-%d")
        _tomorrow_str = (_now + timedelta(days=1)).strftime("%Y-%m-%d")
        _current_hour_iso = _now.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")

        _obs_log = _update_obs_temp_log(_hyp.get("corrected_temp"))
        _obs_entries = _obs_log.get("entries", [])

        _obs_today = [
            e.get("temp") for e in _obs_entries
            if e.get("time", "").startswith(_today_str) and e.get("temp") is not None
        ]

        _fc_today = [
            _ct_temps[i]
            for i, t in enumerate(_ct_times)
            if i < len(_ct_temps) and _ct_temps[i] is not None and t.startswith(_today_str) and t >= _current_hour_iso
        ]

        _today_series = _obs_today + _fc_today
        if _today_series:
            derived["today_high"] = round(max(_today_series), 1)
            derived["today_low"] = round(min(_today_series), 1)

        _fc_tomorrow = [
            _ct_temps[i]
            for i, t in enumerate(_ct_times)
            if i < len(_ct_temps) and _ct_temps[i] is not None and t.startswith(_tomorrow_str)
        ]
        if _fc_tomorrow:
            derived["tomorrow_high"] = round(max(_fc_tomorrow), 1)
            derived["tomorrow_low"] = round(min(_fc_tomorrow), 1)

    
    # Corrected dew point (from corrected temp + humidity)
    _hyp = weather_data.get("hyperlocal", {})
    _ct = _hyp.get("corrected_temp")
    _ch = _hyp.get("corrected_humidity")
    if _ct is not None and _ch is not None and _ch > 0:
        import math
        _tc = (_ct - 32) * 5 / 9
        _gamma = math.log(_ch / 100) + (17.625 * _tc) / (243.04 + _tc)
        _corrected_dewpt = _gamma * 243.04 / (17.625 - _gamma) * 9 / 5 + 32
        derived["corrected_dew_point"] = round(_corrected_dewpt, 1)
        derived["dew_point_spread_f"] = round(_ct - _corrected_dewpt, 1)
    elif current_data:
        current = current_data.get("current", {})
        spread = compute_dew_point_spread(current.get("temperature_2m"), current.get("dew_point_2m"))
        if spread is not None:
            derived["dew_point_spread_f"] = spread

    # Corrected feels-like (from corrected temp + wind + humidity)
    _cw = _hyp.get("corrected_wind_speed")
    if _ct is not None:
        _fl = _ct
        _ws = _cw if _cw is not None else (weather_data.get("current", {}).get("wind_speed") or 0)
        if _ct <= 50 and _ws > 3:
            _fl = 35.74 + (0.6215 * _ct) - (35.75 * (_ws ** 0.16)) + (0.4275 * _ct * (_ws ** 0.16))
        elif _ct >= 80 and _ch is not None:
            _fl = (-42.379 + (2.04901523 * _ct) + (10.14333127 * _ch)
                   - (0.22475541 * _ct * _ch) - (0.00683783 * _ct * _ct)
                   - (0.05481717 * _ch * _ch) + (0.00122874 * _ct * _ct * _ch)
                   + (0.00085282 * _ct * _ch * _ch) - (0.00000199 * _ct * _ct * _ch * _ch))
        derived["corrected_feels_like"] = round(_fl, 1)

    # Fog risk
    if current_data:
        current = current_data.get("current", {})
        fog_risk = calculate_fog_risk(
            current.get("temperature_2m"),
            current.get("dew_point_2m"),
            current.get("relative_humidity_2m"),
            current.get("wind_speed_10m")
        )
        if fog_risk:
            derived["fog_label"] = fog_risk["fog_label"]
            derived["fog_probability"] = fog_risk["fog_probability"]

    # Wet bulb temperatures (for precipitation type classification)
    if "hourly" in weather_data:
        add_wet_bulb_temps(weather_data)

    
    # Wind risk
    wind_risk = compute_wind_risk(weather_data)
    if wind_risk:
        weather_data["wind_risk"] = wind_risk
        if wind_risk.get("gust", {}).get("peak_time"):
            derived["wind_peak_time"] = wind_risk["gust"]["peak_time"]

    # Trough signal
    trough_data = compute_trough_signal(hourly_data)
    if trough_data:
        derived.update(trough_data)

    if derived:
        weather_data["derived"] = derived
    
    # Add these AFTER derived dict is set
    add_850mb_precip_type(weather_data)
    detect_sea_breeze(weather_data)
    
    # Surface precipitation type (corrected, using corrected wet bulb)
    # Must be called AFTER derived dict is set at line 300
    hyperlocal_data = weather_data.get("hyperlocal", {})
    add_corrected_precip_types(weather_data, hyperlocal_data)
    
    # Process 7-day hourly data for forecast generation
    if hourly_7day_data and "hourly" in hourly_7day_data:
        # Normalize 7-day data to match 2-day structure
        raw_hourly = hourly_7day_data["hourly"]
        normalized = {
            "times": raw_hourly.get("time", []),
            "temperature": raw_hourly.get("temperature_2m", []),
            "apparent_temperature": raw_hourly.get("apparent_temperature", []),
            "humidity": raw_hourly.get("relative_humidity_2m", []),
            "dew_point": raw_hourly.get("dew_point_2m", []),
            "precipitation_probability": raw_hourly.get("precipitation_probability", []),
            "precipitation": raw_hourly.get("precipitation", []),
            "weather_code": raw_hourly.get("weather_code", []),
            "cloud_cover": raw_hourly.get("cloud_cover", []),
            "cloud_cover_low": raw_hourly.get("cloud_cover_low", []),
            "cloud_cover_mid": raw_hourly.get("cloud_cover_mid", []),
            "cloud_cover_high": raw_hourly.get("cloud_cover_high", []),
            "wind_speed": raw_hourly.get("wind_speed_10m", []),
            "wind_direction": raw_hourly.get("wind_direction_10m", []),
            "wind_gusts": raw_hourly.get("wind_gusts_10m", []),
            "pressure": raw_hourly.get("pressure_msl", []),
            "temperature_850hPa": raw_hourly.get("temperature_850hPa", []),
            "temperature_700hPa": raw_hourly.get("temperature_700hPa", []),
            "geopotential_height_850hPa": raw_hourly.get("geopotential_height_850hPa", []),
            "col_precip_type_850mb": raw_hourly.get("col_precip_type_850mb", []),
        }
        # Add 850mb precip types, wet bulb, and surface precip types
        temp_data = {"hourly": normalized, "current": weather_data.get("current", {})}
        add_850mb_precip_type(temp_data)
        add_wet_bulb_temps(temp_data)
        add_corrected_precip_types(temp_data, weather_data.get("hyperlocal", {}))
        hourly_7day_data["hourly"] = temp_data["hourly"]

    # Generate forecast text AFTER 850mb data is added
    # Use 7-day hourly data for forecast if available, otherwise fall back to 2-day
    if hourly_7day_data and "hourly" in hourly_7day_data:
        forecast_hourly = {"hrrr": weather_data.get("hourly"), "gfs": hourly_7day_data["hourly"]}
    elif "hourly" in weather_data:
        forecast_hourly = weather_data["hourly"]
    else:
        forecast_hourly = None
    
    if forecast_hourly and "daily" in weather_data:
        _hyp_bias = weather_data.get("hyperlocal", {}).get("weighted_bias", 0) or 0
        forecast_text = generate_forecast_text(forecast_hourly, weather_data["daily"], nws_gridpoints, temp_bias=_hyp_bias, derived=weather_data.get("derived", {}))
        if forecast_text:
            weather_data["forecast_text"] = forecast_text

    if sunset_directional:
        weather_data["sunset_directional"] = sunset_directional

    if birds_data:
        weather_data["birds"] = birds_data

    return weather_data


def main():
    """Main execution function."""
    import time as _time

    print("\n" + "=" * 60)
    print("Wyman Cove Weather - Modular Collector v2.0")
    print("=" * 60 + "\n")

    total_t0 = _time.time()

    def timed_fetch(name, fn, *args, **kwargs):
        t0 = _time.time()
        result = fn(*args, **kwargs)
        elapsed = _time.time() - t0
        print(f"  ⏱  {name}: {elapsed:.1f}s")
        return result

    # Download frost log from GCS before fetching (needed for update_frost_log)
    _download_frost_log_from_gcs()

    # ── Open-Meteo calls: SEQUENTIAL (rate-limit sensitive) ──
    current_data, current_meta = timed_fetch("GFS current", fetch_current_gfs)
    hourly_data, hourly_meta = timed_fetch("HRRR hourly", fetch_hourly_hrrr)
    daily_temps_data, daily_temps_meta = timed_fetch("HRRR daily temps", fetch_hrrr_daily_temps)
    hourly_7day_data, hourly_7day_meta = timed_fetch("GFS 7-day hourly", fetch_hourly_gfs_7day)
    daily_data, daily_meta = timed_fetch("ECMWF daily", fetch_daily_ecmwf)

    # ── Everything else: PARALLEL ──
    from concurrent.futures import ThreadPoolExecutor, as_completed
    parallel_t0 = _time.time()
    parallel_tasks = {
        "NWS gridpoints": (fetch_nws_gridpoints, [], {}),
        "PWS current": (fetch_pws_current, [], {}),
        "Tides": (fetch_tides, [], {}),
        "Salem water temp": (fetch_salem_water_temp, [], {}),
        "KBOS obs": (fetch_kbos_obs, [], {}),
        "KBVY obs": (fetch_kbvy_obs, [], {}),
        "Buoy 44013": (fetch_buoy_44013, [], {}),
        "WU stations": (fetch_wu_stations, [], {}),
        "NWS alerts": (fetch_nws_alerts, [], {}),
        "Pirate Weather": (fetch_pirate_weather, [], {}),
        "eBird": (fetch_ebird, [], {}),
    }
    parallel_results = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_name = {
            executor.submit(fn, *args, **kwargs): name
            for name, (fn, args, kwargs) in parallel_tasks.items()
        }
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                parallel_results[name] = future.result()
            except Exception as e:
                print(f"  ⚠️  {name} failed: {_redact_secrets(e)}")
                parallel_results[name] = (None, {"status": "error", "error": _redact_secrets(e)}) if name != "Salem water temp" else None
    print(f"  ✓ Parallel fetches complete: {_time.time() - parallel_t0:.1f}s")

    nws_gridpoints_data, nws_gridpoints_meta = parallel_results.get("NWS gridpoints", (None, {"status": "error"}))
    pws_data, pws_meta = parallel_results.get("PWS current", (None, {"status": "error"}))
    tide_data, tides_meta = parallel_results.get("Tides", (None, {"status": "error"}))
    salem_water_temp = parallel_results.get("Salem water temp")
    kbos_data, kbos_meta = parallel_results.get("KBOS obs", (None, {"status": "error"}))
    kbvy_data, kbvy_meta = parallel_results.get("KBVY obs", (None, {"status": "error"}))
    buoy_data, buoy_meta = parallel_results.get("Buoy 44013", (None, {"status": "error"}))
    wu_data, wu_meta = parallel_results.get("WU stations", (None, {"status": "error"}))
    alert_data, alerts_meta = parallel_results.get("NWS alerts", (None, {"status": "error"}))
    pirate_data, pirate_meta = parallel_results.get("Pirate Weather", (None, {"status": "error"}))
    birds_data, birds_meta = parallel_results.get("eBird", (None, {"status": "error"}))
    forecast_data, forecast_meta = {}, {"status": "disabled"}  # fetch_nws_forecast() DISABLED

    sources = {
        "gfs_current": current_meta,
        "hrrr_hourly": hourly_meta,
        "ecmwf_daily": daily_meta,
        "pws": pws_meta,
        "tides": tides_meta,
        "kbos": kbos_meta,
        "kbvy": kbvy_meta,
        "buoy_44013": buoy_meta,
        "wu_stations": wu_meta,
        "nws_forecast": forecast_meta,
        "nws_alerts": alerts_meta,
        "pirate_weather": pirate_meta,
        "ebird": birds_meta,
    }

    # Update frost log (reads/writes /tmp/frost_log.json)
    t0 = _time.time()
    print("🌡️ Updating frost log...")
    frost_log = update_frost_log(daily_data)
    print(f"  ⏱  Frost log: {_time.time() - t0:.1f}s")

    # Upload updated frost log back to GCS
    if FROST_LOG_TMP.exists():
        try:
            frost_log_data = json.loads(FROST_LOG_TMP.read_text())
            _upload_to_gcs(frost_log_data, FROST_LOG_GCS_PATH, "frost_log.json")
        except Exception as e:
            print(f"  ⚠  Could not upload frost_log.json: {_redact_secrets(e)}")

    sunset_directional = None
    if daily_data and daily_data.get("daily") and daily_data["daily"].get("sunset"):
        t0 = _time.time()
        from .config import LAT, LON
        sunset_directional = build_sunset_directional_data(
            daily_data["daily"]["sunset"],
            LAT, LON,
            fetch_directional_clouds
        )
        print(f"  ⏱  Sunset directional: {_time.time() - t0:.1f}s")

    # Build complete weather data
    t0 = _time.time()
    weather_data = build_weather_data(
        current_data, hourly_data, daily_data,
        pws_data, tide_data, kbos_data, kbvy_data, buoy_data,
        forecast_data, alert_data, sources,
        wu_data=wu_data,
        frost_log=frost_log,
        salem_water_temp=salem_water_temp,
        sunset_directional=sunset_directional,
        nws_gridpoints=nws_gridpoints_data,
        hourly_7day_data=hourly_7day_data,
        pirate_data=pirate_data,
        birds_data=birds_data,
        daily_temps_data=daily_temps_data
    )
    print(f"  ⏱  Build weather data: {_time.time() - t0:.1f}s")

    # Generate AI briefing headline
    t0 = _time.time()
    try:
        briefing = generate_briefing(weather_data)
    except Exception as e:
        print(f"  ⚠ Briefing generation failed: {e}")
        briefing = None
    elapsed = _time.time() - t0
    if briefing:
        weather_data["briefing"] = briefing
        # Calculate actual age from cached_at timestamp
        _gemini_age = 0
        if briefing.get("cached_at"):
            try:
                from datetime import datetime
                import pytz
                _cached = datetime.fromisoformat(briefing["cached_at"])
                _gemini_age = round((datetime.now(pytz.timezone("America/New_York")) - _cached).total_seconds() / 60, 1)
            except Exception:
                pass
        weather_data["sources"]["gemini"] = {"status": "ok", "age_minutes": _gemini_age}
    else:
        weather_data.setdefault("briefing", {"headline": "", "subheadline": ""})
        weather_data["sources"]["gemini"] = {"status": "error", "age_minutes": 0}
    print(f"  ⏱  Briefing AI: {elapsed:.1f}s")

    # Trim hourly arrays to start from current hour
    from datetime import datetime, timezone
    import pytz; eastern = pytz.timezone("America/New_York"); now_local = datetime.now(eastern)
    current_hour_iso = now_local.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    hourly_times = weather_data.get("hourly", {}).get("times", [])
    trim_idx = next((i for i, t in enumerate(hourly_times) if t >= current_hour_iso), 0)
    if trim_idx > 0 and "hourly" in weather_data:
        for key in weather_data["hourly"]:
            weather_data["hourly"][key] = weather_data["hourly"][key][trim_idx:]

    # Upload weather data to GCS
    _upload_to_gcs(weather_data, WEATHER_DATA_GCS_PATH, "weather_data.json")

    print("\n" + "=" * 60)
    print(f"✓ Update complete - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({_time.time() - total_t0:.1f}s total)")
    print("=" * 60 + "\n")


# Cloud Function entry point
def run(request):
    """HTTP entry point for Cloud Functions."""
    try:
        main()
        return ("OK", 200)
    except Exception as e:
        print(f"ERROR: {_redact_secrets(e)}")
        import traceback
        traceback.print_exc()
        return (f"ERROR: {_redact_secrets(e)}", 500)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Wyman Cove Weather Station - Main Collector
Orchestrates all data fetching and processing
"""
import json
import math
import os
from datetime import datetime
from pathlib import Path
import pytz

from .config import SCHEMA_VERSION, LOCATION_NAME, WIND_EXPOSURE_TABLE
from .utils import iso_utc_now, get_weather_description, get_weather_emoji, compute_age_minutes, redact_secrets

# Import all fetchers
from .fetchers.open_meteo import fetch_current_gfs, fetch_hourly_hrrr, fetch_daily_ecmwf, fetch_hourly_gfs_7day, fetch_hrrr_daily_temps
from .fetchers.pws import fetch_pws_current
from .fetchers.tides import fetch_tides
from .fetchers.noaa import fetch_kbos_obs, fetch_kbvy_obs, fetch_buoy_44013
from .fetchers.salem_water import fetch_salem_water_temp
from .fetchers.nws import fetch_nws_alerts, fetch_nws_gridpoints
from .fetchers.wu import fetch_wu_stations
from .fetchers.pirate_weather import fetch_pirate_weather
from .fetchers.ebird import fetch_ebird
from .fetchers.tempest import fetch_tempest
from .fetchers.briefing_ai import generate_briefing
from .processors.wet_bulb import add_wet_bulb_temps
from .processors.sea_breeze import detect_sea_breeze
from .processors.hyperlocal import build_hyperlocal_data, compute_dew_point_spread
from .processors.station_bias import load_history, save_history, update_history, compute_offsets
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
from .processors.thunderstorm import detect_thunderstorm
from .processors.forecast_text import generate_forecast_text
import logging

GCS_BUCKET = "myweather-data"
FROST_LOG_GCS_PATH = "frost_log.json"
WEATHER_DATA_GCS_PATH = "weather_data.json"
OBS_TEMP_LOG_GCS_PATH = "obs_temp_log.json"
FROST_LOG_TMP = Path("/tmp/frost_log.json")




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
            logging.info(f"  ✓ Downloaded frost_log.json from GCS")
        else:
            logging.info(f"  ℹ  No frost_log.json in GCS yet (first run)")
    except Exception as e:
        logging.warning(f"  ⚠  Could not download frost_log.json from GCS: {redact_secrets(e)}")


def _upload_to_gcs(data, gcs_path, label):
    """Upload a dict as JSON to GCS."""
    try:
        client = _gcs_client()
        blob = client.bucket(GCS_BUCKET).blob(gcs_path)
        payload = json.dumps(data, indent=2)
        blob.upload_from_string(payload, content_type="application/json")
        blob.cache_control = "no-cache, max-age=0"
        blob.patch()
        logging.info(f"  ✓ Uploaded {label} to GCS ({len(payload):,} bytes)")
    except Exception as e:
        logging.error(f"  ✗ Failed to upload {label} to GCS: {redact_secrets(e)}")
        raise


def _load_prev_weather_data():
    """Read the current weather_data.json from GCS as a fallback cache. Returns {} on any failure."""
    try:
        client = _gcs_client()
        blob = client.bucket(GCS_BUCKET).blob(WEATHER_DATA_GCS_PATH)
        if blob.exists():
            prev = json.loads(blob.download_as_text())
            logging.warning(f"  ✓ Loaded previous weather_data.json from GCS for fallback cache")
            return prev
        else:
            logging.info(f"  ℹ  No previous weather_data.json in GCS (first run)")
    except Exception as e:
        logging.warning(f"  ⚠  Could not load previous weather_data.json: {redact_secrets(e)}")
    return {}


def _apply_stale_fallbacks(weather_data, prev, failed_fetches):
    """
    For any source that failed this run, copy the previous run's data.
    failed_fetches: set of source names that returned None this run.
    Mutates weather_data in place. Returns list of stale source names.
    """
    if not prev:
        return []

    stale = []

    # Top-level keys: present in weather_data only when fetch succeeded
    top_level_keys = [
        "pirate_weather", "kbos", "kbvy", "wu_stations",
        "nws_gridpoints", "tides", "buoy", "sunset_directional",
    ]
    for key in top_level_keys:
        if key not in weather_data and key in prev:
            weather_data[key] = prev[key]
            stale.append(key)
            logging.error(f"  ⚠  {key}: using previous run's data (source failed)")

    # current/hourly/daily: built even when GFS fails (silently wrong).
    # Use explicit None-tracking instead of inspecting the built dict.
    for fetch_name, data_key in [("current", "current"), ("hourly", "hourly"), ("daily", "daily")]:
        if fetch_name in failed_fetches and data_key in prev:
            weather_data[data_key] = prev[data_key]
            stale.append(data_key)
            logging.error(f"  ⚠  {data_key}: using previous run's data (fetch failed)")

    return stale


def _load_obs_temp_log():
    """Load observed corrected temperature log from GCS."""
    try:
        client = _gcs_client()
        blob = client.bucket(GCS_BUCKET).blob(OBS_TEMP_LOG_GCS_PATH)
        if blob.exists():
            return json.loads(blob.download_as_text())
    except Exception as e:
        logging.warning(f"  ⚠  Could not load obs_temp_log.json from GCS: {redact_secrets(e)}")
    return {"entries": []}


def _save_obs_temp_log(data):
    """Save observed corrected temperature log to GCS."""
    _upload_to_gcs(data, OBS_TEMP_LOG_GCS_PATH, "obs_temp_log.json")


def _update_obs_temp_log(corrected_temp, precip_in=None, peak_gust_mph=None):
    """Append current corrected temp/precip/gust with local timestamp; keep only today and yesterday."""
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
    existing = next((e for e in entries if e.get("time") == hour_stamp), None)
    if existing is None:
        entry = {"time": hour_stamp, "temp": round(corrected_temp, 1)}
        if precip_in is not None:
            entry["precip_in"] = round(precip_in, 3)
        if peak_gust_mph is not None:
            entry["gust_mph"] = round(peak_gust_mph, 1)
        entries.append(entry)
    else:
        # Update gust if this run observed a higher value
        if peak_gust_mph is not None:
            existing["gust_mph"] = round(max(existing.get("gust_mph", 0), peak_gust_mph), 1)

    entries.sort(key=lambda e: e.get("time", ""))
    log = {"entries": entries}
    _save_obs_temp_log(log)
    return log


def build_weather_data(current_data, hourly_data, daily_data, pws_data, tide_data,
                       kbos_data, kbvy_data, buoy_data, alert_data,
                       sources, wu_data=None, frost_log=None, salem_water_temp=None, sunset_directional=None, nws_gridpoints=None, hourly_7day_data=None, pirate_data=None, birds_data=None, daily_temps_data=None, tempest_data=None):
    """
    Build the complete weather data structure from all sources.
    This is the main processing function that combines all fetched data.
    """
    weather_data = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_utc_now(),
        "location": LOCATION_NAME,
        "sources": sources,
        "wind_exposure_table": [list(row) for row in WIND_EXPOSURE_TABLE],
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
        "direction": weather_data["current"].get("wind_direction"),
        "waterfront": False,
    })
    if kbvy_data and kbvy_data.get("wind_gust_kt"):
        # METARs are issued at :54 past each hour — always < 60 min old, no age filter needed
        wind_candidates.append({
            "source": "KBVY",
            "gust": kbvy_data["wind_gust_kt"] * 1.15078,
            "speed": kbvy_data["wind_speed_kt"] * 1.15078 if kbvy_data.get("wind_speed_kt") else 0,
            "direction": kbvy_data.get("wind_dir"),
            "waterfront": False,
        })
    if wu_data and wu_data.get("stations"):
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)
        for station in wu_data["stations"]:
            if not station.get("wind_gust_mph"):
                continue
            # Filter stale WU observations (> 20 min old)
            ts_str = station.get("timestamp")
            if ts_str:
                try:
                    obs_dt = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc) if ts_str.endswith("Z") else datetime.fromisoformat(ts_str)
                    if obs_dt.tzinfo is None:
                        obs_dt = obs_dt.replace(tzinfo=timezone.utc)
                    age_min = (now_utc - obs_dt).total_seconds() / 60
                    if age_min > 20:
                        continue
                except (ValueError, TypeError):
                    pass  # Unparseable timestamp — include anyway
            wind_candidates.append({
                "source": f"WU_{station.get('station_id', 'unknown')}",
                "gust": station["wind_gust_mph"],
                "speed": station.get("wind_speed_mph", 0),
                "direction": station.get("wind_direction"),
                "waterfront": station.get("waterfront", False),
            })
    if tempest_data:
        for tb in tempest_data.get("stations", []):
            if not tb.get("valid") or not tb.get("wind_gust_mph"):
                continue
            # Filter stale Tempest observations (> 20 min old)
            if tb.get("age_minutes") is not None and tb["age_minutes"] > 20:
                continue
            wind_candidates.append({
                "source": f"Tempest_{tb['station_name']}",
                "gust": tb["wind_gust_mph"],
                "speed": tb.get("wind_avg_mph", 0),
                "direction": tb.get("wind_direction"),
                "waterfront": tb.get("waterfront", False),
            })

    if wind_candidates:
        # Max gust independently
        max_gust_entry = max(wind_candidates, key=lambda x: x['gust'])
        selected_gust = max_gust_entry['gust']

        # Max sustained independently
        max_speed_entry = max(wind_candidates, key=lambda x: x['speed'])
        selected_speed = max_speed_entry['speed']

        # Sanity check: if WU has ≥10 stations and the selected speed is >2x the WU aggregate,
        # the model is likely wrong high — cap at 2x WU aggregate to trust the sensor network
        wu_speed = wu_data.get("wind_speed_mph") if wu_data else None
        wu_stations_wind = wu_data.get("quality", {}).get("stations_used_wind", 0) if wu_data else 0
        if wu_speed is not None and wu_stations_wind >= 10 and selected_speed > wu_speed * 2.5:
            logging.warning(f"  ⚠️ Wind sanity cap: selected {selected_speed:.1f} mph > 2.5× WU aggregate {wu_speed:.1f} mph ({wu_stations_wind} stations) — capping")
            cap = wu_speed * 2.5
            selected_speed = min(selected_speed, cap)
            selected_gust  = min(selected_gust,  cap * 1.3)

        weather_data["current"]["wind_gusts"] = selected_gust
        weather_data["current"]["wind_speed"] = selected_speed

        # Direction: prefer the best fresh waterfront Tempest station; fall back to max-gust source
        waterfront_tempest = [
            c for c in wind_candidates
            if c["waterfront"] and c["source"].startswith("Tempest_") and c["direction"] is not None
        ]
        if waterfront_tempest:
            # Use the waterfront station with the highest gust (most exposed reading)
            dir_source = max(waterfront_tempest, key=lambda x: x['gust'])
        else:
            dir_source = max_gust_entry

        if dir_source['direction'] is not None:
            try:
                weather_data["current"]["wind_direction"] = float(dir_source['direction'])
            except (ValueError, TypeError):
                pass  # Keep existing numeric value from Open-Meteo
        weather_data["current"]["condition_source"] = f"{max_gust_entry['source']} observed"

    # Direction fallback: if GFS failed and no candidate had direction, pull from KBVY directly
    if weather_data["current"].get("wind_direction") is None:
        if kbvy_data and kbvy_data.get("wind_dir") is not None:
            try:
                weather_data["current"]["wind_direction"] = float(kbvy_data["wind_dir"])
            except (ValueError, TypeError):
                pass

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
            "direct_radiation": hourly.get("direct_radiation", []),
            "wind_speed": hourly.get("wind_speed_10m", []),
            "wind_direction": hourly.get("wind_direction_10m", []),
            "wind_gusts": hourly.get("wind_gusts_10m", []),
            "pressure": hourly.get("pressure_msl", []),
            "temperature_850hPa": hourly.get("temperature_850hPa", []),
            "temperature_700hPa": hourly.get("temperature_700hPa", []),
            "geopotential_height_850hPa": hourly.get("geopotential_height_850hPa", []),
            "col_precip_type_850mb": hourly.get("col_precip_type_850mb", []),
        }


    # Pirate Weather cloud cover fallback when HRRR is down
    if pirate_data and pirate_data.get("hourly_cloud_cover"):
        if "hourly" not in weather_data:
            # HRRR completely unavailable — build a minimal hourly block from PW data
            import pytz
            _eastern = pytz.timezone("America/New_York")
            _pw_times = [
                _eastern.localize(__import__("datetime").datetime.fromtimestamp(ts)).strftime("%Y-%m-%dT%H:%M")
                for ts in pirate_data.get("hourly_times", [])
                if ts is not None
            ]
            _pw_cc = pirate_data["hourly_cloud_cover"][:len(_pw_times)]
            weather_data["hourly"] = {
                "times": _pw_times,
                "cloud_cover": _pw_cc,
                "cloud_cover_low": [], "cloud_cover_mid": [], "cloud_cover_high": [],
                "temperature": [], "apparent_temperature": [], "humidity": [],
                "dew_point": [], "precipitation_probability": [], "precipitation": [],
                "weather_code": [], "direct_radiation": [], "wind_speed": [],
                "wind_direction": [], "wind_gusts": [], "pressure": [],
                "temperature_850hPa": [], "temperature_700hPa": [],
                "geopotential_height_850hPa": [], "col_precip_type_850mb": [],
            }
            logging.warning("  ⚠️ HRRR unavailable — using Pirate Weather cloud cover for hourly block")
        elif not weather_data["hourly"].get("cloud_cover"):
            # HRRR returned data but cloud cover is empty — patch from PW
            weather_data["hourly"]["cloud_cover"] = pirate_data["hourly_cloud_cover"][:len(weather_data["hourly"]["times"])]
            logging.warning("  ⚠️ HRRR cloud cover empty — patched from Pirate Weather")

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

    if tempest_data:
        weather_data["tempest"] = tempest_data

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

    # Hyperlocal corrections with per-station bias tracking
    _gcs = _gcs_client()
    _station_history = load_history(_gcs, GCS_BUCKET)
    _station_offsets = compute_offsets(_station_history)
    build_hyperlocal_data(weather_data, wu_data, pws_data, kbos_data, tempest_data=tempest_data, station_offsets=_station_offsets, kbvy_data=kbvy_data)
    update_history(_station_history, wu_data, tempest_data)
    save_history(_station_history, _gcs, GCS_BUCKET)

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

        # Corrected apparent temperature (Steadman shade formula) for all hourly periods
        _ct_arr = weather_data["hourly"]["corrected_temperature"]
        _ch_arr = weather_data["hourly"]["corrected_humidity"]
        _ws_arr = weather_data["hourly"].get("wind_speed", [])
        _dr_arr = weather_data["hourly"].get("direct_radiation", [])
        _corrected_at = []
        for i in range(len(_ct_arr)):
            _t = _ct_arr[i] if i < len(_ct_arr) else None
            _h = _ch_arr[i] if i < len(_ch_arr) else None
            _w = _ws_arr[i] if i < len(_ws_arr) else None
            _dr = _dr_arr[i] if i < len(_dr_arr) else None
            if _t is not None:
                _tc = (_t - 32) * 5 / 9
                _ws_ms = (_w or 0) * 0.44704
                _rh = _h if _h is not None else 50
                _e = (_rh / 100) * 6.105 * math.exp((17.27 * _tc) / (237.7 + _tc))
                if _dr is not None and _dr > 0:
                    _Q = _dr * 0.17
                    _at_c = _tc + 0.348 * _e - 0.70 * _ws_ms + 0.70 * _Q / (_ws_ms + 10) - 4.25
                else:
                    _at_c = _tc + 0.33 * _e - 0.70 * _ws_ms - 4.00
                _corrected_at.append(round(_at_c * 9 / 5 + 32, 1))
            else:
                _corrected_at.append(None)
        weather_data["hourly"]["corrected_apparent_temperature"] = _corrected_at

        # Corrected dew point and absolute humidity for all hourly periods
        _corrected_dp = []
        _corrected_ah = []
        for i in range(len(_ct_arr)):
            _t = _ct_arr[i] if i < len(_ct_arr) else None
            _h = _ch_arr[i] if i < len(_ch_arr) else None
            if _t is not None and _h is not None:
                _tc = (_t - 32) * 5 / 9
                _gamma = math.log(_h / 100) + (17.625 * _tc) / (243.04 + _tc)
                _dp_c = 243.04 * _gamma / (17.625 - _gamma)
                _dp_f = _dp_c * 9 / 5 + 32
                _corrected_dp.append(round(_dp_f, 1))
                # Absolute humidity (g/m³)
                _e = 6.112 * math.exp((17.67 * _dp_c) / (_dp_c + 243.5))
                _ah = (_e * 216.7) / (_tc + 273.15)
                _corrected_ah.append(round(_ah, 1))
            else:
                _corrected_dp.append(None)
                _corrected_ah.append(None)
        weather_data["hourly"]["corrected_dew_point"] = _corrected_dp
        weather_data["hourly"]["corrected_absolute_humidity"] = _corrected_ah

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
        _yesterday_str = (_now - timedelta(days=1)).strftime("%Y-%m-%d")
        _tomorrow_str = (_now + timedelta(days=1)).strftime("%Y-%m-%d")
        _current_hour_iso = _now.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")

        _hourly_times = weather_data["hourly"].get("times", [])
        _hourly_precip_mm = weather_data["hourly"].get("precipitation", [])
        _cur_hour_precip_in = None
        if _current_hour_iso in _hourly_times:
            _ci = _hourly_times.index(_current_hour_iso)
            if _ci < len(_hourly_precip_mm) and _hourly_precip_mm[_ci] is not None:
                _cur_hour_precip_in = _hourly_precip_mm[_ci] / 25.4
        _cur_gust = _hyp.get("corrected_wind_gusts") or weather_data.get("current", {}).get("wind_gusts")

        _obs_log = _update_obs_temp_log(_hyp.get("corrected_temp"), precip_in=_cur_hour_precip_in, peak_gust_mph=_cur_gust)
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

        _entries_yesterday = [e for e in _obs_entries if e.get("time", "").startswith(_yesterday_str)]
        _obs_yesterday_temps = [e["temp"] for e in _entries_yesterday if e.get("temp") is not None]
        if _obs_yesterday_temps:
            derived["yesterday_high"] = round(max(_obs_yesterday_temps), 1)
        _obs_yesterday_precip = [e["precip_in"] for e in _entries_yesterday if e.get("precip_in") is not None]
        if _obs_yesterday_precip:
            derived["yesterday_precip_in"] = round(sum(_obs_yesterday_precip), 2)
        _obs_yesterday_gusts = [e["gust_mph"] for e in _entries_yesterday if e.get("gust_mph") is not None]
        if _obs_yesterday_gusts:
            derived["yesterday_peak_gust"] = round(max(_obs_yesterday_gusts), 1)

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

    # Corrected feels-like (Steadman apparent temperature)
    # Shade: AT = Ta + 0.33*e - 0.70*ws - 4.00
    # Radiation: AT = Ta + 0.348*e - 0.70*ws + 0.70*Q/(ws+10) - 4.25
    _cw = _hyp.get("corrected_wind_speed")
    if _ct is not None:
        _tc_fl = (_ct - 32) * 5 / 9
        _ws_mph = _cw if _cw is not None else (weather_data.get("current", {}).get("wind_speed") or 0)
        _ws_ms = _ws_mph * 0.44704
        _rh = _ch if _ch is not None else 50
        _e = (_rh / 100) * 6.105 * math.exp((17.27 * _tc_fl) / (237.7 + _tc_fl))
        # Solar source priority: Pirate Weather current → Tempest station avg → Open-Meteo direct_radiation
        _solar_wm2 = None
        # 1. Pirate Weather (point forecast for our exact location)
        _pw_solar = weather_data.get("pirate_weather", {}).get("current_solar")
        if isinstance(_pw_solar, (int, float)) and _pw_solar >= 0:
            _solar_wm2 = _pw_solar
        # 2. Average of valid Tempest stations
        if _solar_wm2 is None:
            _t_solar_vals = [
                s["solar_radiation_wm2"] for s in weather_data.get("tempest", {}).get("stations", [])
                if s.get("valid") and isinstance(s.get("solar_radiation_wm2"), (int, float))
            ]
            if _t_solar_vals:
                _solar_wm2 = sum(_t_solar_vals) / len(_t_solar_vals)
        # 3. Open-Meteo direct_radiation (hourly, modeled)
        if _solar_wm2 is None:
            _hourly_direct = weather_data.get("hourly", {}).get("direct_radiation", [])
            _hourly_times = weather_data.get("hourly", {}).get("times", [])
            from datetime import datetime as _dt
            import pytz
            _eastern = pytz.timezone("America/New_York")
            _now_hr = _dt.now(_eastern).strftime("%Y-%m-%dT%H:00")
            for _i, _t in enumerate(_hourly_times):
                if _t == _now_hr and _i < len(_hourly_direct):
                    _solar_wm2 = _hourly_direct[_i]
                    break
        if _solar_wm2 is not None and _solar_wm2 > 0:
            _Q = _solar_wm2 * 0.17
            _at_c = _tc_fl + 0.348 * _e - 0.70 * _ws_ms + 0.70 * _Q / (_ws_ms + 10) - 4.25
        else:
            _at_c = _tc_fl + 0.33 * _e - 0.70 * _ws_ms - 4.00
        _fl = _at_c * 9 / 5 + 32
        derived["corrected_feels_like"] = round(_fl, 1)

        # NWS heat index (shade, no solar term) — valid above 80°F
        if _ct >= 80 and _rh >= 35:
            T, RH = _ct, _rh
            _hi = (-42.379 + 2.04901523*T + 10.14333127*RH - 0.22475541*T*RH
                   - 6.83783e-3*T**2 - 5.481717e-2*RH**2 + 1.22874e-3*T**2*RH
                   + 8.5282e-4*T*RH**2 - 1.99e-6*T**2*RH**2)
            derived["heat_index"] = round(_hi, 1)

    # Fog risk — fall back to HRRR hourly[0] if GFS current is missing
    _fog_current = None
    if current_data:
        _fog_current = current_data.get("current", {})
    elif hourly_data and "hourly" in hourly_data:
        _h = hourly_data["hourly"]
        _fog_current = {
            "temperature_2m": (_h.get("temperature_2m") or [None])[0],
            "dew_point_2m": (_h.get("dew_point_2m") or [None])[0],
            "relative_humidity_2m": (_h.get("relative_humidity_2m") or [None])[0],
            "wind_speed_10m": (_h.get("wind_speed_10m") or [None])[0],
            "wind_direction_10m": (_h.get("wind_direction_10m") or [None])[0],
        }
        logging.warning("  ⚠️ GFS current unavailable, using HRRR hourly[0] for fog calc")
    if _fog_current:
        current = _fog_current
        _buoy = weather_data.get("buoy_44013", {})
        fog_risk = calculate_fog_risk(
            current.get("temperature_2m"),
            current.get("dew_point_2m"),
            current.get("relative_humidity_2m"),
            current.get("wind_speed_10m"),
            wind_direction=current.get("wind_direction_10m"),
            water_temp_f=_buoy.get("water_temp_f")
        )
        if fog_risk:
            derived["fog_label"] = fog_risk["fog_label"]
            derived["fog_probability"] = fog_risk["fog_probability"]

        # Hourly fog probability for next 12h — used for dissipation timing
        _h = weather_data.get("hourly", {})
        _htimes   = _h.get("times", [])
        _htemps   = _h.get("corrected_temperature", _h.get("temperature", []))
        _hdewpts  = _h.get("corrected_dew_point",   _h.get("dew_point", []))
        _hhumids  = _h.get("corrected_humidity",    _h.get("humidity", []))
        _hwinds   = _h.get("wind_speed", [])
        _hwdirs   = _h.get("wind_direction", [])
        _water_f  = weather_data.get("buoy_44013", {}).get("water_temp_f")
        _hourly_fog_probs = []
        for _i in range(min(18, len(_htimes))):
            _fr = calculate_fog_risk(
                _htemps[_i]  if _i < len(_htemps)  else None,
                _hdewpts[_i] if _i < len(_hdewpts)  else None,
                _hhumids[_i] if _i < len(_hhumids)  else None,
                _hwinds[_i]  if _i < len(_hwinds)   else None,
                wind_direction=_hwdirs[_i] if _i < len(_hwdirs) else None,
                water_temp_f=_water_f,
            )
            _hourly_fog_probs.append(_fr["fog_probability"] if _fr else 0)
        derived["fog_hourly_prob"] = _hourly_fog_probs
        derived["fog_hourly_times"] = _htimes[:18]
        # Find dissipation: first run of 2+ consecutive hours below 20%
        _diss_hour = None
        for _i in range(len(_hourly_fog_probs) - 1):
            if _hourly_fog_probs[_i] < 20 and _hourly_fog_probs[_i + 1] < 20:
                _diss_hour = _htimes[_i] if _i < len(_htimes) else None
                break
        if _diss_hour:
            derived["fog_dissipation_hour"] = _diss_hour

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

    # Thunderstorm detection
    ts = detect_thunderstorm(weather_data)
    weather_data["derived"]["thunderstorm"] = ts
    if ts.get("sky_override"):
        weather_data.setdefault("current", {})["condition_override"] = ts["sky_override"]
    
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

    logging.info("\n" + "=" * 60)
    logging.info("Wyman Cove Weather - Modular Collector v2.0")
    logging.info("=" * 60 + "\n")

    total_t0 = _time.time()

    def timed_fetch(name, fn, *args, **kwargs):
        t0 = _time.time()
        result = fn(*args, **kwargs)
        elapsed = _time.time() - t0
        logging.info(f"  ⏱  {name}: {elapsed:.1f}s")
        return result

    # Load previous weather data for stale fallback cache
    prev_weather_data = _load_prev_weather_data()

    # Download frost log from GCS before fetching (needed for update_frost_log)
    _download_frost_log_from_gcs()

    # ── Open-Meteo calls: SEQUENTIAL (rate-limit sensitive) ──
    current_data, current_meta = timed_fetch("GFS current", fetch_current_gfs)
    hourly_data, hourly_meta = timed_fetch("HRRR hourly", fetch_hourly_hrrr)
    daily_temps_data, daily_temps_meta = timed_fetch("HRRR daily temps", fetch_hrrr_daily_temps)
    hourly_7day_data, hourly_7day_meta = timed_fetch("GFS 7-day hourly", fetch_hourly_gfs_7day)
    daily_data, daily_meta = timed_fetch("ECMWF daily", fetch_daily_ecmwf)

    # Track which sequential fetches returned None (used by stale fallback)
    failed_fetches = set()
    if current_data is None:   failed_fetches.add("current")
    if hourly_data is None:    failed_fetches.add("hourly")
    if daily_data is None:     failed_fetches.add("daily")

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
        "Tempest": (fetch_tempest, [], {}),
    }
    parallel_results = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_name = {
            executor.submit(fn, *args, **kwargs): name
            for name, (fn, args, kwargs) in parallel_tasks.items()
        }
        for future in as_completed(future_to_name, timeout=60):
            name = future_to_name[future]
            try:
                parallel_results[name] = future.result(timeout=45)
            except TimeoutError:
                logging.warning(f"  ⚠️  {name} timed out (45s)")
                parallel_results[name] = (None, {"status": "error", "error": "timeout"}) if name != "Salem water temp" else None
            except Exception as e:
                logging.error(f"  ⚠️  {name} failed: {redact_secrets(e)}")
                parallel_results[name] = (None, {"status": "error", "error": redact_secrets(e)}) if name != "Salem water temp" else None
    logging.info(f"  ✓ Parallel fetches complete: {_time.time() - parallel_t0:.1f}s")

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
    tempest_data, tempest_meta = parallel_results.get("Tempest", (None, {"status": "error"}))

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
        "nws_alerts": alerts_meta,
        "pirate_weather": pirate_meta,
        "ebird": birds_meta,
        "tempest": tempest_meta,
    }

    # Update frost log (reads/writes /tmp/frost_log.json)
    t0 = _time.time()
    logging.info("🌡️ Updating frost log...")
    frost_log = update_frost_log(daily_data)
    logging.info(f"  ⏱  Frost log: {_time.time() - t0:.1f}s")

    # Upload updated frost log back to GCS
    if FROST_LOG_TMP.exists():
        try:
            frost_log_data = json.loads(FROST_LOG_TMP.read_text())
            _upload_to_gcs(frost_log_data, FROST_LOG_GCS_PATH, "frost_log.json")
        except Exception as e:
            logging.warning(f"  ⚠  Could not upload frost_log.json: {redact_secrets(e)}")

    sunset_directional = None
    if daily_data and daily_data.get("daily") and daily_data["daily"].get("sunset"):
        t0 = _time.time()
        from .config import LAT, LON
        sunset_directional = build_sunset_directional_data(
            daily_data["daily"]["sunset"],
            LAT, LON,
            fetch_directional_clouds
        )
        logging.info(f"  ⏱  Sunset directional: {_time.time() - t0:.1f}s")

    # Build complete weather data
    t0 = _time.time()
    weather_data = build_weather_data(
        current_data, hourly_data, daily_data,
        pws_data, tide_data, kbos_data, kbvy_data, buoy_data,
        alert_data, sources,
        wu_data=wu_data,
        frost_log=frost_log,
        salem_water_temp=salem_water_temp,
        sunset_directional=sunset_directional,
        nws_gridpoints=nws_gridpoints_data,
        hourly_7day_data=hourly_7day_data,
        pirate_data=pirate_data,
        birds_data=birds_data,
        daily_temps_data=daily_temps_data,
        tempest_data=tempest_data
    )
    logging.info(f"  ⏱  Build weather data: {_time.time() - t0:.1f}s")

    # Generate AI briefing headline
    t0 = _time.time()
    try:
        briefing = generate_briefing(weather_data)
    except Exception as e:
        logging.error(f"  ⚠ Briefing generation failed: {e}")
        briefing = None
    elapsed = _time.time() - t0
    if briefing:
        weather_data["briefing"] = briefing
        # Calculate actual age from cached_at timestamp
        _gemini_age = 0
        if briefing.get("cached_at"):
            try:
                _cached = datetime.fromisoformat(briefing["cached_at"])
                _gemini_age = round((datetime.now(pytz.timezone("America/New_York")) - _cached).total_seconds() / 60, 1)
            except Exception:
                pass
        weather_data["sources"]["gemini"] = {"status": "ok", "age_minutes": _gemini_age}
    else:
        weather_data.setdefault("briefing", {"headline": "", "subheadline": ""})
        weather_data["sources"]["gemini"] = {"status": "error", "age_minutes": 0}
    logging.info(f"  ⏱  Briefing AI: {elapsed:.1f}s")

    # Trim hourly arrays to start from current hour
    now_local = datetime.now(pytz.timezone("America/New_York"))
    current_hour_iso = now_local.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    hourly_times = weather_data.get("hourly", {}).get("times", [])
    trim_idx = next((i for i, t in enumerate(hourly_times) if t >= current_hour_iso), 0)
    if trim_idx > 0 and "hourly" in weather_data:
        for key in weather_data["hourly"]:
            weather_data["hourly"][key] = weather_data["hourly"][key][trim_idx:]

    # Apply stale fallbacks for any source that failed this run
    stale_sources = _apply_stale_fallbacks(weather_data, prev_weather_data, failed_fetches)
    if stale_sources:
        weather_data["stale_sources"] = stale_sources
        logging.warning(f"  ⚠  Stale sources in this payload: {stale_sources}")
    else:
        weather_data.pop("stale_sources", None)

    # Upload weather data to GCS
    _upload_to_gcs(weather_data, WEATHER_DATA_GCS_PATH, "weather_data.json")

    logging.info("\n" + "=" * 60)
    logging.info(f"✓ Update complete - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({_time.time() - total_t0:.1f}s total)")
    logging.info("=" * 60 + "\n")


# Cloud Function entry point
def run(request):
    """HTTP entry point for Cloud Functions."""
    try:
        main()
        return ("OK", 200)
    except Exception as e:
        logging.info(f"ERROR: {redact_secrets(e)}")
        import traceback
        traceback.print_exc()
        return (f"ERROR: {redact_secrets(e)}", 500)


if __name__ == "__main__":
    main()

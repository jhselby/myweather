#!/usr/bin/env python3
"""
Wyman Cove Weather Station - Main Collector
Orchestrates all data fetching and processing
"""
import json
import logging
import math
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytz

from .config import LAT, LON, SCHEMA_VERSION, LOCATION_NAME, WIND_EXPOSURE_TABLE
from .gcs_io import BUCKET, get_client, upload_json
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
from .processors.hyperlocal import build_hyperlocal_data
from .processors.station_bias import load_history, save_history, update_history, compute_offsets
from .processors.precip_850mb import add_850mb_precip_type
from .processors.precip_surface import add_corrected_precip_types
from .processors.sunset_directional import build_sunset_directional_data
from .fetchers.open_meteo import fetch_directional_clouds

# Import all processors
from .processors.frost import update_frost_log
from .processors.pressure import compute_pressure_trend_hpa, get_best_pressure_trend, classify_pressure_alarm
from .processors.wind_risk import compute_wind_risk
from .processors.trough import compute_trough_signal
from .processors.thunderstorm import detect_thunderstorm
from .processors.forecast_text import generate_forecast_text
from .processors.wind_blend import select_observed_wind
from .processors.corrected_hourly import add_corrected_hourly_arrays
from .processors.daily_extremes import compute_daily_extremes
from .processors.current_derived import compute_current_derived
from .processors.fog_metrics import compute_fog_metrics
from .processors.hourly_7day import normalize_for_payload, normalize_for_forecast_generation

FROST_LOG_GCS_PATH = "frost_log.json"
WEATHER_DATA_GCS_PATH = "weather_data.json"
FROST_LOG_TMP = Path("/tmp/frost_log.json")


def _download_frost_log_from_gcs():
    """Download frost_log.json from GCS to /tmp. Silently skips if not found."""
    try:
        client = get_client()
        blob = client.bucket(BUCKET).blob(FROST_LOG_GCS_PATH)
        if blob.exists():
            blob.download_to_filename(str(FROST_LOG_TMP))
            logging.info(f"  ✓ Downloaded frost_log.json from GCS")
        else:
            logging.info(f"  ℹ  No frost_log.json in GCS yet (first run)")
    except Exception as e:
        logging.warning(f"  ⚠  Could not download frost_log.json from GCS: {redact_secrets(e)}")


def _load_prev_weather_data():
    """Read the current weather_data.json from GCS as a fallback cache. Returns {} on any failure."""
    try:
        client = get_client()
        blob = client.bucket(BUCKET).blob(WEATHER_DATA_GCS_PATH)
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
    
    
    # Wind: override model with best available observation; keep candidate list
    # for downstream blending into the hourly forecast.
    wind_candidates = select_observed_wind(weather_data, kbvy_data, wu_data, tempest_data)

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
            "uv_index": hourly.get("uv_index", []),
            "wind_speed": hourly.get("wind_speed_10m", []),
            "wind_direction": hourly.get("wind_direction_10m", []),
            "wind_gusts": hourly.get("wind_gusts_10m", []),
            "pressure": hourly.get("pressure_msl", []),
            "temperature_850hPa": hourly.get("temperature_850hPa", []),
            "temperature_700hPa": hourly.get("temperature_700hPa", []),
            "geopotential_height_850hPa": hourly.get("geopotential_height_850hPa", []),
            "col_precip_type_850mb": hourly.get("col_precip_type_850mb", []),
            "freezing_level_ft": hourly.get("freezinglevel_height", []),
            "precip_water_mm": hourly.get("total_column_integrated_water_vapour", []),
        }


    # Pirate Weather cloud cover fallback when HRRR is down
    if pirate_data and pirate_data.get("hourly_cloud_cover"):
        if "hourly" not in weather_data:
            # HRRR completely unavailable — build a minimal hourly block from PW data
            _eastern = pytz.timezone("America/New_York")
            _pw_times = [
                _eastern.localize(datetime.fromtimestamp(ts)).strftime("%Y-%m-%dT%H:%M")
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
                "freezing_level_ft": [], "precip_water_mm": [],
            }
            logging.warning("  ⚠️ HRRR unavailable — using Pirate Weather cloud cover for hourly block")
        elif not weather_data["hourly"].get("cloud_cover"):
            # HRRR returned data but cloud cover is empty — patch from PW
            weather_data["hourly"]["cloud_cover"] = pirate_data["hourly_cloud_cover"][:len(weather_data["hourly"]["times"])]
            logging.warning("  ⚠️ HRRR cloud cover empty — patched from Pirate Weather")

    # Blend observed wind into hourly forecast for exposed coastal location
    if wind_candidates and "hourly" in weather_data and "wind_gusts" in weather_data["hourly"]:
        observed_gust = weather_data["current"]["wind_gusts"]
        observed_speed = weather_data["current"]["wind_speed"]

        # Find current hour index (times are in local Eastern)
        eastern = pytz.timezone("America/New_York")
        now_local = datetime.now(eastern)
        current_hour_iso = now_local.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
        
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
    # 7-day hourly forecast (GFS) — shipped projection
    if hourly_7day_data:
        weather_data["hourly_7day"] = normalize_for_payload(hourly_7day_data.get("hourly", {}))

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
    # Bind derived to weather_data["derived"] so subsequent extracted modules
    # that use setdefault("derived", {}) pick up the same dict object.
    derived = weather_data.setdefault("derived", {})

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
    _gcs = get_client()
    _station_history = load_history(_gcs, BUCKET)
    _station_offsets = compute_offsets(_station_history)
    build_hyperlocal_data(weather_data, wu_data, pws_data, kbos_data, tempest_data=tempest_data, station_offsets=_station_offsets, kbvy_data=kbvy_data)
    update_history(_station_history, wu_data, tempest_data)
    save_history(_station_history, _gcs, BUCKET)

    # Bias-corrected hourly arrays (must run after build_hyperlocal_data)
    add_corrected_hourly_arrays(weather_data)
    _hyp = weather_data.get("hyperlocal", {})

    # Daily extremes: log current obs to rolling 24h log + 48h forecast snapshot,
    # then derive today (obs + remaining forecast), yesterday (obs only),
    # tomorrow (forecast only), and current-hour atmospheric fields.
    compute_daily_extremes(weather_data)

    # Current-conditions derived metrics: corrected dew point + spread + cloud
    # base, corrected feels-like (with solar if available), and NWS heat index.
    compute_current_derived(weather_data)

    # Fog metrics: current risk + 18-hour probability array + dissipation hour
    compute_fog_metrics(weather_data)

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

    # `derived` is already weather_data["derived"] (bound via setdefault above).
    # Prune the key if nothing was added so the payload stays the same as before.
    if not weather_data["derived"]:
        weather_data.pop("derived", None)
    
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
    
    # Process 7-day hourly data for forecast text generation
    if hourly_7day_data and "hourly" in hourly_7day_data:
        normalize_for_forecast_generation(hourly_7day_data, weather_data)

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
    logging.info("\n" + "=" * 60)
    logging.info("Wyman Cove Weather - Modular Collector v2.0")
    logging.info("=" * 60 + "\n")

    total_t0 = time.time()

    def timed_fetch(name, fn, *args, **kwargs):
        t0 = time.time()
        result = fn(*args, **kwargs)
        elapsed = time.time() - t0
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
    parallel_t0 = time.time()
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
    logging.info(f"  ✓ Parallel fetches complete: {time.time() - parallel_t0:.1f}s")

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
    t0 = time.time()
    logging.info("🌡️ Updating frost log...")
    frost_log = update_frost_log(daily_data)
    logging.info(f"  ⏱  Frost log: {time.time() - t0:.1f}s")

    # Upload updated frost log back to GCS
    if FROST_LOG_TMP.exists():
        try:
            frost_log_data = json.loads(FROST_LOG_TMP.read_text())
            upload_json(frost_log_data, FROST_LOG_GCS_PATH, "frost_log.json")
        except Exception as e:
            logging.warning(f"  ⚠  Could not upload frost_log.json: {redact_secrets(e)}")

    sunset_directional = None
    if daily_data and daily_data.get("daily") and daily_data["daily"].get("sunset"):
        t0 = time.time()
        sunset_directional = build_sunset_directional_data(
            daily_data["daily"]["sunset"],
            LAT, LON,
            fetch_directional_clouds
        )
        logging.info(f"  ⏱  Sunset directional: {time.time() - t0:.1f}s")

    # Build complete weather data
    t0 = time.time()
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
    logging.info(f"  ⏱  Build weather data: {time.time() - t0:.1f}s")

    # Generate AI briefing headline
    t0 = time.time()
    try:
        briefing = generate_briefing(weather_data)
    except Exception as e:
        logging.error(f"  ⚠ Briefing generation failed: {e}")
        briefing = None
    elapsed = time.time() - t0
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
    upload_json(weather_data, WEATHER_DATA_GCS_PATH, "weather_data.json")

    logging.info("\n" + "=" * 60)
    logging.info(f"✓ Update complete - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({time.time() - total_t0:.1f}s total)")
    logging.info("=" * 60 + "\n")


# Cloud Function entry point
def run(request):
    """HTTP entry point for Cloud Functions."""
    try:
        main()
        return ("OK", 200)
    except Exception as e:
        logging.info(f"ERROR: {redact_secrets(e)}")
        traceback.print_exc()
        return (f"ERROR: {redact_secrets(e)}", 500)


if __name__ == "__main__":
    main()

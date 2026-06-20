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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytz

from .config import LAT, LON, SCHEMA_VERSION, LOCATION_NAME, WIND_EXPOSURE_TABLE
from .gcs_io import BUCKET, get_client, upload_json
from .stale_cache import apply_stale_fallbacks, load_prev_weather_data
from .utils import iso_utc_now, compute_age_minutes, redact_secrets

# Import fetchers (data fetching orchestration is fully in fetchers/fetch_all.py;
# briefing AI is called directly from main() since it needs the assembled
# weather_data as input).
from .fetchers.briefing_ai import apply_briefing_to_weather_data
from .fetchers.fetch_all import fetch_all_sources
from .fetchers.open_meteo import fetch_directional_clouds
from .processors.wet_bulb import add_wet_bulb_temps
from .processors.sea_breeze import detect_sea_breeze
from .processors.hyperlocal import build_hyperlocal_data
from .processors.station_bias import load_history, save_history, update_history, compute_offsets
from .processors.precip_850mb import add_850mb_precip_type
from .processors.precip_surface import add_corrected_precip_types
from .processors.sunset_directional import build_sunset_directional_data

# Import all processors
from .processors.frost import update_frost_log
from .processors.pressure import compute_pressure_trend_hpa, get_best_pressure_trend, classify_pressure_alarm
from .processors.wind_risk import compute_wind_risk
from .processors.trough import compute_trough_signal
from .processors.thunderstorm import detect_thunderstorm
from .processors.forecast_text import generate_forecast_text
from .processors.wind_blend import select_observed_wind, blend_observed_into_hourly
from .processors.corrected_hourly import add_corrected_hourly_arrays
from .processors.daily_extremes import compute_daily_extremes
from .processors.current_derived import compute_current_derived
from .processors.fog_metrics import compute_fog_metrics
from .processors.hourly_7day import normalize_for_payload, normalize_for_forecast_generation
from .processors.hourly_trim import trim_hourly_to_current_hour
from .processors.forecast_error_log import update_forecast_error_log
from .processors.decay_fit import fit_decay_corrections
from .processors.decay_apply import apply_decay_corrections, recompute_derived_moisture_arrays
from .processors.normalize import normalize_current, normalize_hourly, normalize_daily, empty_hourly

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
    weather_data["current"] = normalize_current(current_data) or {}

    # ASOS condition override - prefer observed conditions over model
    if kbvy_data and kbvy_data.get("present_weather"):
        weather_data["current"]["condition_override"] = kbvy_data["present_weather"]
        weather_data["current"]["condition_source"] = "KBVY observed"
    
    
    # Wind: override model with best available observation
    select_observed_wind(weather_data, kbvy_data, wu_data, tempest_data,
                         kbos_data=kbos_data)

    # Hourly forecast
    normalized_hourly = normalize_hourly(hourly_data)
    if normalized_hourly is not None:
        weather_data["hourly"] = normalized_hourly


    # Pirate Weather cloud cover fallback when HRRR is down
    if pirate_data and pirate_data.get("hourly_cloud_cover"):
        if "hourly" not in weather_data:
            # HRRR completely unavailable — seed a minimal hourly block from PW
            _eastern = pytz.timezone("America/New_York")
            _pw_times = [
                _eastern.localize(datetime.fromtimestamp(ts)).strftime("%Y-%m-%dT%H:%M")
                for ts in pirate_data.get("hourly_times", [])
                if ts is not None
            ]
            weather_data["hourly"] = empty_hourly()
            weather_data["hourly"]["times"] = _pw_times
            weather_data["hourly"]["cloud_cover"] = pirate_data["hourly_cloud_cover"][:len(_pw_times)]
            logging.warning("  ⚠️ HRRR unavailable — using Pirate Weather cloud cover for hourly block")
        elif not weather_data["hourly"].get("cloud_cover"):
            # HRRR returned data but cloud cover is empty — patch from PW
            weather_data["hourly"]["cloud_cover"] = pirate_data["hourly_cloud_cover"][:len(weather_data["hourly"]["times"])]
            logging.warning("  ⚠️ HRRR cloud cover empty — patched from Pirate Weather")

    # Blend observed wind into the next 24h of forecast (exposed coastal location)
    blend_observed_into_hourly(weather_data)
    # 7-day hourly forecast (GFS) — shipped projection
    if hourly_7day_data:
        weather_data["hourly_7day"] = normalize_for_payload(hourly_7day_data.get("hourly", {}))

    # Daily forecast
    normalized_daily = normalize_daily(daily_data)
    if normalized_daily is not None:
        weather_data["daily"] = normalized_daily

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

    # Per-tick inter-cluster spread (Marblehead/Salem/Swampscott PWS clusters).
    # Best-effort logger feeding the L6 confidence-layer axis evaluation.
    # Orthogonality to R6 confirmed 2026-06-20 (16/20 field-band combos).
    try:
        from .processors.cluster_spread import stamp_and_log as stamp_cluster_spread
        stamp_cluster_spread(weather_data, wu_data, _gcs, BUCKET)
    except Exception as e:
        logging.warning(f"  ⚠  cluster_spread skipped: {e}")

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
    
    # Log raw GFS values for HRRR-vs-GFS spread analysis. Must run BEFORE
    # normalize_for_forecast_generation rewrites the dict in place — the
    # logger reads native Open-Meteo keys (temperature_2m, etc).
    if hourly_7day_data and "hourly" in hourly_7day_data:
        try:
            from .processors.forecast_spread_log import append_gfs_snapshot
            append_gfs_snapshot(hourly_7day_data["hourly"])
        except Exception as e:
            logging.warning(f"  ⚠  GFS spread snapshot failed: {redact_secrets(e)}")

    # Cove-gradient hypothesis: log waterfront vs inland Tempest temps
    # alongside the Salem Channel water temp so we can later test whether
    # the (waterfront − inland) air-temp differential is driven by the
    # land–water thermal gap. Stratifies on sea-breeze active and wind dir.
    try:
        from .processors.cove_gradient_log import append_cove_snapshot
        append_cove_snapshot(weather_data)
    except Exception as e:
        logging.warning(f"  ⚠  Cove gradient snapshot failed: {redact_secrets(e)}")

    # Frontal-passage detection: log per-tick cove obs (T/Td/P/wind),
    # then run the detector to classify quiet/active/recent. Surfaces a
    # frontal block in weather_data for the frontend card + Gemini.
    try:
        from .processors.frontal_log import append_frontal_snapshot
        from .processors.frontal_detection import detect_and_log_frontal
        append_frontal_snapshot(weather_data)
        weather_data["frontal"] = detect_and_log_frontal()
    except Exception as e:
        logging.warning(f"  ⚠  Frontal detection failed: {redact_secrets(e)}")
        weather_data["frontal"] = {"state": "quiet", "event": None, "recent_events": []}

    # Cove correction (R5 candidate, gated OFF). Computes the candidate
    # Δ°F that would apply given current wind octant + sea-breeze state +
    # hour-of-day, stamps weather_data["cove_correction"], but does not
    # modify forecasts until ENABLED is flipped post-06-19 R5 read.
    try:
        from .processors.cove_correction import stamp_cove_correction
        stamp_cove_correction(weather_data)
    except Exception as e:
        logging.warning(f"  ⚠  Cove correction stamp failed: {redact_secrets(e)}")

    # Solar L5 correction (regime-aware solar, gated OFF). Indexed by
    # derived.state.regime_synoptic. Stamps candidate Δ W/m² but does not
    # modify direct_radiation until ENABLED is flipped post-06-22.
    try:
        from .processors.solar_correction import stamp_solar_correction
        stamp_solar_correction(weather_data)
    except Exception as e:
        logging.warning(f"  ⚠  Solar L5 stamp failed: {redact_secrets(e)}")

    # Confidence-layer L6 (regime-transition aware uncertainty, gated OFF).
    # Stamps per-(field, band) widened/narrowed MAE bands on transition hours.
    # Does NOT modify any forecast value — this is the first non-MAE-reducing
    # layer in the stack. See [[project-l6-pivot-to-confidence]].
    try:
        from .processors.confidence_layer import stamp_confidence
        stamp_confidence(weather_data)
    except Exception as e:
        logging.warning(f"  ⚠  Confidence L6 stamp failed: {redact_secrets(e)}")


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

    # Load previous weather data for stale fallback cache
    prev_weather_data = load_prev_weather_data()

    # Download frost log from GCS before fetching (needed for update_frost_log)
    _download_frost_log_from_gcs()

    # Fetch all data — Open-Meteo sequential, everything else parallel.
    fetched = fetch_all_sources()

    # Update frost log (reads/writes /tmp/frost_log.json)
    t0 = time.time()
    logging.info("🌡️ Updating frost log...")
    frost_log = update_frost_log(fetched.daily_data)
    logging.info(f"  ⏱  Frost log: {time.time() - t0:.1f}s")

    # Upload updated frost log back to GCS
    if FROST_LOG_TMP.exists():
        try:
            frost_log_data = json.loads(FROST_LOG_TMP.read_text())
            upload_json(frost_log_data, FROST_LOG_GCS_PATH, "frost_log.json")
        except Exception as e:
            logging.warning(f"  ⚠  Could not upload frost_log.json: {redact_secrets(e)}")

    sunset_directional = None
    if fetched.daily_data and fetched.daily_data.get("daily") and fetched.daily_data["daily"].get("sunset"):
        t0 = time.time()
        sunset_directional = build_sunset_directional_data(
            fetched.daily_data["daily"]["sunset"],
            LAT, LON,
            fetch_directional_clouds
        )
        logging.info(f"  ⏱  Sunset directional: {time.time() - t0:.1f}s")

    # Build complete weather data
    t0 = time.time()
    weather_data = build_weather_data(
        fetched.current_data, fetched.hourly_data, fetched.daily_data,
        fetched.pws_data, fetched.tide_data, fetched.kbos_data, fetched.kbvy_data, fetched.buoy_data,
        fetched.alert_data, fetched.sources,
        wu_data=fetched.wu_data,
        frost_log=frost_log,
        salem_water_temp=fetched.salem_water_temp,
        sunset_directional=sunset_directional,
        nws_gridpoints=fetched.nws_gridpoints_data,
        hourly_7day_data=fetched.hourly_7day_data,
        pirate_data=fetched.pirate_data,
        birds_data=fetched.birds_data,
        daily_temps_data=fetched.daily_temps_data,
        tempest_data=fetched.tempest_data
    )
    logging.info(f"  ⏱  Build weather data: {time.time() - t0:.1f}s")

    # AI briefing — generates headline, wires to payload, records source status
    apply_briefing_to_weather_data(weather_data)

    # Trim hourly arrays so they start at the current local hour
    trim_hourly_to_current_hour(weather_data)

    # L2 cloud blend — Kalman-gated KBOS+KBVY METAR override of hourly[0]
    # cloud_cover (+ L/M/H splits). Same _kalman_gain_cloud() pattern as the
    # temp/humidity L2 logic in hyperlocal.py, just runs AFTER trim so the
    # model reference is HRRR (correct) rather than GFS (the parallel-fetch
    # bug being fixed). When sources agree (low bias_std) K is high → obs
    # dominates; when sources disagree wildly K is low → HRRR dominates.
    try:
        from .processors.cloud_obs_blend import blend_metar_cloud_into_hourly
        blend_metar_cloud_into_hourly(weather_data,
                                      fetched.kbos_data, fetched.kbvy_data)
    except Exception as e:
        logging.warning(f"  ⚠  L2 cloud blend skipped: {redact_secrets(e)}")

    # Apply per-lead decay corrections (Piece 4) on top of the existing bias
    # correction and wind blend. Runs after trim so array index == lead_h.
    # Snapshot was already logged inside build_weather_data, so this does not
    # affect what the Fitter measures next round (keeps corrections stable).
    try:
        apply_decay_corrections(weather_data)
    except Exception as e:
        logging.warning(f"  ⚠  Decay apply failed: {redact_secrets(e)}")

    # FOUNDATIONAL: sync weather_data["current"] from corrected hourly[0].
    # Every "current conditions" card across the app reads current.*; the
    # contract is that those values are the L1→L4-corrected hourly[0]
    # values, not raw model or parallel GFS. Runs last so it sees the
    # output of every layer above. See processors/current_from_hourly.py
    # for the full design note.
    try:
        from .processors.current_from_hourly import sync_current_from_hourly_corrected
        sync_current_from_hourly_corrected(weather_data)
    except Exception as e:
        logging.warning(f"  ⚠  current sync from hourly[0] skipped: {redact_secrets(e)}")

    # Backtest snapshot: write raw L1 forecast arrays (now populated via
    # decay_apply's raw_* stamping) + per-station obs. Backtest framework
    # replays these to test alternative correction configs without waiting
    # for live data. Phase 1: write only; replay runner comes in phase 3.
    try:
        from .processors.backtest_snapshot import write_snapshot
        write_snapshot(weather_data)
    except Exception as e:
        logging.warning(f"  ⚠  Backtest snapshot failed: {redact_secrets(e)}")

    # Forecast snapshot — must run AFTER decay_apply so the snapshot has access
    # to per-layer intermediate arrays (corrected_*_post_l2, corrected_*_post_l3)
    # that decay_apply stamps as side effects. Legacy top-level keys in the
    # snapshot still equal the L2 (pre-decay) value so the Fitter's decay
    # calibration is unaffected by the timing change.
    from .processors.forecast_snapshot import append_forecast_snapshot
    try:
        append_forecast_snapshot(
            weather_data.get("hourly", {}),
            derived=weather_data.get("derived", {}),
        )
    except Exception as e:
        logging.warning(f"  ⚠  Forecast snapshot failed: {redact_secrets(e)}")

    # Per-station uptime tracking (v0.6.30). Records success/fail for every
    # station we attempt this tick into a rolling 7d log; stamps the per-station
    # uptime % summary into hyperlocal so the debug page can render it without
    # a second GCS fetch.
    try:
        from .processors.station_uptime import update_station_uptime
        from .fetchers.wu_scraper_realtime import STATIONS as WU_STATIONS
        from .fetchers.tempest import TEMPEST_STATIONS as TP_STATIONS
        attempted_wu = list(WU_STATIONS)
        attempted_tp = [s["id"] for s in TP_STATIONS]
        uptime_summary = update_station_uptime(weather_data, attempted_wu, attempted_tp)
        if uptime_summary:
            weather_data.setdefault("hyperlocal", {})["station_uptime"] = uptime_summary
    except Exception as e:
        logging.warning(f"  ⚠  Station uptime update failed: {redact_secrets(e)}")

    # Match past forecast snapshots against observed hours and log the errors
    # (feeds the per-field decay-curve fitter). Non-essential to the main
    # payload — log and continue on failure.
    t0 = time.time()
    try:
        update_forecast_error_log()
        logging.info(f"  ⏱  Forecast error log: {time.time() - t0:.1f}s")
    except Exception as e:
        logging.warning(f"  ⚠  Forecast error log update failed: {redact_secrets(e)}")

    # Apply stale fallbacks for any source that failed this run
    stale_sources = apply_stale_fallbacks(weather_data, prev_weather_data, fetched.failed_fetches)
    if stale_sources:
        weather_data["stale_sources"] = stale_sources
        logging.warning(f"  ⚠  Stale sources in this payload: {stale_sources}")
    else:
        weather_data.pop("stale_sources", None)

    # Re-derive the moisture quadruple from whatever T + T_d are in hourly now.
    # If hourly came from this run, decay_apply already did this; if it came
    # from the stale cache, this run's call is what keeps (T, T_d, RH, AH)
    # internally consistent. Idempotent — safe to always call.
    recompute_derived_moisture_arrays(weather_data)

    # Upload weather data to GCS
    upload_json(weather_data, WEATHER_DATA_GCS_PATH, "weather_data.json")

    # Fit per-field per-lead_h decay corrections twice daily at the X:07 tick
    # (03:07 EDT post-overnight + 15:07 EDT mid-afternoon). Dropped from 4×/day
    # in v0.6.47 — the active build phase is over (L2 lead-decay shipped, L3/L4
    # whitelist settled) and per-tick GCS cost was visible in the bill.
    # Also prunes forecast_error_log.jsonl to RETENTION_DAYS and resets the GCS
    # compose component count back to 1.
    now_local = datetime.now(pytz.timezone("America/New_York"))
    if now_local.hour in (3, 15) and now_local.minute < 10:
        t0 = time.time()
        try:
            fit_decay_corrections()
            logging.info(f"  ⏱  Decay fit: {time.time() - t0:.1f}s")
        except Exception as e:
            logging.warning(f"  ⚠  Decay fit failed: {redact_secrets(e)}")

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

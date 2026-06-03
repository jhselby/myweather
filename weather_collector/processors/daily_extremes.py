"""
Daily temperature extremes + current observation logging.

Today's high/low merge observed corrected temps (so far) with the remaining
hourly forecast. Yesterday is observation-only (high temp, total precip,
peak gust). Tomorrow is forecast-only. Also logs the current 10-minute
snapshot to the rolling 24h obs log and writes the 48h forecast snapshot
to the 14-day history log.
"""
from datetime import datetime, timedelta

import pytz

# forecast_snapshot moved out of compute_daily_extremes (v0.6.25b) — it now
# runs AFTER decay_apply in collector.py so the snapshot can capture all four
# per-layer forecast values (raw, +L2, +L3, +L4). Legacy top-level keys (t, h,
# etc.) in the snapshot still equal the pre-decay L2 value so the Fitter's
# decay-correction calibration is unchanged.
from .obs_log import update_obs_temp_log


TZ = pytz.timezone("America/New_York")


def _current_hour_precip_in(weather_data, current_hour_iso):
    """Observed precip rate from WU rain gauges (real), falling back to
    the forecast hourly precipitation array (converted mm → in)."""
    wu_rate = weather_data.get("wu_stations", {}).get("precip_rate_in")
    if wu_rate is not None:
        return wu_rate
    times = weather_data["hourly"].get("times", [])
    precip_mm = weather_data["hourly"].get("precipitation", [])
    if current_hour_iso in times:
        i = times.index(current_hour_iso)
        if i < len(precip_mm) and precip_mm[i] is not None:
            return precip_mm[i] / 25.4
    return None


def _gather_current_observation(weather_data, current_hour_iso):
    """Collect the 9 fields update_obs_temp_log records each run."""
    hyp = weather_data.get("hyperlocal", {})
    cur = weather_data.get("current", {})
    der = weather_data.get("derived", {})
    kbos = weather_data.get("kbos") or {}
    # Cloud cover: KBOS METAR sky condition (real observation, ~15mi south coast).
    # No fallback to model value — that would feed the Joiner forecast-vs-forecast
    # pairs with zero error and pollute the Fitter. When KBOS is down, obs_log
    # just omits the cloud field for that tick.
    cloud_cover = kbos.get("cloud_cover_pct")
    return {
        "corrected_temp": hyp.get("corrected_temp"),
        "precip_in": _current_hour_precip_in(weather_data, current_hour_iso),
        "peak_gust_mph": hyp.get("corrected_wind_gusts") or cur.get("wind_gusts"),
        "wind_mph": hyp.get("corrected_wind_speed") or cur.get("wind_speed"),
        "wind_dir": cur.get("wind_direction"),
        "dew_point_f": hyp.get("corrected_dew_point") or der.get("corrected_dew_point"),
        "pressure_in": hyp.get("corrected_pressure_in"),
        "cloud_cover": cloud_cover,
        # Use the station-network–corrected humidity (matches how `corrected_temp`
        # is sourced two lines above). Storing raw model humidity here causes the
        # Joiner / Fitter to see the Kalman bias itself as "error," which makes
        # the Layer-3 decay correction effectively undo Layer 1 — see comment in
        # decay_apply.py and the May 31 evening session notes.
        "humidity": hyp.get("corrected_humidity") if hyp.get("corrected_humidity") is not None else cur.get("humidity"),
    }


def _extract_atmospheric_now(weather_data, current_hour_iso):
    """Pull freezing level, precip water, low cloud cover for the current hour."""
    hourly = weather_data["hourly"]
    times = hourly.get("times", [])
    if current_hour_iso not in times:
        return {}
    i = times.index(current_hour_iso)
    out = {}
    fl = hourly.get("freezing_level_ft", [])
    pw = hourly.get("precip_water_mm", [])
    ccl = hourly.get("cloud_cover_low", [])
    if i < len(fl) and fl[i] is not None:
        out["freezing_level_ft"] = round(fl[i])
    if i < len(pw) and pw[i] is not None:
        out["precip_water_mm"] = round(pw[i], 1)
    if i < len(ccl) and ccl[i] is not None:
        out["cloud_cover_low_pct"] = round(ccl[i])
    return out


def compute_daily_extremes(weather_data):
    """Log current snapshot + 48h forecast, then compute daily extremes.

    Mutates weather_data["derived"] with today_high/today_low,
    yesterday_high/yesterday_precip_in/yesterday_peak_gust,
    tomorrow_high/tomorrow_low, and the current-hour atmospheric fields.
    Attaches the rolling obs_temp_log to weather_data["obs_temp_log"].

    No-op if hourly is missing (obs log set to empty so the payload
    still has the key).
    """
    if "hourly" not in weather_data:
        weather_data["obs_temp_log"] = {"entries": []}
        return

    hourly = weather_data["hourly"]
    ct_times = hourly.get("times", [])
    ct_temps = hourly.get("corrected_temperature", [])

    now_local = datetime.now(TZ)
    today_str = now_local.strftime("%Y-%m-%d")
    yesterday_str = (now_local - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_str = (now_local + timedelta(days=1)).strftime("%Y-%m-%d")
    current_hour_iso = now_local.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")

    # 1. Write current snapshot to GCS. Forecast snapshot moved to collector.py
    # (post-decay_apply) so it can capture all per-layer values.
    obs_values = _gather_current_observation(weather_data, current_hour_iso)
    obs_log = update_obs_temp_log(**obs_values)
    weather_data["obs_temp_log"] = obs_log
    entries = obs_log.get("entries", [])

    derived = weather_data.setdefault("derived", {})

    # 2. Today high/low: observed so far + remaining forecast hours
    obs_today = [e["temp"] for e in entries
                 if e.get("time", "").startswith(today_str) and e.get("temp") is not None]
    fc_today = [ct_temps[i] for i, t in enumerate(ct_times)
                if i < len(ct_temps) and ct_temps[i] is not None
                and t.startswith(today_str) and t >= current_hour_iso]
    today_series = obs_today + fc_today
    if today_series:
        derived["today_high"] = round(max(today_series), 1)
        derived["today_low"] = round(min(today_series), 1)

    # 3. Yesterday: observation-only (the obs log is the only authoritative source)
    ye_entries = [e for e in entries if e.get("time", "").startswith(yesterday_str)]
    ye_temps = [e["temp"] for e in ye_entries if e.get("temp") is not None]
    if ye_temps:
        derived["yesterday_high"] = round(max(ye_temps), 1)
    ye_precip = [e["precip_in"] for e in ye_entries if e.get("precip_in") is not None]
    if ye_precip:
        derived["yesterday_precip_in"] = round(sum(ye_precip), 2)
    ye_gusts = [e["gust_mph"] for e in ye_entries if e.get("gust_mph") is not None]
    if ye_gusts:
        derived["yesterday_peak_gust"] = round(max(ye_gusts), 1)

    # 4. Atmospheric fields for current hour (freezing level, precip water, low cloud)
    derived.update(_extract_atmospheric_now(weather_data, current_hour_iso))

    # 5. Tomorrow: forecast-only
    fc_tomorrow = [ct_temps[i] for i, t in enumerate(ct_times)
                   if i < len(ct_temps) and ct_temps[i] is not None
                   and t.startswith(tomorrow_str)]
    if fc_tomorrow:
        derived["tomorrow_high"] = round(max(fc_tomorrow), 1)
        derived["tomorrow_low"] = round(min(fc_tomorrow), 1)

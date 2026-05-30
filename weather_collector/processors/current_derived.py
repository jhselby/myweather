"""
Current-conditions derived metrics.

All run off the bias-corrected hyperlocal values produced by
build_hyperlocal_data, with a model-only fallback for the dew point
spread when corrected values aren't available.

Outputs (in weather_data["derived"]):
  - corrected_dew_point, dew_point_spread_f, cloud_base_ft
  - corrected_feels_like (Steadman, with solar when available)
  - heat_index (NWS polynomial, only valid above 80°F + 35% RH)
"""
from datetime import datetime

import pytz

from ..utils import magnus_dew_point_f, steadman_feels_like_f
from .hyperlocal import compute_dew_point_spread


TZ = pytz.timezone("America/New_York")


def _solar_irradiance_wm2(weather_data):
    """Best-available current solar radiation at our location, in W/m².

    Priority: Pirate Weather point forecast → average of valid Tempest
    stations → Open-Meteo direct_radiation for the current hour.
    Returns None if no source is available.
    """
    # 1. Pirate Weather (point forecast for our exact location)
    pw_solar = weather_data.get("pirate_weather", {}).get("current_solar")
    if isinstance(pw_solar, (int, float)) and pw_solar >= 0:
        return pw_solar
    # 2. Average of valid Tempest stations
    tempest_vals = [
        s["solar_radiation_wm2"]
        for s in weather_data.get("tempest", {}).get("stations", [])
        if s.get("valid") and isinstance(s.get("solar_radiation_wm2"), (int, float))
    ]
    if tempest_vals:
        return sum(tempest_vals) / len(tempest_vals)
    # 3. Open-Meteo hourly direct_radiation at the current hour
    hourly_direct = weather_data.get("hourly", {}).get("direct_radiation", [])
    hourly_times = weather_data.get("hourly", {}).get("times", [])
    now_hr = datetime.now(TZ).strftime("%Y-%m-%dT%H:00")
    for i, t in enumerate(hourly_times):
        if t == now_hr and i < len(hourly_direct):
            return hourly_direct[i]
    return None


def _nws_heat_index_f(temp_f, rh_pct):
    """NWS heat index polynomial — valid above 80°F + 35% RH.
    Returns None below threshold."""
    if temp_f < 80 or rh_pct < 35:
        return None
    T, RH = temp_f, rh_pct
    hi = (-42.379 + 2.04901523 * T + 10.14333127 * RH - 0.22475541 * T * RH
          - 6.83783e-3 * T ** 2 - 5.481717e-2 * RH ** 2 + 1.22874e-3 * T ** 2 * RH
          + 8.5282e-4 * T * RH ** 2 - 1.99e-6 * T ** 2 * RH ** 2)
    return round(hi, 1)


def compute_current_derived(weather_data):
    """Add corrected dew point + feels-like + heat index to derived dict."""
    derived = weather_data.setdefault("derived", {})
    hyp = weather_data.get("hyperlocal", {})
    cur = weather_data.get("current", {})

    ct = hyp.get("corrected_temp")
    ch = hyp.get("corrected_humidity")

    # 1. Corrected dew point + spread + cloud base
    corrected_dewpt = magnus_dew_point_f(ct, ch)
    if corrected_dewpt is not None:
        derived["corrected_dew_point"] = corrected_dewpt
        derived["dew_point_spread_f"] = round(ct - corrected_dewpt, 1)
        derived["cloud_base_ft"] = max(0, round((ct - corrected_dewpt) * 225))
    else:
        # Fallback: spread from raw GFS current dew point (no cloud-base estimate)
        spread = compute_dew_point_spread(cur.get("temperature"), cur.get("dew_point"))
        if spread is not None:
            derived["dew_point_spread_f"] = spread

    if ct is None:
        return  # Nothing more to compute without a temperature

    # 2. Corrected feels-like (Steadman, with solar when available)
    cw = hyp.get("corrected_wind_speed")
    ws_mph = cw if cw is not None else (cur.get("wind_speed") or 0)
    solar = _solar_irradiance_wm2(weather_data)
    fl = steadman_feels_like_f(ct, ch, ws_mph, solar)
    if fl is not None:
        derived["corrected_feels_like"] = fl

    # 3. NWS heat index (shade, no solar term) — only above 80°F + 35% RH
    rh = ch if ch is not None else 50
    hi = _nws_heat_index_f(ct, rh)
    if hi is not None:
        derived["heat_index"] = hi

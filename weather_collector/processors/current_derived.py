"""
Current-conditions derived metrics.

All run off the bias-corrected hyperlocal values produced by
build_hyperlocal_data, with a model-only fallback for the dew point
spread when corrected values aren't available.

Outputs (in weather_data["derived"]):
  - corrected_dew_point, dew_point_spread_f, cloud_base_ft
  - corrected_feels_like (Steadman, with solar when available)
  - heat_index (NWS polynomial, only valid above 80°F + 35% RH)
  - observed_sky_label, solar_transmissivity (from observed solar vs
    clear-sky model — overrides HRRR cloud_cover when sun is bright)
"""
import math
from datetime import datetime, timezone

import pytz

from ..config import LAT, LON
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


def _solar_elevation_deg(lat, lon, dt_utc):
    """Solar elevation angle above the horizon, in degrees.

    Spencer / NOAA approximation — accurate to ~0.5° for our use case
    (sky-condition classification, not navigation)."""
    doy = dt_utc.timetuple().tm_yday
    # Solar declination (Cooper 1969)
    decl = 23.45 * math.sin(math.radians(360 * (284 + doy) / 365))
    # Equation of time (Spencer 1971, abbreviated)
    B = math.radians(360 * (doy - 81) / 364)
    eot_min = 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)
    # Local solar time (hours)
    hr_utc = dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600
    solar_hr = hr_utc + (lon / 15.0) + (eot_min / 60.0)
    hour_angle_deg = 15.0 * (solar_hr - 12.0)
    # Elevation
    lat_r = math.radians(lat)
    decl_r = math.radians(decl)
    ha_r = math.radians(hour_angle_deg)
    sin_elev = (math.sin(lat_r) * math.sin(decl_r)
                + math.cos(lat_r) * math.cos(decl_r) * math.cos(ha_r))
    sin_elev = max(-1.0, min(1.0, sin_elev))
    return math.degrees(math.asin(sin_elev))


def _observed_sky(weather_data):
    """Derive sky label from observed solar vs clear-sky model.

    Returns dict with `label`, `transmissivity`, `solar_observed_wm2`,
    `solar_clearsky_wm2`, or None if sun is too low or no observed solar.

    Transmissivity bins:
      ≥ 0.80  → Clear
      0.55–0.80 → Hazy
      0.35–0.55 → Partly Cloudy
      0.15–0.35 → Mostly Cloudy
      < 0.15  → Overcast
    """
    elev = _solar_elevation_deg(LAT, LON, datetime.now(timezone.utc))
    if elev < 10:
        return None  # Sun too low — observed solar isn't a reliable sky signal
    observed = _solar_irradiance_wm2(weather_data)
    if observed is None or observed < 0:
        return None
    # Simplified clear-sky GHI (Haurwitz, 1945):
    #   GHI_clear ≈ 1098 * sin(elev) * exp(-0.057 / sin(elev))
    sin_e = math.sin(math.radians(elev))
    clearsky = 1098.0 * sin_e * math.exp(-0.057 / sin_e)
    if clearsky < 30:
        return None
    tau = observed / clearsky
    label, _ = _tau_to_label_and_pct(tau)
    return {
        "label": label,
        "transmissivity": round(tau, 3),
        "solar_observed_wm2": round(observed),
        "solar_clearsky_wm2": round(clearsky),
        "solar_elevation_deg": round(elev, 1),
    }


def _tau_to_label_and_pct(tau):
    """Bin transmissivity → (sky label, equivalent cloud cover %)."""
    tau = max(0.0, min(1.2, tau))
    if tau >= 0.80:   lbl = "Clear"
    elif tau >= 0.55: lbl = "Hazy"
    elif tau >= 0.35: lbl = "Partly Cloudy"
    elif tau >= 0.15: lbl = "Mostly Cloudy"
    else:             lbl = "Overcast"
    cc_pct = round(max(0, min(100, (1 - min(1.0, tau)) * 100)))
    return lbl, cc_pct


def _forecast_sky_arrays(weather_data):
    """Per-hour solar-derived sky for the full 48h forecast horizon.

    Returns (labels, taus, cloud_pct) lists aligned with hourly.times.
    Hours with sun < 5° elev get (None, None, None) — caller falls back
    to the model cloud_cover.

    Why this is useful even though the SR forecast itself has error: the
    transmissivity calc is binary-ish at the level we care about — a 100%
    cloud_cover with 600 W/m² direct_rad is clearly thin/high cloud, not
    overcast. Catches the model contradicting itself.
    """
    hourly = weather_data.get("hourly", {})
    times = hourly.get("times", [])
    dr = hourly.get("direct_radiation", [])
    if not times or not dr:
        return [], [], []

    labels, taus, cloud_pct = [], [], []
    n = min(len(times), len(dr))
    for i in range(n):
        t_str = times[i]
        rad = dr[i]
        if not t_str or rad is None:
            labels.append(None); taus.append(None); cloud_pct.append(None); continue
        try:
            dt_local = TZ.localize(datetime.fromisoformat(t_str))
            dt_utc = dt_local.astimezone(timezone.utc)
        except (ValueError, TypeError):
            labels.append(None); taus.append(None); cloud_pct.append(None); continue
        elev = _solar_elevation_deg(LAT, LON, dt_utc)
        if elev < 5:
            labels.append(None); taus.append(None); cloud_pct.append(None); continue
        sin_e = math.sin(math.radians(elev))
        clearsky = 1098.0 * sin_e * math.exp(-0.057 / sin_e)
        if clearsky < 20:
            labels.append(None); taus.append(None); cloud_pct.append(None); continue
        tau = rad / clearsky
        lbl, cc = _tau_to_label_and_pct(tau)
        labels.append(lbl)
        taus.append(round(max(0.0, min(1.2, tau)), 3))
        cloud_pct.append(cc)
    return labels, taus, cloud_pct


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

    # 4. Observed sky condition — backs out cloud cover from solar
    # transmissivity (observed Tempest/Pirate solar vs Haurwitz clear-sky).
    # Catches the case where HRRR claims overcast but sun is hitting the
    # ground at full strength. Frontend prefers this over weather_code.
    sky = _observed_sky(weather_data)
    if sky is not None:
        derived["observed_sky_label"] = sky["label"]
        derived["solar_transmissivity"] = sky["transmissivity"]
        derived["solar_observed_wm2"] = sky["solar_observed_wm2"]
        derived["solar_clearsky_wm2"] = sky["solar_clearsky_wm2"]
        derived["solar_elevation_deg"] = sky["solar_elevation_deg"]

    # 5. Forecast sky arrays — per-hour sky labels + solar-derived cloud
    # cover for the full 48h horizon. Reads HRRR/GFS direct_radiation and
    # back-computes against Haurwitz clear-sky for each hour's sun angle.
    # Nighttime hours stay None and the forecast narrative falls back to
    # model cloud_cover. Read by forecast_text.py.
    f_labels, f_taus, f_cc = _forecast_sky_arrays(weather_data)
    if f_labels:
        derived["forecast_sky_label"] = f_labels
        derived["forecast_transmissivity"] = f_taus
        derived["forecast_cloud_cover_solar"] = f_cc

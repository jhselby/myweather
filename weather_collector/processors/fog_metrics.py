"""
Fog risk computation: current + 18-hour probability array + dissipation hour.

The current fog risk uses the freshest available GFS current; if GFS
failed entirely (current is empty), falls back to the first hourly slot
from HRRR. The 18-hour array uses the bias-corrected hourly forecast
arrays so dissipation timing matches what the chart shows.
"""
import logging

from .fog import calculate_fog_risk


HOURLY_HORIZON = 18
# Two consecutive hours below this fog probability count as "dissipated"
DISSIPATION_THRESHOLD = 20


def _current_fog_inputs(weather_data):
    """Return (temp_f, dew_point_f, humidity, wind_mph, wind_dir) for the
    current moment. Prefers the cleaned GFS current; falls back to hourly[0]
    if GFS is empty. Returns Nones if neither is available."""
    cur = weather_data.get("current") or {}
    if cur.get("temperature") is not None:
        return (
            cur.get("temperature"),
            cur.get("dew_point"),
            cur.get("humidity"),
            cur.get("wind_speed"),
            cur.get("wind_direction"),
        )
    hourly = weather_data.get("hourly", {})
    if hourly.get("times"):
        logging.warning("  ⚠️ GFS current unavailable, using hourly[0] for fog calc")
        return (
            (hourly.get("temperature") or [None])[0],
            (hourly.get("dew_point") or [None])[0],
            (hourly.get("humidity") or [None])[0],
            (hourly.get("wind_speed") or [None])[0],
            (hourly.get("wind_direction") or [None])[0],
        )
    return (None, None, None, None, None)


def compute_fog_metrics(weather_data):
    """Add fog risk + hourly fog probability + dissipation timing to derived."""
    temp_f, dp_f, rh, wind_mph, wind_dir = _current_fog_inputs(weather_data)
    if temp_f is None and dp_f is None and rh is None and wind_mph is None:
        return  # No usable inputs

    derived = weather_data.setdefault("derived", {})
    water_temp_f = weather_data.get("buoy_44013", {}).get("water_temp_f")
    cloud_low_pct = derived.get("cloud_cover_low_pct")

    # 1. Current fog risk
    fog_risk = calculate_fog_risk(
        temp_f, dp_f, rh, wind_mph,
        wind_direction=wind_dir,
        water_temp_f=water_temp_f,
        cloud_cover_low_pct=cloud_low_pct,
    )
    if fog_risk:
        derived["fog_label"] = fog_risk["fog_label"]
        derived["fog_probability"] = fog_risk["fog_probability"]

    # 2. 18-hour fog probability array (uses bias-corrected hourly arrays)
    h = weather_data.get("hourly", {})
    htimes  = h.get("times", [])
    htemps  = h.get("corrected_temperature", h.get("temperature", []))
    hdewpts = h.get("corrected_dew_point",   h.get("dew_point", []))
    hhumids = h.get("corrected_humidity",    h.get("humidity", []))
    hwinds  = h.get("wind_speed", [])
    hwdirs  = h.get("wind_direction", [])
    hccl    = h.get("cloud_cover_low", [])

    probs = []
    for i in range(min(HOURLY_HORIZON, len(htimes))):
        fr = calculate_fog_risk(
            htemps[i]  if i < len(htemps)  else None,
            hdewpts[i] if i < len(hdewpts)  else None,
            hhumids[i] if i < len(hhumids)  else None,
            hwinds[i]  if i < len(hwinds)   else None,
            wind_direction=hwdirs[i] if i < len(hwdirs) else None,
            water_temp_f=water_temp_f,
            cloud_cover_low_pct=hccl[i] if i < len(hccl) else None,
        )
        probs.append(fr["fog_probability"] if fr else 0)
    derived["fog_hourly_prob"] = probs
    derived["fog_hourly_times"] = htimes[:HOURLY_HORIZON]

    # 3. Dissipation: first run of 2+ consecutive hours below threshold
    for i in range(len(probs) - 1):
        if probs[i] < DISSIPATION_THRESHOLD and probs[i + 1] < DISSIPATION_THRESHOLD:
            if i < len(htimes):
                derived["fog_dissipation_hour"] = htimes[i]
            break

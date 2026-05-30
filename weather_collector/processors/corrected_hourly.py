"""
Build the bias-corrected hourly arrays that the frontend charts read:
    - corrected_temperature        (raw + station-network temp bias)
    - corrected_humidity           (raw + station-network humidity bias)
    - corrected_apparent_temperature  (Steadman, with solar when available)
    - corrected_dew_point          (Magnus)
    - corrected_absolute_humidity  (g/m³, derived from corrected dew point)

Must run AFTER build_hyperlocal_data (which sets the bias values).
Mutates weather_data["hourly"] in place.
"""
import math

from ..utils import magnus_dew_point_f, steadman_feels_like_f


def add_corrected_hourly_arrays(weather_data):
    """Populate the five corrected hourly arrays. No-op if hourly is missing."""
    if "hourly" not in weather_data:
        return

    hyp = weather_data.get("hyperlocal", {})
    temp_bias = hyp.get("weighted_bias", 0)
    humid_bias = hyp.get("bias_humidity", 0)

    hourly = weather_data["hourly"]
    raw_temps = hourly.get("temperature", [])
    raw_humid = hourly.get("humidity", [])

    hourly["corrected_temperature"] = [
        round(t + temp_bias, 1) if t is not None else None for t in raw_temps
    ]
    hourly["corrected_humidity"] = [
        round(h + humid_bias, 1) if h is not None else None for h in raw_humid
    ]

    ct_arr = hourly["corrected_temperature"]
    ch_arr = hourly["corrected_humidity"]
    ws_arr = hourly.get("wind_speed", [])
    dr_arr = hourly.get("direct_radiation", [])

    corrected_at = []
    corrected_dp = []
    corrected_ah = []
    for i in range(len(ct_arr)):
        t = ct_arr[i] if i < len(ct_arr) else None
        h = ch_arr[i] if i < len(ch_arr) else None
        w = ws_arr[i] if i < len(ws_arr) else None
        dr = dr_arr[i] if i < len(dr_arr) else None

        corrected_at.append(steadman_feels_like_f(t, h, w, dr))

        dp_f = magnus_dew_point_f(t, h)
        if dp_f is not None:
            corrected_dp.append(dp_f)
            # Absolute humidity (g/m³) — Bolton saturation vapor pressure at dew point
            t_c = (t - 32) * 5 / 9
            dp_c = (dp_f - 32) * 5 / 9
            e = 6.112 * math.exp((17.67 * dp_c) / (dp_c + 243.5))
            ah = (e * 216.7) / (t_c + 273.15)
            corrected_ah.append(round(ah, 1))
        else:
            corrected_dp.append(None)
            corrected_ah.append(None)

    hourly["corrected_apparent_temperature"] = corrected_at
    hourly["corrected_dew_point"] = corrected_dp
    hourly["corrected_absolute_humidity"] = corrected_ah

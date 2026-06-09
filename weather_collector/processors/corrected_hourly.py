"""
Build the bias-corrected hourly arrays that the frontend charts read:
    - corrected_temperature        (raw + station-network temp bias × decay(lead))
    - corrected_humidity           (raw + station-network humidity bias × decay(lead))
    - corrected_apparent_temperature  (Steadman, with solar when available)
    - corrected_dew_point          (Magnus)
    - corrected_absolute_humidity  (g/m³, derived from corrected dew point)

Must run AFTER build_hyperlocal_data (which sets the bias values).
Mutates weather_data["hourly"] in place.

L2 lead-decay (v0.6.44): instead of applying the station bias flat across
all 48 lead hours, apply bias × exp(-lead/τ_field). τ is fit per field by
analysis/l2_lead_decay_fit.py. Fields not in L2_TAUS (or τ ≥ 1e8) get
flat application. Optional GCS override via l2_decay.json.
"""
import math

from ..gcs_io import load_json
from ..utils import magnus_dew_point_f, steadman_feels_like_f


# Default per-field τ in hours. Source: analysis/l2_lead_decay_fit.py run on
# 73,510 train pairs (cutoff 2026-06-06). Held-out wins: t +5.1%, h +3.8%,
# pr +4.2% vs flat L2. Fields not listed → flat application (current behavior).
DEFAULT_L2_TAUS = {
    "t":  4.0,    # temperature: bias mostly useful at very short leads
    "h":  240.0,  # humidity: slow decay, bias persists across the horizon
    "pr": 12.0,   # pressure: half-life ~8h
}
L2_DECAY_PATH = "l2_decay.json"


def _load_l2_taus():
    """Prefer a GCS-published refit; fall back to the inline defaults.

    Accepts numeric τ in hours; "inf" (str) or values >= 1e8 mean flat (current
    L2 behavior). The fitter writes "inf" as a string when the grid search
    picks the flat candidate; numeric values are kept as-is.

    Loader-side degenerate-fit guard: if every loaded numeric τ equals the
    minimum grid value (0.5h) — the signature of a starved-signal fit — the
    file is treated as missing and DEFAULT_L2_TAUS kicks in. Belt + suspenders
    with the fitter-side write guard in decay_fit.py.
    """
    doc = load_json(L2_DECAY_PATH, default=None)
    if isinstance(doc, dict):
        taus = doc.get("tau_hours")
        if isinstance(taus, dict):
            out = {}
            for k, v in taus.items():
                if isinstance(v, (int, float)):
                    out[k] = float(v)
                elif isinstance(v, str) and v.lower() in ("inf", "infinity"):
                    out[k] = 1e9
            if out:
                numeric_vals = [v for v in out.values() if v < 1e8]
                if numeric_vals and all(v == 0.5 for v in numeric_vals):
                    import logging
                    logging.warning(
                        "  ⊘ L2 τ load: l2_decay.json is degenerate (every "
                        "field at min τ=0.5h); using DEFAULT_L2_TAUS instead."
                    )
                else:
                    return out
    return dict(DEFAULT_L2_TAUS)


def _decay_factors(tau, n):
    """exp(-lead/τ) for lead = 0..n-1. τ >= 1e8 (or None) → flat 1.0."""
    if tau is None or tau >= 1e8:
        return [1.0] * n
    return [math.exp(-i / tau) for i in range(n)]


def add_corrected_hourly_arrays(weather_data):
    """Populate the five corrected hourly arrays. No-op if hourly is missing."""
    if "hourly" not in weather_data:
        return

    hyp = weather_data.get("hyperlocal", {})
    weighted_bias = hyp.get("weighted_bias", 0)
    kalman_gain = hyp.get("kalman_gain", 1.0)
    if kalman_gain is None:
        kalman_gain = 1.0
    # Layer 3 (Adaptive Bias Control): Kalman gain scales how aggressively
    # the network bias is applied. Few stations / high scatter → low K → less
    # bias trusted into the forecast. Matches the Right-Now calculation in
    # hyperlocal.py: corrected_temp = model_t + K * weighted_bias.
    temp_bias = kalman_gain * weighted_bias
    humid_bias = hyp.get("bias_humidity", 0)

    hourly = weather_data["hourly"]
    raw_temps = hourly.get("temperature", [])
    raw_humid = hourly.get("humidity", [])

    taus = _load_l2_taus()
    weather_data["l2_decay_meta"] = {"tau_hours": dict(taus)}
    n_hours = max(len(raw_temps), len(raw_humid), 48)
    t_decay = _decay_factors(taus.get("t"), n_hours)
    h_decay = _decay_factors(taus.get("h"), n_hours)

    hourly["corrected_temperature"] = [
        round(t + temp_bias * t_decay[i], 1) if t is not None else None
        for i, t in enumerate(raw_temps)
    ]
    hourly["corrected_humidity"] = [
        round(h + humid_bias * h_decay[i], 1) if h is not None else None
        for i, h in enumerate(raw_humid)
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

    # Pressure: model gives hPa/mb in `pressure` (post-normalize.py rename
    # from pressure_msl); stations report inHg. Convert model to inHg, add
    # Layer-2 bias. Layers 3 (decay) and 4 (diurnal) apply downstream to
    # corrected_pressure_in directly.
    pressure_bias_in = hyp.get("bias_pressure_in", 0) or 0
    raw_pressure_mb = hourly.get("pressure", [])
    if raw_pressure_mb:
        raw_pressure_in = [round(p / 33.8639, 3) if p is not None else None for p in raw_pressure_mb]
        hourly["raw_pressure_in"] = raw_pressure_in
        pr_decay = _decay_factors(taus.get("pr"), max(len(raw_pressure_in), 48))
        hourly["corrected_pressure_in"] = [
            round(p + pressure_bias_in * pr_decay[i], 3) if p is not None else None
            for i, p in enumerate(raw_pressure_in)
        ]

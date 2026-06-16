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


L2_GUARDRAIL_MIN_IMPROVEMENT_PCT = 0.0  # held-out must beat default (≥0%)
L2_GUARDRAIL_MIN_N_TEST = 100           # need at least this many test pairs
L2_GUARDRAIL_TAU_LOW_MULT = 0.25        # fitted τ must be ≥ 0.25× default
L2_GUARDRAIL_TAU_HIGH_MULT = 4.0        # fitted τ must be ≤ 4× default


def _load_l2_taus():
    """Per-field guardrailed loader for L2 τ values.

    Returns (taus_dict, meta_dict). `taus_dict` is {field: τ_hours} for the
    apply step; `meta_dict` is the debug-page-facing record of which τ was
    adopted, why (source = "fitted" or "default"), and the held-out report
    behind it.

    For each field, the fitter publishes a τ plus a held-out report. The
    loader adopts the fitted τ only if BOTH:
      • the fit beat the hardcoded default on held-out RMSE
        (improvement_vs_default_pct ≥ L2_GUARDRAIL_MIN_IMPROVEMENT_PCT)
        with at least L2_GUARDRAIL_MIN_N_TEST test pairs, AND
      • the fitted τ is within [0.25×, 4×] of the default (sanity bound —
        prevents a wild-swing publish from poisoning forecasts even if the
        held-out score happens to favor it).
    Otherwise, fall back to DEFAULT_L2_TAUS for that field. Field-level
    guardrails so a bad fit on one field doesn't take the others down with it.
    """
    import logging
    doc = load_json(L2_DECAY_PATH, default=None)
    taus_out = {}
    meta_fields = {}
    file_taus = (doc.get("tau_hours") if isinstance(doc, dict) else None) or {}
    file_heldout = (doc.get("heldout") if isinstance(doc, dict) else None) or {}

    for field, default_tau in DEFAULT_L2_TAUS.items():
        v = file_taus.get(field)
        if isinstance(v, str) and v.lower() in ("inf", "infinity"):
            fitted_tau = 1e9
        elif isinstance(v, (int, float)):
            fitted_tau = float(v)
        else:
            fitted_tau = None

        h = file_heldout.get(field) or {}
        n_test = h.get("n_test", 0)
        improvement = h.get("improvement_vs_default_pct", None)

        adopted = default_tau
        source = "default"
        reason = "no fitted value published"

        if fitted_tau is not None:
            if improvement is None or n_test < L2_GUARDRAIL_MIN_N_TEST:
                reason = f"no held-out score (n_test={n_test})"
            elif improvement < L2_GUARDRAIL_MIN_IMPROVEMENT_PCT:
                reason = (f"held-out improvement {improvement:+.2f}% "
                          f"below threshold")
            elif fitted_tau < 1e8 and not (
                L2_GUARDRAIL_TAU_LOW_MULT * default_tau
                <= fitted_tau
                <= L2_GUARDRAIL_TAU_HIGH_MULT * default_tau
            ):
                reason = (f"fitted τ={fitted_tau}h outside guardrail "
                          f"[{L2_GUARDRAIL_TAU_LOW_MULT * default_tau:.1f}, "
                          f"{L2_GUARDRAIL_TAU_HIGH_MULT * default_tau:.1f}]h")
            else:
                adopted = fitted_tau
                source = "fitted"
                reason = (f"held-out {improvement:+.2f}% vs default, "
                          f"n_test={n_test:,}")

        taus_out[field] = adopted
        meta_fields[field] = {
            "tau_hours": (1e9 if adopted >= 1e8 else adopted),
            "default_tau_hours": default_tau,
            "fitted_tau_hours": (None if fitted_tau is None
                                 else (1e9 if fitted_tau >= 1e8 else fitted_tau)),
            "source": source,
            "reason": reason,
            "n_test": n_test,
            "improvement_vs_default_pct": improvement,
            "mae_default": h.get("mae_default"),
            "mae_fitted": h.get("mae_fitted"),
            "mae_flat": h.get("mae_flat"),
        }
        prefix = "✓" if source == "fitted" else " "
        logging.info(f"  {prefix} L2 τ[{field}]: {adopted}h ({source}; {reason})")

    meta_out = {
        "tau_hours": {f: (1e9 if v >= 1e8 else v) for f, v in taus_out.items()},
        "fields": meta_fields,
        "fitted_at": (doc.get("fitted_at") if isinstance(doc, dict) else None),
        "heldout_days": (doc.get("heldout_days") if isinstance(doc, dict) else None),
        "guardrail": {
            "min_improvement_pct": L2_GUARDRAIL_MIN_IMPROVEMENT_PCT,
            "min_n_test": L2_GUARDRAIL_MIN_N_TEST,
            "tau_low_mult": L2_GUARDRAIL_TAU_LOW_MULT,
            "tau_high_mult": L2_GUARDRAIL_TAU_HIGH_MULT,
        },
    }
    return taus_out, meta_out


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

    taus, l2_meta = _load_l2_taus()
    weather_data["l2_decay_meta"] = l2_meta
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

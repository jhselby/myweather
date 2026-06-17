"""
Solar radiation regime-aware correction (L5 candidate) — gated OFF.

R2 (state-stratified accuracy) ranks regime_synoptic as the #1 opportunity
across all fields: solar bias varies from +89 W/m² in frontal regime
(model overpredicts solar — actual cloud thicker than model anticipates)
to −32 W/m² in sw_flow (model underpredicts — model's clouds dissipate
faster in practice). That's a 121 W/m² systematic offset that L3 / L4 /
L2 can't address because they don't condition on regime.

L5 fixes that by indexing the correction on the current synoptic regime
classification (`derived.state.regime_synoptic` — same axis the state
stratification used). At each tick, look up the regime, return the
negated mean bias as the candidate correction.

Phase 1 (gated OFF, like the cove correction):
  stamp `weather_data["solar_correction"]` with the candidate delta + regime
  but do NOT modify direct_radiation. After we have a few weeks of side-by-side
  data (what we WOULD have predicted vs what production predicted vs actual
  observation), evaluate whether to flip ENABLED = True.

Decision rule (for the 06-22 L5 ship/hold decision):
  - Pull pair-log obs and compute what L5-applied MAE WOULD have been per
    regime bin vs L1 MAE actual.
  - Ship if the per-regime improvement is consistent (not just one regime
    carrying the day) and total MAE drops ≥ 5%.
  - Hold otherwise.

Two practical caveats baked in:
  1. Solar is zero at night — applying +89 W/m² when actual solar is 0
     is nonsense. Correction is suppressed when the raw forecast is below
     SUN_UP_THRESHOLD (50 W/m² ≈ early morning twilight onwards).
  2. The bias values below are from the 30-day rolling state_stratified
     window as of v0.6.93. They will be refreshed by a follow-up commit
     that auto-pulls the latest state_stratified instead of hardcoding.
"""
from datetime import datetime

import pytz


TZ = pytz.timezone("America/New_York")
ENABLED = False  # Flip to True after the 06-22 evaluation passes.
SUN_UP_THRESHOLD = 50.0  # W/m² — suppress correction below this raw value.

# Mean signed bias (forecast − observed) by (regime × hour_local) cell,
# computed from DAYTIME pair-log data (raw_solar ≥ 50 W/m²) over a 14-day
# window. First evaluation (regime-only lookup) showed only 2/8 regimes
# improving — the diagnosis: bias varies HUGELY by hour-of-day within
# each regime (e.g., ne_flow swings from −238 W/m² at 10:00 to +247 W/m²
# at 14:00). Averaging across hours produced systematically wrong
# corrections for any specific hour.
# Sign convention: positive bias = forecast > observed.
# Correction = −bias (subtract the systematic over/underprediction).
# Regenerate via `python3 analysis/l5_recompute_biases_hourly.py`.
# Fallback dict applies when an hour cell has too few samples to trust.
_BIAS_FALLBACK_BY_REGIME = {
    "frontal": -169.2,
    "sw_flow": -111.3,
    "pre_frontal": -115.1,
    "sea_breeze": -27.0,
    "nw_flow": -41.0,
    "calm": -79.4,
    "se_flow": -27.3,
    "ne_flow": -206.3,
    "unknown": 0.0,
}
_BIAS_BY_REGIME_HOUR = {
    "frontal": {
        10: -237.5,
        11: -315.0,
        12: -236.2,
        13: -225.2,
        14: -305.5,
        15: -133.9,
        16: -214.3,
        17: +30.1,
    },
    "sw_flow": {
         8: -44.0,
         9: -210.2,
        10: -220.7,
        14: -110.4,
        16: -170.5,
        17: +57.5,
        18: +20.5,
        19: +45.2,
    },
    "pre_frontal": {
         7: +62.6,
         8: -87.7,
         9: -158.3,
        10: -246.4,
        11: -272.0,
        12: -191.6,
        13: -261.1,
        14: -50.6,
        15: -158.5,
        16: -129.6,
        17: -0.4,
        18: +46.5,
        19: +72.0,
    },
    "sea_breeze": {
        12: -134.5,
        13: -224.7,
        14: +231.6,
        15: +13.5,
        16: -20.4,
        17: -12.4,
        18: +30.4,
        19: +42.4,
    },
    "nw_flow": {
         7: +91.0,
         8: -65.9,
         9: -144.5,
        10: -176.3,
        11: -178.3,
        12: -134.3,
        13: -139.2,
        14: -97.7,
        15: -67.5,
        16: +14.7,
        17: +36.7,
        18: +201.6,
        19: +68.0,
    },
    "calm": {
         7: -10.1,
         8: -84.1,
         9: -189.5,
        10: -32.7,
        11: -302.3,
        12: -0.3,
        18: +40.8,
        19: +72.8,
    },
    "se_flow": {
         7: +21.5,
         8: -32.7,
        11: -168.6,
        12: -149.5,
        13: -177.0,
        14: +176.6,
        15: +259.2,
        16: +69.5,
        17: -25.5,
        18: +16.1,
        19: +82.0,
    },
    "ne_flow": {
         8: -80.0,
         9: -32.1,
        10: -281.3,
        11: -268.0,
        12: -237.7,
        14: -243.9,
        18: -86.6,
    },
}


def compute_solar_correction(regime_synoptic, raw_solar_wm2, hour_local=None):
    """Return candidate Δ W/m² to add to L1 solar forecast.

    Indexed by (regime × hour_local). Falls back to regime-overall bias
    when the hour cell has too few samples to trust.

    Returns 0.0 if regime unknown, raw_solar missing, or below SUN_UP_THRESHOLD
    (night-time, no real solar to correct).
    """
    if regime_synoptic is None or raw_solar_wm2 is None:
        return 0.0
    if raw_solar_wm2 < SUN_UP_THRESHOLD:
        return 0.0
    # Try (regime, hour) cell first; fall back to regime overall.
    regime_cells = _BIAS_BY_REGIME_HOUR.get(regime_synoptic, {})
    if hour_local is not None and hour_local in regime_cells:
        bias = regime_cells[hour_local]
    else:
        bias = _BIAS_FALLBACK_BY_REGIME.get(regime_synoptic, 0.0)
    # Correction = -bias (push forecast back toward observed)
    return round(-bias, 1)


def stamp_solar_correction(weather_data):
    """Stamp candidate solar correction on weather_data. Does NOT modify
    direct_radiation arrays in Phase 1.
    """
    derived = weather_data.get("derived") or {}
    state = derived.get("state") or {}
    regime = state.get("regime_synoptic")

    # Live regime: the classifier currently only runs on pair-log records
    # via the Joiner. For the live forecast we classify inline so the G1
    # debug-page card actually has a regime to look up.
    if regime is None:
        try:
            from .regime_classifier import classify_synoptic_regime
            cur = weather_data.get("current") or {}
            now_local_for_classify = datetime.now(TZ)
            regime = classify_synoptic_regime(
                wind_dir_deg=cur.get("wind_direction"),
                wind_speed_mph=cur.get("wind_speed"),
                pressure_in=(cur.get("pressure") * 0.02953 if cur.get("pressure") else None),
                pressure_trend_3h=derived.get("pressure_trend_hpa_3h"),
                hour_local=now_local_for_classify.hour,
                temp_f=cur.get("temperature"),
            )
        except Exception:
            regime = None

    hourly = weather_data.get("hourly") or {}
    raw_solar_arr = hourly.get("raw_direct_radiation") or hourly.get("direct_radiation") or []
    raw_solar_now = raw_solar_arr[0] if raw_solar_arr else None

    now_local = datetime.now(TZ)
    delta = compute_solar_correction(regime, raw_solar_now, hour_local=now_local.hour)

    weather_data["solar_correction"] = {
        "candidate_delta_wm2": delta,
        "applied": ENABLED,
        "regime": {
            "regime_synoptic": regime,
            "raw_solar_wm2": raw_solar_now,
            "sun_up_threshold": SUN_UP_THRESHOLD,
            "hour_local": now_local.hour,
        },
        "note": (
            "Candidate L5 regime-aware solar correction. Gated OFF until "
            "the 2026-06-22 evaluation confirms per-regime improvement."
            if not ENABLED
            else "L5 regime correction applied to direct_radiation."
        ),
    }

    if ENABLED:
        # When we flip the switch, apply the delta to direct_radiation array
        # only at lead positions where raw_solar is above SUN_UP_THRESHOLD.
        # Forecasts at lead L use the SAME regime label as right now — a
        # simplification (the regime might evolve), but conservative and
        # easy to audit. Refinement: project the regime forward.
        target = hourly.get("direct_radiation")
        if isinstance(target, list) and target:
            hourly["direct_radiation"] = [
                round(v + delta, 1) if (v is not None and v >= SUN_UP_THRESHOLD) else v
                for v in target
            ]

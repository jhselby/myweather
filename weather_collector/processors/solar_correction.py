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
    "frontal":     -81.1,
    "sw_flow":     -79.3,
    "pre_frontal": -107.3,
    "sea_breeze":  -44.6,
    "nw_flow":     -40.8,
    "calm":        -57.2,
    "se_flow":    -114.9,
    "ne_flow":    -206.3,
    "unknown":       0.0,
}
_BIAS_BY_REGIME_HOUR = {
    "frontal": {
         7: +39.0,
         8: -40.6,
         9: -71.6,
        10: -160.5,
        11: -261.0,
        12: -82.8,
        13: -201.5,
        14: -269.5,
        15: +21.9,
        16: +43.7,
        17:  -4.9,
        18: -11.0,
        19: +112.9,
    },
    "sw_flow": {
         7: +15.2,
         8: -54.1,
         9: -110.4,
        10: -194.0,
        11: -267.3,
        14: -40.8,
        16: -170.5,
        17: +65.4,
        18: +12.9,
        19: +64.7,
    },
    "pre_frontal": {
         7: +40.8,
         8: -53.1,
         9: -134.0,
        10: -229.1,
        11: -257.8,
        12: -173.0,
        13: -255.7,
        14: -108.9,
        15: -113.0,
        16: -97.9,
        17:  +4.0,
        18: +58.4,
        19: +77.4,
    },
    "sea_breeze": {
        12: -96.7,
        13: -184.0,
        14: -22.6,
        15: -17.4,
        16: -17.7,
        17:  +3.4,
        18: +42.9,
        19: +78.4,
    },
    "nw_flow": {
         7: +83.9,
         8: -21.0,
         9: -149.9,
        10: -218.4,
        11: -229.7,
        12: -94.4,
        13: -159.7,
        14: -19.9,
        15: -33.8,
        16: +22.3,
        17: +63.1,
        18: +115.5,
        19: +88.1,
        20: +45.8,
    },
    "calm": {
         7: +22.8,
         8: -58.8,
         9: -189.5,
        10: -32.7,
        11: -302.3,
        12:  -0.3,
        18: +40.8,
        19: +87.8,
    },
    "se_flow": {
         7: +19.3,
         8: -28.2,
        10: -400.0,
        11: -231.2,
        12: -181.9,
        13: -262.3,
        14: -202.0,
        15: +51.3,
        16:  +6.9,
        17:  +1.9,
        18: +43.8,
        19: +92.8,
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

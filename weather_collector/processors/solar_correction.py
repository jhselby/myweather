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
    "frontal": +12.1,
    "sw_flow": -122.8,
    "pre_frontal": -65.6,
    "sea_breeze": -17.3,
    "nw_flow": -57.7,
    "calm": -57.9,
    "se_flow": -67.1,
    "ne_flow": -137.5,
    "unknown": 0.0,
}
_BIAS_BY_REGIME_HOUR = {
    "frontal": {7: -7.9, 8: -185.8, 9: -228.0, 10: -106.3, 11: -150.6,
                12: -35.6, 13: +33.3, 14: +88.7, 15: +280.4, 16: +185.8,
                17: +110.8, 18: +82.8, 19: +67.0},
    "sw_flow": {7: -33.1, 8: -123.2, 9: -265.4, 10: -236.4, 11: -276.8,
                12: -209.9, 13: -151.8, 14: -176.8, 15: -73.3,
                17: +81.2, 18: +123.9, 19: +67.1},
    "pre_frontal": {7: -23.2, 8: -196.1, 9: -259.8, 10: -205.4, 11: -274.6,
                    12: -97.1, 13: -50.2, 14: -109.2, 15: -39.8,
                    16: +47.2, 17: +113.6, 18: +110.6, 19: +74.8},
    "sea_breeze": {12: -124.1, 13: -72.1, 14: -108.4, 15: +5.2,
                   16: +49.1, 17: +89.3, 18: +100.2, 19: +84.6},
    "nw_flow": {7: -28.4, 8: -215.9, 9: -250.7, 10: -190.8, 11: -201.7,
                12: -126.8, 13: -94.8, 14: -4.7, 15: +115.1, 16: +92.2,
                17: +165.7, 18: +124.2, 19: +84.6},
    "calm": {7: -46.2, 8: -105.0, 9: -106.0, 10: -183.5, 11: -197.3,
             12: -121.0, 13: -42.6, 14: -244.8, 15: +77.0, 16: +27.1,
             17: +81.3, 18: +123.2, 19: +89.5, 20: +57.0},
    "se_flow": {7: -11.4, 8: -143.3, 10: -201.0, 11: -248.2, 12: -227.4,
                13: -105.6, 14: -47.4, 15: +64.1, 16: +64.5, 17: +82.5,
                18: +137.2, 19: +108.0, 20: +51.5},
    "ne_flow": {7: -41.8, 8: -138.4, 9: -219.1, 10: -238.3, 11: -215.4,
                13: +169.3, 14: +246.8, 18: +157.9, 19: +120.4},
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

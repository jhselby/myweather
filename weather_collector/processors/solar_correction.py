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

# Mean signed bias (forecast − observed) per synoptic regime, computed
# from DAYTIME ONLY pair-log data (raw_solar ≥ 50 W/m²) over a 14-day
# window ending 2026-06-15. Originally seeded from state_stratified, but
# that average included nighttime zeros which masked the daytime signal.
# Sign convention: positive bias = forecast > observed.
# Correction = −bias (subtract the systematic over/underprediction).
# Regenerate via `python3 analysis/l5_recompute_biases.py`.
_BIAS_BY_REGIME = {
    "frontal":     +12.1,  # n=5,871,  σ=232.7
    "sw_flow":    -122.8,  # n=19,989, σ=190.1
    "pre_frontal": -65.6,  # n=23,994, σ=229.2
    "sea_breeze":  -17.3,  # n=24,616, σ=239.8
    "nw_flow":     -57.7,  # n=48,473, σ=210.0
    "calm":        -57.9,  # n=30,521, σ=187.8
    "se_flow":     -67.1,  # n=23,536, σ=238.4
    "ne_flow":    -137.5,  # n=6,020,  σ=212.2
    "unknown":       0.0,
}


def compute_solar_correction(regime_synoptic, raw_solar_wm2):
    """Return candidate Δ W/m² to add to L1 solar forecast.

    Returns 0.0 if regime unknown, raw_solar missing, or below SUN_UP_THRESHOLD
    (night-time, no real solar to correct).
    """
    if regime_synoptic is None or raw_solar_wm2 is None:
        return 0.0
    if raw_solar_wm2 < SUN_UP_THRESHOLD:
        return 0.0
    # Correction = -bias (push forecast back toward observed)
    bias = _BIAS_BY_REGIME.get(regime_synoptic, 0.0)
    return round(-bias, 1)


def stamp_solar_correction(weather_data):
    """Stamp candidate solar correction on weather_data. Does NOT modify
    direct_radiation arrays in Phase 1.
    """
    derived = weather_data.get("derived") or {}
    state = derived.get("state") or {}
    regime = state.get("regime_synoptic")

    hourly = weather_data.get("hourly") or {}
    raw_solar_arr = hourly.get("raw_direct_radiation") or hourly.get("direct_radiation") or []
    raw_solar_now = raw_solar_arr[0] if raw_solar_arr else None

    delta = compute_solar_correction(regime, raw_solar_now)
    now_local = datetime.now(TZ)

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

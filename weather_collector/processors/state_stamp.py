"""
Populate `weather_data["derived"]["state"]` with the current-tick regime
labels and inputs. Runs once per collector tick, before any consumer that
needs regime-conditional behavior (decay_apply's skip table, solar_correction,
backtest_snapshot, confidence_layer, state_stratified).

Historical gap (found 2026-07-06 v0.6.310): the design assumed something
stamped derived.state each tick, but no writer existed. Consequences:

  * decay_apply.py:461 read `state.get("regime_synoptic")` and got None,
    so `_should_skip()` fail-safed to False on every row → the L3/L4
    skip table shipped v0.6.279 has never fired since ship day. ws L3
    still applies in ne_flow all bands and sea_breeze 0-11h despite the
    skip cells being populated.
  * solar_correction.py worked around it by classifying inline (line
    255-269). That path still works, but duplicates the classifier call.
  * backtest_snapshot.py stamped `regime_synoptic: None` on every entry.
  * confidence_layer + state_stratified read None and their regime
    branches never took the regime path.

This module writes ONE dict at derived["state"] and every downstream
consumer keeps reading the same key.

Fields written (matches backtest_snapshot's expected schema):
  * regime_synoptic  — from classify_synoptic_regime()
  * regime_flow      — from classify_flow_regime()
  * wind_dir         — passed straight from current
  * wind_speed       — passed straight from current
  * wind_octant      — 8-direction bucket (N/NE/E/...) for R2/stratification
  * cloud_cover      — passed straight from current
"""
import logging
from datetime import datetime

import pytz

from .regime_classifier import classify_flow_regime, classify_synoptic_regime


TZ = pytz.timezone("America/New_York")
_OCTANTS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _wind_octant(deg):
    if deg is None:
        return None
    try:
        d = (float(deg) + 22.5) % 360
    except (TypeError, ValueError):
        return None
    return _OCTANTS[int(d // 45)]


def stamp_state(weather_data):
    """Populate weather_data["derived"]["state"] with current regime labels.

    Idempotent — safe to call twice; second call overwrites with the same
    values. Fail-safe: any classifier exception yields None fields.
    """
    derived = weather_data.setdefault("derived", {})
    current = weather_data.get("current") or {}

    wind_dir = current.get("wind_direction")
    wind_speed = current.get("wind_speed")
    pressure_hpa = current.get("pressure")
    pressure_in = (pressure_hpa * 0.02953) if pressure_hpa else None
    pressure_trend_3h = derived.get("pressure_trend_hpa_3h")
    temp_f = current.get("temperature")
    cloud_cover = current.get("cloud_cover")
    hour_local = datetime.now(TZ).hour

    try:
        regime_flow = classify_flow_regime(wind_dir, wind_speed)
    except Exception as e:
        logging.warning(f"  ⚠  classify_flow_regime failed: {e}")
        regime_flow = None

    try:
        regime_synoptic = classify_synoptic_regime(
            wind_dir_deg=wind_dir,
            wind_speed_mph=wind_speed,
            pressure_in=pressure_in,
            pressure_trend_3h=pressure_trend_3h,
            hour_local=hour_local,
            temp_f=temp_f,
        )
    except Exception as e:
        logging.warning(f"  ⚠  classify_synoptic_regime failed: {e}")
        regime_synoptic = None

    state = {
        "regime_synoptic": regime_synoptic,
        "regime_flow":     regime_flow,
        "wind_dir":        wind_dir,
        "wind_speed":      wind_speed,
        "wind_octant":     _wind_octant(wind_dir),
        "cloud_cover":     cloud_cover,
    }
    derived["state"] = state
    logging.info(
        f"  ✓ state stamped: synoptic={regime_synoptic} flow={regime_flow} "
        f"octant={state['wind_octant']} ws={wind_speed}"
    )
    return state

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

Also writes `derived["state_fc_by_lead"]` — array of regime_synoptic per
hourly lead index, using the same classifier applied to forecast values.
Canonical location for consumers that need per-hour transition detection
(e.g. wd_persistence_gate's transition trigger, future UI widening on
`state_fc[lead] != state.regime_synoptic`). Extracted 2026-08-10 v0.6.401c
from wd_persistence_gate.py to give it a home not owned by one specialist.
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

    fc_by_lead = _classify_state_fc_by_lead(weather_data, pressure_trend_3h)
    derived["state_fc_by_lead"] = fc_by_lead

    n_transitions = sum(
        1 for r in fc_by_lead
        if r is not None and regime_synoptic is not None and r != regime_synoptic
    )
    logging.info(
        f"  ✓ state stamped: synoptic={regime_synoptic} flow={regime_flow} "
        f"octant={state['wind_octant']} ws={wind_speed} "
        f"fc_leads={len(fc_by_lead)} transitions={n_transitions}"
    )
    return state


def _classify_state_fc_by_lead(weather_data, pressure_trend_3h):
    """Per-lead classify_synoptic_regime using forecast values at each hour.
    Returns list of regime strings (or None per lead when inputs missing).
    Uses the same input signature as classify_synoptic_regime; pressure_trend
    is the current tick's 3h trend (state_fc inherits it — matches
    forecast_error_log.py's state_fc construction)."""
    hourly = weather_data.get("hourly") or {}
    wd_arr = hourly.get("wind_direction") or []
    ws_arr = hourly.get("wind_speed") or []
    pr_arr = hourly.get("pressure_in") or hourly.get("pressure") or []
    t_arr = hourly.get("temperature") or []
    time_arr = hourly.get("time") or []
    n = len(wd_arr)
    out = [None] * n
    for i in range(n):
        try:
            wd = float(wd_arr[i]) if wd_arr[i] is not None else None
            ws = float(ws_arr[i]) if i < len(ws_arr) and ws_arr[i] is not None else None
            pr = float(pr_arr[i]) if i < len(pr_arr) and pr_arr[i] is not None else None
            t = float(t_arr[i]) if i < len(t_arr) and t_arr[i] is not None else None
        except (TypeError, ValueError):
            continue
        hour_local = None
        if i < len(time_arr) and time_arr[i]:
            try:
                hour_local = int(time_arr[i][11:13])
            except Exception:
                pass
        try:
            out[i] = classify_synoptic_regime(wd, ws, pr, pressure_trend_3h, hour_local, t)
        except Exception:
            continue
    return out

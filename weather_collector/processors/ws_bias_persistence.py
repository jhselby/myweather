"""ws bias-persistence gate — antecedent-based ws forecast correction.

Sibling of dp_bias_persistence (v0.6.387). Fires when the previous-24h
per-regime mean ws bias (forecast_l1 minus current-hour observed, accumulated
across ticks) is above TRIGGER_THRESHOLD for one of FOCUS_REGIMES, SUBTRACTING
a capped amount (proportional to the observed prev-day over-forecast) from
the corrected wind speed forecast at leads >= MIN_LEAD.

Rests on Stage 0/1 findings (2026-07-28):
  - Pooled ws lag-1 r=+0.470; strong per-regime persistence in calm (+0.706)
    and ne_flow (+0.649). Other regimes had moderate lag-1 but were driven
    by intermittent under-forecast events (gust misses) that a fixed
    antecedent correction hurts on quiet days.
  - Stage 1 halves-verified only for calm: pooled +11.07% (halves +13.35 /
    +10.33), fires 38% consistently across pooled + A + B halves. ne_flow
    also Stage 1 SHIP but A-half had 0 fires (regime drifted mid-window;
    fragile verdict) → dropped from ship.
  - Correction magnitude uses -min(prev_bias, CORRECTION_CAP) — proportional
    to the persisting bias, capped. Unlike dpbp which uses a fixed +2.0°F.

Runtime data source:
  - GCS `ws_bias_antecedent_state.json` — rolling 48h list of per-tick
    (fc_l1 - obs_ws, regime, timestamp).
  - Curated JSON (this file's sibling) — params + focus regime set.
  - hourly.wind_speed — post-L4 corrected forecast (read + modify).
    Note: for wind fields decay_apply writes back to `hourly.wind_speed`
    directly (not `corrected_wind_speed`); the L1 raw is preserved as
    `hourly.raw_wind_speed` by wind_blend.
  - current.wind_speed — observed
  - derived.state.regime_synoptic — regime at obs time

Placement: runs AFTER decay_apply and dp_residual_persistence (both of
which touch dp) — but BEFORE the applicability descriptor block. For ws
specifically this composes on top of wind_blend (L2) + decay_apply
(L3/L4 SKIP_TABLE, incl. v0.6.386 wg long-lead cells).

When ENABLED=False the module still stamps unconditional shadow arrays
(hourly.wind_speed_shadow_wsbp) per [[feedback_persistence_gate_shadow_write]].
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path


ENABLED = False   # 7-day flip gate. Stage 3 wired 2026-07-28; earliest flip 2026-08-04.

FIELD = "ws"
HOURLY_KEY = "wind_speed"
RAW_KEY = "raw_wind_speed"    # wind_blend preserves L1 raw here
PRE_GATE_KEY = "wind_speed_pre_wsbp"
SHADOW_KEY = "wind_speed_shadow_wsbp"

_TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / "ws_bias_persistence_curated.json"
_TABLE_CACHE = None

GCS_STATE_PATH = "ws_bias_antecedent_state.json"
STATE_WINDOW_HOURS = 48
ANTECEDENT_WINDOW_HOURS = 24
MIN_N_ANTECEDENT = 20

DEFAULT_TRIGGER_THRESHOLD = 1.0     # mph; prev-24h bias ABOVE this fires (over-forecast direction only)
DEFAULT_CORRECTION_CAP = 3.0         # mph; abs cap on correction magnitude
DEFAULT_MIN_LEAD = 6                  # skip leads 0-5 (wind_blend covers 0-3; leads 4-5 marginal per per-cell)
DEFAULT_FOCUS_REGIMES = ("calm",)


def _load_table():
    global _TABLE_CACHE
    if _TABLE_CACHE is not None:
        return _TABLE_CACHE
    try:
        _TABLE_CACHE = json.loads(_TABLE_PATH.read_text())
    except FileNotFoundError:
        logging.warning(f"  ⚠  wsbp table missing at {_TABLE_PATH}; using defaults")
        _TABLE_CACHE = {}
    except Exception as e:
        logging.warning(f"  ⚠  wsbp table load failed: {e}; using defaults")
        _TABLE_CACHE = {}
    return _TABLE_CACHE


def _params():
    t = _load_table()
    return (
        float(t.get("trigger_threshold_mph", DEFAULT_TRIGGER_THRESHOLD)),
        float(t.get("correction_cap_mph", DEFAULT_CORRECTION_CAP)),
        int(t.get("min_lead_h", DEFAULT_MIN_LEAD)),
        frozenset(t.get("focus_regimes") or DEFAULT_FOCUS_REGIMES),
    )


def load_state(gcs_client, bucket_name):
    try:
        blob = gcs_client.bucket(bucket_name).blob(GCS_STATE_PATH)
        if blob.exists():
            return json.loads(blob.download_as_text())
        logging.info("  ℹ  No ws_bias_antecedent_state.json yet (first run)")
    except Exception as e:
        logging.warning(f"  ⚠  wsbp state load failed: {e}")
    return {"entries": []}


def save_state(state, gcs_client, bucket_name):
    try:
        blob = gcs_client.bucket(bucket_name).blob(GCS_STATE_PATH)
        blob.upload_from_string(json.dumps(state), content_type="application/json")
    except Exception as e:
        logging.warning(f"  ⚠  wsbp state save failed: {e}")


def _now_utc():
    return datetime.now(timezone.utc)


def _prune(entries, now):
    cutoff = (now - timedelta(hours=STATE_WINDOW_HOURS)).strftime("%Y-%m-%dT%H:%M")
    return [e for e in entries if e.get("t", "") >= cutoff]


def _antecedent_bias(entries, now, regime):
    lo = (now - timedelta(hours=ANTECEDENT_WINDOW_HOURS)).strftime("%Y-%m-%dT%H:%M")
    hi = now.strftime("%Y-%m-%dT%H:%M")
    matched = [e for e in entries
               if e.get("regime") == regime and lo <= e.get("t", "") <= hi]
    if len(matched) < MIN_N_ANTECEDENT:
        return None, len(matched)
    total = sum(float(e["bias"]) for e in matched)
    return total / len(matched), len(matched)


def _current_hour_index(hourly):
    times = hourly.get("times") or []
    if not times:
        return None
    now = _now_utc()
    prefix = now.strftime("%Y-%m-%dT%H")
    for i, t in enumerate(times):
        if isinstance(t, str) and t.startswith(prefix):
            return i
    return None


def _current_bias(weather_data):
    """Return (bias, regime) where bias = fc_l1 - obs at current tick.
    Uses raw_wind_speed (L1) preserved by wind_blend, falls back to
    hourly.wind_speed if raw missing (edge case, first tick after cold deploy)."""
    hourly = weather_data.get("hourly") or {}
    raw_arr = hourly.get(RAW_KEY) or hourly.get(HOURLY_KEY) or []
    idx = _current_hour_index(hourly)
    if idx is None or idx >= len(raw_arr):
        return None, None
    fc_l1 = raw_arr[idx]
    obs = (weather_data.get("current") or {}).get(HOURLY_KEY)
    if fc_l1 is None or obs is None:
        return None, None
    regime = ((weather_data.get("derived") or {}).get("state") or {}).get("regime_synoptic")
    return (float(fc_l1) - float(obs)), regime


def stamp_ws_bias_persistence(weather_data, gcs_client=None, bucket_name=None):
    """Main entry. Same shape as stamp_dp_bias_persistence but for ws.
    Correction subtracts a capped amount of the prev-24h over-forecast bias.
    """
    hourly = weather_data.get("hourly") or {}
    ws_arr = hourly.get(HOURLY_KEY)
    if not ws_arr:
        return
    times = hourly.get("times") or []
    if not times:
        return

    state = {"entries": []}
    if gcs_client is not None and bucket_name is not None:
        state = load_state(gcs_client, bucket_name)
        now = _now_utc()
        state["entries"] = _prune(state.get("entries", []), now)
        bias_now, regime_now = _current_bias(weather_data)
        if bias_now is not None and regime_now:
            state["entries"].append({
                "t": now.strftime("%Y-%m-%dT%H:%M"),
                "regime": regime_now,
                "bias": round(bias_now, 3),
            })
        state["generated_at"] = now.isoformat()
        save_state(state, gcs_client, bucket_name)

    trigger, cap, min_lead, focus_regimes = _params()
    now = _now_utc()

    if PRE_GATE_KEY not in hourly:
        hourly[PRE_GATE_KEY] = list(ws_arr)

    cur_idx = _current_hour_index(hourly) or 0
    regime_curr = ((weather_data.get("derived") or {}).get("state") or {}).get("regime_synoptic")

    ant = {}
    for r in focus_regimes:
        ant[r] = _antecedent_bias(state.get("entries", []), now, r)

    corrected = list(hourly[PRE_GATE_KEY])
    shadow = list(hourly[PRE_GATE_KEY])
    n_fired = 0

    for i in range(len(corrected)):
        lead = max(0, i - cur_idx)
        should_fire = False
        if regime_curr in focus_regimes and lead >= min_lead:
            mean_bias, n_ant = ant.get(regime_curr, (None, 0))
            # Fire only when prev-day was OVER-forecast (positive bias above trigger)
            if mean_bias is not None and mean_bias > trigger:
                should_fire = True
        if should_fire:
            mean_bias, _ = ant[regime_curr]
            correction = -min(max(mean_bias, -cap), cap)  # sign-flip, capped ±cap
            new_val = max(0.0, shadow[i] + correction)     # clamp to non-negative wind
            shadow[i] = new_val
            n_fired += 1

    hourly[SHADOW_KEY] = shadow

    if ENABLED:
        hourly[HOURLY_KEY] = shadow

    weather_data["ws_bias_persistence"] = {
        "enabled": ENABLED,
        "regime_curr": regime_curr,
        "trigger_threshold_mph": trigger,
        "correction_cap_mph": cap,
        "min_lead_h": min_lead,
        "focus_regimes": sorted(focus_regimes),
        "antecedent": {
            r: {"mean_bias": (None if ant[r][0] is None else round(ant[r][0], 3)),
                "n": ant[r][1]}
            for r in focus_regimes
        },
        "leads_fired": n_fired,
        "leads_total": len(corrected),
    }


def describe_applicability():
    trigger, cap, min_lead, focus_regimes = _params()
    return [{
        "layer_id": "ws_bias_persistence",
        "field": FIELD,
        "name": "ws bias-persistence gate",
        "enabled": ENABLED,
        "gate_summary": (
            f"regime ∈ {{{', '.join(sorted(focus_regimes))}}} "
            f"AND lead ≥ {min_lead}h AND prev-24h ws_bias > +{trigger:.1f} mph"
        ),
        "action": f"subtract min(prev_bias, {cap:.1f}) mph from wind_speed",
    }]

"""dp bias-persistence gate — antecedent-based dp forecast correction.

Fires when the previous-24h per-regime mean dp_bias (forecast_l1 minus
observed at the tick's current hour, accumulated across ticks) is below
TRIGGER_THRESHOLD for one of the FOCUS_REGIMES, adding CORRECTION °F to
the corrected dew point forecast at leads >= MIN_LEAD.

Rests on Stage 0/1/2 findings (2026-07-28):
  - Lag-1 Pearson r = +0.583 across pooled daily dp_bias.
  - Big dp under-forecast events cluster in multi-day streaks; once
    day D-1 is a big miss, day D is likely a big miss too.
  - Stage 1 halves-verified: pre_frontal +17.23% / +21.59 / +11.99,
    nw_flow +14.51% / +15.64 / +13.83, sw_flow +14.62% / +6.05 / +17.90.
  - 0-5h leads are DAMAGED by the fixed-magnitude add (already close to
    obs from station_bias / L2 blend); lead >= 6 is the safe range.

Runtime data source:
  - GCS `dp_bias_antecedent_state.json` — rolling 48h list of
    per-tick observations of (fc_l1 - obs_dp, regime, timestamp).
  - Curated JSON (this file's sibling) — params + focus regime set.
  - hourly.corrected_dew_point — post-L4 dp forecast (read + modify)
  - hourly.dew_point — raw model L1 dp forecast
  - current.dew_point — observed
  - derived.state.regime_synoptic — regime at obs time

Placement: runs AFTER dp_residual_persistence so we compose on top of
whatever that gate did (currently ENABLED=False so passthrough).
Overwrites hourly.corrected_dew_point in-place, preserving the pre-gate
array as hourly.corrected_dew_point_pre_dpbp for attribution.

When ENABLED=False the module still stamps unconditional shadow arrays
(hourly.corrected_dew_point_shadow_dpbp) so the 7-day flip gate has real
data to read. Missing this bit wdp and clp; see
[[feedback_persistence_gate_shadow_write]].
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path


ENABLED = True    # Flipped 2026-08-04 v0.6.391 after 7-day shadow-week clear. Stage 3 wired 2026-07-28 v0.6.387; Stage 1 halves-verified pre_frontal +17.2%, nw_flow +14.5%, sw_flow +14.6%.

FIELD = "dp"
HOURLY_KEY = "corrected_dew_point"
PRE_GATE_KEY = "corrected_dew_point_pre_dpbp"
SHADOW_KEY = "corrected_dew_point_shadow_dpbp"

_TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / "dp_bias_persistence_curated.json"
_TABLE_CACHE = None

GCS_STATE_PATH = "dp_bias_antecedent_state.json"
STATE_WINDOW_HOURS = 48
ANTECEDENT_WINDOW_HOURS = 24
MIN_N_ANTECEDENT = 20

DEFAULT_TRIGGER_THRESHOLD = -1.5   # °F; prev-24h dp_bias below this fires the gate
DEFAULT_CORRECTION = 2.0            # °F to ADD to forecast dp
DEFAULT_MIN_LEAD = 6                 # skip 0-5h leads (fixed add damages there)
DEFAULT_FOCUS_REGIMES = ("pre_frontal", "nw_flow", "sw_flow")


def _load_table():
    global _TABLE_CACHE
    if _TABLE_CACHE is not None:
        return _TABLE_CACHE
    try:
        _TABLE_CACHE = json.loads(_TABLE_PATH.read_text())
    except FileNotFoundError:
        logging.warning(f"  ⚠  dpbp table missing at {_TABLE_PATH}; using defaults")
        _TABLE_CACHE = {}
    except Exception as e:
        logging.warning(f"  ⚠  dpbp table load failed: {e}; using defaults")
        _TABLE_CACHE = {}
    return _TABLE_CACHE


def _params():
    t = _load_table()
    return (
        float(t.get("trigger_threshold_f", DEFAULT_TRIGGER_THRESHOLD)),
        float(t.get("correction_f", DEFAULT_CORRECTION)),
        int(t.get("min_lead_h", DEFAULT_MIN_LEAD)),
        frozenset(t.get("focus_regimes") or DEFAULT_FOCUS_REGIMES),
    )


def load_state(gcs_client, bucket_name):
    try:
        blob = gcs_client.bucket(bucket_name).blob(GCS_STATE_PATH)
        if blob.exists():
            return json.loads(blob.download_as_text())
        logging.info("  ℹ  No dp_bias_antecedent_state.json yet (first run)")
    except Exception as e:
        logging.warning(f"  ⚠  dpbp state load failed: {e}")
    return {"entries": []}


def save_state(state, gcs_client, bucket_name):
    try:
        blob = gcs_client.bucket(bucket_name).blob(GCS_STATE_PATH)
        blob.upload_from_string(json.dumps(state), content_type="application/json")
    except Exception as e:
        logging.warning(f"  ⚠  dpbp state save failed: {e}")


def _now_utc():
    return datetime.now(timezone.utc)


def _prune(entries, now):
    cutoff_dt = now - timedelta(hours=STATE_WINDOW_HOURS)
    cutoff = cutoff_dt.strftime("%Y-%m-%dT%H:%M")
    return [e for e in entries if e.get("t", "") >= cutoff]


def _antecedent_bias(entries, now, regime):
    """Return (mean_dp_bias_prev_24h, n) for this regime. None if thin."""
    hi = now
    lo = now - timedelta(hours=ANTECEDENT_WINDOW_HOURS)
    lo_iso = lo.strftime("%Y-%m-%dT%H:%M")
    hi_iso = hi.strftime("%Y-%m-%dT%H:%M")
    matched = [e for e in entries
               if e.get("regime") == regime
               and lo_iso <= e.get("t", "") <= hi_iso]
    if len(matched) < MIN_N_ANTECEDENT:
        return None, len(matched)
    total = sum(float(e["bias"]) for e in matched)
    return total / len(matched), len(matched)


def _current_hour_index(hourly):
    times = hourly.get("times") or []
    if not times:
        return None
    now = _now_utc()
    # times are ISO strings, may be local or UTC — collector uses "%Y-%m-%dT%H:%M"
    # matching by hour prefix works either way if now aligns
    hour_prefix = now.strftime("%Y-%m-%dT%H")
    for i, t in enumerate(times):
        if isinstance(t, str) and t.startswith(hour_prefix):
            return i
    return None


def _current_bias(weather_data):
    """Return (bias, regime) where bias = fc_l1 - obs at current tick.
    None if either component is missing."""
    hourly = weather_data.get("hourly") or {}
    dp_arr = hourly.get("dew_point") or []
    idx = _current_hour_index(hourly)
    if idx is None or idx >= len(dp_arr):
        return None, None
    fc_l1 = dp_arr[idx]
    obs = (weather_data.get("current") or {}).get("dew_point")
    if fc_l1 is None or obs is None:
        return None, None
    regime = ((weather_data.get("derived") or {}).get("state") or {}).get("regime_synoptic")
    return (float(fc_l1) - float(obs)), regime


def stamp_dp_bias_persistence(weather_data, gcs_client=None, bucket_name=None):
    """Main entry. Updates antecedent state on GCS (if clients passed), then
    applies (or shadows) the correction to hourly.corrected_dew_point.

    Always writes hourly.corrected_dew_point_shadow_dpbp unconditionally
    (per shadow-write invariant). Only mutates the live array when
    ENABLED=True and gate fires.
    """
    hourly = weather_data.get("hourly") or {}
    corr_arr = hourly.get(HOURLY_KEY)
    if not corr_arr:
        return  # nothing to do

    times = hourly.get("times") or []
    if not times:
        return

    # ── State update: append this tick's (fc_l1 - obs) sample, prune, save
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

    # ── Fire decision per lead index
    trigger, correction, min_lead, focus_regimes = _params()
    now = _now_utc()

    # Preserve pre-gate array (idempotent)
    if PRE_GATE_KEY not in hourly:
        hourly[PRE_GATE_KEY] = list(corr_arr)

    # Determine current-run start hour so we can compute lead per index
    # (times[0] anchors the run; lead = i - current_hour_index if current
    # hour is inside the array, otherwise lead = i.)
    cur_idx = _current_hour_index(hourly) or 0

    # forecast regime — use current derived regime as best proxy for lead-0;
    # more sophisticated versions would use state_fc per-lead. For MVP
    # we apply per-regime antecedent based on the run-time regime.
    regime_curr = ((weather_data.get("derived") or {}).get("state") or {}).get("regime_synoptic")

    # Compute antecedent for each focus regime once (they don't change
    # per-lead; the fire condition depends on current regime + lead).
    ant = {}
    for r in focus_regimes:
        ant[r] = _antecedent_bias(state.get("entries", []), now, r)

    fires_by_lead = []
    corrected = list(hourly[PRE_GATE_KEY])   # start from pre-gate baseline
    shadow = list(hourly[PRE_GATE_KEY])
    n_fired = 0

    for i in range(len(corrected)):
        lead = max(0, i - cur_idx)
        # For MVP, use run-time regime for all leads (state_fc-per-lead
        # can be added later). Only fires if current regime is in focus set
        # AND lead >= min_lead AND antecedent thick enough AND below trigger.
        should_fire = False
        detail = None
        if regime_curr in focus_regimes and lead >= min_lead:
            mean_bias, n_ant = ant.get(regime_curr, (None, 0))
            if mean_bias is not None and mean_bias < trigger:
                should_fire = True
                detail = {"antecedent": round(mean_bias, 3), "n": n_ant}
        fires_by_lead.append(should_fire)
        if should_fire:
            shadow[i] = corrected[i] + correction
            n_fired += 1

    # Shadow-write unconditional
    hourly[SHADOW_KEY] = shadow

    # Live write only if ENABLED
    if ENABLED:
        hourly[HOURLY_KEY] = shadow

    # Telemetry envelope
    weather_data.setdefault("dp_bias_persistence", {})
    weather_data["dp_bias_persistence"] = {
        "enabled": ENABLED,
        "regime_curr": regime_curr,
        "trigger_threshold_f": trigger,
        "correction_f": correction,
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
    """Applicability descriptor for the debug page. Returns list of
    layer descriptors per applicability_map schema."""
    trigger, correction, min_lead, focus_regimes = _params()
    return [{
        "layer_id": "dp_bias_persistence",
        "field": FIELD,
        "name": "dp bias-persistence gate",
        "enabled": ENABLED,
        "gate_summary": (
            f"regime ∈ {{{', '.join(sorted(focus_regimes))}}} "
            f"AND lead ≥ {min_lead}h AND prev-24h dp_bias < {trigger:+.1f}°F"
        ),
        "action": f"+{correction:.1f}°F to corrected dew point",
    }]

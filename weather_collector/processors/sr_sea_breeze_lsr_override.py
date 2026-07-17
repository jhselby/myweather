"""
sr sea_breeze cc-gated Lsr override — Stage 3 wiring, gated OFF.

Follow-on to sr_sea_breeze_lsr_refit_stage2.py Stage 2 PROMOTE
(2026-07-17). Stage 2 found pooled sea_breeze sr MAE improves +25.27%
(halves +29.0% / +21.5%, lead-band clean) when the current-Prod Lsr
output is replaced with per-hour-bias-corrected shortwave_radiation on
cc-gated rows: (cc < 25) OR (cc >= 75). Middle cc bins keep current Lsr.

Physical read: fc_shortwave over-predicts vs Tempest total-shortwave in
clear-sky sea_breeze (coastal cloud burns off), under-predicts in overcast
(thick attenuation missed). Both effects are stable enough to correct
with a per-hour bias. Partly-cloudy is genuinely noisy at the pixel scale
— no fit works, so gate it out.

Reads: weather_collector/data/sr_sea_breeze_lsr_curated.json
       (bias_by_hour, cc_gate, verdict; produced by Stage 2 script).

Runs AFTER stamp_solar_correction in the collector pipeline. When the
gate fires, overwrites hourly["direct_radiation"][lead] with
(shortwave_radiation[lead] − bias(hour_local)). Preserves the pre-override
value in hourly["direct_radiation_pre_sb"] so the pair log's per-layer
error keys still see the Lsr baseline for A/B watching.

Phase 1 (this module, gated OFF):
  Every tick, compute per-lead candidate deltas and stamp
  weather_data["sr_sea_breeze_correction"] with the gate state, but do NOT
  modify direct_radiation. Weekly Sun-morning halves re-runs of Stage 2
  through 07-24 will decide the flip.

Decision rule (ship if):
  Stage 2 pooled Δ ≥ +20% and both halves ≥ +10% across weekly re-reads
  W29 (07-19) and W30 (07-26), lead-band SHIP+MARGIN > SKIP.
"""
import json
import logging
import os
from datetime import datetime

import pytz

from ..utils import redact_secrets


TZ = pytz.timezone("America/New_York")
ENABLED = False  # Flip after 07-24 weekly Sun-morning re-reads confirm.
SUN_UP_THRESHOLD = 50.0  # W/m² — mirror Lsr's night-time suppression.

_CURATED_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data",
    "sr_sea_breeze_lsr_curated.json",
)


def _load_curated():
    """Load bias table + gate config. Returns (bias_by_hour, overall_bias, cc_lo, cc_hi)."""
    try:
        with open(os.path.abspath(_CURATED_PATH)) as f:
            d = json.load(f)
    except FileNotFoundError:
        return {}, 0.0, 25.0, 75.0
    hb_str = d.get("hourly_bias_wm2") or {}
    bias_by_hour = {int(k): float(v) for k, v in hb_str.items()}
    overall = float(d.get("overall_bias_wm2") or 0.0)
    gate = d.get("cc_gate") or {}
    cc_lo = float(gate.get("lo", 25.0))
    cc_hi = float(gate.get("hi", 75.0))
    return bias_by_hour, overall, cc_lo, cc_hi


_BIAS_BY_HOUR, _OVERALL_BIAS, _CC_LO, _CC_HI = _load_curated()


def _cc_gated(cc):
    if cc is None:
        return False
    return cc < _CC_LO or cc >= _CC_HI


def _record_firing(regime, fired, skipped):
    """When ENABLED=False, gated leads count as skips (would-have-fired).
    When ENABLED=True, they count as fires."""
    try:
        from . import gate_firing_log
        fires = fired if ENABLED else 0
        skips = skipped if ENABLED else (fired + skipped)
        gate_firing_log.record_firing(
            operator="Lsb", regime=regime,
            by_field={"sr": {"fires": fires, "skips": skips}},
            leads=48,
        )
    except Exception as e:
        logging.warning(f"  ⚠  gate_firing record (Lsb) failed: {redact_secrets(e)}")


def compute_override(shortwave_wm2, hour_local, cc):
    """Return (override_wm2, gate_state).

    gate_state ∈ {"applied", "middle_cc_skip", "no_shortwave", "no_hour",
                  "no_cc", "night"}.
    override_wm2 is None when gate_state != "applied".
    """
    if shortwave_wm2 is None:
        return None, "no_shortwave"
    if shortwave_wm2 < SUN_UP_THRESHOLD:
        return None, "night"
    if hour_local is None:
        return None, "no_hour"
    if cc is None:
        return None, "no_cc"
    if not _cc_gated(cc):
        return None, "middle_cc_skip"
    bias = _BIAS_BY_HOUR.get(hour_local, _OVERALL_BIAS)
    return round(shortwave_wm2 - bias, 1), "applied"


def describe_applicability():
    """Applicability descriptor for Lsb (sr sea_breeze cc-gated override).
    Returns a list of layer dicts matching applicability_map_schema.json.
    """
    if ENABLED:
        fires_when = (
            "ENABLED AND regime_synoptic == sea_breeze AND "
            f"(cc < {_CC_LO} OR cc >= {_CC_HI}) AND "
            f"shortwave_radiation >= {SUN_UP_THRESHOLD}"
        )
        current_state = (
            f"ENABLED True; overriding direct_radiation with "
            f"(shortwave_radiation − bias(hod)) in the cc-gated band."
        )
    else:
        fires_when = (
            f"OFF — would fire when ENABLED, sea_breeze regime, "
            f"(cc < {_CC_LO} OR cc >= {_CC_HI}), sun up."
        )
        current_state = "ENABLED False; no override applied."
    return [
        {
            "layer_id": "Lsb",
            "name": "sr sea_breeze cc-gated Lsr override",
            "category": "specialist",
            "fields": [
                {
                    "field": "sr",
                    "fires_when": fires_when,
                    "gated_by": "ENABLED",
                    "current_state": current_state,
                }
            ],
        }
    ]


def stamp_sr_sea_breeze_correction(weather_data):
    """Stamp per-lead override candidates + apply when ENABLED.

    Runs after stamp_solar_correction. Reads current per-lead sea_breeze
    classification via forecast-side state (regime is per-lead, matching
    the training-data axis in Stage 2).
    """
    hourly = weather_data.get("hourly") or {}
    times = hourly.get("times") or hourly.get("time") or []
    direct_arr = hourly.get("direct_radiation") or []
    sw_arr = hourly.get("shortwave_radiation") or []
    cc_arr = hourly.get("cloud_cover") or []

    derived = weather_data.get("derived") or {}
    regime_now = ((derived.get("state") or {}).get("regime_synoptic"))

    # We need per-lead regime for accuracy. The collector doesn't (today)
    # stamp per-lead regime_synoptic into hourly[], so we use current-tick
    # regime as a first approximation. TODO: swap to per-lead classification
    # when the state_stamp module gains a per-lead pass. Matches Lsr's
    # single-tick regime assumption.
    is_sea_breeze = regime_now == "sea_breeze"

    if not times or not direct_arr or not sw_arr or not cc_arr:
        weather_data["sr_sea_breeze_correction"] = {
            "applied": ENABLED,
            "regime_now": regime_now,
            "n_leads_gated": 0,
            "note": "insufficient data (missing times / direct / shortwave / cc arrays)",
        }
        _record_firing(regime_now, fired=0, skipped=0)
        return

    per_lead = []
    fired = skipped_middle_cc = 0
    for i, t_iso in enumerate(times[:48]):
        if not is_sea_breeze:
            continue
        try:
            t_utc = datetime.fromisoformat(str(t_iso).replace("Z", "+00:00"))
            if t_utc.tzinfo is None:
                t_utc = pytz.UTC.localize(t_utc)
            hour_local = t_utc.astimezone(TZ).hour
        except Exception:
            hour_local = None
        sw = sw_arr[i] if i < len(sw_arr) else None
        cc = cc_arr[i] if i < len(cc_arr) else None
        override, state = compute_override(sw, hour_local, cc)
        if state == "applied":
            per_lead.append({
                "lead_h": i,
                "hour_local": hour_local,
                "shortwave_wm2": sw,
                "cc": cc,
                "bias_wm2": round(sw - override, 1),
                "override_wm2": override,
                "was_direct_wm2": direct_arr[i] if i < len(direct_arr) else None,
            })
            fired += 1
        elif state == "middle_cc_skip":
            skipped_middle_cc += 1

    weather_data["sr_sea_breeze_correction"] = {
        "applied": ENABLED,
        "regime_now": regime_now,
        "cc_gate": {"lo": _CC_LO, "hi": _CC_HI},
        "n_leads_gated": fired,
        "n_leads_middle_cc_skip": skipped_middle_cc,
        "per_lead_active": per_lead[:24],
        "note": (
            "Stage 3 sandbox override for sr in sea_breeze regime, cc-gated. "
            "Gated OFF until 07-24 weekly Sun-morning halves re-run confirms."
            if not ENABLED
            else "sr sea_breeze cc-gated override applied to direct_radiation."
        ),
    }

    _record_firing(regime_now, fired=fired, skipped=skipped_middle_cc)

    if ENABLED and fired:
        # Preserve pre-override direct_radiation for pair log / debug diff.
        if "direct_radiation_pre_sb" not in hourly:
            hourly["direct_radiation_pre_sb"] = list(direct_arr)
        for entry in per_lead:
            lead_h = entry["lead_h"]
            if lead_h < len(direct_arr):
                direct_arr[lead_h] = entry["override_wm2"]
        hourly["direct_radiation"] = direct_arr

"""
Marine-layer cloud-cover correction (sandbox, gated OFF).

Stage 2 finding (analysis/marine_layer_stage2.py, 2026-06-21): in NE-flow
mornings (wind_dir 45-105°, hour 4-9 EDT), HRRR/GFS systematically over-call
cloud cover by +25-+38 percentage points. Effect is invisible to global
L3/L4 walk-forward (cc consistently L2-only-recommend) because it lives in
~3% of conditions, but inside the bin the bias is strong, robust to bin
perturbation (±15° wd, ±1h hour all in +20-+29 range), and steeply
lead-dependent (~0 at 0-5h → +35.5 at 24-47h).

Stage 2 also showed temporal non-stationarity (W23 +11.6 → W24 +32.5 →
W25 +38.0). Weekly Sun-morning re-reads through 07-12 will decide whether
to ship this layer. Architectural slot: sibling to L5 (regime-conditional
bias correction).

Phase 1 (this sandbox, gated OFF):
  Stamp weather_data["marine_layer_correction"] every tick with the
  per-lead candidate deltas + gate state, but do NOT modify the
  cloud_cover arrays. After 06-28 / 07-05 / 07-12 weekly re-reads confirm,
  flip ENABLED = True.

Decision rule (ship if):
  Weekly Stage-2 in-bin cc bias stays in +25 to +40 range across W26-W28.

Sign convention: bias = forecast - observed. Bias is positive (model
over-calls), so correction = -bias (subtract overprediction from forecast).
"""
import logging
from datetime import datetime, timedelta

import pytz

from ..utils import redact_secrets


def _record_mlc_firing(regime, gated_count):
    """Emit MLC firing record for the gate_firing_log. When ENABLED=False,
    every gated lead counts as a "skip" (would-have-fired). When True,
    every gated lead counts as a "fire.\""""
    try:
        from . import gate_firing_log
        fires = gated_count if ENABLED else 0
        skips = 0 if ENABLED else gated_count
        gate_firing_log.record_firing(
            operator="MLC", regime=regime,
            by_field={"cc": {"fires": fires, "skips": skips}},
            leads=48,
        )
    except Exception as e:
        logging.warning(f"  ⚠  gate_firing record (MLC) failed: {redact_secrets(e)}")


TZ = pytz.timezone("America/New_York")
ENABLED = False  # Flip after 06-28 / 07-05 / 07-12 weekly re-reads confirm.

# Gate: NE flow morning (Stage 2 baseline cell). Half-open intervals.
NE_FLOW_WD_RANGE = (45.0, 105.0)
MORNING_HOURS_RANGE = (4, 9)  # local hour, [start, end)

# Magnitude cap inherited from L5 cc cap (40%). Stage 2 max observed bias
# was +35.5 at 24-47h, comfortably under the cap.
MAX_DELTA_PCT = 40.0

# Mean signed bias (forecast - observed) by lead band, from
# analysis/marine_layer_stage2.py Q3 (2026-06-21 read, n=3,119).
# Correction = -bias (subtract over-prediction).
# 0-5h is essentially zero (-2.0) — skip; correcting noise.
_BIAS_BY_LEAD_BAND = [
    # (lead_lo, lead_hi, bias_pct)
    (6,  12, +18.8),   # 6-11h
    (12, 24, +31.8),   # 12-23h
    (24, 48, +35.5),   # 24-47h
]


def _correction_for_lead(lead_h):
    """Return -bias for the given lead hour, or 0.0 if outside the
    corrected bands (lead < 6h or lead >= 48h)."""
    for lo, hi, bias in _BIAS_BY_LEAD_BAND:
        if lo <= lead_h < hi:
            return round(-bias, 1)
    return 0.0


def _is_marine_layer_gated(wind_dir_deg, hour_local):
    """True iff the (wd, hour) cell is in the NE-flow-morning bin."""
    if wind_dir_deg is None or hour_local is None:
        return False
    wd_lo, wd_hi = NE_FLOW_WD_RANGE
    hr_lo, hr_hi = MORNING_HOURS_RANGE
    return wd_lo <= wind_dir_deg < wd_hi and hr_lo <= hour_local < hr_hi


def compute_marine_layer_correction(wind_dir_deg, hour_local, lead_h):
    """Return candidate Δ%cc to add to L1 cloud_cover forecast at this lead.

    Returns 0.0 unless the (wd, hour) gate is satisfied AND lead_h is in
    one of the corrected bands.
    """
    if not _is_marine_layer_gated(wind_dir_deg, hour_local):
        return 0.0
    delta = _correction_for_lead(lead_h)
    # Clip to safety cap.
    if delta > MAX_DELTA_PCT:
        delta = MAX_DELTA_PCT
    elif delta < -MAX_DELTA_PCT:
        delta = -MAX_DELTA_PCT
    return delta


def stamp_marine_layer_correction(weather_data):
    """Stamp candidate marine-layer correction on weather_data.

    Phase 1 (ENABLED=False): records per-lead deltas + gate state but does
    NOT modify cloud_cover. Phase 2 will walk the hourly cc array.
    """
    hourly = weather_data.get("hourly") or {}
    times = hourly.get("times") or hourly.get("time") or []
    cc_arr = hourly.get("cloud_cover") or []
    wd_arr = hourly.get("wind_direction") or hourly.get("wind_direction_10m") or []
    _regime_now = (
        (weather_data.get("derived") or {}).get("state") or {}
    ).get("regime_synoptic")
    if not times or not cc_arr:
        # Still log a zero-fire row so the rollup can distinguish "MLC
        # didn't run this tick" from "MLC ran with 0 fires."
        _record_mlc_firing(_regime_now, gated_count=0)
        return

    now_local = datetime.now(TZ)

    # Walk every forecast hour; the gate is evaluated PER-LEAD using the
    # forecast wd at that lead and the local hour at that lead. This
    # differs from L5 (uses single current-tick regime); marine layer
    # only fires in a narrow time window so we need per-hour granularity.
    per_lead = []  # list of {lead_h, delta_pct, gated}
    for lead_h, t_iso in enumerate(times[:48]):
        # Parse forecast time → local hour
        try:
            t_utc = datetime.fromisoformat(t_iso.replace("Z", "+00:00"))
            if t_utc.tzinfo is None:
                t_utc = pytz.UTC.localize(t_utc)
            t_local = t_utc.astimezone(TZ)
            hour_local = t_local.hour
        except Exception:
            hour_local = None
        wd = wd_arr[lead_h] if lead_h < len(wd_arr) else None
        delta = compute_marine_layer_correction(wd, hour_local, lead_h)
        if delta != 0.0:
            per_lead.append({
                "lead_h": lead_h,
                "delta_pct": delta,
                "hour_local": hour_local,
                "wind_dir_deg": wd,
            })

    weather_data["marine_layer_correction"] = {
        "applied": ENABLED,
        "gate": {
            "wd_range": list(NE_FLOW_WD_RANGE),
            "hour_local_range": list(MORNING_HOURS_RANGE),
        },
        "bias_table_lead_bands": [
            {"lead_lo": lo, "lead_hi": hi, "bias_pct": b, "delta_pct": -b}
            for (lo, hi, b) in _BIAS_BY_LEAD_BAND
        ],
        "n_lead_hours_gated": len(per_lead),
        "per_lead_active": per_lead[:24],  # cap the stamp size
        "note": (
            "Candidate marine-layer cc correction (Stage 3 sandbox, gated OFF). "
            "NE-flow morning over-call bias from Stage 2 (2026-06-21 read). "
            "Weekly Sun-morning re-reads through 07-12 will confirm or reject."
            if not ENABLED
            else "Marine-layer cc correction applied to cloud_cover."
        ),
    }

    # Log firing for MLC. When ENABLED=False, `len(per_lead)` is the
    # would-have-fired count → skips. When ENABLED=True, it's fires.
    _record_mlc_firing(_regime_now, gated_count=len(per_lead))

    if ENABLED:
        # When flipped, subtract bias from cloud_cover at gated lead hours.
        # Clamp result to [0, 100].
        new_cc = []
        for lead_h, v in enumerate(cc_arr[:48]):
            if v is None:
                new_cc.append(v); continue
            try:
                t_utc = datetime.fromisoformat(times[lead_h].replace("Z", "+00:00"))
                if t_utc.tzinfo is None:
                    t_utc = pytz.UTC.localize(t_utc)
                hour_local = t_utc.astimezone(TZ).hour
            except Exception:
                hour_local = None
            wd = wd_arr[lead_h] if lead_h < len(wd_arr) else None
            delta = compute_marine_layer_correction(wd, hour_local, lead_h)
            new_v = v + delta
            new_cc.append(max(0.0, min(100.0, round(new_v, 1))))
        # Preserve any tail beyond 48 leads.
        hourly["cloud_cover"] = new_cc + list(cc_arr[48:])

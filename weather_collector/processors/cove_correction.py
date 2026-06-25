"""
Wyman Cove temperature correction — candidate lookup table from R5 data.

Built from 3 days of `cove_gradient_log.json` showing the bidirectional
microclimate pattern:
  - Cove WARMS +1.5 to +2.1°F under active S/SE/SW sea breeze (peninsula-lee
    heating: marine air crosses ~2 mi of sun-heated land before reaching the
    waterfront stations).
  - Cove COOLS −3 to −5°F at 06-10 AM EDT under offshore/calm conditions
    (cool marine pool over Salem Sound persists; inland surfaces warm with
    sunrise while the cove stays anchored to the marine boundary).

Phase 1 (gated OFF): the function computes the candidate correction for
current conditions and stamps `weather_data["cove_correction"]` for the
debug page. The corrected_temperature is NOT modified. After the formal
06-19 R5 read confirms or refines the table, ENABLED can be flipped to
True and the correction starts applying.

Magnitude is tunable from a single source — this file. The pattern shape
(direction-times-state-times-hour) is the structure to validate; the
specific magnitudes will tighten as more data accumulates.
"""
from datetime import datetime

import pytz


TZ = pytz.timezone("America/New_York")
ENABLED = False  # Flip to True after 06-19 R5 read confirms the pattern.

# Octant labels in clockwise order from north.
_OCTANTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _octant(wind_dir_deg):
    if wind_dir_deg is None:
        return None
    return _OCTANTS[int((wind_dir_deg + 22.5) % 360 / 45)]


# Mean Δ(waterfront − inland) in °F per (sb_active, octant) bin, from R5
# data collected 2026-06-12 onward. Values shrunk slightly as sample size
# grew — these reflect the 3-day means with n ≥ 13 per bin (smaller bins
# left out for stability). Bins missing here fall back to 0 (no correction).
_DELTA_BY_OCTANT = {
    (True,  "S"):   +1.5,
    (True,  "SE"):  +2.0,
    (True,  "SW"):  +1.1,
    (False, "N"):   -1.0,
    (False, "NE"):  -1.0,
    (False, "E"):   -1.3,
    (False, "NW"):  -0.9,
    (False, "SE"):  +0.1,
    (False, "SW"):  +0.3,
    (False, "W"):   -0.2,
}

# Hour-of-day modulation for offshore/inactive sea breeze regime ONLY.
# Captures the morning marine-cooling trough. Active-sea-breeze hours
# are already well-represented by the constant octant value because the
# breeze itself only fires 14-18 EDT.
_HOUR_DELTA_SB_OFF = {
    0: +0.5, 1: +0.4, 2: +0.2, 3: +0.2,
    4: +0.3, 5: +0.1, 6: -0.2, 7: -0.3, 8: -0.9, 9: -1.6, 10: -2.9,
    11: -3.2, 12: -3.7, 13: -2.9, 14: -3.0,
    15: -1.9, 16: -1.6, 17: -1.1, 18: -0.3,
    19: +0.3, 20: +0.5, 21: +0.2, 22: +0.1, 23: +0.3,
}


def compute_cove_correction(wind_dir_deg, sb_active, hour_local):
    """Return candidate Δ°F to add to inland-trained forecast for the cove.

    Returns 0.0 (no correction) if inputs are missing or the bin is unrepresented.

    The blend strategy: when sb_active, use the octant value directly (the
    sea-breeze regime overrides the diurnal background). When sb_off, use
    the hour-of-day value — it dominates the octant signal because the
    morning marine pool effect is what's driving the variation.
    """
    if wind_dir_deg is None or hour_local is None:
        return 0.0
    oct_ = _octant(wind_dir_deg)
    if oct_ is None:
        return 0.0

    if sb_active:
        # Sea-breeze regime: use the constant octant value.
        return _DELTA_BY_OCTANT.get((True, oct_), 0.0)
    else:
        # Offshore/calm regime: hour-of-day dominates.
        return _HOUR_DELTA_SB_OFF.get(hour_local, 0.0)


def stamp_cove_correction(weather_data):
    """Compute the candidate cove correction for current conditions and
    stamp it on weather_data. Does NOT modify forecast arrays (Phase 1).

    When ENABLED is flipped to True, the corrected_temperature array will
    have the per-hour correction applied. For now the candidate is just
    logged for the debug page and silent validation.
    """
    current = weather_data.get("current") or {}
    sb = weather_data.get("sea_breeze") or {}

    wind_dir = current.get("wind_direction")
    sb_active = bool(sb.get("active"))
    now_local = datetime.now(TZ)
    hour_local = now_local.hour

    delta = compute_cove_correction(wind_dir, sb_active, hour_local)

    weather_data["cove_correction"] = {
        "candidate_delta_f": round(delta, 2),
        "applied": ENABLED,
        "regime": {
            "wind_dir": wind_dir,
            "wind_octant": _octant(wind_dir),
            "sb_active": sb_active,
            "hour_local": hour_local,
        },
        "note": (
            "Candidate cove-specific correction from R5 lookup. Gated OFF "
            "until 7-day R5 read on 2026-06-19 confirms the pattern."
            if not ENABLED
            else "R5 correction applied to corrected_temperature."
        ),
    }

    if ENABLED:
        hourly = weather_data.get("hourly") or {}
        ct = hourly.get("corrected_temperature")
        if isinstance(ct, list) and ct:
            # Apply the same delta to all leads — for now. A more honest
            # implementation would project the regime forward (which wind
            # octant is expected at each lead hour?) but that's noise on
            # noise without forecast wind state.
            hourly["corrected_temperature"] = [
                round(v + delta, 1) if v is not None else None
                for v in ct
            ]

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
ENABLED = False  # Shipped 2026-06-26; both branches disabled 2026-07-01 v0.6.276 (compute_cove_correction returns 0.0); top-level flag flipped 2026-07-03 so badges + applicability map + telemetry stop lying. Re-enable only after Fix B refit against L2 baseline.

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


def describe_applicability():
    """Applicability descriptor for L6 (cove microclimate correction). One field (t).
    Both branches disabled 2026-07-01 after per-row Production data exposed
    the warming branch as also net-negative. See
    weather_collector/data/applicability_map_schema.json.
    """
    if ENABLED:
        fires_when = (
            "ENABLED — but both branches return 0.0 since v0.6.276. "
            "compute_cove_correction() is a no-op; L6 has no effective firing state."
        )
        current_state = (
            "ENABLED True but no-op; both warming (sb_active S/SE/SW) and cooling "
            "(sb_off morning table) branches return 0.0. Cooling killed 2026-06-30 "
            "(v0.6.259) — L1 already cold-biased ~2.25°F, cooling doubled MAE. "
            "Warming killed 2026-07-01 (v0.6.276) — real per-row Production showed "
            "L6-fired rows at MAE 3.66 vs L2 alone 2.59 on same rows (~40% worse); "
            "L2 already weights waterfront Tempests heavily, warming Δ double-counts. "
            "Refit lookup against L2-corrected baseline (Fix B) before re-enabling."
        )
    else:
        fires_when = "OFF — no branches active"
        current_state = "ENABLED False; no cove correction applied"
    return [
        {
            "layer_id": "L6",
            "name": "Cove microclimate correction",
            "category": "specialist",
            "fields": [
                {
                    "field": "t",
                    "fires_when": fires_when,
                    "gated_by": "ENABLED",
                    "current_state": current_state,
                }
            ],
        }
    ]


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

    # BOTH BRANCHES DISABLED 2026-07-01. Cooling branch was killed 2026-06-30
    # (see block below); on 2026-07-01 the real per-row Production data (from
    # v0.6.269 applied-layer stamping + v0.6.275 retro backfill) exposed that
    # the *warming* branch is also net-negative:
    #   - T Production real = 2.91°F MAE vs L2 alone = 2.59°F (12% worse)
    #   - T Production real vs raw L1 = 2.66°F (9% worse than raw)
    #   - Math: Production = 0.7·L2 + 0.3·L6-fired → L6-fired MAE ≈ 3.66°F
    #     vs L2 alone at 2.59°F on the same rows. Warming branch is ~40%
    #     worse than L2 on the rows where it fires.
    # Root cause matches the original double-counting hypothesis for the
    # warming case too: L2's Kalman blend for T is dominated by waterfront
    # Tempests (Willow Rd, Neptune Rd) at ~0.1-0.2 mi from the cove — L2
    # already carries "waterfront bias" by station weighting. Adding a
    # (waterfront - inland) warming Δ on top double-counts the same signal.
    # analysis/production_whatif.py preview: disabling warming branch flips
    # T Production from +9.7% BAD to -2.6% GOOD (12.3 pp improvement).
    # Re-enable only after refitting the lookup against L2-corrected baseline
    # (Fix B in project_l6_l2_double_counting_hypothesis).
    return 0.0
    # ----- retained for context (both branches now return 0.0 above) -----
    if sb_active:
        # Sea-breeze regime: use the constant octant value.
        return _DELTA_BY_OCTANT.get((True, oct_), 0.0)
    else:
        # Offshore/calm regime DISABLED 2026-06-30. Diagnostic in
        # analysis/l6_l2_double_counting.py showed L1 is already cold-biased
        # ~2.25 °F at the cove and L2 only erases ~3.7% of that. Applying
        # the morning offshore cooling Δ on top doubled MAE on cooling rows
        # (Δ ≤ -2 °F bucket: MAE 3.52 → 6.16, -74.9%). The sb_active
        # warming branch was retained here originally; killed 2026-07-01
        # after real per-row Production data exposed the same over-count.
        return 0.0


def _sb_active_forecast(hour_local, wind_dir_deg):
    """Heuristic forecast of sb_active at a future hour.

    The live sb detector reads wind speed, temperature gradient, and other
    fields we don't have for forecast hours — only forecast wind direction.
    Proxy: sea breeze typically fires 13–18 EDT with S-half wind direction
    (SE / S / SW). Off otherwise. Coarser than the live detector but adequate
    for projecting the regime forward to label which lookup branch each
    forecast lead should use.
    """
    if hour_local is None or wind_dir_deg is None:
        return False
    if not (13 <= hour_local <= 18):
        return False
    return _octant(wind_dir_deg) in {"S", "SE", "SW"}


def stamp_cove_correction(weather_data):
    """Stamp `weather_data["cove_correction"]` with the current regime + Δ,
    and when ENABLED apply a per-lead Δ°F to corrected_temperature.

    Per-lead application (v0.6.237+): each forecast lead is corrected with
    the Δ°F appropriate to *that* lead's projected regime (forecast wind
    direction + hour-of-day + heuristic sb_active), not the current-tick Δ
    applied uniformly across all 48 leads. The old single-Δ behavior was
    wrong by 3–5 °F at distant leads when the regime swing in the lookup
    tables crossed zero (e.g. applying a noon −3.7 °F to a midnight lead).
    """
    current = weather_data.get("current") or {}
    sb = weather_data.get("sea_breeze") or {}
    hourly = weather_data.get("hourly") or {}

    # Current-tick regime — used for the candidate stamp (what's being applied
    # to the displayed "now" temperature).
    wind_dir = current.get("wind_direction")
    sb_active = bool(sb.get("active"))
    now_local = datetime.now(TZ)
    hour_local = now_local.hour
    delta = compute_cove_correction(wind_dir, sb_active, hour_local)

    # Per-lead Δ°F array, parallel to hourly["corrected_temperature"].
    # Falls back to the current-tick Δ for leads where forecast wind dir or
    # timestamp is missing.
    times = hourly.get("times") or []
    fc_wind_dir = hourly.get("wind_direction") or []
    per_lead_deltas = []
    for i, t in enumerate(times):
        try:
            h_i = int(str(t)[11:13])
        except (TypeError, ValueError, IndexError):
            h_i = hour_local
        wd_i = fc_wind_dir[i] if i < len(fc_wind_dir) and fc_wind_dir[i] is not None else wind_dir
        sb_i = _sb_active_forecast(h_i, wd_i)
        per_lead_deltas.append(compute_cove_correction(wd_i, sb_i, h_i))

    summary = {}
    if per_lead_deltas:
        summary = {
            "min":  round(min(per_lead_deltas), 2),
            "max":  round(max(per_lead_deltas), 2),
            "mean": round(sum(per_lead_deltas) / len(per_lead_deltas), 2),
        }

    weather_data["cove_correction"] = {
        "candidate_delta_f": round(delta, 2),
        "applied": ENABLED,
        "regime": {
            "wind_dir": wind_dir,
            "wind_octant": _octant(wind_dir),
            "sb_active": sb_active,
            "hour_local": hour_local,
        },
        "per_lead_delta_summary": summary,
        "note": (
            "Candidate cove correction from R5 lookup; gated OFF."
            if not ENABLED
            else "L6 cove correction applied per-lead to corrected_temperature."
        ),
    }

    if ENABLED:
        ct = hourly.get("corrected_temperature")
        if isinstance(ct, list) and ct:
            # Snapshot the pre-cove L4 array so the per-layer accuracy chart
            # can isolate L4 vs (L4+L6) for temperature. forecast_snapshot.py
            # reads this as the l4 layer; the post-cove array (assigned just
            # below) is captured as l6.
            hourly["corrected_temperature_post_l4"] = list(ct)
            n = min(len(ct), len(per_lead_deltas))
            new_ct = [
                round(ct[i] + per_lead_deltas[i], 1) if ct[i] is not None else None
                for i in range(n)
            ]
            # Preserve any trailing leads beyond what we had forecast wind for
            # by leaving them at L4 (no L6 contribution).
            if len(ct) > n:
                new_ct.extend(ct[n:])
            hourly["corrected_temperature"] = new_ct

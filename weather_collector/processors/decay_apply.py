"""
Piece 4 of the decay model: apply fitted per-(field, lead_h) corrections
to the user-facing hourly arrays. Reduces the lead-time-dependent residual
error (the part the existing flat bias correction can't address by design —
bias correction handles "model is off right now", decay correction handles
"model gets worse further out").

Runs once per tick from collector.main() AFTER trim_hourly_to_current_hour,
so hourly array index i corresponds directly to lead_h = i. Runs AFTER the
forecast snapshot has been logged inside build_weather_data, so the
snapshot continues to measure pre-decay residual — keeps the fitted
corrections from shrinking to zero across iterations.

Safe no-op if decay_corrections.json is missing, malformed, or stale
(>STALE_DAYS old). Sanity caps prevent a pathological future fit from
blowing up the forecast.

After mutating corrected_temperature, corrected_humidity, corrected_dew_point,
wind_speed, wind_gusts, and precipitation_probability, recomputes the
derived corrected_apparent_temperature and corrected_absolute_humidity
arrays so they stay consistent with the now-corrected base values.
"""
import logging
import math
from datetime import datetime, timedelta

import pytz

from ..gcs_io import load_json
from ..utils import steadman_feels_like_f


CORRECTIONS_PATH = "decay_corrections.json"
TZ = pytz.timezone("America/New_York")
STALE_DAYS = 7

# Sanity caps on |correction| per field in each field's native units. A
# pathological fit cannot move the forecast more than this regardless of
# what decay_corrections.json says.
CAPS = {
    "t":  5.0,   # °F
    "dp": 5.0,   # °F
    "h":  20.0,  # %
    "ws": 10.0,  # mph
    "wg": 15.0,  # mph
    "pp": 25.0,  # %
}

# Fitter short keys → which hourly array to mutate.
TARGET_ARRAY = {
    "t":  "corrected_temperature",
    "dp": "corrected_dew_point",
    "h":  "corrected_humidity",
    "ws": "wind_speed",
    "wg": "wind_gusts",
    "pp": "precipitation_probability",
}

# Per-field display rounding to match what the rest of the pipeline writes.
ROUND_DIGITS = {"t": 1, "dp": 1, "h": 1, "ws": 1, "wg": 1, "pp": 0}

# POP gets piecewise-linear correction scaling instead of flat additive (since
# v0.6.5). Flat additive over-inflates clearly-clear-sky hours: a fitted POP
# correction of -12% would push raw_model=0 to corrected=12, claiming a 12%
# rain chance during obviously dry weather. The scaling is:
#     applied(R) = POP_NOISE_FLOOR + (raw_correction − POP_NOISE_FLOOR) × R/100
# At R=0%   →  applied ≈ POP_NOISE_FLOOR (negligible bump, stays near 0).
# At R=50%  →  half the correction kicks in.
# At R=100% →  full correction applies.
# T=2% is a small "noise floor" that admits we don't know nothing without
# forcing meaningful POP onto clearly-clear-sky hours. Other fields keep
# the flat additive correction (temp/humidity/wind have no analogous
# zero-floor problem).
POP_NOISE_FLOOR = 2.0


def _parse_local(stamp):
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M")


def _absolute_humidity(t_f, dp_f):
    if t_f is None or dp_f is None:
        return None
    t_c = (t_f - 32) * 5 / 9
    dp_c = (dp_f - 32) * 5 / 9
    e = 6.112 * math.exp((17.67 * dp_c) / (dp_c + 243.5))
    return round((e * 216.7) / (t_c + 273.15), 1)


def apply_decay_corrections(weather_data):
    """Subtract per-(field, lead_h) mean error from each hourly forecast
    array. Mutates weather_data["hourly"] in place. Recomputes derived
    arrays. Safe no-op on missing, malformed, or stale corrections."""
    hourly = weather_data.get("hourly")
    if not isinstance(hourly, dict):
        return

    corr_doc = load_json(CORRECTIONS_PATH, default=None)
    if not corr_doc:
        logging.info("  ℹ  Decay apply: no decay_corrections.json — skipping")
        return

    fitted_at = corr_doc.get("fitted_at")
    if fitted_at:
        try:
            fitted_dt = _parse_local(fitted_at)
            now_local = datetime.now(TZ).replace(tzinfo=None)
            if (now_local - fitted_dt) > timedelta(days=STALE_DAYS):
                logging.warning(f"  ⚠  Decay apply: corrections stale (fitted {fitted_at}) — skipping")
                return
        except (ValueError, TypeError):
            pass

    corrections = corr_doc.get("corrections", {})
    if not isinstance(corrections, dict):
        logging.warning("  ⚠  Decay apply: corrections malformed — skipping")
        return

    # Preserve raw POP before the per-field loop mutates it. (temp/humidity
    # have separate corrected_* arrays so their raw arrays already survive;
    # wind/gust raw is captured upstream in blend_observed_into_hourly.)
    if "precipitation_probability" in hourly and "raw_precipitation_probability" not in hourly:
        hourly["raw_precipitation_probability"] = list(hourly["precipitation_probability"])

    applied = 0
    capped = 0
    for short, array_name in TARGET_ARRAY.items():
        arr = hourly.get(array_name)
        if not isinstance(arr, list):
            continue
        per_lead = corrections.get(short, [])
        if not isinstance(per_lead, list):
            continue
        cap = CAPS.get(short, float("inf"))
        digits = ROUND_DIGITS.get(short, 1)
        for h in range(min(len(arr), len(per_lead))):
            val = arr[h]
            c = per_lead[h]
            if val is None or c is None:
                continue
            try:
                c = float(c)
            except (TypeError, ValueError):
                continue
            # POP: piecewise-linear scaling so clear-sky (R=0) hours don't get
            # inflated by the full mean residual. Other fields: flat additive.
            if short == "pp":
                r_frac = max(0.0, min(1.0, float(val) / 100.0))
                applied_c = POP_NOISE_FLOOR + (c - POP_NOISE_FLOOR) * r_frac
            else:
                applied_c = c
            if abs(applied_c) > cap:
                capped += 1
                applied_c = cap if applied_c > 0 else -cap
            result = val - applied_c
            # Clamp POP to [0, 100]; other fields have no hard bounds here.
            if short == "pp":
                result = max(0.0, min(100.0, result))
            arr[h] = round(result, digits)
            applied += 1

    # Recompute derived arrays so they stay consistent with the corrected
    # base arrays. apparent_temp depends on temp/humidity/wind/radiation;
    # absolute_humidity depends on temp/dew_point.
    ct = hourly.get("corrected_temperature", [])
    ch = hourly.get("corrected_humidity", [])
    cdp = hourly.get("corrected_dew_point", [])
    ws = hourly.get("wind_speed", [])
    dr = hourly.get("direct_radiation", [])

    if "corrected_apparent_temperature" in hourly and ct:
        new_at = []
        for i in range(len(ct)):
            t = ct[i] if i < len(ct) else None
            h = ch[i] if i < len(ch) else None
            w = ws[i] if i < len(ws) else None
            d = dr[i] if i < len(dr) else None
            new_at.append(steadman_feels_like_f(t, h, w, d))
        hourly["corrected_apparent_temperature"] = new_at

    if "corrected_absolute_humidity" in hourly and ct:
        new_ah = []
        for i in range(len(ct)):
            t = ct[i] if i < len(ct) else None
            d = cdp[i] if i < len(cdp) else None
            new_ah.append(_absolute_humidity(t, d))
        hourly["corrected_absolute_humidity"] = new_ah

    if applied:
        msg = f"  ✓ Decay apply: {applied} hourly cells corrected"
        if capped:
            msg += f" ({capped} capped at sanity bound)"
        logging.info(msg)

    # Per-field correction value at lead +24h — the most actionable
    # "tomorrow's forecast got adjusted by" number for the Corrections card.
    # Already capped to match what Apply actually did.
    per_field_24h = {}
    LEAD_24H = 24
    for short in TARGET_ARRAY:
        per_lead = corrections.get(short, [])
        if not isinstance(per_lead, list) or len(per_lead) <= LEAD_24H:
            continue
        c = per_lead[LEAD_24H]
        if c is None:
            continue
        try:
            c = float(c)
        except (TypeError, ValueError):
            continue
        cap = CAPS.get(short, float("inf"))
        if abs(c) > cap:
            c = cap if c > 0 else -cap
        per_field_24h[short] = round(c, 2)

    # Stamp the payload so the debug page (and anything else) can tell
    # which weather_data ticks actually had decay corrections applied.
    weather_data["decay_meta"] = {
        "fitted_at": fitted_at,
        "applied_at": datetime.now(TZ).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M"),
        "cells_corrected": applied,
        "cells_capped": capped,
        "per_field_24h": per_field_24h,
    }

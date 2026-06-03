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
DIURNAL_CORRECTIONS_PATH = "diurnal_corrections.json"
TZ = pytz.timezone("America/New_York")
STALE_DAYS = 7

# Sanity caps on |correction| per field in each field's native units. A
# pathological fit cannot move the forecast more than this regardless of
# what decay_corrections.json says.
CAPS = {
    "t":  5.0,    # °F
    "dp": 5.0,    # °F
    "h":  20.0,   # %
    "ws": 10.0,   # mph
    "wg": 15.0,   # mph
    "pp": 25.0,   # %
    "pr": 0.30,   # inHg (typical synoptic-scale pressure swing in a few hours; cap protects against fitter wackiness)
    "cc": 40.0,   # % (cloud cover varies hugely; cap prevents pathological corrections from flipping clear↔overcast)
    "sr": 300.0,  # W/m² (solar varies wildly with sun angle + clouds; cap prevents pathological diurnal interactions)
    "pa": 0.20,   # in/hr (rain rates are noisy and sparse — strict cap to prevent dry/wet flip pathology)
    "cl": 40.0,   # % low cloud
    "cm": 40.0,   # % mid cloud
    "ch": 40.0,   # % high cloud
}

# Fitter short keys → which hourly array to mutate.
TARGET_ARRAY = {
    "t":  "corrected_temperature",
    "dp": "corrected_dew_point",
    "h":  "corrected_humidity",
    "ws": "wind_speed",
    "wg": "wind_gusts",
    "pp": "precipitation_probability",
    "pr": "corrected_pressure_in",
    "cc": "cloud_cover",
    "sr": "direct_radiation",
    "pa": "precipitation",
    "cl": "cloud_cover_low",
    "cm": "cloud_cover_mid",
    "ch": "cloud_cover_high",
}

# Per-field display rounding to match what the rest of the pipeline writes.
ROUND_DIGITS = {"t": 1, "dp": 1, "h": 1, "ws": 1, "wg": 1, "pp": 0, "pr": 3, "cc": 0,
                "sr": 0, "pa": 3, "cl": 0, "cm": 0, "ch": 0}

# Physical bounds on the corrected forecast value per field. Without these,
# a large negative-sign correction at low raw values can push results below
# physically possible (e.g. wind gust = 3 mph + correction = -12 mph → -9 mph).
# Tuple is (floor, ceiling); None means unbounded on that side. Temperature
# and dew point intentionally have no floor — negative °F is valid.
FIELD_BOUNDS = {
    "ws": (0.0, None),
    "wg": (0.0, None),
    "h":  (0.0, 100.0),
    "pp": (0.0, 100.0),
    "pr": (25.0, 32.0),  # realistic Earth-surface inHg range; absurd Fitter outputs get clamped
    "cc": (0.0, 100.0),
    "sr": (0.0, 1400.0),  # peak solar at this latitude ~1100 W/m² noon-summer
    "pa": (0.0, 5.0),     # in/hr — even extreme tropical rain rates rarely exceed this
    "cl": (0.0, 100.0),
    "cm": (0.0, 100.0),
    "ch": (0.0, 100.0),
}

# POP reverted to flat additive correction in v0.6.20 after offline Brier-score
# analysis (analysis/pop_calibration.py) showed the piecewise-scaled approach
# (v0.6.5–v0.6.19) was barely better than no correction at all:
#     RAW MODEL       Brier 782.8
#     PIECEWISE SCALED Brier 768.9  (v0.6.5–v0.6.19)
#     FLAT ADDITIVE   Brier 745.4  ← reverted to this
# The "inflates clear-sky hours" concern that drove the piecewise approach
# turned out to be over-cautious — the [0, 100] clamp in FIELD_BOUNDS already
# prevents pathological inflation, and the per-lead corrections shrink toward
# zero where the model is reliable. POP now uses the same simple additive
# correction as every other field.


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
    # Same for cloud_cover — mutated in place by the per-field loop below
    if "cloud_cover" in hourly and "raw_cloud_cover" not in hourly:
        hourly["raw_cloud_cover"] = list(hourly["cloud_cover"])
    # v0.6.26: preserve raw copies of newly-added correction fields before mutation
    for src, dst in [
        ("direct_radiation",   "raw_direct_radiation"),
        ("precipitation",      "raw_precipitation"),
        ("cloud_cover_low",    "raw_cloud_cover_low"),
        ("cloud_cover_mid",    "raw_cloud_cover_mid"),
        ("cloud_cover_high",   "raw_cloud_cover_high"),
        ("wind_direction",     "raw_wind_direction"),  # v0.6.27 circular correction
    ]:
        if src in hourly and dst not in hourly:
            hourly[dst] = list(hourly[src])

    # v0.6.27 wind direction circular correction (Layer 3 only).
    # Per-lead sin/cos component corrections fitted by decay_fit; apply via
    # atan2 of the corrected (sin, cos) pair back to degrees [0, 360).
    # Sanity cap on |sin/cos| correction to limit max angular shift (≈ asin(0.3)
    # ≈ 17° single-axis, ~24° max combined). Without this an overfit lead-N
    # correction from 1-2 pairs can flip the wind direction 170°. Pairs
    # accumulate; cap stays in place to bound any future drift.
    WD_COMPONENT_CAP = 0.30
    wd_components = corrections.get("wd_components") or {}
    wd_sin_corr = wd_components.get("sin") or []
    wd_cos_corr = wd_components.get("cos") or []
    wd_arr = hourly.get("wind_direction")
    if isinstance(wd_arr, list) and wd_sin_corr and wd_cos_corr:
        wd_applied = 0
        wd_capped = 0
        for h in range(min(len(wd_arr), len(wd_sin_corr), len(wd_cos_corr))):
            v = wd_arr[h]
            s_corr = wd_sin_corr[h]
            c_corr = wd_cos_corr[h]
            if v is None or s_corr is None or c_corr is None:
                continue
            try:
                v_f = float(v); s = float(s_corr); c = float(c_corr)
            except (TypeError, ValueError):
                continue
            # Cap sin and cos corrections independently
            if abs(s) > WD_COMPONENT_CAP:
                wd_capped += 1
                s = WD_COMPONENT_CAP if s > 0 else -WD_COMPONENT_CAP
            if abs(c) > WD_COMPONENT_CAP:
                wd_capped += 1
                c = WD_COMPONENT_CAP if c > 0 else -WD_COMPONENT_CAP
            v_rad = math.radians(v_f)
            new_sin = math.sin(v_rad) - s
            new_cos = math.cos(v_rad) - c
            if abs(new_sin) < 1e-9 and abs(new_cos) < 1e-9:
                continue
            new_deg = (math.degrees(math.atan2(new_sin, new_cos)) + 360.0) % 360.0
            wd_arr[h] = round(new_deg)
            wd_applied += 1
        if wd_applied:
            cap_note = f" ({wd_capped} sin/cos values capped)" if wd_capped else ""
            logging.info(f"  ✓ Wind dir circular fit applied to {wd_applied} hourly cells{cap_note}")

    # v0.6.25: snapshot the post-Layer-2 state (= what corrected_hourly built,
    # before any forecast-time correction). This is the L2 layer's output —
    # needed downstream so the per-layer MAE accuracy section can compute
    # "what the forecast looked like after mesonet, before decay" per pair.
    for short, array_name in TARGET_ARRAY.items():
        arr = hourly.get(array_name)
        if isinstance(arr, list):
            hourly[f"{array_name}_post_l2"] = list(arr)

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
            applied_c = c
            if abs(applied_c) > cap:
                capped += 1
                applied_c = cap if applied_c > 0 else -cap
            result = val - applied_c
            # Physical bounds per field (wind ≥ 0, humidity/POP in [0,100]).
            lo, hi = FIELD_BOUNDS.get(short, (None, None))
            if lo is not None and result < lo:
                result = lo
            if hi is not None and result > hi:
                result = hi
            arr[h] = round(result, digits)
            applied += 1

    # v0.6.25: snapshot post-Layer-3 (= after decay, before diurnal) for the
    # per-layer MAE accuracy table. Each layer's output captured = (raw → L2 →
    # L3 → L4 final) so the Fitter can compare per-pair errors at each stage.
    for short, array_name in TARGET_ARRAY.items():
        arr = hourly.get(array_name)
        if isinstance(arr, list):
            hourly[f"{array_name}_post_l3"] = list(arr)

    # ── Layer 5: diurnal (hour-of-day) correction ────────────────────────────
    # Applied AFTER Layer 4 decay correction. For each forecast hour, look up
    # the per-(field, hour_of_day) correction from diurnal_corrections.json
    # and subtract it from the corresponding hourly array slot. Same sanity
    # caps and physical bounds as Layer 4. Graceful no-op if the diurnal
    # corrections file is missing, malformed, or stale.
    diurnal_applied = 0
    diurnal_capped = 0
    diurnal_doc = load_json(DIURNAL_CORRECTIONS_PATH, default=None)
    diurnal_fitted_at = None
    diurnal_corrections = None
    if diurnal_doc:
        diurnal_fitted_at = diurnal_doc.get("fitted_at")
        if diurnal_fitted_at:
            try:
                fdt = _parse_local(diurnal_fitted_at)
                now_local = datetime.now(TZ).replace(tzinfo=None)
                if (now_local - fdt) > timedelta(days=STALE_DAYS):
                    logging.warning(f"  ⚠  Diurnal apply: stale (fitted {diurnal_fitted_at}) — skipping")
                    diurnal_doc = None
            except (ValueError, TypeError):
                pass
    if diurnal_doc:
        diurnal_corrections = diurnal_doc.get("corrections_by_hour", {})
        if not isinstance(diurnal_corrections, dict):
            diurnal_corrections = None
    times = hourly.get("times", []) if diurnal_corrections else []
    if diurnal_corrections and times:
        for short, array_name in TARGET_ARRAY.items():
            arr = hourly.get(array_name)
            if not isinstance(arr, list):
                continue
            per_hour = diurnal_corrections.get(short, [])
            if not isinstance(per_hour, list) or len(per_hour) < 24:
                continue
            cap = CAPS.get(short, float("inf"))
            digits = ROUND_DIGITS.get(short, 1)
            lo, hi = FIELD_BOUNDS.get(short, (None, None))
            for h in range(min(len(arr), len(times))):
                val = arr[h]
                ts = times[h]
                if val is None or not isinstance(ts, str) or len(ts) < 13:
                    continue
                try:
                    hod = int(ts[11:13])
                except (ValueError, IndexError):
                    continue
                if not (0 <= hod < 24):
                    continue
                c = per_hour[hod]
                if c is None:
                    continue
                try:
                    c = float(c)
                except (TypeError, ValueError):
                    continue
                if abs(c) > cap:
                    diurnal_capped += 1
                    c = cap if c > 0 else -cap
                result = val - c
                if lo is not None and result < lo:
                    result = lo
                if hi is not None and result > hi:
                    result = hi
                arr[h] = round(result, digits)
                diurnal_applied += 1
        if diurnal_applied:
            msg = f"  ✓ Diurnal apply: {diurnal_applied} hourly cells corrected"
            if diurnal_capped:
                msg += f" ({diurnal_capped} capped at sanity bound)"
            logging.info(msg)

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
        "diurnal_fitted_at": diurnal_fitted_at,
        "diurnal_cells_corrected": diurnal_applied,
        "diurnal_cells_capped": diurnal_capped,
    }

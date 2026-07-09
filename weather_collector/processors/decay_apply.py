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

After mutating corrected_temperature, corrected_dew_point, wind_speed,
wind_gusts, precipitation_probability, and others, recomputes the derived
corrected_humidity (Magnus from corrected T + T_d), corrected_apparent_temperature
(Steadman from corrected T, derived RH, wind, radiation), and
corrected_absolute_humidity (from corrected T + T_d) so the full moisture
state ships as one internally consistent (T, T_d, RH, AH) triple. The
independent L2/L3/L4 corrections on humidity still run as background and
appear in the per-layer pair-log entries — they're retained for comparison
but the user-facing humidity is the derived value.
"""
import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta

import pytz

from ..gcs_io import load_json
from ..utils import steadman_feels_like_f
from . import gate_firing_log


CORRECTIONS_PATH = "decay_corrections.json"
DIURNAL_CORRECTIONS_PATH = "diurnal_corrections.json"
TZ = pytz.timezone("America/New_York")
STALE_DAYS = 7

# v0.6.45: per-field L3/L4 whitelist (Phase 0 of the L3/L4 audit). Held-out
# MAE table on time_series_diagnostic showed L3/L4 net-negative on
# temp/humidity/dp/solar/clouds-low/precip/pressure but clearly positive on
# wind speed, gusts, and high cloud (and marginal on mid cloud). Enable per
# field only where the audit data justifies it; everything else stays paused.
# Snapshots (_post_l2, _post_l3) still happen for every field so the per-layer
# MAE diagnostic continues to publish — disabled fields show L3 = L2 and
# L4 = L3 by construction.
#
# v0.6.49: POP ("pp") re-added — the v0.6.45 audit measured by MAE, which is
# the wrong yardstick for a probabilistic forecast. The original v0.6.20 work
# (`analysis/pop_calibration.py`) showed flat-additive POP correction cuts
# Brier from 783 → 745 (5% improvement). The MAE-based audit was correctly
# flagging that L3 hurts MAE on POP, but that's the *price* of better Brier
# calibration, not a regression. POP is evaluated by Brier, not MAE — frontend
# audit table flags pp as Brier-evaluated and suppresses the ⚠ rule for it.
# L3_FIELDS / L4_FIELDS are deliberate WHITELISTS — fields earn their way in
# via held-out validation (walk-forward validator). The fitter still fits
# everything (including wd sin/cos components) so the evidence exists to
# enable a field later; corrections for non-whitelisted fields are computed
# but never applied. wd being fitted-but-not-applied is by design, not a bug.
# v0.6.111: cm removed from L3. Both methods that decide L3 membership agreed:
# walk-forward validator (re-run 2026-06-15) recommended dropping cm; B1
# backtest sweep (2026-06-16, 173k pairs over 2 days) confirmed cm out of L3
# improves cloud-mid MAE by 3.8%. Two independent reads on different held-out
# windows is the rule for shipping a whitelist change.
# v0.6.213: cc added to L4. h_cloud_l4_sim.py 70/30 train/test simulation
# returned cc +5.0% MAE improvement on 2026-06-22 AND 2026-06-24 reads
# (06-23 dipped to +2.7% — a 1-day artifact). Two reads >=3% with one read
# >=5% clears the 2-read promotion gate. cm rides along at +3.0% on 06-24
# (was +2.7% on 06-23) — borderline; reconfirm 06-29 before adding.
L3_FIELDS = {"ws", "wg", "ch", "cm"}  # pp dropped 2026-07-04 v0.6.304 after audit reconciliation: Fitter Brier l1=0.0734→l3=0.0765 (WORSE +4.2%), production_whatif +87.3% WORSE, h_regime_l3 pp sea_breeze L3 LOSES -96%, walkforward has never included pp in L3_FIELDS across 13 daily reads. The "pp L3 Brier +8.0% gain" claim on the debug page was a hallucinated number I codified earlier today; no analysis output supports it. This drop is reverting a decision that was based on that number. ws + wg strip candidacy queued but NOT shipped — earliest ship 2026-07-10 if the picture holds.
L4_FIELDS = {"ch", "cc"}
# Fields where the L3/L4 audit's MAE-based ⚠ rule should be suppressed because
# the field's correction is justified by a different metric (Brier, etc.).
L3_BRIER_FIELDS = {"pp"}

# Skip table — per-(field, layer, regime, lead_band) rules for skipping a
# correction that's shipped at the field level but hurts on specific regime
# cells. Populated 2026-07-02 v0.6.279 from l3_regime_lead_analysis (694K
# L3-field pair rows) and l4_regime_lead_analysis (dp analysis added
# 2026-06-30). Each entry: (regime_name, lead_lo, lead_hi) — skip the
# correction when state_fc.regime_synoptic matches AND lead_lo <= lead_h < lead_hi.
# lead_hi = 48 means "all bands." Fail-safe: if regime is None (missing
# classifier output), we apply normally rather than over-skipping.
#
# 2026-07-02 cells:
#   ws L3 — regime cross-cut showed L3 wins in calm/frontal/pre_frontal but
#     LOSES catastrophically in ne_flow (all 4 bands, -5% to -9%) and
#     short-lead sea_breeze (-9.5% to -15.2%). Skip these cells.
#   dp L4 — 15 L4 LOSES cells across ne_flow (all bands, -10% to -19%),
#     sea_breeze (all bands, -4.5% to -18.5%), nw_flow short leads
#     (-20.2% at 0-5h, -7.9% at 6-11h). Skip these too. Note: dp is not
#     currently in L4_FIELDS at all, so the skip cells for dp only matter
#     if dp is later added — architectural placeholder for that day.
#
# See feedback memory: feedback_calm_gate_wrong_intervention for the
# earlier failed attempt (fc_ws<3 threshold gate — was skipping L3 in the
# calm regime where L3 wins biggest).
SKIP_TABLE = {
    ("ws", "l3"): [
        ("ne_flow",    0, 48),   # all bands, n=1.0K-4.1K, -5% to -9%
        ("sea_breeze", 0, 12),   # 0-11h only, n=966+918, -9.5% / -15.2%
    ],
    ("dp", "l4"): [
        ("ne_flow",    0, 48),
        ("sea_breeze", 0, 48),
        ("nw_flow",    0, 12),
    ],
}


def _should_skip(field, layer, regime, lead_h):
    """Return True if the (field, layer) skip table has a cell matching this
    (regime, lead_h). Fail-safe: unknown regime → apply normally."""
    if regime is None or lead_h is None:
        return False
    cells = SKIP_TABLE.get((field, layer))
    if not cells:
        return False
    for r, lo, hi in cells:
        if r == regime and lo <= lead_h < hi:
            return True
    return False

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


def describe_applicability():
    """Return applicability descriptors for the L3 and L4 layers this module
    applies. Collector concatenates output across all correction modules into
    weather_data['applicability_map']['layers'] each tick; the debug page
    renders Section D from the full union and per-layer slices by filtering
    on layer_id. Schema example: weather_collector/data/applicability_map_schema.json.
    """
    def _fires_when_with_skip(field, layer):
        cells = SKIP_TABLE.get((field, layer)) or []
        base = f"L{layer[-1]}_FIELDS contains {field}"
        if not cells:
            return f"{base} (always, at every lead)"
        parts = []
        for r, lo, hi in cells:
            if hi >= 48:
                parts.append(f"{r} (all bands)")
            else:
                parts.append(f"{r} ({lo}-{hi-1}h)")
        return f"{base} EXCEPT skip when regime + lead ∈ {{ " + ", ".join(parts) + " }"

    l3_fields = [
        {"field": f, "fires_when": _fires_when_with_skip(f, "l3")}
        for f in sorted(L3_FIELDS)
    ]

    l4_fields = [
        {"field": f, "fires_when": _fires_when_with_skip(f, "l4")}
        for f in sorted(L4_FIELDS)
    ]

    return [
        {
            "layer_id": "L3",
            "name": "Lead-decay correction",
            "category": "general-purpose",
            "fields": l3_fields,
        },
        {
            "layer_id": "L4",
            "name": "Diurnal correction",
            "category": "general-purpose",
            "fields": l4_fields,
        },
    ]


def _parse_local(stamp):
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M")


def _absolute_humidity(t_f, dp_f):
    if t_f is None or dp_f is None:
        return None
    t_c = (t_f - 32) * 5 / 9
    dp_c = (dp_f - 32) * 5 / 9
    e = 6.112 * math.exp((17.67 * dp_c) / (dp_c + 243.5))
    return round((e * 216.7) / (t_c + 273.15), 1)


def _relative_humidity(t_f, dp_f):
    """Magnus formula: RH = 100 × e(T_d) / e_s(T). Inputs in °F. Returns RH
    in [0, 100] or None on bad input. dp > t (unphysical) clamps to 100."""
    if t_f is None or dp_f is None:
        return None
    if dp_f >= t_f:
        return 100.0
    t_c = (t_f - 32) * 5 / 9
    dp_c = (dp_f - 32) * 5 / 9
    a, b = 17.625, 243.04
    e_s = math.exp(a * t_c / (t_c + b))
    e   = math.exp(a * dp_c / (dp_c + b))
    return max(0.0, min(100.0, 100.0 * e / e_s))


def preserve_raw_forecast_arrays(weather_data):
    """Preserve raw HRRR/GFS forecast arrays as `raw_*` copies BEFORE any
    correction layer runs. Called from the collector early in the pipeline
    (before stamp_solar_correction, apply_decay_corrections, stamp_cove_correction).

    Idempotent — guarded by `dst not in hourly`, so calling it multiple times
    (from decay_apply as well as the collector) has no effect after the first
    call. This is a bugfix landed 2026-07-02 v0.6.285: previously the
    preservation lived only inside apply_decay_corrections, which runs AFTER
    stamp_solar_correction — so raw_direct_radiation captured post-L5 values,
    not raw HRRR. Debug page's "Raw model" line for sr was showing L5-corrected
    values as a result. User-facing forecasts were unaffected (direct_radiation
    is post-L5 by design); only diagnostics were wrong.
    """
    hourly = weather_data.get("hourly") or {}
    if not hourly:
        return
    if "precipitation_probability" in hourly and "raw_precipitation_probability" not in hourly:
        hourly["raw_precipitation_probability"] = list(hourly["precipitation_probability"])
    if "cloud_cover" in hourly and "raw_cloud_cover" not in hourly:
        hourly["raw_cloud_cover"] = list(hourly["cloud_cover"])
    for src, dst in [
        ("direct_radiation",   "raw_direct_radiation"),
        ("precipitation",      "raw_precipitation"),
        ("cloud_cover_low",    "raw_cloud_cover_low"),
        ("cloud_cover_mid",    "raw_cloud_cover_mid"),
        ("cloud_cover_high",   "raw_cloud_cover_high"),
        ("wind_direction",     "raw_wind_direction"),
    ]:
        if src in hourly and dst not in hourly:
            hourly[dst] = list(hourly[src])


def recompute_derived_moisture_arrays(weather_data):
    """Derive corrected_humidity from corrected (T, T_d) via Magnus, then
    recompute corrected_apparent_temperature and corrected_absolute_humidity
    from the now-consistent base arrays. Idempotent and safe to call multiple
    times. Called both at the end of apply_decay_corrections (fresh-data path)
    and from collector.main() after apply_stale_fallbacks (cached-data path)
    so the (T, T_d, RH, AH) quadruple stays consistent regardless of which
    path produced the hourly arrays."""
    hourly = weather_data.get("hourly") if isinstance(weather_data, dict) else None
    if not isinstance(hourly, dict):
        return
    ct  = hourly.get("corrected_temperature", [])
    cdp = hourly.get("corrected_dew_point", [])
    ws  = hourly.get("wind_speed", [])
    dr  = hourly.get("direct_radiation", [])

    ch_arr = hourly.get("corrected_humidity")
    if isinstance(ch_arr, list) and ct and cdp:
        for i in range(min(len(ch_arr), len(ct), len(cdp))):
            derived = _relative_humidity(ct[i], cdp[i])
            if derived is not None:
                ch_arr[i] = round(derived, 1)
    ch = hourly.get("corrected_humidity", [])

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


def apply_decay_corrections(weather_data, config=None):
    """Subtract per-(field, lead_h) mean error from each hourly forecast
    array. Mutates weather_data["hourly"] in place. Recomputes derived
    arrays. Safe no-op on missing, malformed, or stale corrections.

    config (optional): when provided, overrides production whitelists.
      Recognized keys:
        - "L3_FIELDS": set of field shorts → L3 applied (default L3_FIELDS)
        - "L4_FIELDS": set of field shorts → L4 applied (default L4_FIELDS)
      Anything not in the config dict falls back to module-level constants.
      Used by the backtest framework to A/B alternative configs against
      historical snapshots without redeploying.
    """
    # Resolve config-overridable knobs once, here. Everything downstream
    # references the locals, not the module globals.
    l3_fields = (config or {}).get("L3_FIELDS", L3_FIELDS)
    l4_fields = (config or {}).get("L4_FIELDS", L4_FIELDS)

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

    # Idempotent-preserve; the collector calls preserve_raw_forecast_arrays
    # earlier now (2026-07-02 v0.6.285) so raw_* arrays survive even when
    # a correction runs before apply_decay_corrections (L5 solar was the
    # first one — solar_correction was mutating direct_radiation before
    # this block preserved it, so raw_direct_radiation ended up holding
    # the L5-corrected value). The guard `dst not in hourly` makes this
    # a no-op when the earlier preservation already ran.
    preserve_raw_forecast_arrays(weather_data)

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
    if "wd" in l3_fields and isinstance(wd_arr, list) and wd_sin_corr and wd_cos_corr:
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

    # Skip-table lookup — read the current-tick synoptic regime once, use for
    # all L3/L4 skip decisions across all leads. Approximation: treats the
    # current regime as the forecast regime for every future lead (rather than
    # per-lead regime classification, which would need forecast_wind_dir +
    # forecast_pressure per lead + inline classifier calls). Correct when the
    # regime is stable; misses on transition-heavy days. Refinement queued.
    _state = (weather_data.get("derived") or {}).get("state") or {}
    _regime_now = _state.get("regime_synoptic")
    skip_l3 = 0
    skip_l4 = 0
    # Per-field firing counters for the gate-firing log (Phase (a)). "Fires" =
    # correction actually mutated the array. "Skips" = skip table matched.
    # Both are keyed by the L3/L4 whitelist fields only; fields NOT in the
    # whitelist don't appear (that's a config-level dormancy the applied-layer
    # audit already catches).
    l3_by_field = defaultdict(lambda: {"fires": 0, "skips": 0})
    l4_by_field = defaultdict(lambda: {"fires": 0, "skips": 0})

    applied = 0
    capped = 0
    for short, array_name in TARGET_ARRAY.items():
        if short not in l3_fields:
            continue
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
            if _should_skip(short, "l3", _regime_now, h):
                skip_l3 += 1
                l3_by_field[short]["skips"] += 1
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
            lo, hi = FIELD_BOUNDS.get(short, (None, None))
            if lo is not None and result < lo:
                result = lo
            if hi is not None and result > hi:
                result = hi
            arr[h] = round(result, digits)
            applied += 1
            l3_by_field[short]["fires"] += 1

    # Log L3 firings. Zero-fire fields are not in this dict — the rollup script
    # infers dormancy by cross-referencing L3_FIELDS against the aggregated log.
    gate_firing_log.record_firing(
        operator="L3", regime=_regime_now,
        by_field=dict(l3_by_field), leads=48,
    )

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
            if short not in l4_fields:
                continue
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
                if _should_skip(short, "l4", _regime_now, h):
                    skip_l4 += 1
                    l4_by_field[short]["skips"] += 1
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
                l4_by_field[short]["fires"] += 1
        if diurnal_applied:
            msg = f"  ✓ Diurnal apply: {diurnal_applied} hourly cells corrected"
            if diurnal_capped:
                msg += f" ({diurnal_capped} capped at sanity bound)"
            logging.info(msg)

    # Log L4 firings. Emitted unconditionally (even if diurnal_doc was missing
    # or stale) so the aggregator can distinguish "L4 fields exist but nothing
    # fired" (dormancy: file missing) from "L4 fired on 0 cells" (silent
    # skip-table match).
    gate_firing_log.record_firing(
        operator="L4", regime=_regime_now,
        by_field=dict(l4_by_field), leads=48,
    )

    # Derive the consistent moisture quadruple from the now-corrected T + T_d.
    recompute_derived_moisture_arrays(weather_data)

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
        if short not in l3_fields:
            continue
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
        "layer_3_fields": sorted(l3_fields),
        "layer_4_fields": sorted(l4_fields),
        "layer_3_brier_fields": sorted(L3_BRIER_FIELDS),
        "layer_3_paused": len(l3_fields) == 0,
        "layer_4_paused": len(l4_fields) == 0,
        "skip_table_regime": _regime_now,
        "skip_table_l3_cells_skipped": skip_l3,
        "skip_table_l4_cells_skipped": skip_l4,
    }

"""
Rolling log of corrected 48h forecast snapshots, stored in GCS.

Every collector run writes one compact snapshot of what we think the next
48 hours will look like. Kept for RETENTION_DAYS days for downstream
forecast-vs-observed calibration (decay curves, POP accuracy, dew point
drift, etc.). One entry per hour, fields use short keys to keep file
size manageable across two weeks of 10-minute runs.
"""
from datetime import datetime, timedelta, timezone as _dt_timezone

import pytz

from ..gcs_io import load_json, upload_json
from ..utils import magnus_dew_point_f
from . import cl_persistence_gate, ch_persistence_gate, wd_persistence_gate
from .forecast_text import _extract_nws_value


GCS_PATH = "forecast_log.json"
RETENTION_DAYS = 14
SNAPSHOT_HOURS = 48
TZ = pytz.timezone("America/New_York")


# v0.6.431 — NWS gridpoint (NBM-derived official NWS forecast) as an alternate
# forecast source alongside HRRR/GFS/Pirate. Stamped per-hour under `{short}_nws`
# so the pair log emits forecast_nws + error_nws for downstream benchmarking.
# NWS gridpoint properties are irregular-interval (typically hourly out to
# ~72h then 3-hourly) and each entry carries a validTime range; we align to
# our hourly grid by asking for the value valid at each hour's timestamp.
# Fields covered (NWS gridpoint returns unit-tagged values; we convert to
# our internal units):
#   t  ← temperature (degC → F)
#   dp ← dewpoint (degC → F)
#   pp ← probabilityOfPrecipitation (percent, no conversion)
#   ws ← windSpeed (km/h → mph)
#   wd ← windDirection (deg, no conversion)
# Not covered (NWS gridpoint returns no equivalent): h, cc, cl, cm, ch, sr,
# wg, pa (QPF is in mm and can be added later once we settle on the pa unit).
_NWS_FIELDS = ("t", "dp", "pp", "ws", "wd")

# Phase 1 (option-1 parallel HRRR/NBM cascade, 2026-08-18) — NBM CO grib
# point extract fetched hourly by nbm-ingester CF, stamped per-hour as
# {short}_raw_nbm so downstream (pair log, L2/L3/L4 NBM cascades, selector)
# have a clean HRRR-vs-NBM comparison. Fields NBM emits: see
# weather_collector/fetchers/nbm_point.py — no cl/cm/h/pr/pa/pp (single-
# source, HRRR-only forever).
_NBM_FIELDS = ("t", "dp", "ws", "wd", "wg", "sr", "cc", "ch", "h")

# Phase 2 (2026-08-18) — L2_nbm coverage. Intersection of (fields NBM emits)
# with (fields L2 corrects), minus derived (cc = Ccd(cl,cm,ch), dp = Magnus(t,h)).
# For each of these 5 fields the snapshot stamps {field}_l2_nbm using the
# same correction delta L2 applied to HRRR: `l2_nbm = raw_nbm + (l2_hrrr −
# raw_hrrr)`. Rationale: station-derived corrections are (in v1) treated as
# model-agnostic — the delta L2 computed for HRRR is what the NBM cascade
# would also need. Refinable in Phase 5+ once station-vs-NBM bias data
# accumulates. wd uses circular subtraction/addition.
_L2_NBM_FIELDS = ("t", "ws", "wd", "wg", "h")

# Phase 3 (2026-08-19) — L3_NBM coverage. Per-lead signed bias applied to
# {field}_l2_nbm: `l3_nbm = l2_nbm - bias_table[field][lead_h]`. Table
# comes from analysis/l3_nbm_fit.py fitting the pair log's error_l2_nbm
# residual. wd excluded (would need per-layer sin/cos plumbing, matches
# HRRR-side L3_FIELDS not carrying wd). Shadow-only until Phase 4
# selector arms user-visible NBM outputs.
from .l3_nbm import (
    L3_NBM_FIELDS as _L3_NBM_FIELDS,
    L3_NBM_WD as _L3_NBM_WD,
    l3_nbm_bias as _l3_nbm_bias,
    l3_nbm_wd_components as _l3_nbm_wd_components,
)


def _nws_value_at(nws_gridpoints, nws_key, target_utc, convert):
    """Extract an NWS gridpoint value at target_utc (tz-aware UTC), applying
    the unit conversion. Returns None if the property is missing or the
    target time falls outside any validTime interval."""
    if not nws_gridpoints:
        return None
    prop = nws_gridpoints.get(nws_key)
    if not prop:
        return None
    raw = _extract_nws_value(prop, target_utc)
    if raw is None:
        return None
    try:
        return convert(float(raw))
    except (TypeError, ValueError):
        return None


def append_forecast_snapshot(hourly, derived=None, nws_gridpoints=None, nbm_extract=None):
    """Append a snapshot of the corrected 48h forecast for later validation.
    Prunes snapshots older than RETENTION_DAYS on each write. No-op if the
    hourly data has no usable hours.

    Optional `derived` argument (added v0.6.29) — when provided, snapshot-level
    state fields like pressure_trend_hpa_3h are stamped as metadata on each
    snapshot for downstream conditional-state analysis (same value applies to
    all hours in this snapshot).
    """
    now_local = datetime.now(TZ)
    run_stamp = now_local.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    cutoff = (now_local - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")

    # Phase 1 — build a valid-UTC → NBM-lead-values map so we can look up
    # NBM's forecast for each of our snapshot hours without a per-hour scan.
    nbm_by_valid_utc = {}
    if nbm_extract and isinstance(nbm_extract, dict):
        leads = nbm_extract.get("leads") or {}
        valid_map = nbm_extract.get("lead_valid_utc") or {}
        for lead_str, fields in leads.items():
            v = valid_map.get(lead_str)
            if v and fields:
                nbm_by_valid_utc[v] = fields

    times = hourly.get("times", [])
    # Per-layer forecast arrays. The Fitter (decay_fit) computes per-layer MAE
    # by comparing each layer's forecast against the same observation, so we
    # snapshot all 4 layers' values per hour. Mapping:
    #   L1 (raw)        = raw_* or the unprocessed model array
    #   L2 (mesonet)    = *_post_l2 (added by decay_apply.py)
    #   L3 (post-decay) = *_post_l3 (added by decay_apply.py)
    #   L4 (final)      = the live corrected_* / _post_diurnal array
    # Fields with no L2 (wind/POP/cloud) have L1 == L2.
    layers = {
        # Temperature: cove L6 sits AFTER L4 in the stack. When ENABLED, the
        # pre-cove L4 array is preserved as corrected_temperature_post_l4 by
        # stamp_cove_correction so we can isolate L6's contribution; when
        # disabled, the post_l4 key is absent and l4 falls back to the live
        # corrected_temperature (cove is a no-op in that path).
        # v0.6.432: l1r (L1-router) layer holds the router's user-visible output.
        # At leads <6h it equals l6 (router falls through to cascade); at ≥6h
        # for routed hours it holds the NWS-gridpoint value. The upstream l6
        # slot reads from *_pre_router when the router preserved it, so l6
        # remains the cascade's honest output and error_l6 stays scoring the
        # cascade even after v0.6.432 flipped.
        "t":  {"l1": hourly.get("temperature", []),
               "l2": hourly.get("corrected_temperature_post_l2", []),
               "l3": hourly.get("corrected_temperature_post_l3", []),
               "l4": hourly.get("corrected_temperature_post_l4",
                                hourly.get("corrected_temperature_pre_router",
                                           hourly.get("corrected_temperature", []))),
               "l6": hourly.get("corrected_temperature_pre_router",
                                hourly.get("corrected_temperature", [])),
               "l1r": hourly.get("corrected_temperature", [])},
        "h":  {"l1": hourly.get("humidity", []),
               "l2": hourly.get("corrected_humidity_post_l2", []),
               "l3": hourly.get("corrected_humidity_post_l3", []),
               "l4": hourly.get("corrected_humidity", [])},
        # v0.6.432: l1r holds post-router live wind_speed; l4 falls back to
        # wind_speed_pre_router where the router captured it so error_l4
        # continues to score the cascade honestly.
        "ws": {"l1": hourly.get("raw_wind_speed", hourly.get("wind_speed", [])),
               "l2": hourly.get("wind_speed_post_l2", []),
               "l3": hourly.get("wind_speed_post_l3", []),
               "l4": hourly.get("wind_speed_pre_router",
                                hourly.get("wind_speed", [])),
               "l1r": hourly.get("wind_speed", [])},
        "wg": {"l1": hourly.get("raw_wind_gusts", hourly.get("wind_gusts", [])),
               "l2": hourly.get("wind_gusts_post_l2", []),
               "l3": hourly.get("wind_gusts_post_l3", []),
               "l4": hourly.get("wind_gusts", [])},
        "pp": {"l1": hourly.get("raw_precipitation_probability",
                                 hourly.get("precipitation_probability", [])),
               "l2": hourly.get("precipitation_probability_post_l2", []),
               "l3": hourly.get("precipitation_probability_post_l3", []),
               "l4": hourly.get("precipitation_probability", [])},
        "pr": {"l1": hourly.get("raw_pressure_in", []),
               "l2": hourly.get("corrected_pressure_in_post_l2", []),
               "l3": hourly.get("corrected_pressure_in_post_l3", []),
               "l4": hourly.get("corrected_pressure_in", [])},
        # Clouds: Lc (cloud saturation-unbiasing) sits AFTER L4 for
        # cc / cl / cm / ch. When ENABLED, pre-Lc array is preserved as
        # <field>_post_l4 by stamp_cloud_saturation_correction so we can
        # isolate Lc's contribution; when disabled, post_l4 is absent and
        # l4 falls back to the live array (Lc is a no-op in that path).
        # Lc rides the l6 slot (Lt was L6-temperature-only, retired 07-13).
        "cc": {"l1": hourly.get("raw_cloud_cover", hourly.get("cloud_cover", [])),
               "l2": hourly.get("cloud_cover_post_l2", []),
               "l3": hourly.get("cloud_cover_post_l3", []),
               "l4": hourly.get("cloud_cover_post_l4",
                                hourly.get("cloud_cover", [])),
               "l6": hourly.get("cloud_cover", [])},
        # Solar: L5 (regime correction) sits AFTER L4 in the stack — same
        # shape as cove L6 for temperature. When ENABLED, pre-L5 array is
        # preserved as direct_radiation_post_l4 so l4 stays L4-only; the
        # post-L5 array (live direct_radiation) is captured as l5. When
        # disabled, post_l4 is absent and l4 falls back to direct_radiation
        # (L5 is a no-op in that path).
        "sr": {"l1": hourly.get("raw_direct_radiation", hourly.get("direct_radiation", [])),
               "l2": hourly.get("direct_radiation_post_l2", []),
               "l3": hourly.get("direct_radiation_post_l3", []),
               "l4": hourly.get("direct_radiation_post_l4",
                                hourly.get("direct_radiation", [])),
               "l5": hourly.get("direct_radiation", [])},
        "pa": {"l1": hourly.get("raw_precipitation", hourly.get("precipitation", [])),
               "l2": hourly.get("precipitation_post_l2", []),
               "l3": hourly.get("precipitation_post_l3", []),
               "l4": hourly.get("precipitation", [])},
        # v0.6.361 pattern (same as ch): l6 attributes Lc alone, "clp"
        # attributes cl_persistence_gate (v0.6.379 successor to the retired
        # cl_persistence_short_lead). Slot populates whenever the gate flips
        # ENABLED; today it mirrors the post-Lc array.
        "cl": {"l1": hourly.get("raw_cloud_cover_low", hourly.get("cloud_cover_low", [])),
               "l2": hourly.get("cloud_cover_low_post_l2", []),
               "l3": hourly.get("cloud_cover_low_post_l3", []),
               "l4": hourly.get("cloud_cover_low_post_l4",
                                hourly.get("cloud_cover_low", [])),
               "l6": hourly.get("cloud_cover_low_post_lc",
                                hourly.get("cloud_cover_low", [])),
               # v0.6.382p: prefer shadow key so ENABLED=False shadow
               # values reach the pair log (falls back to live array when
               # gate is ENABLED — shadow == live in that case).
               "clp": hourly.get("cloud_cover_low_shadow_clp",
                                 hourly.get("cloud_cover_low", []))},
        "cm": {"l1": hourly.get("raw_cloud_cover_mid", hourly.get("cloud_cover_mid", [])),
               "l2": hourly.get("cloud_cover_mid_post_l2", []),
               "l3": hourly.get("cloud_cover_mid_post_l3", []),
               "l4": hourly.get("cloud_cover_mid_post_l4",
                                hourly.get("cloud_cover_mid", [])),
               "l6": hourly.get("cloud_cover_mid", [])},
        # v0.6.361: l6 for ch now attributes Lc's contribution alone —
        # points at post_lc (pre-persistence-gate) when the persistence gate
        # preserved it, else falls back to the live array (same as before,
        # since with persistence disabled the live array IS post-Lc). The
        # "chp" slot captures post-persistence-gate (the true final applied)
        # so ch_persistence_gate's impact can be plotted separately from Lc.
        "ch": {"l1": hourly.get("raw_cloud_cover_high", hourly.get("cloud_cover_high", [])),
               "l2": hourly.get("cloud_cover_high_post_l2", []),
               "l3": hourly.get("cloud_cover_high_post_l3", []),
               "l4": hourly.get("cloud_cover_high_post_l4",
                                hourly.get("cloud_cover_high", [])),
               "l6": hourly.get("cloud_cover_high_post_lc",
                                hourly.get("cloud_cover_high", [])),
               # v0.6.382p: prefer shadow key (matches clp/wdp pattern —
               # no behavior change today since chp is ENABLED=True and
               # shadow == live).
               "chp": hourly.get("cloud_cover_high_shadow_chp",
                                 hourly.get("cloud_cover_high", []))},
        # Wind direction is circular — needs special sin/cos math in Fitter
        # and Apply. v0.6.368 added wd to L2 (wind_blend circular unit-vector
        # blend). v0.6.382 added wdp (wd_persistence_gate) — post-L2 specialist
        # that overwrites wind_direction on gate-fired cells. l3 = l4 = l2 =
        # wind_direction_pre_wd_gate (L2 blend result). wdp slot holds the
        # post-wdp array. wind_direction_pre_wd_gate is stashed by
        # wd_persistence_gate.py PRE_GATE_KEY BEFORE the gate overwrites
        # hourly.wind_direction; falls back to hourly.wind_direction when the
        # gate is disabled or fired on zero cells (identity fallback).
        # v0.6.432: wdp reads from wind_direction_pre_router when set (so
        # wdp's contribution is scored against the pre-router array, not the
        # router-overridden live one). l1r holds the post-router live value.
        "wd": {"l1": hourly.get("raw_wind_direction", hourly.get("wind_direction", [])),
               "l2": hourly.get("wind_direction_pre_wd_gate", hourly.get("wind_direction", [])),
               "l3": hourly.get("wind_direction_pre_wd_gate", hourly.get("wind_direction", [])),
               "l4": hourly.get("wind_direction_pre_wd_gate", hourly.get("wind_direction", [])),
               "wdp": hourly.get("wind_direction_shadow_wdp",
                                 hourly.get("wind_direction_pre_router",
                                            hourly.get("wind_direction", []))),
               "l1r": hourly.get("wind_direction", [])},
    }
    # Dew point is derived from t + h via Magnus at each layer (no separate model array).
    # Backward-compat top-level keys (t / h / ws / wg / pp / pr / cc) kept = L4 final.

    def _round_for(field, val):
        if val is None:
            return None
        if field == "pr":  return round(val, 3)
        if field == "pa":  return round(val, 3)
        if field in ("pp", "cc", "cl", "cm", "ch", "sr", "wd"): return round(val)
        return round(val, 1)

    def _derive_applied_layer(field_layers, i, eps=1e-6):
        """Deepest layer whose value at index i differs from the previously
        captured layer's value by > eps. Every correction gate today is
        deterministic at forecast time (L2/L3/L4 by field membership; L5 by
        sun-up threshold; L6 by regime + sea-breeze; marine-layer by wd+hour;
        future skip table by state_fc regime). All those decisions land in
        the per-layer arrays as either "changed the value" (fired) or
        "identical to prior layer" (skipped). So this equality-based walk
        recovers the actual applied layer per (field, lead) — the value
        users see is arr_applied[i]. Falls back to "l1" if nothing above l1
        has a distinct value.
        """
        applied = None
        prev_val = None
        # v0.6.361: iteration order = pipeline order. Specialists that run
        # after Lc/L5 (chp, clp) walked last so applied_layer stamps them
        # when their contribution differs from the prior layer.
        # v0.6.390j: skip specialist keys when the corresponding module is
        # ENABLED=False. Shadow arrays are still written unconditionally
        # (v0.6.382p flip-gate visibility fix), so without this guard a
        # dormant specialist gets stamped as the applied layer and poisons
        # every downstream metric that reads applied_layer (Fitter's
        # per_layer_mae_by_lead[.].production and mae_over_time[.].prod_real).
        # v0.6.432: l1r appended at the end so router attribution wins over
        # l4/l6/wdp on hours where the router fired (value differs from
        # cascade output). At leads <6h, l1r == prior layer so walk falls
        # back to cascade attribution.
        for lk in ("l1", "l2", "l3", "l4", "l5", "l6", "chp", "clp", "wdp", "l1r"):
            if lk == "clp" and not cl_persistence_gate.ENABLED: continue
            if lk == "chp" and not ch_persistence_gate.ENABLED: continue
            if lk == "wdp" and not wd_persistence_gate.ENABLED: continue
            arr = field_layers.get(lk) or []
            if i >= len(arr) or arr[i] is None:
                continue
            v = arr[i]
            if applied is None:
                applied = lk
                prev_val = v
            elif abs(v - prev_val) > eps:
                applied = lk
                prev_val = v
        return applied or "l1"

    hours = []
    for i, t in enumerate(times[:SNAPSHOT_HOURS]):
        if not t:
            continue
        entry = {"v": t}
        # Per-layer values per field
        for field, lyrs in layers.items():
            for lyr_key, arr in lyrs.items():
                if i < len(arr) and arr[i] is not None:
                    entry[f"{field}_{lyr_key}"] = _round_for(field, arr[i])
        # v0.6.269: applied-layer stamp per (field, lead). Recovers the actual
        # user-visible layer for this lead so the pair-log downstream can
        # score a real per-row Production error instead of the approximation
        # that treats one layer as "the applied one" per field. dp is derived
        # (applied stamp inherited from t's applied layer). v0.6.382: wd
        # participates now that wdp writes a distinct value on gate-fired cells.
        for field, lyrs in layers.items():
            applied = _derive_applied_layer(lyrs, i)
            entry[f"{field}_applied"] = applied
        # Backward-compat top-level keys. CRITICAL: these must equal the L2
        # (pre-decay) value, NOT L4. The Fitter reads the top-level key as
        # "the forecast" and calibrates decay corrections from (forecast - obs).
        # If top-level = L4 (post-decay), the calibration would see ~0 error
        # and decay corrections would shrink to zero. Pre-v0.6.25b the snapshot
        # was taken BEFORE decay_apply so the legacy key was naturally L2. We
        # now snapshot AFTER decay_apply to capture all 4 layers — preserving
        # legacy semantics requires explicitly using the _l2 value here.
        for field in ("t","h","ws","wg","pp","pr","cc","sr","pa","cl","cm","ch","wd"):
            l2 = entry.get(f"{field}_l2")
            if l2 is not None:
                entry[field] = l2
        # Dew point per layer (derived from t/h at each layer via Magnus)
        for lyr_key in ("l1","l2","l3","l4"):
            tv = entry.get(f"t_{lyr_key}")
            hv = entry.get(f"h_{lyr_key}")
            if tv is not None and hv is not None:
                dp = magnus_dew_point_f(tv, hv)
                if dp is not None:
                    entry[f"dp_{lyr_key}"] = dp
        # Legacy dp = dp_l2 for the same Fitter-calibration reason as above.
        if entry.get("dp_l2") is not None:
            entry["dp"] = entry["dp_l2"]
        # Applied-layer stamp for dp — same equality walk as above but on the
        # derived dp_lN values we just computed.
        dp_applied = None
        prev = None
        for lk in ("l1","l2","l3","l4"):
            v = entry.get(f"dp_{lk}")
            if v is None:
                continue
            if dp_applied is None:
                dp_applied = lk
                prev = v
            elif abs(v - prev) > 1e-6:
                dp_applied = lk
                prev = v
        if dp_applied:
            entry["dp_applied"] = dp_applied
        # v0.6.309: shadow-log shortwave + diffuse solar radiation from
        # Open-Meteo alongside sr's direct_radiation. Diagnostic only —
        # Tempest station sr sensors measure total shortwave, so pairing
        # them against direct-beam-only forecast_l1 gives a "bias" that's
        # really a definitional gap. Storing sw + diffuse per-hour lets
        # forecast_error_log stamp them on each sr pair for an apples-to-
        # apples model-vs-obs comparison.
        sw_arr = hourly.get("shortwave_radiation", [])
        diff_arr = hourly.get("diffuse_radiation", [])
        if i < len(sw_arr) and sw_arr[i] is not None:
            entry["sr_sw"] = round(float(sw_arr[i]))
        if i < len(diff_arr) and diff_arr[i] is not None:
            entry["sr_diffuse"] = round(float(diff_arr[i]))
        # Parse this hour's local-ET timestamp into tz-aware UTC once —
        # used by both the NWS gridpoint alignment (v0.6.431) and the NBM
        # raw stamp (Phase 1, 2026-08-18).
        try:
            naive = datetime.fromisoformat(t[:16])  # "YYYY-MM-DDTHH:MM"
            target_utc = TZ.localize(naive).astimezone(_dt_timezone.utc)
        except (ValueError, TypeError):
            target_utc = None
        # v0.6.431 — NWS gridpoint (NBM-derived) values at this hour.
        if nws_gridpoints:
            if target_utc is not None:
                # temperature: degC → F
                v = _nws_value_at(nws_gridpoints, "temperature", target_utc,
                                  lambda c: c * 9.0 / 5.0 + 32.0)
                if v is not None:
                    entry["t_nws"] = _round_for("t", v)
                # dewpoint: degC → F
                v = _nws_value_at(nws_gridpoints, "dewpoint", target_utc,
                                  lambda c: c * 9.0 / 5.0 + 32.0)
                if v is not None:
                    entry["dp_nws"] = _round_for("dp", v)
                # POP: percent, no conversion
                v = _nws_value_at(nws_gridpoints, "probabilityOfPrecipitation",
                                  target_utc, lambda x: x)
                if v is not None:
                    entry["pp_nws"] = _round_for("pp", v)
                # wind speed: km/h → mph
                v = _nws_value_at(nws_gridpoints, "windSpeed", target_utc,
                                  lambda k: k * 0.621371)
                if v is not None:
                    entry["ws_nws"] = _round_for("ws", v)
                # wind direction: deg, no conversion
                v = _nws_value_at(nws_gridpoints, "windDirection", target_utc,
                                  lambda d: d)
                if v is not None:
                    entry["wd_nws"] = _round_for("wd", v)
        # Phase 1 (2026-08-18) — NBM raw stamp per field for parallel
        # HRRR/NBM cascade. Look up this hour's valid UTC in the extract's
        # lead_valid_utc map; if the ingester covered it, stamp _raw_nbm
        # for every field NBM emits. Fields NBM does not emit (cl/cm/h/pr/
        # pa/pp) get nothing here — selector will always pick HRRR for
        # those. Depends on target_utc already computed from the nws
        # branch above being tz-aware UTC.
        if nbm_by_valid_utc and target_utc is not None:
            key = target_utc.strftime("%Y-%m-%dT%H:00:00Z")
            fields = nbm_by_valid_utc.get(key)
            if fields:
                for f in _NBM_FIELDS:
                    v = fields.get(f)
                    if v is not None:
                        entry[f"{f}_raw_nbm"] = _round_for(f, v)
                # Phase 2 (2026-08-18) — L2_nbm = raw_nbm + (l2_hrrr − raw_hrrr)
                # per field where the HRRR side already stamped l1 + l2 above.
                # wd uses circular arithmetic (delta in [-180, 180], sum wraps
                # into [0, 360)). Skip when any input is missing.
                import math as _math
                for f in _L2_NBM_FIELDS:
                    raw_nbm = entry.get(f"{f}_raw_nbm")
                    raw_hrrr = entry.get(f"{f}_l1")
                    l2_hrrr = entry.get(f"{f}_l2")
                    if raw_nbm is None or raw_hrrr is None or l2_hrrr is None:
                        continue
                    if f == "wd":
                        # Circular: delta = signed angular diff in (-180, 180]
                        d = (l2_hrrr - raw_hrrr + 180.0) % 360.0 - 180.0
                        combined = (raw_nbm + d) % 360.0
                        entry[f"{f}_l2_nbm"] = _round_for(f, combined)
                    else:
                        entry[f"{f}_l2_nbm"] = _round_for(f, raw_nbm + (l2_hrrr - raw_hrrr))
                # Phase 3 (2026-08-19) — L3_NBM. Scalar fields (t/ws/wg/h)
                # subtract a per-lead signed bias. wd uses circular sin/cos
                # correction: subtract per-lead sin/cos residuals then atan2
                # back to degrees. Both branches identity-fall-through when
                # the curated table has no coverage (bias 0.0 / (0.0, 0.0)).
                for f in _L3_NBM_FIELDS:
                    l2_nbm = entry.get(f"{f}_l2_nbm")
                    if l2_nbm is None:
                        continue
                    entry[f"{f}_l3_nbm"] = _round_for(f, l2_nbm - _l3_nbm_bias(f, i))
                wd_l2_nbm = entry.get(f"{_L3_NBM_WD}_l2_nbm")
                if wd_l2_nbm is not None:
                    sin_c, cos_c = _l3_nbm_wd_components(i)
                    wd_rad = _math.radians(float(wd_l2_nbm))
                    s = _math.sin(wd_rad) - sin_c
                    c = _math.cos(wd_rad) - cos_c
                    corrected = _math.degrees(_math.atan2(s, c)) % 360.0
                    entry[f"{_L3_NBM_WD}_l3_nbm"] = _round_for(_L3_NBM_WD, corrected)
        hours.append(entry)

    if not hours:
        return

    log = load_json(GCS_PATH, default={"snapshots": []})
    snapshots = [s for s in log.get("snapshots", []) if s.get("run", "") >= cutoff]
    snap_entry = {"run": run_stamp, "hours": hours}
    # Snapshot-level state fields (apply to all hours in this snapshot) — used
    # by the Joiner to stamp state on each pair for conditional-state analysis.
    if derived:
        pt = derived.get("pressure_trend_hpa_3h")
        if pt is not None:
            snap_entry["pressure_trend_hpa_3h"] = round(float(pt), 2)
        sigma = derived.get("cloud_inter_source_sigma")
        if sigma is not None:
            snap_entry["cloud_inter_source_sigma"] = round(float(sigma), 2)
        n_src = derived.get("cloud_n_sources")
        if n_src is not None:
            snap_entry["cloud_n_sources"] = int(n_src)
    snapshots.append(snap_entry)
    upload_json({"snapshots": snapshots}, GCS_PATH, "forecast_log.json")

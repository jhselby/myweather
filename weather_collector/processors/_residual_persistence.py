"""Shared residual-persistence Stage 3 processor harness.

Extracted 2026-08-31 v0.6.532 from the three ~230-line clones
(`wg_residual_persistence.py`, `dp_residual_persistence.py`,
`h_residual_persistence.py`) after h Stage 3 landed as the third clone,
matching the pre-registered v0.6.525 deferral condition. Analysis-side
harnesses (`analysis/_residual_persistence_stage1.py`,
`analysis/_residual_persistence_stage2.py`) followed the same shape 08-30.

Each per-field wrapper module still owns its `ENABLED` flag + the deltas
(FIELD constant + hourly key names + sanity clamp magnitude + physical
bounds + pre-key suffix) and exposes the same `stamp_<field>_residual_persistence`
+ `describe_applicability` API the collector already imports, so
`weather_collector/collector.py` wiring is unchanged. All four v0.6.525
bugfixes live here (telemetry pre-clamp match, mtime cache invalidation,
`clamped_out_by_band` separate counter, `record_firing` in the
no_hourly_array early-return path).

Correction semantics unchanged: in cells where (regime, lead_band) is SHIP
or MARGIN in the curated JSON, replace the post-L3 field value with
`fc_l2 + hour_of_day_correction`, then clamp to physical bounds if provided.
When ENABLED=False the module still stamps telemetry so the 7-day live-layer
change gate can watch it. See [[feedback_whitelist_promotion_gate]] and
[[feedback_regime_gate_first]].
"""
import json
import logging
import os
from pathlib import Path

TABLE_ROOT = Path(__file__).resolve().parent.parent / "data"

# Note: lead 0 (i=0) intentionally unbanded — "0-5" runs 1..5 to exclude
# the current-tick "now" observation from the correction. Consistent with
# sibling persistence-gate processors (chp/clp/wdp).
_LEAD_BANDS = [
    ("0-5",   1,  5),
    ("6-11",  6, 11),
    ("12-23", 12, 23),
    ("24-47", 24, 47),
]

# Per-field cache state — keyed by field so each wrapper's _TABLE_CACHE
# and _TABLE_MTIME are isolated (each field has its own curated JSON).
_CACHE_STATE = {}  # field -> {"cache": dict|None, "mtime": float|None}


def _load_table(field, table_path):
    """Load curated JSON with mtime-check invalidation so a Stage 2 refit
    lands without needing a worker restart. Also respects MYWEATHER_REFRESH=1
    per [[feedback_cache_refresh_policy]]. Cache is per-field."""
    state = _CACHE_STATE.setdefault(field, {"cache": None, "mtime": None})
    if os.environ.get("MYWEATHER_REFRESH") == "1":
        state["cache"] = None
        state["mtime"] = None
    try:
        mtime = table_path.stat().st_mtime
    except FileNotFoundError:
        mtime = None
    if state["cache"] is not None and mtime == state["mtime"]:
        return state["cache"]
    try:
        state["cache"] = json.loads(table_path.read_text())
        state["mtime"] = mtime
    except FileNotFoundError:
        logging.warning(f"  ⚠  {field} residual persistence table missing at {table_path}; gate will not fire")
        state["cache"] = {"cells": {}, "hourly_correction": {}}
        state["mtime"] = None
    except Exception as e:
        logging.warning(f"  ⚠  {field} residual persistence table load failed: {e}")
        state["cache"] = {"cells": {}, "hourly_correction": {}}
        state["mtime"] = None
    return state["cache"]


def _lead_band(lead_h):
    for name, lo, hi in _LEAD_BANDS:
        if lo <= lead_h <= hi:
            return name
    return None


def _cell_fires(cells, regime, band):
    cell = cells.get(regime, {}).get(band)
    if not cell:
        return False
    return cell.get("verdict") in ("SHIP", "MARGIN")


def _parse_hour(ts):
    if not isinstance(ts, str) or len(ts) < 13:
        return None
    try:
        return int(ts[11:13])
    except ValueError:
        return None


def _apply_bounds(v, lo, hi):
    """Physical clamp: order-independent since lo <= hi by construction.
    Applied BEFORE stamping per_lead_would_apply so telemetry matches the
    value that actually lands in the hourly array (v0.6.525 fix)."""
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


def describe_field(*, field, table_path, enabled):
    """Return an applicability-map descriptor list for one field's processor.
    Shape identical to the pre-refactor per-field describe_applicability()."""
    table = _load_table(field, table_path)
    cells = table.get("cells", {})
    hc = (table.get("hourly_correction") or {}).get("hour_of_day") or {}
    n_slots = sum(1 for v in hc.values() if v is not None)

    if enabled:
        fires_when = (f"ENABLED — replaces post-L3 {field} with (fc_l2 + hour_of_day_correction) "
                      "when (regime, lead_band) is SHIP or MARGIN. SKIP cells pass through unchanged.")
        state_prefix = "ENABLED True"
    else:
        fires_when = f"OFF — ENABLED False. Telemetry stamped for 7-day watch; no {field} values modified."
        state_prefix = "ENABLED False"

    ship_cells, skip_cells, thin_cells, margin_cells = [], [], [], []
    for regime, bandmap in cells.items():
        for band, cell in bandmap.items():
            v = cell.get("verdict")
            key = f"{regime}/{band}"
            if v == "SHIP":
                ship_cells.append(key)
            elif v == "MARGIN":
                margin_cells.append(key)
            elif v == "SKIP":
                skip_cells.append(key)
            elif v == "THIN":
                thin_cells.append(key)

    current_state = (
        f"{state_prefix}. Cells — SHIP: {len(ship_cells)}, MARGIN: {len(margin_cells)}, "
        f"SKIP: {len(skip_cells)} (pass through L3), THIN: {len(thin_cells)}. "
        f"Hour-of-day correction slots populated: {n_slots}/24."
    )

    return [{
        "layer_id": f"{field}_residual_persistence",
        "name": f"{field} residual persistence gate (regime × lead_band L2-residual add-on)",
        "category": "specialist",
        "fields": [{
            "field": field,
            "fires_when": fires_when,
            "gated_by": "ENABLED + SHIP/MARGIN verdict per (regime, lead_band) + hour_of_day correction populated",
            "current_state": current_state,
        }],
    }]


def stamp_field(weather_data, *, field, hourly_key, l2_key, table_path,
                max_abs_correction, pre_key_suffix, enabled,
                physical_bounds=(None, None)):
    """One tick of a residual-persistence Stage 3 processor for `field`.

    Reads `hourly[hourly_key]` (post-L3) and `hourly[l2_key]` (L2 output
    stashed by decay_apply). In cells where (regime, lead_band) has
    verdict SHIP or MARGIN, sets a candidate replacement value
    `fc_l2 + hour_of_day_correction`, clamped to `physical_bounds`.
    When `enabled`, writes the replaced array to `hourly[hourly_key]`
    and stashes the pre-gate array to `hourly[hourly_key + pre_key_suffix]`.
    Always stamps `weather_data[f"{field}_residual_persistence"]` telemetry
    + calls `gate_firing_log.record_firing`.

    Semantic-preservation contract: identical to the per-field clones
    before extraction (verified 2026-08-31 v0.6.532 via byte-diff on 3
    fields × 4 regimes)."""
    operator = f"{field}_residual_persistence"
    hourly = weather_data.get("hourly") or {}
    arr = hourly.get(hourly_key)
    if not isinstance(arr, list) or not arr:
        weather_data[operator] = {
            "enabled": enabled,
            "status": "no_hourly_array",
        }
        # v0.6.525: record 0/0 so the 7-day watch sees "operator ran,
        # nothing to do" instead of "operator did not run" — biasing the
        # flip decision.
        try:
            from . import gate_firing_log
            gate_firing_log.record_firing(
                operator=operator,
                regime="unknown",
                by_field={field: {"fires": 0, "skips": 0}},
                leads=0,
            )
        except Exception:
            pass
        return

    l2_arr = hourly.get(l2_key)
    times = hourly.get("times") or []

    table = _load_table(field, table_path)
    cells = table.get("cells", {})
    hc_block = table.get("hourly_correction") or {}
    hour_corr = hc_block.get("hour_of_day") or {}

    regime = ((weather_data.get("derived") or {}).get("state") or {}).get("regime_synoptic") or "unknown"

    n_leads = len(arr)
    per_lead_would_apply = [None] * n_leads
    per_lead_fires = [False] * n_leads
    fires_by_band = {name: 0 for name, _, _ in _LEAD_BANDS}
    skips_by_band = {name: 0 for name, _, _ in _LEAD_BANDS}
    # v0.6.525: separate counter for the sanity-clamp path so a bad refit
    # slot (hour_of_day |corr| > max_abs_correction) is observable in
    # telemetry instead of silently pooled with normal skips.
    clamped_out_by_band = {name: 0 for name, _, _ in _LEAD_BANDS}

    l2_available = isinstance(l2_arr, list) and len(l2_arr) == n_leads
    lo_bound, hi_bound = physical_bounds

    for i in range(n_leads):
        band = _lead_band(i)
        if band is None:
            continue
        if not _cell_fires(cells, regime, band):
            skips_by_band[band] += 1
            continue
        if not l2_available or l2_arr[i] is None:
            skips_by_band[band] += 1
            continue
        hour = _parse_hour(times[i]) if i < len(times) else None
        if hour is None:
            skips_by_band[band] += 1
            continue
        corr = hour_corr.get(str(hour))
        if corr is None:
            skips_by_band[band] += 1
            continue
        if abs(corr) > max_abs_correction:
            clamped_out_by_band[band] += 1
            continue
        candidate = float(l2_arr[i]) + float(corr)
        # Clamp BEFORE stamping so per_lead_would_apply matches what
        # actually lands in hourly[hourly_key] (v0.6.525 fix).
        candidate = _apply_bounds(candidate, lo_bound, hi_bound)
        per_lead_would_apply[i] = round(candidate, 3)
        per_lead_fires[i] = True
        fires_by_band[band] += 1

    if enabled:
        pre_key = f"{hourly_key}{pre_key_suffix}"
        if pre_key not in hourly:
            hourly[pre_key] = list(arr)
        new_arr = list(arr)
        for i, fires in enumerate(per_lead_fires):
            if fires and per_lead_would_apply[i] is not None:
                new_arr[i] = per_lead_would_apply[i]
        hourly[hourly_key] = new_arr

    weather_data[operator] = {
        "enabled": enabled,
        "regime": regime,
        "l2_available": l2_available,
        "fires_by_band": fires_by_band,
        "skips_by_band": skips_by_band,
        "clamped_out_by_band": clamped_out_by_band,
        "per_lead_would_apply": per_lead_would_apply,
        "table_generated_at": table.get("generated_at"),
        "hourly_correction_fit_asof": hc_block.get("fit_asof"),
    }

    try:
        from . import gate_firing_log
        total_fires = sum(fires_by_band.values())
        total_skips = sum(skips_by_band.values())
        gate_firing_log.record_firing(
            operator=operator,
            regime=regime,
            by_field={field: {
                "fires": total_fires if enabled else 0,
                "skips": total_skips if enabled else total_fires + total_skips,
            }},
            leads=n_leads,
        )
    except Exception as e:
        try:
            logging.warning(f"  ⚠  gate_firing record ({operator}) failed: {e}")
        except Exception:
            pass

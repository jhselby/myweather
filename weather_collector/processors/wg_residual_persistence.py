"""wg residual-persistence gate — regime × lead_band conditioned diurnal
L2-residual correction for wind_gusts.

Follow-on to [[wg-residual-persistence]] Stage 0/1/2 findings. The prior
14d mean of L2 residuals (obs - fc_l2) at the same clock hour, added on
top of L2, cleared held-out MAE +16.54% pooled in Stage 1. Stage 2 per-cell
verification narrowed the win to 6 SHIP cells (long-lead in flow regimes:
frontal/pre_frontal 24-47, se_flow 12-23/24-47, sw_flow 12-23/24-47) and
30 SKIP cells (short-lead in every regime — L2 already tracks recent obs,
adding a 14d mean re-introduces stale bias).

Gate: in cells where (regime, lead_band) is SHIP or MARGIN, replace the
post-L3 wg value with (fc_l2 + hour_of_day_correction). Elsewhere the
L3-corrected value passes through unchanged.

Runtime data source:
  hourly.wind_gusts_post_l2      — L2 output stashed by decay_apply
  hourly.times                   — per-lead ISO timestamps for clock hour lookup
  wg_residual_persistence_curated.json — cell verdicts + 24-slot hour-of-day
                                         correction table (mph), refit each
                                         Stage 2 run.

Placement: runs AFTER decay_apply so it overrides the L3-corrected wg value
where the gate fires. Overwrites hourly.wind_gusts in-place, preserving the
pre-gate array as hourly.wind_gusts_post_l3_pre_wgrp for attribution.

When ENABLED=False the module still stamps telemetry so the 7-day live-layer
change gate can watch it. Flip ENABLED=True only after gate agreement across
7 daily reads. See [[feedback_whitelist_promotion_gate]] and
[[feedback_regime_gate_first]].
"""
import json
import logging
from pathlib import Path


ENABLED = False  # Live-layer change gate: 7-day agreement + halves-stability + no-halves-flip before flipping True. Stage 2 preview shipped 2026-07-14.

FIELD = "wg"
HOURLY_KEY = "wind_gusts"
L2_KEY = "wind_gusts_post_l2"

_LEAD_BANDS = [
    ("0-5",   1,  5),
    ("6-11",  6, 11),
    ("12-23", 12, 23),
    ("24-47", 24, 47),
]

_TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / "wg_residual_persistence_curated.json"
_TABLE_CACHE = None

_MAX_ABS_CORRECTION_MPH = 15.0  # sanity clamp; larger => refuse to apply


def _load_table():
    global _TABLE_CACHE
    if _TABLE_CACHE is not None:
        return _TABLE_CACHE
    try:
        _TABLE_CACHE = json.loads(_TABLE_PATH.read_text())
    except FileNotFoundError:
        logging.warning(f"  ⚠  wg residual persistence table missing at {_TABLE_PATH}; gate will not fire")
        _TABLE_CACHE = {"cells": {}, "hourly_correction": {}}
    except Exception as e:
        logging.warning(f"  ⚠  wg residual persistence table load failed: {e}")
        _TABLE_CACHE = {"cells": {}, "hourly_correction": {}}
    return _TABLE_CACHE


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


def describe_applicability():
    table = _load_table()
    cells = table.get("cells", {})
    hc = (table.get("hourly_correction") or {}).get("hour_of_day") or {}
    n_slots = sum(1 for v in hc.values() if v is not None)

    if ENABLED:
        fires_when = ("ENABLED — replaces post-L3 wg with (fc_l2 + hour_of_day_correction) "
                      "when (regime, lead_band) is SHIP or MARGIN. SKIP cells pass through unchanged.")
        state_prefix = "ENABLED True"
    else:
        fires_when = "OFF — ENABLED False. Telemetry stamped for 7-day watch; no wg values modified."
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
        "layer_id": "wg_residual_persistence",
        "name": "wg residual persistence gate (regime × lead_band L2-residual add-on)",
        "category": "specialist",
        "fields": [{
            "field": FIELD,
            "fires_when": fires_when,
            "gated_by": "ENABLED + SHIP/MARGIN verdict per (regime, lead_band) + hour_of_day correction populated",
            "current_state": current_state,
        }],
    }]


def stamp_wg_residual_persistence(weather_data):
    hourly = weather_data.get("hourly") or {}
    arr = hourly.get(HOURLY_KEY)
    if not isinstance(arr, list) or not arr:
        weather_data["wg_residual_persistence"] = {
            "enabled": ENABLED,
            "status": "no_hourly_array",
        }
        return

    l2_arr = hourly.get(L2_KEY)
    times = hourly.get("times") or []

    table = _load_table()
    cells = table.get("cells", {})
    hc_block = table.get("hourly_correction") or {}
    hour_corr = hc_block.get("hour_of_day") or {}

    regime = ((weather_data.get("derived") or {}).get("state") or {}).get("regime_synoptic") or "unknown"

    n_leads = len(arr)
    per_lead_would_apply = [None] * n_leads
    per_lead_bands = [None] * n_leads
    per_lead_fires = [False] * n_leads
    fires_by_band = {name: 0 for name, _, _ in _LEAD_BANDS}
    skips_by_band = {name: 0 for name, _, _ in _LEAD_BANDS}

    l2_available = isinstance(l2_arr, list) and len(l2_arr) == n_leads

    for i in range(n_leads):
        band = _lead_band(i)
        per_lead_bands[i] = band
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
        if corr is None or abs(corr) > _MAX_ABS_CORRECTION_MPH:
            skips_by_band[band] += 1
            continue
        candidate = float(l2_arr[i]) + float(corr)
        per_lead_would_apply[i] = round(candidate, 3)
        per_lead_fires[i] = True
        fires_by_band[band] += 1

    if ENABLED:
        pre_key = f"{HOURLY_KEY}_post_l3_pre_wgrp"
        if pre_key not in hourly:
            hourly[pre_key] = list(arr)
        new_arr = list(arr)
        for i, fires in enumerate(per_lead_fires):
            if fires and per_lead_would_apply[i] is not None:
                new_arr[i] = max(0.0, per_lead_would_apply[i])
        hourly[HOURLY_KEY] = new_arr

    weather_data["wg_residual_persistence"] = {
        "enabled": ENABLED,
        "regime": regime,
        "l2_available": l2_available,
        "fires_by_band": fires_by_band,
        "skips_by_band": skips_by_band,
        "per_lead_would_apply": per_lead_would_apply,
        "table_generated_at": table.get("generated_at"),
        "hourly_correction_fit_asof": hc_block.get("fit_asof"),
    }

    try:
        from . import gate_firing_log
        total_fires = sum(fires_by_band.values())
        total_skips = sum(skips_by_band.values())
        gate_firing_log.record_firing(
            operator="wg_residual_persistence",
            regime=regime,
            by_field={FIELD: {
                "fires": total_fires if ENABLED else 0,
                "skips": total_skips if ENABLED else total_fires + total_skips,
            }},
            leads=n_leads,
        )
    except Exception as e:
        try:
            logging.warning(f"  ⚠  gate_firing record (wg_residual_persistence) failed: {e}")
        except Exception:
            pass

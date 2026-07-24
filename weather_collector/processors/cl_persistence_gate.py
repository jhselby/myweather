"""cl persistence gate — regime x lead_band conditioned bypass for cl.

Successor to `cl_persistence_short_lead.py` (retired 2026-07-24 v0.6.379).
The short-lead gate was a narrow shape hypothesis (all 9 regimes at 0-5h)
awaiting the 07-19 halves-verified re-run. That re-run
(h_cl_persistence_blend_stage2.py) shows the narrow shape is wrong on
two counts: (1) persistence wins BEYOND 0-5h in several regimes
(calm all-leads, se_flow all-leads, unknown all-leads, nw_flow 24-47h);
(2) persistence LOSES at 0-5h in sea_breeze on halves-stability. So the
gate needs full regime x lead_band conditioning, mirroring ch.

Whitelist shape (shorter than blacklist per Stage 2 preview): baseline
by default, use persistence only on SHIP + MARGIN cells. frontal is
excluded from the whitelist by contract (gate uses baseline for frontal
by design; MARGIN 0.0% cells there are a definitional artifact).

Runtime persistence source:
  Preferred: cloud_l2_meta.fields_applied[cloud_cover_low].obs_mean
             (pure KBOS+KBVY blended obs, pre-Kalman-shrinkage).
  Fallback:  hourly[0].cloud_cover_low (Kalman-blended value).
  If neither is available, the gate is a no-op this tick.

Placement: runs AFTER Lc so persistence overwrites Lc output where the
gate fires. Lc was fit against L1 for cl (no L4 exists) and would
re-introduce bias if applied on top of persistence.

Baseline for cl = raw L1 (no L4 correction exists for cl). SKIP cells
and frontal fall back to the L1/Lc value already in the hourly array;
the gate only overwrites when it fires.

When ENABLED=False the module still stamps telemetry (what would be
overwritten) so the 7-day live-layer change gate can watch it. Flip
ENABLED=True only after gate agreement across 7 daily reads. See
[[feedback_whitelist_promotion_gate]] and [[feedback_regime_gate_first]].
"""
import json
import logging
from pathlib import Path


ENABLED = False  # Stage 3 shipped 2026-07-24 v0.6.379. 7-day live-layer change gate: flip earliest 2026-07-31 after 7 daily reads agree on SHIP cell set.

FIELD = "cl"
HOURLY_KEY = "cloud_cover_low"

_LEAD_BANDS = [
    ("0-5",   1,  5),
    ("6-11",  6, 11),
    ("12-23", 12, 23),
    ("24-47", 24, 47),
]

_TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / "cl_persistence_gate_curated.json"
_TABLE_CACHE = None


def _load_table():
    global _TABLE_CACHE
    if _TABLE_CACHE is not None:
        return _TABLE_CACHE
    try:
        _TABLE_CACHE = json.loads(_TABLE_PATH.read_text())
    except FileNotFoundError:
        logging.warning(f"  cl persistence gate table missing at {_TABLE_PATH}; gate will not fire")
        _TABLE_CACHE = {"cells": {}}
    except Exception as e:
        logging.warning(f"  cl persistence gate table load failed: {e}")
        _TABLE_CACHE = {"cells": {}}
    return _TABLE_CACHE


def _lead_band(lead_h):
    for name, lo, hi in _LEAD_BANDS:
        if lo <= lead_h <= hi:
            return name
    return None


def _cell_fires(cells, regime, band):
    """True if (regime, band) is SHIP or MARGIN. frontal always falls to
    baseline regardless of table content (gate contract; frontal MARGIN
    cells are a definitional 0.0% artifact, not a persistence signal)."""
    if regime == "frontal":
        return False
    cell = cells.get(regime, {}).get(band)
    if not cell:
        return False
    verdict = cell.get("verdict")
    return verdict in ("SHIP", "MARGIN")


def _persistence_source(weather_data):
    hourly = weather_data.get("hourly") or {}

    meta = hourly.get("cloud_l2_meta") or {}
    for entry in (meta.get("fields_applied") or []):
        if entry.get("field") == HOURLY_KEY:
            v = entry.get("obs_mean")
            if v is not None:
                return float(v), "cloud_l2_meta.obs_mean"

    arr = hourly.get(HOURLY_KEY)
    if isinstance(arr, list) and arr and arr[0] is not None:
        return float(arr[0]), "hourly[0].cloud_cover_low (Kalman-blended)"

    return None, None


def describe_applicability():
    table = _load_table()
    cells = table.get("cells", {})
    if ENABLED:
        fires_when = ("ENABLED — replaces cl (cloud_cover_low) with "
                      "persistence-of-obs when (regime, lead_band) is SHIP or MARGIN. "
                      "frontal + SKIP cells fall back to baseline (raw L1).")
        state_prefix = "ENABLED True"
    else:
        fires_when = ("OFF — ENABLED False. Telemetry stamped for 7-day watch; "
                      "no cl values modified.")
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
        f"SKIP: {len(skip_cells)} (fall back to baseline), THIN: {len(thin_cells)}. "
        f"frontal always baseline by design."
    )

    return [{
        "layer_id": "cl_persistence_gate",
        "name": "cl persistence gate (regime x lead_band bypass)",
        "category": "specialist",
        "fields": [{
            "field": FIELD,
            "fires_when": fires_when,
            "gated_by": ("ENABLED + SHIP/MARGIN verdict per (regime, lead_band); "
                         "frontal always falls to baseline"),
            "current_state": current_state,
        }],
    }]


def stamp_cl_persistence_gate(weather_data):
    """Stamp `weather_data['cl_persistence_gate']` telemetry per lead.
    When ENABLED=True, overwrite hourly.cloud_cover_low on cells that
    fire; preserve pre-gate array as hourly['cloud_cover_low_post_lc']."""
    hourly = weather_data.get("hourly") or {}
    arr = hourly.get(HOURLY_KEY)
    if not isinstance(arr, list) or not arr:
        weather_data["cl_persistence_gate"] = {
            "enabled": ENABLED,
            "status": "no_hourly_array",
        }
        return

    table = _load_table()
    cells = table.get("cells", {})

    regime = ((weather_data.get("derived") or {}).get("state") or {}).get("regime_synoptic") or "unknown"

    persist_val, persist_src = _persistence_source(weather_data)

    n_leads = len(arr)
    per_lead_would_apply = [None] * n_leads
    per_lead_bands = [None] * n_leads
    per_lead_fires = [False] * n_leads
    fires_by_band = {name: 0 for name, _, _ in _LEAD_BANDS}
    skips_by_band = {name: 0 for name, _, _ in _LEAD_BANDS}

    for i in range(n_leads):
        band = _lead_band(i)
        per_lead_bands[i] = band
        if band is None or persist_val is None:
            continue
        if _cell_fires(cells, regime, band):
            per_lead_would_apply[i] = round(persist_val, 3)
            per_lead_fires[i] = True
            fires_by_band[band] += 1
        else:
            skips_by_band[band] += 1

    if ENABLED and persist_val is not None:
        post_lc_key = f"{HOURLY_KEY}_post_lc"
        if post_lc_key not in hourly:
            hourly[post_lc_key] = list(arr)
        new_arr = list(arr)
        for i, fires in enumerate(per_lead_fires):
            if fires and new_arr[i] is not None:
                new_arr[i] = max(0.0, min(100.0, persist_val))
        hourly[HOURLY_KEY] = new_arr

    weather_data["cl_persistence_gate"] = {
        "enabled": ENABLED,
        "regime": regime,
        "persistence_value": (round(persist_val, 3) if persist_val is not None else None),
        "persistence_source": persist_src,
        "fires_by_band": fires_by_band,
        "skips_by_band": skips_by_band,
        "per_lead_would_apply": per_lead_would_apply,
        "table_generated_at": table.get("generated_at"),
    }

    try:
        from . import gate_firing_log
        total_fires = sum(fires_by_band.values())
        total_skips = sum(skips_by_band.values())
        gate_firing_log.record_firing(
            operator="cl_persistence_gate",
            regime=regime,
            by_field={FIELD: {
                "fires": total_fires if ENABLED else 0,
                "skips": total_skips if ENABLED else total_fires + total_skips,
            }},
            leads=n_leads,
        )
    except Exception as e:
        try:
            logging.warning(f"  gate_firing record (cl_persistence_gate) failed: {e}")
        except Exception:
            pass

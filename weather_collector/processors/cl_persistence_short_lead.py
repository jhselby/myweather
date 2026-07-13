"""cl persistence short-lead gate — narrow 0-5h persistence for cloud_cover_low.

Sibling of [[ch_persistence_gate]] with a much simpler shape. Where ch
has cell-conditioned per (regime × lead_band) SHIP/SKIP verdicts, cl's
Stage 2 preview (h_cl_linear_ramp_stage2.py, 07-12) showed:

  - Halves on regime_gate + persist_only DIVERGE (anomaly-inflated
    recent wins; prior half loses)
  - linear_ramp τ scan monotonic-with-τ (red flag — no natural sweet spot)
  - BUT: 0-5h band ships in all 9 regimes even under τ scan noise

So cl's ship criterion is narrow — persistence at very short lead only,
where the physical signal (obs is fresh, atmosphere hasn't evolved) is
strongest. All 9 regimes SHIP at 0-5h. Longer bands would need a lot
more architecture; not attempted.

Ships ENABLED=False pending post-anomaly halves-verified re-run
(2026-07-19). If halves converge and 0-5h SHIPs hold in the clean
window, flip ENABLED=True. If not, cl gets no gate.

Placement: runs AFTER Lc (same rationale as ch_persistence_gate — Lc's
shift was fit against L4-corrected values; applying it on top of
persistence would re-introduce bias). Runs BEFORE ch_persistence_gate
purely by pipeline order — both are independent and don't touch the
same field.

Persistence source (priority order):
  1. cloud_l2_meta.fields_applied[cloud_cover_low].obs_mean — pure
     KBOS+KBVY blended obs at forecast issue time, pre-Kalman shrinkage.
     Matches h_cl_persistence_blend.py's semantic exactly.
  2. hourly[0].cloud_cover_low — Kalman-blended value (deviates from
     pure obs only when K<1).
  3. Neither present → gate is a no-op this tick.
"""
import json
import logging
from pathlib import Path


ENABLED = False  # Live-layer change gate: 7-day agreement + halves-verified re-run 2026-07-19+ before flipping True. Stage 3 shipped 2026-07-13 v0.6.330.

FIELD = "cl"
HOURLY_KEY = "cloud_cover_low"

_LEAD_BANDS = [
    ("0-5h",   1,  5),
    ("6-11h",  6, 11),
    ("12-23h", 12, 23),
    ("24-47h", 24, 47),
]

_TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / "cl_persistence_gate_curated.json"
_TABLE_CACHE = None


def _load_table():
    """Load and cache the curated cell table. Missing / malformed →
    empty table (gate is a no-op)."""
    global _TABLE_CACHE
    if _TABLE_CACHE is not None:
        return _TABLE_CACHE
    try:
        _TABLE_CACHE = json.loads(_TABLE_PATH.read_text())
    except FileNotFoundError:
        logging.warning(f"  ⚠  cl persistence gate table missing at {_TABLE_PATH}; gate will not fire")
        _TABLE_CACHE = {"cells": {}}
    except Exception as e:
        logging.warning(f"  ⚠  cl persistence gate table load failed: {e}")
        _TABLE_CACHE = {"cells": {}}
    return _TABLE_CACHE


def _lead_band(lead_h):
    for name, lo, hi in _LEAD_BANDS:
        if lo <= lead_h <= hi:
            return name
    return None


def _cell_fires(cells, regime, band):
    """True iff (regime, band) is SHIP. No MARGIN in cl narrow-gate — the
    Stage 2 read gave clean 0-5h SHIPs and clear SKIPs elsewhere."""
    cell = cells.get(regime, {}).get(band)
    if not cell:
        return False
    return cell.get("status") == "SHIP"


def _persistence_source(weather_data):
    """Return (value, source_label) or (None, None). Matches
    ch_persistence_gate._persistence_source semantic exactly, adapted
    for cloud_cover_low."""
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
    """Applicability descriptor for the cl persistence gate."""
    table = _load_table()
    cells = table.get("cells", {})
    if ENABLED:
        fires_when = ("ENABLED — replaces cl (cloud_cover_low) with "
                      "persistence-of-obs when (regime, lead_band) is SHIP. "
                      "Narrow: all 9 regimes SHIP at 0-5h only.")
        state_prefix = "ENABLED True"
    else:
        fires_when = ("OFF — ENABLED False. Telemetry stamped for 7-day watch; "
                      "no cl values modified. Waiting on 07-19 halves-verified "
                      "re-run before flip.")
        state_prefix = "ENABLED False"

    ship_cells, skip_cells = [], []
    for regime, bandmap in cells.items():
        for band, cell in bandmap.items():
            key = f"{regime}/{band}"
            v = cell.get("status")
            if v == "SHIP":
                ship_cells.append(key)
            elif v == "SKIP":
                skip_cells.append(key)
    current_state = (
        f"{state_prefix}. Cells — SHIP: {len(ship_cells)} "
        f"(all 9 regimes at 0-5h), SKIP: {len(skip_cells)} (longer bands)."
    )

    return [{
        "layer_id": "cl_persistence_short_lead",
        "name": "cl persistence gate (short-lead only, all regimes)",
        "category": "specialist",
        "fields": [{
            "field": FIELD,
            "fires_when": fires_when,
            "gated_by": ("ENABLED + SHIP verdict per (regime, lead_band). "
                         "Narrow-gate shape: 0-5h in all 9 regimes."),
            "current_state": current_state,
        }],
    }]


def stamp_cl_persistence_short_lead(weather_data):
    """Stamp `weather_data['cl_persistence_short_lead']` telemetry per
    lead. When ENABLED=True, overwrite `hourly.cloud_cover_low` on cells
    that fire; preserve pre-gate array as
    `hourly['cloud_cover_low_post_lc']` for snapshot attribution."""
    hourly = weather_data.get("hourly") or {}
    arr = hourly.get(HOURLY_KEY)
    if not isinstance(arr, list) or not arr:
        weather_data["cl_persistence_short_lead"] = {
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
    per_lead_fires = [False] * n_leads
    fires_by_band = {name: 0 for name, _, _ in _LEAD_BANDS}
    skips_by_band = {name: 0 for name, _, _ in _LEAD_BANDS}

    for i in range(n_leads):
        band = _lead_band(i)
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

    weather_data["cl_persistence_short_lead"] = {
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
            operator="cl_persistence_short_lead",
            regime=regime,
            by_field={FIELD: {
                "fires": total_fires if ENABLED else 0,
                "skips": total_skips if ENABLED else total_fires + total_skips,
            }},
            leads=n_leads,
        )
    except Exception as e:
        try:
            logging.warning(f"  ⚠  gate_firing record (cl_persistence_short_lead) failed: {e}")
        except Exception:
            pass

"""Shared primitives for persistence-of-obs gate specialists.

Extracted 2026-07-27 v0.6.383 after three concrete specialists shipped:
`ch_persistence_gate` (07-19 v0.6.358), `cl_persistence_gate`
(07-24 v0.6.379), `wd_persistence_gate` (07-27 v0.6.382). All three had
independently-drifted copies of the same table load, band bucketing,
applicability descriptor shape, telemetry envelope, and — as of
v0.6.382p — the same shadow-write pattern.

**This module is the template for the NEXT specialist.** The existing
three still hold their own copies (a follow-up refactor commit will
migrate them once their post-ship watches close; touching them today
during clp/wdp gate windows risks noise on the very watches we want to
read cleanly). New specialists (wgp, dpp, ppp, …) should be written as
thin wrappers over `run_specialist(…)`.

## Two shapes covered

**post-obs bypass** (chp, clp) — fire condition depends only on the
current-state regime + lead band:

    fires_when = _cell_fires(cells, state_curr, band)

**predicted-transition** (wdp) — fires only when the model predicts a
regime CHANGE from current, and the forecast regime + lead band clears
the whitelist:

    fires_when = (state_curr != state_fc[i]) AND _cell_fires(cells, state_fc[i], band)

The `fire_context_for_lead` callable injected into `run_specialist(…)`
returns the fire decision (+ optional per-lead extra metadata) for
lead index i. Everything else — band bucketing, table caching,
telemetry, shadow-write, gate_firing_log, applicability descriptor
— is shared.

## The shadow-write invariant

Every specialist MUST write `hourly[HOURLY_KEY + "_shadow_<short>"]`
unconditionally (independent of ENABLED). The pair log and snapshot
writer read the shadow key; if the write is ENABLED-guarded, the
7-day flip gate evaluates against zero real data. See
[[feedback_persistence_gate_shadow_write]] — this bug bit both wdp
(entire 07-20 → 07-27 shadow week empty) and clp (7-day gate through
07-31 reading zero real data). Fixed v0.6.382p.

`run_specialist(…)` bakes this invariant in; you cannot forget it.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


LEAD_BANDS = [
    ("0-5",   1,  5),
    ("6-11",  6, 11),
    ("12-23", 12, 23),
    ("24-47", 24, 47),
]


def lead_band(lead_h: int) -> Optional[str]:
    for name, lo, hi in LEAD_BANDS:
        if lo <= lead_h <= hi:
            return name
    return None


def load_table(path: Path, gate_label: str) -> dict:
    """Load a curated gate table. Missing / malformed → empty (no-op)."""
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        logging.warning(f"  ⚠  {gate_label} table missing at {path}; gate will not fire")
        return {"cells": {}}
    except Exception as e:
        logging.warning(f"  ⚠  {gate_label} table load failed: {e}")
        return {"cells": {}}


def cell_fires(cells: dict, regime: str, band: str,
               always_skip_regimes: frozenset[str] = frozenset()) -> bool:
    """True if (regime, band) has verdict SHIP or MARGIN. Regimes in
    `always_skip_regimes` are forced-False regardless of table content."""
    if regime in always_skip_regimes:
        return False
    cell = cells.get(regime, {}).get(band)
    if not cell:
        return False
    return cell.get("verdict") in ("SHIP", "MARGIN")


def build_applicability_descriptor(
    *,
    layer_id: str,
    name: str,
    field_name: str,
    enabled: bool,
    fires_when_enabled: str,
    fires_when_disabled: str,
    gated_by: str,
    cells: dict,
    skip_fallback_label: str,
    always_baseline_note: str,
) -> list[dict]:
    """Shared shape of `describe_applicability()` return value."""
    ship, margin, skip, thin = [], [], [], []
    for regime, bandmap in cells.items():
        for band, cell in bandmap.items():
            v = cell.get("verdict")
            key = f"{regime}/{band}"
            if v == "SHIP":     ship.append(key)
            elif v == "MARGIN": margin.append(key)
            elif v == "SKIP":   skip.append(key)
            elif v == "THIN":   thin.append(key)
    state_prefix = f"ENABLED {enabled}"
    current_state = (
        f"{state_prefix}. Cells — SHIP: {len(ship)}, MARGIN: {len(margin)}, "
        f"SKIP: {len(skip)} ({skip_fallback_label}), THIN: {len(thin)}. "
        f"{always_baseline_note}"
    )
    fires_when = fires_when_enabled if enabled else fires_when_disabled
    return [{
        "layer_id": layer_id,
        "name": name,
        "category": "specialist",
        "fields": [{
            "field": field_name,
            "fires_when": fires_when,
            "gated_by": gated_by,
            "current_state": current_state,
        }],
    }]


@dataclass
class SpecialistSpec:
    """Registration record for one persistence-of-obs specialist.

    Injected callables:
      persistence_source(weather_data) -> (value, source_label) | (None, None)
      fire_context_for_lead(weather_data, i, cells, state_curr)
          -> (fires: bool, extra_lead_meta: dict) — extra_lead_meta may
          contain e.g. {"fc_regime": ...} for the predicted-transition shape.
      clamp_value(value: float) -> float
          — e.g. lambda v: max(0.0, min(100.0, v)) for 0-100 cloud pct,
                 lambda v: round(v % 360.0, 1)     for wind direction.
    """
    short_name: str                       # e.g. "chp", "clp", "wdp"
    field: str                            # e.g. "ch"
    hourly_key: str                       # e.g. "cloud_cover_high"
    table_path: Path
    enabled: bool
    pre_gate_hourly_key: str              # preserved copy of pre-gate array
    telemetry_key: str                    # e.g. "ch_persistence_gate"
    operator_label: str                   # e.g. "ch_persistence_gate"
    persistence_source: Callable[[dict], tuple[Optional[float], Optional[str]]]
    fire_context_for_lead: Callable[..., tuple[bool, dict]]
    clamp_value: Callable[[float], float]
    always_skip_regimes: frozenset[str] = field(default_factory=frozenset)
    state_key_in_telemetry: str = "regime"  # "regime" for chp/clp, "state_curr" for wdp


def run_specialist(spec: SpecialistSpec, weather_data: dict) -> None:
    """Stamp telemetry + (if ENABLED) overwrite the hourly array. Writes
    the unconditional shadow array either way — the shadow-write invariant
    is baked in here so no future clone can regress the v0.6.382p fix."""
    hourly = weather_data.get("hourly") or {}
    arr = hourly.get(spec.hourly_key)
    if not isinstance(arr, list) or not arr:
        weather_data[spec.telemetry_key] = {
            "enabled": spec.enabled,
            "status": "no_hourly_array",
        }
        return

    table = load_table(spec.table_path, spec.operator_label)
    cells = table.get("cells", {})

    state_curr = ((weather_data.get("derived") or {}).get("state") or {}).get("regime_synoptic") or "unknown"
    persist_val, persist_src = spec.persistence_source(weather_data)

    n_leads = len(arr)
    per_lead_would_apply: list[Optional[float]] = [None] * n_leads
    per_lead_fires = [False] * n_leads
    per_lead_extra: list[dict] = [{} for _ in range(n_leads)]
    fires_by_band = {name: 0 for name, _, _ in LEAD_BANDS}
    skips_by_band = {name: 0 for name, _, _ in LEAD_BANDS}

    for i in range(n_leads):
        band = lead_band(i)
        if band is None or persist_val is None:
            continue
        fires, extra = spec.fire_context_for_lead(
            weather_data, i, cells, state_curr,
            always_skip_regimes=spec.always_skip_regimes,
        )
        per_lead_extra[i] = extra
        if fires:
            per_lead_would_apply[i] = round(persist_val, 3)
            per_lead_fires[i] = True
            fires_by_band[band] += 1
        else:
            skips_by_band[band] += 1

    # Unconditional shadow-array write — invariant per v0.6.382p /
    # [[feedback_persistence_gate_shadow_write]]. Never make this
    # ENABLED-guarded; the shadow key is what the 7-day flip gate reads.
    shadow_arr = list(arr)
    if persist_val is not None:
        for i, fires in enumerate(per_lead_fires):
            if fires and shadow_arr[i] is not None:
                shadow_arr[i] = spec.clamp_value(persist_val)
    hourly[f"{spec.hourly_key}_shadow_{spec.short_name}"] = shadow_arr

    if spec.enabled and persist_val is not None:
        if spec.pre_gate_hourly_key not in hourly:
            hourly[spec.pre_gate_hourly_key] = list(arr)
        hourly[spec.hourly_key] = shadow_arr

    telemetry = {
        "enabled": spec.enabled,
        spec.state_key_in_telemetry: state_curr,
        "persistence_value": (round(persist_val, 3) if persist_val is not None else None),
        "persistence_source": persist_src,
        "fires_by_band": fires_by_band,
        "skips_by_band": skips_by_band,
        "per_lead_would_apply": per_lead_would_apply,
        "table_generated_at": table.get("generated_at"),
    }
    # Merge per-lead extras (e.g. wdp's per_lead_fc_regime) into telemetry.
    extra_keys: dict[str, list] = {}
    for i, meta in enumerate(per_lead_extra):
        for k, v in meta.items():
            extra_keys.setdefault(k, [None] * n_leads)[i] = v
    telemetry.update(extra_keys)
    weather_data[spec.telemetry_key] = telemetry

    try:
        from . import gate_firing_log
        total_fires = sum(fires_by_band.values())
        total_skips = sum(skips_by_band.values())
        gate_firing_log.record_firing(
            operator=spec.operator_label,
            regime=state_curr,
            by_field={spec.field: {
                "fires": total_fires if spec.enabled else 0,
                "skips": total_skips if spec.enabled else total_fires + total_skips,
            }},
            leads=n_leads,
        )
    except Exception as e:
        try:
            logging.warning(f"  ⚠  gate_firing record ({spec.operator_label}) failed: {e}")
        except Exception:
            pass


# ─────────────────────── ready-made fire_context builders ───────────────────────

def post_obs_bypass_context(weather_data, i, cells, state_curr, *, always_skip_regimes):
    """chp/clp shape — regime is state_curr, same for all leads."""
    band = lead_band(i)
    if band is None:
        return False, {}
    return cell_fires(cells, state_curr, band, always_skip_regimes), {}


def predicted_transition_context_factory(fc_regime_for_lead: Callable[[dict, int], Optional[str]]):
    """wdp shape — fc_regime is per-lead; fires only on predicted transition."""
    def _context(weather_data, i, cells, state_curr, *, always_skip_regimes):
        band = lead_band(i)
        if band is None:
            return False, {}
        fc_regime = fc_regime_for_lead(weather_data, i) or "unknown"
        transition_predicted = (state_curr != fc_regime)
        active = cell_fires(cells, fc_regime, band, always_skip_regimes)
        return (transition_predicted and active), {"fc_regime": fc_regime}
    return _context


# ─────────────────────── minimal usage example ───────────────────────
# See docstring at top of file. Sketch of a new specialist ("wgp"):
#
#     from pathlib import Path
#     from .persistence_gate_base import (
#         SpecialistSpec, run_specialist, post_obs_bypass_context,
#     )
#
#     ENABLED = False
#     _TABLE = Path(__file__).resolve().parent.parent / "data" / "wg_persistence_gate_curated.json"
#
#     def _persistence_source(wd):
#         cur = (wd.get("current") or {}).get("wind_gust")
#         return (float(cur), "current.wind_gust") if cur is not None else (None, None)
#
#     _SPEC = SpecialistSpec(
#         short_name="wgp", field="wg", hourly_key="wind_gusts_10m",
#         table_path=_TABLE, enabled=ENABLED,
#         pre_gate_hourly_key="wind_gusts_10m_pre_wgp",
#         telemetry_key="wg_persistence_gate",
#         operator_label="wg_persistence_gate",
#         persistence_source=_persistence_source,
#         fire_context_for_lead=post_obs_bypass_context,
#         clamp_value=lambda v: max(0.0, v),
#         always_skip_regimes=frozenset({"frontal"}),
#     )
#
#     def stamp_wg_persistence_gate(weather_data):
#         run_specialist(_SPEC, weather_data)
#
# All the boilerplate — shadow-write, telemetry envelope, gate_firing_log,
# band bucketing, table caching, applicability descriptor — is inherited.

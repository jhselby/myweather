"""Lc — cloud saturation-unbiasing (specialist).

Post-L4 correction on cloud fields (cc, cl, cm, ch). For each forecast
lead of each cloud field, look up which value bin the L4-corrected
forecast falls into and subtract the fitted per-(field, bin) bias so the
mean of predictions in that bin matches the mean of the observations we
saw in that bin over the fit window.

Design notes:
  * Domain-scoped specialist: physics of bounded-percentage saturation
    only exists on cloud fields.
  * Per-(field, bin) shift is learned by `analysis/lc_fit.py` and written
    to weather_collector/data/lc_correction_table.json. Only cells with
    verdict=SHIP are ever applied.
  * Corrected value is clamped to [0, 100] — Lc's output feeds a
    percentage field.
  * When ENABLED=False, the module still stamps telemetry (what would be
    applied) so the debug page + digest can watch it before we flip.
  * When ENABLED=True, mutates hourly[field] in place. Preserves the
    pre-Lc array as hourly["<field>_post_l4"] so the forecast snapshot
    can attribute L4 vs (L4+Lc) cleanly, matching the pattern
    stamp_cove_correction uses for Lt.
"""
import json
import logging
from pathlib import Path


ENABLED = True  # Flipped 2026-07-17 v0.6.355 after 8/7-day gate clear, 16 SHIP cells stable, LC_ENABLED READY on divergence report, no cc/cl/cm/ch ANOMALY. Fit shipped 2026-07-04.

# Lc recent-bias gate. When True, consult `lc_recent_bias_gate.json` (emitted
# by analysis/h_lc_recent_bias_gate.py, v0.6.407) and suppress the historical
# Lc shift on cells where recent-window observed bias disagrees with the
# historical fit — the mechanism that broke cl in v0.6.389f.
#
# Runtime contract (also documented in the JSON's `notes` field):
#   for field in fields_cleared AND per_cell[field][bin].gate_apply == False:
#     do NOT apply the historical shift.
#   All other cells (fields not cleared, or gate_apply True/None): existing
#   lc_correction_table behavior.
#
# Shipped OFF 2026-08-14 v0.6.410. Flip to True once at least one field
# clears the recent-bias 7-day gate (earliest 2026-08-15 per today's read:
# ch streak 6/7). Standing plan item 3.
LC_RECENT_BIAS_GATE_ENABLED = True  # flipped 2026-08-15 v0.6.413 — ch cleared 7-day streak; live no-op today (0/3 ch bins gate_apply=False) but ships the self-healing mechanism ahead of any per-bin drift.

CLOUD_FIELDS = ["cc", "cl", "cm", "ch"]

# Emergency cell-skip set (2026-07-30). Two supported shapes:
#   (field, bin)              — skip that cell in every regime
#   (field, regime, bin)      — skip only when state_fc.regime_synoptic matches
# Both checked before the curated-table SHIP lookup fires. Same shape as
# v0.6.382t chp emergency demote — bandages while regime-conditional Lc is
# built out.
#
# See:
#   analysis/output/h_lc_regime_stage0.txt      — divergence-vs-pooled cells
#   analysis/output/h_lc_rolling_window.txt     — 3-day held-out under all windows
#   analysis/output/walkforward_lc_regime.txt   — 10-day walk-forward
_CELL_SKIP = frozenset({
    # cc entries retired 2026-07-30 v0.6.390 — cc is now a derived field
    # (Ccd overwrites hourly.cloud_cover from max(cl_l6, cm_l6, ch_l6)
    # after Lc). cc is in _FIELD_SKIP below, so per-cell demotes are moot.
    # cl entries removed 2026-07-30 v0.6.389f — cl fully off Lc via _FIELD_SKIP,
    # so per-regime demotes for cl are redundant.
})

# Field-level Lc kill.
#   cl (v0.6.389f 2026-07-30): walk-forward showed cl broken under BOTH
#     pooled Lc (-22.15% vs raw) AND regime-conditional Lc (-30.37% vs raw).
#     Held out until fit stabilizes or the architecture changes.
#   cc (v0.6.390 2026-07-30): retired from Lc entirely. cc is HRRR's own
#     internal combine of cl/cm/ch — correcting it independently in
#     parallel with the components was double-correction from day one.
#     Ccd (cc_from_derivation.py, ENABLED=True) overwrites hourly.cloud_cover
#     from max(cl_l6, cm_l6, ch_l6) after Lc. cc is now a derived field.
_FIELD_SKIP = frozenset({"cl", "cc"})

_FIELD_TO_HOURLY_KEY = {
    "cc": "cloud_cover",
    "cl": "cloud_cover_low",
    "cm": "cloud_cover_mid",
    "ch": "cloud_cover_high",
}

_BINS = [
    (0,   5,      "0-5"),
    (5,   20,     "5-20"),
    (20,  50,     "20-50"),
    (50,  80,     "50-80"),
    (80,  95,     "80-95"),
    (95,  100.01, "95-100"),
]

_TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / "lc_correction_table.json"
_TABLE_CACHE = None

_GATE_PATH = Path(__file__).resolve().parent.parent / "data" / "lc_recent_bias_gate.json"
_GATE_CACHE = None


def _load_gate():
    """Load and cache the recent-bias gate table. Missing / malformed →
    empty gate (nothing suppressed). Never raises."""
    global _GATE_CACHE
    if _GATE_CACHE is not None:
        return _GATE_CACHE
    try:
        _GATE_CACHE = json.loads(_GATE_PATH.read_text())
    except FileNotFoundError:
        logging.warning(f"  ⚠  Lc recent-bias gate missing at {_GATE_PATH}; gate is a no-op")
        _GATE_CACHE = {"fields_cleared": [], "per_cell": {}}
    except Exception as e:
        logging.warning(f"  ⚠  Lc recent-bias gate load failed: {e}")
        _GATE_CACHE = {"fields_cleared": [], "per_cell": {}}
    return _GATE_CACHE


def _gate_suppresses(gate, field, bin_lab):
    """Runtime contract: suppress iff LC_RECENT_BIAS_GATE_ENABLED AND
    field in fields_cleared AND per_cell[field][bin_lab].gate_apply == False.
    Returns True → skip the historical shift for this cell."""
    if not LC_RECENT_BIAS_GATE_ENABLED:
        return False
    if field not in (gate.get("fields_cleared") or []):
        return False
    cell = ((gate.get("per_cell") or {}).get(field) or {}).get(bin_lab)
    if not cell:
        return False
    return cell.get("gate_apply") is False


def _load_table():
    """Load and cache the fit table. Missing / malformed file → empty
    table (nothing ships)."""
    global _TABLE_CACHE
    if _TABLE_CACHE is not None:
        return _TABLE_CACHE
    try:
        _TABLE_CACHE = json.loads(_TABLE_PATH.read_text())
    except FileNotFoundError:
        logging.warning(f"  ⚠  Lc fit table missing at {_TABLE_PATH}; Lc will not fire")
        _TABLE_CACHE = {"cells": {}}
    except Exception as e:
        logging.warning(f"  ⚠  Lc fit table load failed: {e}")
        _TABLE_CACHE = {"cells": {}}
    return _TABLE_CACHE


def _bin_of(v):
    for lo, hi, lab in _BINS:
        if lo <= v < hi:
            return lab
    return None


def _shift_for(cells, field, value, regime=None, gate=None):
    """Return (shift, bin_label, demote_reason). demote_reason is one of
    None, 'cell_skip', 'regime_skip', or 'recent_bias_gate' — lets the
    caller distinguish natural SKIPs (verdict != SHIP) from active
    demotes for telemetry."""
    bin_lab = _bin_of(value)
    if bin_lab is None:
        return 0.0, None, None
    cell = cells.get(field, {}).get(bin_lab)
    if not cell:
        return 0.0, bin_lab, None
    if cell.get("verdict") != "SHIP":
        return 0.0, bin_lab, None
    if (field, bin_lab) in _CELL_SKIP:
        return 0.0, bin_lab, "cell_skip"
    if regime is not None and (field, regime, bin_lab) in _CELL_SKIP:
        return 0.0, bin_lab, "regime_skip"
    if gate is not None and _gate_suppresses(gate, field, bin_lab):
        return 0.0, bin_lab, "recent_bias_gate"
    return float(cell.get("shift", 0.0)), bin_lab, None


def describe_applicability():
    """Applicability descriptor for Lc (cloud saturation-unbiasing).
    Four fields (cc, cl, cm, ch). Per-field state respects `_FIELD_SKIP`
    so cc + cl (which Lc no longer touches) don't misleadingly display as
    ENABLED. See weather_collector/data/applicability_map_schema.json.
    """
    table = _load_table()
    cells = table.get("cells", {})
    gate = _load_gate()
    gate_note = ""
    if LC_RECENT_BIAS_GATE_ENABLED:
        cleared = gate.get("fields_cleared") or []
        gate_note = (
            f" + recent-bias gate ENABLED on {sorted(cleared) or '(none cleared yet)'}: "
            f"cell suppressed when per_cell[field][bin].gate_apply == False"
        )
    else:
        gate_note = " + recent-bias gate DISABLED (defensive; flip after ch 7-day streak clears)"

    # Per-field _FIELD_SKIP reasons — one-liner surfaced in fires_when +
    # current_state so the applicability map reads accurately for cc/cl.
    field_skip_reason = {
        "cc": ("cc retired from Lc v0.6.390 (2026-07-30) — cc is a derived "
               "field, overwritten by Ccd (cc_from_derivation.py) from "
               "max(cl_l6, cm_l6, ch_l6) after Lc runs."),
        "cl": ("cl killed from Lc v0.6.389f (2026-07-30) — walk-forward "
               "showed cl broken under both pooled Lc (-22% vs raw) and "
               "regime-conditional (-30%). Held out until architecture "
               "changes (see project_lc_cl_unskip_investigation)."),
    }

    if ENABLED:
        fires_when_active = (
            "ENABLED — fires when the L4-corrected forecast falls in a SHIP-verdict value bin, "
            "except for regime-demoted cells (see _CELL_SKIP)" + gate_note
        )
        state_prefix_active = "ENABLED True"
    else:
        fires_when_active = "OFF — ENABLED False. Telemetry stamped for 7-day watch."
        state_prefix_active = "ENABLED False"

    field_descriptors = []
    for f in CLOUD_FIELDS:
        cell_states = []
        for _, _, lab in _BINS:
            c = cells.get(f, {}).get(lab)
            if not c:
                continue
            cell_states.append(f"{lab}: {c.get('verdict', '?')} (shift {c.get('shift', 0):+.1f})")
        cell_summary = "; ".join(cell_states) if cell_states else "no fit data"

        if f in _FIELD_SKIP:
            reason = field_skip_reason.get(f, "in _FIELD_SKIP; Lc is a no-op for this field")
            fires_when = f"FIELD-SKIPPED — {reason}"
            current_state = (
                f"FIELD-SKIPPED. {reason} Diagnostic cells (would apply if un-skipped): "
                + cell_summary
            )
        else:
            fires_when = fires_when_active
            current_state = f"{state_prefix_active}. Cells for {f}: " + cell_summary

        field_descriptors.append({
            "field": f,
            "fires_when": fires_when,
            "gated_by": ("_FIELD_SKIP membership" if f in _FIELD_SKIP else
                         "ENABLED + SHIP verdict per (field, value_bin) cell"),
            "current_state": current_state,
        })

    return [{
        "layer_id": "Lc",
        "name": "Cloud saturation-unbiasing",
        "category": "specialist",
        "fields": field_descriptors,
    }]


def stamp_cloud_saturation_correction(weather_data):
    """Stamp `weather_data["cloud_saturation_correction"]` with per-lead
    per-field would-be deltas + fit-table meta. When ENABLED, mutate the
    hourly cloud arrays in place, preserving the pre-Lc state under
    `hourly["<field>_post_l4"]`."""
    hourly = weather_data.get("hourly") or {}
    table = _load_table()
    cells = table.get("cells", {})
    gate = _load_gate()
    regime = ((weather_data.get("derived") or {}).get("state") or {}).get("regime_synoptic")

    per_field = {}
    for field in CLOUD_FIELDS:
        hourly_key = _FIELD_TO_HOURLY_KEY[field]
        arr = hourly.get(hourly_key)
        if not arr:
            continue

        field_skipped = field in _FIELD_SKIP

        # Per-lead: bin lookup + shift on the L4-corrected value.
        deltas = [0.0] * len(arr)
        bins = [None] * len(arr)
        fired = 0
        demoted = 0
        gate_suppressed = 0
        if not field_skipped:
            for i, v in enumerate(arr):
                if v is None:
                    continue
                shift, bin_lab, demote_reason = _shift_for(
                    cells, field, v, regime=regime, gate=gate,
                )
                bins[i] = bin_lab
                deltas[i] = shift
                if shift != 0.0:
                    fired += 1
                elif demote_reason == "recent_bias_gate":
                    gate_suppressed += 1
                elif demote_reason in ("cell_skip", "regime_skip"):
                    demoted += 1

        per_field[field] = {
            "hourly_key": hourly_key,
            "deltas": [round(d, 3) for d in deltas],
            "bins": bins,
            "cells_fired": fired,
            "cells_demoted": demoted,
            "cells_gate_suppressed": gate_suppressed,
            "field_skipped": field_skipped,
            "n_leads": len(arr),
        }

        if ENABLED:
            # Preserve the pre-Lc array for forecast-snapshot attribution.
            post_l4_key = f"{hourly_key}_post_l4"
            if post_l4_key not in hourly:
                hourly[post_l4_key] = list(arr)
            corrected = []
            for v, d in zip(arr, deltas):
                if v is None:
                    corrected.append(None)
                else:
                    corrected.append(max(0.0, min(100.0, v + d)))
            hourly[hourly_key] = corrected

    weather_data["cloud_saturation_correction"] = {
        "enabled": ENABLED,
        "fit_table_generated_at": table.get("generated_at"),
        "fit_rules": table.get("fit_rules"),
        "regime_at_apply": regime,
        "cell_skip": sorted([list(x) for x in _CELL_SKIP], key=lambda x: (x[0], len(x), x[-1])),
        "field_skip": sorted(list(_FIELD_SKIP)),
        "recent_bias_gate": {
            "enabled": LC_RECENT_BIAS_GATE_ENABLED,
            "gate_generated_at": gate.get("generated_at"),
            "fields_cleared": gate.get("fields_cleared") or [],
        },
        "per_field": per_field,
    }

    # Log firing for Lc. When ENABLED=False, `cells_fired` is the would-
    # have-fired count → skips. When True, fires.
    try:
        import logging as _logging
        from . import gate_firing_log
        from ..utils import redact_secrets as _redact
        by_field = {}
        for field, meta in per_field.items():
            f = meta.get("cells_fired", 0) or 0
            by_field[field] = {
                "fires": f if ENABLED else 0,
                "skips": 0 if ENABLED else f,
            }
        if by_field:
            gate_firing_log.record_firing(
                operator="Lc", regime=regime,
                by_field=by_field, leads=48,
            )
    except Exception as _e:
        try:
            _logging.warning(f"  ⚠  gate_firing record (Lc) failed: {_redact(_e)}")
        except Exception:
            pass

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

CLOUD_FIELDS = ["cc", "cl", "cm", "ch"]

# Emergency regime demote (2026-07-30). Stage 0 regime × bin sweep
# (analysis/h_lc_regime_stage0.py) surfaced live SHIP cells where pooled Lc
# over-corrects by >20pp for a specific regime. When state_fc.regime_synoptic
# matches, treat the cell as SKIP for this tick regardless of the curated
# table. Same shape as v0.6.382t chp emergency demote — a bandage while
# regime-conditional Lc is built out.
#
#   (field, regime, bin) — see analysis/output/h_lc_regime_stage0.txt divergence table.
_REGIME_SKIP = frozenset({
    ("cc", "ne_flow", "50-80"),   # live shift -27, regime wants  -3 (23pp over) — SKIP-mag verdict
    ("cc", "ne_flow", "80-95"),   # live shift -30, regime wants  -8 (22pp over) — SKIP-Δ verdict
    # cl ne_flow entries removed 2026-07-30 v0.6.389f — cl fully off Lc via _FIELD_SKIP below,
    # so per-regime demotes for cl are redundant.
})

# Field-level Lc kill (2026-07-30 v0.6.389f). Walk-forward validator
# (analysis/walkforward_lc_regime.py) train pre-07-20 / test 07-20→07-30
# showed cl broken under BOTH pooled Lc (-22.15% vs raw) AND regime-conditional
# Lc (-30.37% vs raw). Neither shift-table architecture fits cl's recent
# distribution. Held out from Lc entirely until the fit stabilizes or the
# architecture changes (rolling shorter-lookback fit, shrinkage, etc.).
# cc/cm/ch still get pooled Lc — they either helped (+0.63% / +34% / +36%
# vs raw on held-out) or were flat.
_FIELD_SKIP = frozenset({"cl"})

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


def _shift_for(cells, field, value, regime=None):
    """Return the (shift, bin_label, demoted) that Lc would apply to `value`
    for `field`, or (0.0, None, False) if the cell is not SHIP or the value
    is out of range. If (field, regime, bin_lab) is in `_REGIME_SKIP`, the
    shift is zeroed and `demoted=True` is returned so the caller can log
    the demote separately from natural SKIPs."""
    bin_lab = _bin_of(value)
    if bin_lab is None:
        return 0.0, None, False
    cell = cells.get(field, {}).get(bin_lab)
    if not cell:
        return 0.0, bin_lab, False
    if cell.get("verdict") != "SHIP":
        return 0.0, bin_lab, False
    if regime is not None and (field, regime, bin_lab) in _REGIME_SKIP:
        return 0.0, bin_lab, True
    return float(cell.get("shift", 0.0)), bin_lab, False


def describe_applicability():
    """Applicability descriptor for Lc (cloud saturation-unbiasing).
    Four fields (cc, cl, cm, ch). See
    weather_collector/data/applicability_map_schema.json."""
    table = _load_table()
    cells = table.get("cells", {})
    if ENABLED:
        fires_when_tmpl = (
            "ENABLED — fires when the L4-corrected forecast falls in a SHIP-verdict value bin, "
            "except for regime-demoted cells (see _REGIME_SKIP)"
        )
        state_prefix = "ENABLED True"
    else:
        fires_when_tmpl = "OFF — ENABLED False. Telemetry stamped for 7-day watch."
        state_prefix = "ENABLED False"

    field_descriptors = []
    for f in CLOUD_FIELDS:
        cell_states = []
        for _, _, lab in _BINS:
            c = cells.get(f, {}).get(lab)
            if not c:
                continue
            cell_states.append(f"{lab}: {c.get('verdict', '?')} (shift {c.get('shift', 0):+.1f})")
        current_state = f"{state_prefix}. Cells for {f}: " + "; ".join(cell_states) if cell_states else f"{state_prefix}. No fit data for {f}."
        field_descriptors.append({
            "field": f,
            "fires_when": fires_when_tmpl,
            "gated_by": "ENABLED + SHIP verdict per (field, value_bin) cell",
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
        if not field_skipped:
            for i, v in enumerate(arr):
                if v is None:
                    continue
                shift, bin_lab, was_demoted = _shift_for(cells, field, v, regime=regime)
                bins[i] = bin_lab
                deltas[i] = shift
                if shift != 0.0:
                    fired += 1
                elif was_demoted:
                    demoted += 1

        per_field[field] = {
            "hourly_key": hourly_key,
            "deltas": [round(d, 3) for d in deltas],
            "bins": bins,
            "cells_fired": fired,
            "cells_demoted": demoted,
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
        "regime_skip_cells": sorted(list(_REGIME_SKIP)),
        "field_skip": sorted(list(_FIELD_SKIP)),
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

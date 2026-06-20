"""
L6 confidence layer — stamps per-(field, band) uncertainty bands on transition
hours. Gated OFF in Stage 3.

Premise (2026-06-19 pivot): the regime-transition penalty is real but uncorrectable
by point-estimate bias subtraction (multiple formulations of regime_bias and
l1_fallback ruled out under leakage-free per-cutoff tests). The honest response
is to widen — or narrow — the displayed uncertainty band, not move the forecast
value. Some (field, band) cells actually narrow on transitions (cloud cover/low/
mid/high and precip-prob at short leads — when a front is moving the cloud
structure is determined; in stable regimes the model has to guess patchy
distributions and gets them wrong more often).

Calibration source: analysis/output/l6_confidence_curated.json (Stage 2 curated
table). Cells are tagged SHIP / MARGINAL / REVIEW / SKIP. Stage 3 wires
SHIP and MARGINAL; ignores REVIEW (manual outlier flag) and SKIP (below
sample or magnitude floor).

Detection (Stage 3 simplification — mirrors solar_correction.py):
  classify the current observed regime inline; compare to the model's currently-
  predicted regime (derived.state.regime_synoptic). On mismatch, the transition
  band is applied to ALL forecast hours. A per-hour classification (more
  accurate) is reserved for Stage 4 if calibration justifies it.

Output:
  weather_data["confidence"] = {
    "applied":       False,             # ENABLED flag echoed for transparency
    "in_transition": bool,
    "regime_obs":    str,
    "regime_pred":   str,
    "cells":         {field: {band: {stable_mae, transition_mae, displayed_mae, direction}, …}}
  }
Does NOT modify any forecast value; this is the first non-MAE-reducing layer
(see [[project-l6-pivot-to-confidence]]).
"""
import json
import logging
import os
from datetime import datetime

import pytz

from .regime_classifier import classify_synoptic_regime


# Flip True after Stage 4 wires the UI to read confidence bands AND the
# calibration audit confirms displayed bands contain truth at the claimed rate.
ENABLED = False

# Wire SHIP and MARGINAL statuses. REVIEW + SKIP are intentionally excluded —
# REVIEW means a cell contradicts its field's dominant direction (manual gate);
# SKIP means below sample or magnitude floor.
_WIRED_STATUSES = ("SHIP", "MARGINAL")

# Path to the Stage 2 curated table. Lives under weather_collector/data/ (the
# collector tree) so it ships with the Cloud Function deploy. The analysis/
# output/ tree is .gitignore'd and would not be uploaded.
_CURATED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "l6_confidence_curated.json",
)

TZ = pytz.timezone("America/New_York")
MB_TO_INHG = 1.0 / 33.8639


def _load_curated_table():
    """Read the Stage 2 curated table. Returns the cells dict keyed by
    (field, band), filtered to SHIP/MARGINAL only. Empty dict on missing file
    — confidence layer becomes a no-op rather than failing the collector run.
    """
    try:
        with open(_CURATED_PATH) as f:
            doc = json.load(f)
    except FileNotFoundError:
        logging.warning(f"  ⚠ confidence_layer: curated table missing at {_CURATED_PATH}")
        return {}
    except Exception as e:
        logging.warning(f"  ⚠ confidence_layer: curated table load failed: {e}")
        return {}

    wired = {}
    for field, bands in (doc.get("cells") or {}).items():
        for band, entry in bands.items():
            if entry.get("status") not in _WIRED_STATUSES:
                continue
            wired.setdefault(field, {})[band] = {
                "stable_mae":     entry["stable_mae"],
                "transition_mae": entry["transition_mae"],
                "direction":      entry["direction"],
                "premium_pct":    entry["premium_pct"],
                "status":         entry["status"],
            }
    return wired


# Load once at import — the table changes only when the Stage 2 curation script
# is re-run, and re-importing the processor module is required for collector
# reload anyway.
_CURATED_CELLS = _load_curated_table()


def _classify_current_regime(weather_data):
    """Classify the live regime from current observed conditions. Returns
    None if any required field is missing — caller treats that as "no
    transition detection available," not "no transition."
    """
    cur = weather_data.get("current") or {}
    derived = weather_data.get("derived") or {}
    try:
        pressure_in = None
        p_hpa = cur.get("pressure")
        if p_hpa is not None:
            pressure_in = p_hpa * MB_TO_INHG
        now_local = datetime.now(TZ)
        return classify_synoptic_regime(
            wind_dir_deg=cur.get("wind_direction"),
            wind_speed_mph=cur.get("wind_speed"),
            pressure_in=pressure_in,
            pressure_trend_3h=derived.get("pressure_trend_hpa_3h"),
            hour_local=now_local.hour,
            temp_f=cur.get("temperature"),
        )
    except Exception as e:
        logging.warning(f"  ⚠ confidence_layer: regime classify failed: {e}")
        return None


def stamp_confidence(weather_data):
    """Stamp the candidate confidence-band table on `weather_data["confidence"]`.

    Does NOT mutate any forecast value, regardless of ENABLED — this is by
    design (L6 is non-MAE-reducing). The ENABLED flag only controls whether
    downstream UI should treat the stamped values as authoritative.
    """
    # Predicted regime: prefer the joiner-stamped value when present (rare in
    # live runs since the joiner stamps on pair-log records, not forecasts);
    # fall back to inline classification of current state.
    derived = weather_data.get("derived") or {}
    state = derived.get("state") or {}
    regime_pred = state.get("regime_synoptic") or _classify_current_regime(weather_data)
    regime_obs  = _classify_current_regime(weather_data)

    in_transition = bool(
        regime_pred and regime_obs and regime_pred != regime_obs
    )

    cells_out = {}
    for field, bands in _CURATED_CELLS.items():
        cells_out[field] = {}
        for band, entry in bands.items():
            stable = entry["stable_mae"]
            transit = entry["transition_mae"]
            cells_out[field][band] = {
                "stable_mae":     stable,
                "transition_mae": transit,
                # The value the UI should display. Mirrors transition_mae when
                # in_transition (regardless of direction — NARROW cells claim
                # smaller bands on transitions, that's what they're for).
                "displayed_mae":  transit if in_transition else stable,
                "direction":      entry["direction"],
                "premium_pct":    entry["premium_pct"],
                "status":         entry["status"],
            }

    weather_data["confidence"] = {
        "applied":       ENABLED,
        "in_transition": in_transition,
        "regime_obs":    regime_obs,
        "regime_pred":   regime_pred,
        "n_cells":       sum(len(v) for v in cells_out.values()),
        "cells":         cells_out,
        "note": (
            "Candidate L6 confidence-layer bands. Gated OFF until UI calibration "
            "audit confirms displayed bands contain truth at the claimed rate."
            if not ENABLED else
            "L6 confidence-layer bands applied (read by UI for transition-aware uncertainty)."
        ),
    }

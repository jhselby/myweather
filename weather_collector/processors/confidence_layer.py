"""
C1 confidence layer — stamps per-(field, band) uncertainty bands on transition
hours. Gated OFF in Stage 3.

Premise (2026-06-19 pivot): the regime-transition penalty is real but uncorrectable
by point-estimate bias subtraction (multiple formulations of regime_bias and
l1_fallback ruled out under leakage-free per-cutoff tests). The honest response
is to widen — or narrow — the displayed uncertainty band, not move the forecast
value. Some (field, band) cells actually narrow on transitions (cloud cover/low/
mid/high and precip-prob at short leads — when a front is moving the cloud
structure is determined; in stable regimes the model has to guess patchy
distributions and gets them wrong more often).

Calibration source: analysis/output/c1_confidence_curated.json (Stage 2 curated
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
(see [[project-c1-pivot-to-confidence]]).
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
#
# v2 (multi-axis) takes precedence when present — it carries both the legacy
# single-axis fields AND the by_axes sub-table needed for cluster-spread +
# pt-aware lookups. Falls back to v1 if v2 hasn't been generated yet.
_CURATED_PATH_V2 = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "c1_confidence_curated_v2.json",
)
_CURATED_PATH_V1 = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "c1_confidence_curated.json",
)
_CURATED_PATH = _CURATED_PATH_V2 if os.path.exists(_CURATED_PATH_V2) else _CURATED_PATH_V1

TZ = pytz.timezone("America/New_York")
MB_TO_INHG = 1.0 / 33.8639


def _load_curated_table():
    """Read the Stage 2 curated table. Returns (wired_cells, meta).
      wired_cells: {field: {band: {legacy fields..., "by_axes": {key: {mae, n, status, direction}, …}}}}
      meta: {"spread_cuts": {q1, q3}, "pt_bins": [...]} or None if v1.

    Empty dict on missing file — confidence layer becomes a no-op rather than
    failing the collector run.
    """
    try:
        with open(_CURATED_PATH) as f:
            doc = json.load(f)
    except FileNotFoundError:
        logging.warning(f"  ⚠ confidence_layer: curated table missing at {_CURATED_PATH}")
        return {}, None
    except Exception as e:
        logging.warning(f"  ⚠ confidence_layer: curated table load failed: {e}")
        return {}, None

    wired = {}
    for field, bands in (doc.get("cells") or {}).items():
        for band, entry in bands.items():
            if entry.get("status") not in _WIRED_STATUSES:
                # Even if the legacy axis SKIPs, multi-axis cells may have signal.
                # Keep the entry but mark legacy as not-applicable.
                if not (entry.get("by_axes") or {}):
                    continue
            cell = {
                "stable_mae":     entry["stable_mae"],
                "transition_mae": entry["transition_mae"],
                "direction":      entry.get("direction"),
                "premium_pct":    entry.get("premium_pct"),
                "status":         entry.get("status"),
                "by_axes":        {},
            }
            for axis_key, ax in (entry.get("by_axes") or {}).items():
                if ax.get("status") not in _WIRED_STATUSES:
                    continue
                cell["by_axes"][axis_key] = {
                    "mae":       ax["mae"],
                    "n":         ax["n"],
                    "direction": ax.get("direction"),
                    "status":    ax.get("status"),
                }
            wired.setdefault(field, {})[band] = cell

    meta = None
    sm = doc.get("stage1_meta") or {}
    if sm.get("spread_cuts") and sm.get("pt_bins"):
        meta = {
            "spread_cuts": sm["spread_cuts"],
            "pt_bins":     sm["pt_bins"],
        }
    return wired, meta


# Load once at import — the table changes only when the Stage 2 curation script
# is re-run, and re-importing the processor module is required for collector
# reload anyway.
_CURATED_CELLS, _CURATED_META = _load_curated_table()


def _current_spread_quartile(weather_data):
    """Classify the live cluster_spread into Q1 / Q23 / Q4 using the cuts
    from the curated table's stage1_meta. Returns None if either side missing."""
    if not _CURATED_META:
        return None
    cuts = _CURATED_META.get("spread_cuts") or {}
    q1, q3 = cuts.get("q1"), cuts.get("q3")
    cs = (weather_data.get("cluster_spread") or {}).get("spread_t")
    if cs is None or q1 is None or q3 is None:
        return None
    if cs <= q1:
        return "Q1"
    if cs >= q3:
        return "Q4"
    return "Q23"


def _current_pt_bin(weather_data):
    """Classify the live pressure_trend_hpa_3h via the curated table's pt_bins."""
    if not _CURATED_META:
        return None
    derived = weather_data.get("derived") or {}
    pt = derived.get("pressure_trend_hpa_3h")
    if pt is None:
        return None
    for spec in _CURATED_META.get("pt_bins") or []:
        lo = spec.get("lo") if spec.get("lo") is not None else float("-inf")
        hi = spec.get("hi") if spec.get("hi") is not None else float("inf")
        if lo <= pt < hi:
            return spec["label"]
    return None


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
    design (C1 is non-MAE-reducing). The ENABLED flag only controls whether
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

    # Compute the live axis values once — they don't vary across (field, band).
    spread_q = _current_spread_quartile(weather_data)
    pt_label = _current_pt_bin(weather_data)
    trans_label = "transition" if in_transition else "stable"
    axis_key = (f"{spread_q}::{pt_label}::{trans_label}"
                if (spread_q and pt_label) else None)

    cells_out = {}
    multi_hits = 0
    for field, bands in _CURATED_CELLS.items():
        cells_out[field] = {}
        for band, entry in bands.items():
            stable = entry["stable_mae"]
            transit = entry["transition_mae"]
            # Legacy displayed_mae — what a v1-aware UI sees.
            legacy_displayed = transit if in_transition else stable
            # Multi-axis lookup. If the specific (spread_q × pt_bin × trans)
            # cell is wired, prefer that. Otherwise fall back to legacy.
            axis_mae = None
            axis_direction = None
            axis_status = None
            if axis_key:
                hit = (entry.get("by_axes") or {}).get(axis_key)
                if hit:
                    axis_mae = hit["mae"]
                    axis_direction = hit.get("direction")
                    axis_status = hit.get("status")
                    multi_hits += 1
            displayed_mae = axis_mae if axis_mae is not None else legacy_displayed

            cells_out[field][band] = {
                "stable_mae":     stable,
                "transition_mae": transit,
                "displayed_mae":  displayed_mae,
                "direction":      axis_direction or entry.get("direction"),
                "premium_pct":    entry.get("premium_pct"),
                "status":         axis_status or entry.get("status"),
                "axis_source":    ("multi" if axis_mae is not None else "legacy"),
            }

    weather_data["confidence"] = {
        "applied":       ENABLED,
        "in_transition": in_transition,
        "regime_obs":    regime_obs,
        "regime_pred":   regime_pred,
        "n_cells":       sum(len(v) for v in cells_out.values()),
        "cells":         cells_out,
        "live_axes": {
            "spread_quartile": spread_q,
            "pt_bin":          pt_label,
            "axis_key":        axis_key,
            "multi_hits":      multi_hits,
            "table_version":   "v2" if _CURATED_PATH.endswith("_v2.json") else "v1",
        },
        "note": (
            "Candidate C1 confidence-layer bands. Gated OFF until UI calibration "
            "audit confirms displayed bands contain truth at the claimed rate."
            if not ENABLED else
            "C1 confidence-layer bands applied (read by UI for transition-aware uncertainty)."
        ),
    }

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
from datetime import datetime, timedelta

import pytz

from ..gcs_io import load_json
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

# Standalone marginal-premium tables. Both are stamp-time multipliers that
# compose on top of the base displayed_mae (legacy or multi-axis lookup).
# See analysis/c1h_calibration.py + analysis/c1d_calibration.py for how the
# tables were built; c1h_curate.py + c1d_curate.py apply SHIP/MARGINAL gating.
_C1H_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "c1h_curated.json",
)
_C1D_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "c1d_curated.json",
)

TZ = pytz.timezone("America/New_York")
MB_TO_INHG = 1.0 / 33.8639


def describe_applicability():
    """Applicability descriptor for C1 (confidence layer). C1 doesn't fit the
    per-field model the other layers use — it widens/narrows uncertainty bands
    along orthogonal AXES that cross multiple (field, band) cells via a curated
    lookup table. Uses an 'axes' subkey instead of 'fields'. See the C1 note
    in weather_collector/data/applicability_map_schema.json.
    """
    axes = [
        {
            "axis_id": "C1a",
            "name": "Regime transition",
            "fires_when": "state_obs.regime_synoptic != state_pred.regime_synoptic at run time",
        },
        {
            "axis_id": "C1f",
            "name": "Pre-frontal proximity",
            "fires_when": "hours_until_front <= 6 (per-band)",
        },
        {
            "axis_id": "pt_bin",
            "name": "Pressure tendency band",
            "fires_when": "current pressure trend bin (rising/falling/stable) from snapshot pressure_trend_hpa_3h",
        },
        {
            "axis_id": "cluster_spread",
            "name": "Mesonet cluster spread quartile",
            "fires_when": "Q1-Q4 quartile of current-tick station-cluster spread (multi-axis lookup only)",
        },
        {
            "axis_id": "C1e",
            "name": "Hours since front (post-frontal window)",
            "fires_when": (
                "hours since most recent frontal passage < 24 (post) vs ≥ 24 (baseline). "
                "Live axis stamped on weather_data.confidence.live_axes.hsf_group; "
                "multi-axis widening lookup wired via 5-tuple axis_key. Post-2026-07-01 "
                "curated tables emit hsf-keyed cells; earlier tables fall back to legacy."
            ),
        },
        {
            "axis_id": "C1h",
            "name": "Trend direction (6h forecast shift)",
            "fires_when": (
                "|forecast_l1[lead] − forecast_l1[lead−6]| > per-field threshold "
                f"(cc 20, cl 15, cm 15, ch 15, t 3), AND the per-cell co-axis "
                f"ortho gate permits. 2026-07-10: h_c1h_orthogonality first "
                f"read (11/30 orthogonal cells overall) surfaced per-cell "
                f"double-count risk vs C1f (precip_fc) and C1e (post-frontal). "
                f"Only cl × 3 bands fire freely; cc/cm/ch/t cells are gated on "
                f"the axis they're non-orthogonal to (or skipped entirely for "
                f"cells REDUND to both — all t cells, ch 24-47h). Wired "
                f"2026-07-08 as a marginal multiplier composed on top of the "
                f"base displayed_mae; reads {os.path.basename(_C1H_PATH)} + "
                f"the in-code _C1H_CO_AXIS_GATE table."
            ),
        },
        {
            "axis_id": "C1d",
            "name": "Cloud KBOS-vs-KBVY disagreement",
            "fires_when": (
                "current cloud_inter_source_sigma ≥ Q3 (high-disagreement slot). "
                f"Wired 2026-07-08 as a marginal multiplier composed on top of "
                f"the base displayed_mae; reads {os.path.basename(_C1D_PATH)}."
            ),
        },
    ]
    if ENABLED:
        current_state = (
            "ENABLED True; stamping displayed bands via curated table at "
            f"{os.path.basename(_CURATED_PATH)} for cells with status in {_WIRED_STATUSES}"
        )
    else:
        current_state = (
            "ENABLED False — confidence block is stamped on weather_data for transparency "
            "but bands are NOT shown to users. Flip after Stage 4 calibration audit."
        )
    return [
        {
            "layer_id": "C1",
            "name": "Confidence layer",
            "category": "confidence",
            "axes": axes,
            "gated_by": "ENABLED",
            "current_state": current_state,
            "notes": (
                "Does NOT modify any forecast value. Curated cells with status in "
                f"{_WIRED_STATUSES} are wired; REVIEW + SKIP excluded."
            ),
        }
    ]


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


def _load_marginal_table(path, slot_names):
    """Load a marginal-premium curated table (c1h or c1d shape).
    Returns (cells, meta) where cells is {field: {band: {direction, premium_pct,
    status}}} filtered to SHIP/MARGINAL, and meta is the file-level dict
    (sigma_cuts, thresholds, etc.) or {}.
    """
    try:
        with open(path) as f:
            doc = json.load(f)
    except FileNotFoundError:
        logging.warning(f"  ⚠ confidence_layer: marginal table missing at {path}")
        return {}, {}
    except Exception as e:
        logging.warning(f"  ⚠ confidence_layer: marginal table load failed at {path}: {e}")
        return {}, {}
    out = {}
    for field, bands in (doc.get("cells") or {}).items():
        for band, entry in bands.items():
            if entry.get("status") not in _WIRED_STATUSES:
                continue
            direction = entry.get("direction")
            pct = entry.get("premium_pct")
            if direction not in ("WIDEN", "NARROW") or pct is None:
                continue
            out.setdefault(field, {})[band] = {
                "direction":   direction,
                "premium_pct": float(pct),
                "status":      entry.get("status"),
            }
    meta = {k: v for k, v in doc.items() if k != "cells"}
    return out, meta


_C1H_CELLS, _C1H_META = _load_marginal_table(_C1H_PATH, ("flat", "fires"))
_C1D_CELLS, _C1D_META = _load_marginal_table(_C1D_PATH, ("low", "high"))
_C1H_THRESH = (_C1H_META.get("stage1_meta") or {}).get("thresholds") or {}
_C1D_SIGMA_CUTS = _C1D_META.get("sigma_cuts") or {}


# Field-to-hourly-array mapping for C1h L1 lookup at stamp time. C1h fires
# when |L1[lead] − L1[lead-6]| exceeds THRESH for the target hour. Uses the
# raw / L1 arrays so the axis reads the model's own trend, not our L4 output.
_C1H_L1_KEY = {
    "cc": "raw_cloud_cover",
    "cl": "raw_cloud_cover_low",
    "cm": "raw_cloud_cover_mid",
    "ch": "raw_cloud_cover_high",
    "t":  "temperature",  # raw t is 'temperature' (no raw_ prefix; L1 = model)
}

# Snapshot-log lookup keys for each field (matches forecast_snapshot.py's
# per-layer stamps: field_l1). We use the L1 value from the ~6h-old snapshot
# for the same target hour.
_C1H_SNAP_KEY = {
    "cc": "cc_l1",
    "cl": "cl_l1",
    "cm": "cm_l1",
    "ch": "ch_l1",
    "t":  "t_l1",
}

# Band midpoint hours used to pick the representative target for C1h stamp-time
# firing. The per-band aggregation is a simplification of the per-hour axis;
# calibration averaged premium across all hours in the band, so the midpoint
# is a reasonable representative. See CLAUDE.md rule 4 — the actual per-band
# firing rate over time will show whether midpoint is close enough.
_C1H_BAND_MID = {
    "6-11h":  9,
    "12-23h": 18,
    "24-47h": 36,
}

# Per-cell co-axis ortho gate. Source: h_c1h_orthogonality.py first read
# 2026-07-10 (see analysis/output/runlog/h_c1h_orthogonality.log). C1h passed
# the overall PROMOTE gate (11 orthogonal cells / 30 judged), but per-cell
# only cl × 3 bands are ortho to BOTH C1f (precip_fc > 0.01) and C1e
# (post-frontal < 24h). The remaining 12 SHIP cells are wholly-or-partially
# redundant with a co-axis — firing them when that co-axis is on would
# double-widen the confidence band without adding independent signal.
#
# Semantics per cell:
#   require_c1f_off = True  → suppress fire when C1f (precip_fc>0 in band) is on
#   require_c1e_off = True  → suppress fire when C1e (post-frontal <24h) is on
#   always_skip     = True  → REDUND to both axes; never fire (signal is fully
#                             captured by the incumbent axes)
# Cells not listed here have no gate (fire whenever threshold met). Any new
# c1h cell added to the curated table must be added here explicitly — the
# fire path defaults to "always allow" and needs an ortho verdict to gate.
_C1H_CO_AXIS_GATE = {
    ("cl", "6-11h"):  {},   # ORTHO/ORTHO — fire freely
    ("cl", "12-23h"): {},
    ("cl", "24-47h"): {},
    ("cc", "6-11h"):  {"require_c1e_off": True},   # ORTHO F, AMBIG E
    ("cc", "12-23h"): {"require_c1e_off": True},
    ("cc", "24-47h"): {"require_c1f_off": True, "require_c1e_off": True},  # CONFOUND F, AMBIG E
    ("cm", "6-11h"):  {"require_c1f_off": True},   # AMBIG F, ORTHO E
    ("cm", "12-23h"): {"require_c1f_off": True},
    ("cm", "24-47h"): {"require_c1f_off": True},
    ("ch", "6-11h"):  {"require_c1f_off": True, "require_c1e_off": True},  # AMBIG F, CONFOUND E
    ("ch", "12-23h"): {"require_c1f_off": True, "require_c1e_off": True},
    ("ch", "24-47h"): {"always_skip": True},                                # REDUND both
    ("t",  "6-11h"):  {"always_skip": True},                                # REDUND both
    ("t",  "12-23h"): {"always_skip": True},
    ("t",  "24-47h"): {"always_skip": True},
}


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


_C1F_BAND_LEADS = {
    "0-5h":   (0, 6),
    "6-11h":  (6, 12),
    "12-23h": (12, 24),
    "24-47h": (24, 48),
}


def _c1f_per_band(weather_data):
    """Per-band C1f flag: "p1" if hourly precipitation forecast > 0 anywhere in
    that band's lead window, "p0" otherwise. Returns {band_label: "p0"|"p1"|None}.
    Mirrors how state_fc.precip_in was used in the v3 calibration — each pair-log
    row inherited the precip flag of its specific target hour.
    """
    h = weather_data.get("hourly") or {}
    precip = h.get("precipitation") or []
    if not precip:
        return {band: None for band in _C1F_BAND_LEADS}
    out = {}
    for band, (lo, hi) in _C1F_BAND_LEADS.items():
        window = precip[lo:hi]
        if not window:
            out[band] = None
            continue
        out[band] = "p1" if any((v or 0) > 0 for v in window) else "p0"
    return out


# C1e — hours-since-front axis. 2026-07-01 h_hsf_orthogonality promotion:
# 9 ORTHOGONAL cells / 23 REDUNDANT / 4 AMBIGUOUS vs C1a; strongest on
# ch (all bands), cm (all bands), cc long-lead, cl 6-11h. Post-frontal
# window = 24h; ≥24h since last passage = baseline. Stamped live here as
# telemetry — actual widening kicks in once the Stage 2 v2 curator is
# extended to include hsf as a 5th key dimension in the by_axes table.
_C1E_POST_WINDOW_H = 24


def _current_hsf_group(weather_data):
    """Classify current hour into 'post' (0-24h since last front) or
    'baseline' (≥24h). Reads the frontal_events_log written by
    frontal_detection.py. Returns None if the log can't be loaded or no
    passages are on record — the multi-axis lookup treats None as
    "axis unavailable, use legacy fallback."
    """
    try:
        doc = load_json("frontal_events_log.json", default={}) or {}
    except Exception as e:
        logging.debug(f"  ⚠ confidence_layer C1e: frontal log load failed: {e}")
        return None
    events = doc.get("events") or doc.get("entries") or doc.get("frontal_events") or []
    if not events and isinstance(doc, list):
        events = doc
    if not events:
        return None
    now = datetime.now(TZ).replace(second=0, microsecond=0)
    now_naive = datetime(now.year, now.month, now.day, now.hour, now.minute)
    latest = None
    for e in events:
        ts = e.get("ts") or e.get("timestamp") or e.get("when")
        if not ts:
            continue
        try:
            ts_clean = ts.replace("Z", "").replace("+00:00", "")
            dt = datetime.fromisoformat(ts_clean[:19])
        except Exception:
            continue
        if dt <= now_naive and (latest is None or dt > latest):
            latest = dt
    if latest is None:
        return None
    hours = (now_naive - latest).total_seconds() / 3600.0
    return "post" if hours < _C1E_POST_WINDOW_H else "baseline"


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


def _current_c1d_slot(weather_data):
    """Classify current cloud_inter_source_sigma into 'low'/'high'/None.
    Middle-band (Q1 < σ < Q3) returns None → axis inactive at this tick.
    Cuts come from the curated file (analysis-side pins them via c1d_calibration.py).
    """
    q1 = _C1D_SIGMA_CUTS.get("q1")
    q3 = _C1D_SIGMA_CUTS.get("q3")
    if q1 is None or q3 is None:
        return None
    derived = weather_data.get("derived") or {}
    sigma = derived.get("cloud_inter_source_sigma")
    if sigma is None:
        return None
    if sigma <= q1:
        return "low"
    if sigma >= q3:
        return "high"
    return None


def _load_prior_snapshot(hours_ago):
    """Return the forecast_log snapshot whose run_stamp is closest to
    `hours_ago` hours before now, or None. The snapshot log is written once
    per collector tick (~10 min); we round to the nearest available entry.
    """
    try:
        doc = load_json("forecast_log.json", default={"snapshots": []}) or {}
    except Exception as e:
        logging.debug(f"  ⚠ confidence_layer C1h: forecast_log load failed: {e}")
        return None
    snapshots = doc.get("snapshots") or []
    if not snapshots:
        return None
    target = datetime.now(TZ).replace(second=0, microsecond=0)
    target_naive = datetime(target.year, target.month, target.day,
                            target.hour, target.minute)
    target_naive -= timedelta(hours=hours_ago)
    best = None
    best_dt = None
    best_delta = None
    for s in snapshots:
        rs = s.get("run")
        if not rs:
            continue
        try:
            dt = datetime.fromisoformat(rs[:19])
        except Exception:
            continue
        delta = abs((dt - target_naive).total_seconds())
        if best is None or delta < best_delta:
            best = s
            best_dt = dt
            best_delta = delta
    # Guardrail: reject if best match is >90 min off — the snapshot log
    # probably has a gap and C1h should silently skip rather than fire on
    # stale data.
    if best is None or best_delta > 90 * 60:
        return None
    return best


def _c1h_fires_per_band_field(weather_data):
    """For each (field, band), decide whether C1h fires at stamp time.
    Compares the current forecast_l1 for the band's representative target
    hour against the L1 value at the same absolute target time in the
    ~6h-old snapshot from forecast_log.json. Fires when |Δ| > THRESH[field]
    AND the per-cell co-axis gate (_C1H_CO_AXIS_GATE) permits — see
    h_c1h_orthogonality.py for the source verdicts. Cells that are REDUND
    to both incumbent axes never fire; cells that are AMBIG/CONFOUND to one
    axis are suppressed when that axis is currently active.

    Returns {(field, band): "fires"|"flat"|"coax_gated"|None}. None means
    the trend axis is inactive (missing data on either side); "coax_gated"
    means the trend crossed the threshold but the co-axis ortho gate
    suppressed the fire. Both non-"fires" states cause the caller to skip
    the marginal premium.
    """
    out = {}
    if not _C1H_CELLS:
        return out
    hourly = weather_data.get("hourly") or {}
    times = hourly.get("times") or hourly.get("time") or []
    if not times:
        return out
    prior = _load_prior_snapshot(6)
    if not prior:
        # No usable 6h-old snapshot → all bands report None (safe fallback).
        for field, bands in _C1H_CELLS.items():
            for band in bands:
                out[(field, band)] = None
        return out
    # Build a lookup from target-time string → hour entry in the prior snapshot.
    prior_by_v = {}
    for h in (prior.get("hours") or []):
        v = h.get("v")
        if v:
            prior_by_v[v] = h

    # Co-axis live state for the ortho gate. C1f is per-band (precip in the
    # band's lead window). C1e is a single "post"/"baseline" for the whole
    # tick — post-frontal < 24h since latest passage.
    c1f_state = _c1f_per_band(weather_data)   # {band: "p0"|"p1"|None}
    c1e_state = _current_hsf_group(weather_data)  # "post"|"baseline"|None

    for field, bands in _C1H_CELLS.items():
        thr = _C1H_THRESH.get(field)
        cur_key = _C1H_L1_KEY.get(field)
        snap_key = _C1H_SNAP_KEY.get(field)
        cur_arr = hourly.get(cur_key) or [] if cur_key else []
        for band in bands:
            # Missing gate entry = ortho verdict never applied to this cell.
            # Fail closed: refuse to fire until a human curates the gate.
            # Prevents silent add-without-ortho when new cells promote via
            # c1h_curate but the ortho eval isn't refreshed. See
            # h_c1h_orthogonality.py for the source verdicts.
            if (field, band) not in _C1H_CO_AXIS_GATE:
                out[(field, band)] = "coax_gated"
                continue
            gate = _C1H_CO_AXIS_GATE[(field, band)]
            # Fast path: cells that are REDUND to both incumbent axes never
            # fire regardless of trend. Skip the L1 lookup entirely.
            if gate.get("always_skip"):
                out[(field, band)] = "coax_gated"
                continue
            mid_lead = _C1H_BAND_MID.get(band)
            if thr is None or mid_lead is None or mid_lead >= len(times):
                out[(field, band)] = None
                continue
            target_t = times[mid_lead]
            cur_v = cur_arr[mid_lead] if mid_lead < len(cur_arr) else None
            prior_hour = prior_by_v.get(target_t)
            if cur_v is None or prior_hour is None:
                out[(field, band)] = None
                continue
            prior_v = prior_hour.get(snap_key)
            if prior_v is None:
                out[(field, band)] = None
                continue
            try:
                delta = abs(float(cur_v) - float(prior_v))
            except (TypeError, ValueError):
                out[(field, band)] = None
                continue
            if delta <= thr:
                out[(field, band)] = "flat"
                continue
            # Trend threshold crossed. Apply the co-axis ortho gate: if the
            # cell is non-ortho to a currently-firing co-axis, suppress.
            if gate.get("require_c1f_off") and c1f_state.get(band) == "p1":
                out[(field, band)] = "coax_gated"
                continue
            if gate.get("require_c1e_off") and c1e_state == "post":
                out[(field, band)] = "coax_gated"
                continue
            out[(field, band)] = "fires"
    return out


def _apply_marginal(base_mae, direction, premium_pct):
    """Multiplicatively compose a marginal-axis premium onto base_mae.
    WIDEN → multiply by (1 + |pct|/100). NARROW → multiply by max(0, 1 − |pct|/100).
    Returns (new_mae, multiplier_applied).
    """
    if base_mae is None or direction not in ("WIDEN", "NARROW") or premium_pct is None:
        return base_mae, 1.0
    pct = abs(float(premium_pct)) / 100.0
    if direction == "WIDEN":
        m = 1.0 + pct
    else:
        m = max(0.0, 1.0 - pct)
    return base_mae * m, m


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

    # Compute the live axis values once — three of four are global. C1f varies
    # per band so it's computed inside the band loop below.
    spread_q = _current_spread_quartile(weather_data)
    pt_label = _current_pt_bin(weather_data)
    trans_label = "transition" if in_transition else "stable"
    c1f_per_band = _c1f_per_band(weather_data)
    # C1e — hours-since-front axis. Post-2026-07-01 the v2 curator emits
    # 5-tuple keys `spread_q::pt_label::trans::c1f::hsf_group`; the axis_key
    # composition below matches. Live tick classifies from frontal_events_log.
    hsf_group = _current_hsf_group(weather_data)

    # Marginal-axis live values. C1d is a scalar (one slot for the whole
    # tick). C1h is per (field, band). Both are None-safe — a missing axis
    # value means the marginal multiplier is 1.0 for the affected cell.
    c1d_slot = _current_c1d_slot(weather_data)
    c1h_by_cell = _c1h_fires_per_band_field(weather_data)
    c1h_hits = 0
    c1d_hits = 0

    # Union of fields that appear in any of the three tables so C1h/C1d can
    # contribute cells even where the legacy v2/v1 table has none. Non-legacy
    # fields fall through with legacy_displayed=None; the multiplier still
    # composes onto whatever base_mae the multi-axis lookup provides (or None,
    # in which case the cell reports axis effects but no MAE).
    all_fields = set(_CURATED_CELLS.keys()) | set(_C1H_CELLS.keys()) | set(_C1D_CELLS.keys())

    cells_out = {}
    multi_hits = 0
    for field in all_fields:
        bands = _CURATED_CELLS.get(field, {})
        cells_out[field] = {}
        # Also include bands present only in c1h/c1d.
        extra_bands = set()
        for tbl in (_C1H_CELLS, _C1D_CELLS):
            extra_bands |= set(tbl.get(field, {}).keys())
        for band in set(bands.keys()) | extra_bands:
            entry = bands.get(band, {})
            stable = entry.get("stable_mae")
            transit = entry.get("transition_mae")
            # Legacy displayed_mae — what a v1-aware UI sees.
            legacy_displayed = transit if in_transition else stable
            # Multi-axis lookup. Build the 4-axis key for THIS band (C1f
            # depends on the band's lead window). If the specific
            # (spread_q × pt_bin × trans × c1f) cell is wired, prefer that.
            # Otherwise fall back to legacy.
            c1f_band = c1f_per_band.get(band)
            # 5-tuple axis_key (curator v4 emits keys with hsf as the 5th
            # dimension after 2026-07-01). Falls through to None if ANY
            # required axis is missing at this tick — that's the "axis
            # unavailable, use legacy fallback" case.
            axis_key = (f"{spread_q}::{pt_label}::{trans_label}::{c1f_band}::{hsf_group}"
                        if (spread_q and pt_label and c1f_band and hsf_group) else None)
            axis_mae = None
            axis_direction = None
            axis_status = None
            if axis_key and entry:
                hit = (entry.get("by_axes") or {}).get(axis_key)
                if hit:
                    axis_mae = hit["mae"]
                    axis_direction = hit.get("direction")
                    axis_status = hit.get("status")
                    multi_hits += 1
            base_displayed = axis_mae if axis_mae is not None else legacy_displayed

            # Compose marginal premiums (C1h, C1d) on top of base_displayed.
            # Each is a multiplicative WIDEN/NARROW that only applies when its
            # live axis value activates the wired cell.
            c1h_cell = _C1H_CELLS.get(field, {}).get(band)
            c1h_state = c1h_by_cell.get((field, band))  # "fires" | "flat" | None
            c1h_direction = None
            c1h_pct = None
            c1h_applied = False
            if c1h_cell and c1h_state == "fires":
                c1h_direction = c1h_cell["direction"]
                c1h_pct = c1h_cell["premium_pct"]
                c1h_applied = True
                c1h_hits += 1

            c1d_cell = _C1D_CELLS.get(field, {}).get(band)
            c1d_direction = None
            c1d_pct = None
            c1d_applied = False
            if c1d_cell and c1d_slot == "high":
                # c1d cells' direction is the effect of the HIGH slot vs LOW.
                # Only apply when live σ is in the HIGH slot; LOW is the
                # baseline the calibration was measured against.
                c1d_direction = c1d_cell["direction"]
                c1d_pct = c1d_cell["premium_pct"]
                c1d_applied = True
                c1d_hits += 1

            displayed_mae = base_displayed
            displayed_mae, m_h = _apply_marginal(displayed_mae, c1h_direction, c1h_pct)
            displayed_mae, m_d = _apply_marginal(displayed_mae, c1d_direction, c1d_pct)

            cells_out[field][band] = {
                "stable_mae":     stable,
                "transition_mae": transit,
                "base_displayed": base_displayed,
                "displayed_mae":  displayed_mae,
                "direction":      axis_direction or entry.get("direction"),
                "premium_pct":    entry.get("premium_pct"),
                "status":         axis_status or entry.get("status"),
                "axis_source":    ("multi" if axis_mae is not None else "legacy"),
                "c1h": {
                    "applied":     c1h_applied,
                    "state":       c1h_state,
                    "direction":   c1h_cell["direction"] if c1h_cell else None,
                    "premium_pct": c1h_cell["premium_pct"] if c1h_cell else None,
                    "multiplier":  round(m_h, 4),
                },
                "c1d": {
                    "applied":     c1d_applied,
                    "slot":        c1d_slot,
                    "direction":   c1d_cell["direction"] if c1d_cell else None,
                    "premium_pct": c1d_cell["premium_pct"] if c1d_cell else None,
                    "multiplier":  round(m_d, 4),
                },
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
            "c1f_per_band":    c1f_per_band,
            "hsf_group":       hsf_group,  # C1e — 2026-07-01, telemetry only
            "c1d_slot":        c1d_slot,   # C1d — 2026-07-08, marginal wired
            "c1h_hits":        c1h_hits,   # C1h — 2026-07-08, marginal wired
            "c1d_hits":        c1d_hits,
            "multi_hits":      multi_hits,
            "table_version":   "v3" if _CURATED_PATH.endswith("_v2.json") else "v1",
        },
        "note": (
            "Candidate C1 confidence-layer bands. Gated OFF until UI calibration "
            "audit confirms displayed bands contain truth at the claimed rate."
            if not ENABLED else
            "C1 confidence-layer bands applied (read by UI for transition-aware uncertainty)."
        ),
    }

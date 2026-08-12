"""Per-tick cross-run spread computation for the c1 xr_q axis.

Reads forecast_log.json (per-run L1 snapshots from forecast_snapshot.py),
groups by (field, valid_time), computes max−min across recent snapshots,
buckets into xr_q quintiles using edges from c1_confidence_curated_v2.json.
Stamps weather_data["cross_run_spread"] for downstream consumption.

Origin: 2026-08-12. h_cross_run_spread_c1_stage2 cleared PROMOTE — cross-
run spread is orthogonal to cluster_spread_q in 7 fields (t, wd, wg, dp, h,
pr, ws) and to transition + pt (Stage 1). See project_cross_run_spread_c1_axis.

Wired-in but consumer-less today: this stamps the axis so we can validate the
computation over a day of live ticks before confidence_layer.py starts
reading it. When confidence_layer wires the marginal multiplier (mirroring
C1h / C1d), it will look up by_xr_q entries in the curated table keyed by
the xr_q bucket per (field, band) — aggregating across the band's hours.
"""
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from ..gcs_io import load_json
from ..utils import magnus_dew_point_f, redact_secrets


# Fields the promotion cleared. Others have no xr_edges and are skipped.
FIELDS = ("t", "wd", "wg", "dp", "h", "pr", "ws")

FORECAST_LOG = "forecast_log.json"

# Two full HRRR cycles worth of collector ticks. Long enough to bracket the
# live forecast against a couple of recent runs; short enough that a truly
# stale run doesn't drag the spread. Analysis parity is 14 days on the pair
# log; we can widen later if the live distribution drifts from the curated
# edges.
LOOKBACK_HOURS = 12
MIN_RUNS_PER_VT = 3

_CURATED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "c1_confidence_curated_v2.json",
)


def _load_edges():
    try:
        with open(_CURATED_PATH) as f:
            doc = json.load(f)
    except FileNotFoundError:
        logging.warning(f"  ⚠ cross_run_spread: curated table missing at {_CURATED_PATH}")
        return {}
    except Exception as e:
        logging.warning(f"  ⚠ cross_run_spread: curated table load failed: {e}")
        return {}
    return ((doc.get("stage1_meta") or {}).get("xr_edges_by_field")) or {}


_EDGES = _load_edges()


def _bucket(sp, edges):
    """5-quintile bucket: Q1 (lowest) .. Q5 (highest). Returns None if
    edges are absent or malformed."""
    if sp is None or not edges or len(edges) < 4:
        return None
    for i, e in enumerate(edges):
        if sp < e:
            return f"Q{i + 1}"
    return "Q5"


# hourly-key mapping for live L1 values. Mirrors the _l1 slot forecast_snapshot
# picks per field so live and logged values sit in the same key namespace.
_LIVE_KEYS = {
    "t":  ("temperature",),
    "h":  ("humidity",),
    "ws": ("raw_wind_speed", "wind_speed"),
    "wg": ("raw_wind_gusts", "wind_gusts"),
    "pr": ("raw_pressure_in",),
    "wd": ("raw_wind_direction", "wind_direction"),
}


def _live_l1_by_vt(hourly):
    """Extract per-field L1 values keyed by valid_time from this tick's
    hourly payload. Returns {field: {vt: value}}. dp is derived from t + h
    via Magnus, matching how forecast_snapshot fills dp_l1."""
    times = hourly.get("times") or []
    if not times:
        return {}
    out = {}
    for f, cand in _LIVE_KEYS.items():
        arr = []
        for k in cand:
            arr = hourly.get(k) or []
            if arr:
                break
        if not arr:
            continue
        per_vt = {}
        n = min(len(times), len(arr))
        for i in range(n):
            v = arr[i]
            t = times[i]
            if v is None or not t:
                continue
            per_vt[t] = float(v)
        if per_vt:
            out[f] = per_vt

    t_arr = hourly.get("temperature") or []
    h_arr = hourly.get("humidity") or []
    if t_arr and h_arr:
        per_vt = {}
        n = min(len(times), len(t_arr), len(h_arr))
        for i in range(n):
            tv = t_arr[i]
            hv = h_arr[i]
            vt = times[i]
            if tv is None or hv is None or not vt:
                continue
            dp = magnus_dew_point_f(tv, hv)
            if dp is not None:
                per_vt[vt] = float(dp)
        if per_vt:
            out["dp"] = per_vt
    return out


def stamp(weather_data):
    """Compute per-(field, valid_time) cross-run spread from forecast_log
    snapshots plus this tick's live L1 values. Bucket into xr_q using the
    curated edges. Stamp weather_data["cross_run_spread"]. Best-effort — any
    failure logs and returns without raising.
    """
    if not _EDGES:
        return

    hourly = weather_data.get("hourly") or {}
    live = _live_l1_by_vt(hourly)

    try:
        log = load_json(FORECAST_LOG, default={"snapshots": []}) or {}
    except Exception as e:
        logging.warning(f"  ⚠ cross_run_spread: forecast_log load failed: {redact_secrets(e)}")
        return

    snapshots = log.get("snapshots") or []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M")

    per_key = defaultdict(list)  # (field, vt) -> [l1, ...]
    for snap in snapshots:
        if (snap.get("run") or "") < cutoff:
            continue
        for hr in snap.get("hours") or []:
            vt = hr.get("v")
            if not vt:
                continue
            for f in FIELDS:
                v = hr.get(f"{f}_l1")
                if v is None:
                    continue
                per_key[(f, vt)].append(float(v))

    for f, per_vt in live.items():
        for vt, v in per_vt.items():
            per_key[(f, vt)].append(v)

    out = {}
    for (f, vt), vals in per_key.items():
        if len(vals) < MIN_RUNS_PER_VT:
            continue
        sp = round(max(vals) - min(vals), 4)
        xr_q = _bucket(sp, _EDGES.get(f))
        if xr_q is None:
            continue
        out.setdefault(f, {})[vt] = {"spread": sp, "xr_q": xr_q, "n": len(vals)}

    if not out:
        logging.info("  ⊘ cross_run_spread: no (field, vt) cells cleared MIN_RUNS_PER_VT")
        return

    weather_data["cross_run_spread"] = out
    n_cells = sum(len(v) for v in out.values())
    logging.info(f"  ✓ cross_run_spread: {n_cells:,} (field, vt) cells across "
                 f"{len(out)} fields (lookback {LOOKBACK_HOURS}h)")

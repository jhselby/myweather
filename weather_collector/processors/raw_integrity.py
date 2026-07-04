"""Runtime invariant: raw_<field> arrays must equal the source array as
captured at the start of the pipeline, before any correction layer runs.

Raw_ fields are the ground truth for every downstream analysis — debug page
baselines, Production comparisons, walkforward, digest scripts. If a layer
mutates the source array before its raw_ counterpart is snapshotted, the
raw baseline is silently polluted and every analysis reads a lie. This bit
us with L5-solar on raw_direct_radiation for a week ending 2026-07-02
(fix: v0.6.285).

Two-step guarantee:
  1. snapshot_raw_baseline() — deep-copies every hourly array with a raw_
     counterpart, called immediately after preserve_raw_forecast_arrays
     and before any correction layer runs.
  2. verify_raw_integrity() — end of build_weather_data, asserts each
     raw_<field> equals its snapshot. Drift is appended to
     raw_pollution_log.jsonl in GCS; the digest surfaces it.

Non-blocking by design: raw pollution corrupts analyses, not user-facing
forecasts, so we log rather than fail the write.
"""
import logging
from datetime import datetime, timezone

from ..gcs_io import load_json, upload_json
from ..utils import redact_secrets


POLLUTION_LOG_GCS_PATH = "raw_pollution_log.jsonl"

# Every hourly array that has a raw_ counterpart somewhere in the pipeline.
# Snapshotting at pipeline start means the snapshot IS ground truth regardless
# of where downstream code creates the raw_ copy.
_RAW_FIELDS = [
    ("direct_radiation",           "raw_direct_radiation"),
    ("precipitation",              "raw_precipitation"),
    ("precipitation_probability",  "raw_precipitation_probability"),
    ("cloud_cover",                "raw_cloud_cover"),
    ("cloud_cover_low",            "raw_cloud_cover_low"),
    ("cloud_cover_mid",            "raw_cloud_cover_mid"),
    ("cloud_cover_high",           "raw_cloud_cover_high"),
    ("wind_direction",             "raw_wind_direction"),
    ("wind_speed",                 "raw_wind_speed"),
    ("wind_gusts",                 "raw_wind_gusts"),
]


def snapshot_raw_baseline(weather_data):
    """Deep-copy every present source array. Return an opaque dict keyed by
    source-field name. Safe to call multiple times; only the first matters
    for the L5-class check."""
    hourly = (weather_data or {}).get("hourly") or {}
    return {src: list(hourly[src]) for src, _ in _RAW_FIELDS if src in hourly}


def _compare(base, got):
    """Return (kind, first_bad_idx, max_delta) or None if arrays agree.
    None values are treated as equal to None; mixed None vs number counts
    as a divergence."""
    if got is None:
        return ("missing", None, None)
    if len(got) != len(base):
        return ("length_mismatch", None, None)
    first_bad = None
    max_delta = 0.0
    for i, (a, b) in enumerate(zip(base, got)):
        if a is None and b is None:
            continue
        if a is None or b is None:
            if first_bad is None:
                first_bad = i
            continue
        try:
            d = abs(float(a) - float(b))
        except (TypeError, ValueError):
            if a != b and first_bad is None:
                first_bad = i
            continue
        if d > max_delta:
            max_delta = d
        if d > 0 and first_bad is None:
            first_bad = i
    if first_bad is None:
        return None
    return ("value_drift", first_bad, max_delta)


def verify_raw_integrity(weather_data, snapshot):
    """Compare each raw_<field> against the snapshot. On drift, append events
    to raw_pollution_log.jsonl in GCS and log a warning. Never raises."""
    if not snapshot:
        return []
    hourly = (weather_data or {}).get("hourly") or {}
    events = []
    ts = datetime.now(timezone.utc).isoformat()
    for src, raw_key in _RAW_FIELDS:
        if src not in snapshot:
            continue
        result = _compare(snapshot[src], hourly.get(raw_key))
        if result is None:
            continue
        kind, first_bad, max_delta = result
        ev = {
            "ts": ts,
            "field": raw_key,
            "source": src,
            "kind": kind,
            "n_snapshot": len(snapshot[src]),
        }
        if first_bad is not None:
            ev["first_bad_idx"] = first_bad
        if max_delta is not None:
            ev["max_delta"] = max_delta
        events.append(ev)

    if events:
        _append_pollution_events(events)
        for ev in events:
            logging.warning(
                f"  ⚠  raw_integrity drift: {ev['field']} kind={ev['kind']} "
                f"idx={ev.get('first_bad_idx')} Δ={ev.get('max_delta')}"
            )
    return events


def _append_pollution_events(events):
    """Append events to the GCS pollution log. Best-effort — a log-write
    failure must not fail the collector tick."""
    try:
        existing = load_json(POLLUTION_LOG_GCS_PATH, default=[]) or []
        if not isinstance(existing, list):
            existing = []
        existing.extend(events)
        # Cap at 10k entries to keep the file bounded. Drift events are rare
        # by design; if we hit the cap, something big has been broken for
        # long enough that older events aren't the diagnostic value anymore.
        if len(existing) > 10000:
            existing = existing[-10000:]
        upload_json(existing, POLLUTION_LOG_GCS_PATH, "raw_pollution_log.jsonl")
    except Exception as e:
        logging.warning(f"  ⚠  Could not append to raw_pollution_log: {redact_secrets(e)}")

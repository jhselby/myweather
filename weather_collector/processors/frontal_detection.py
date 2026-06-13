"""
Frontal-passage detector.

Reads frontal_obs_log.json, computes rate-of-change features across a
90-minute rolling window, classifies cold-front / sea-breeze-front
passages. Emits state quiet/active/recent + event details for the
frontend card and Gemini briefing.

A "passage" requires at least 2 of 3 signals within a 60-min window:
  - Dewpoint drop > 8°F
  - Wind direction shift > 60° (angular)
  - Pressure inflection (minimum followed by rising trend)

State machine:
  - active:  any signal currently present (last tick in passage window)
  - recent:  a passage was detected within the last 12 hours but is over
  - quiet:   no passage signal anywhere in recent history

Detected events are appended to frontal_events_log.json (14-day retention).
"""
import math
from datetime import datetime, timedelta

import pytz

from ..gcs_io import load_json, upload_json

OBS_LOG_PATH = "frontal_obs_log.json"
EVENTS_LOG_PATH = "frontal_events_log.json"
RETENTION_DAYS = 14
TZ = pytz.timezone("America/New_York")

WINDOW_MIN = 60          # rolling window for rate-of-change features
RECENT_HOURS = 12        # how long a "recent" passage is surfaced

DP_DROP_THRESHOLD = 8.0  # °F drop over 60 min
WD_SHIFT_THRESHOLD = 60  # degrees, angular
PRESSURE_BOUNCE_MIN = 0.02  # inHg rise after local min

# Octant labels for wind-shift readout
OCTANTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _octant(deg):
    if deg is None:
        return None
    return OCTANTS[int((deg + 22.5) % 360 / 45)]


def _angular_diff(a, b):
    """Smallest angle between two compass bearings, 0-180."""
    if a is None or b is None:
        return None
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def _parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M")


def _window_entries(entries, now_local, minutes):
    cutoff = now_local - timedelta(minutes=minutes)
    return [e for e in entries if _parse_ts(e["ts"]) >= cutoff.replace(tzinfo=None)]


def _classify_type(dp_drop, wd_from, wd_to, pressure_rising):
    """Best guess at front type from signature."""
    to_oct = _octant(wd_to)
    from_oct = _octant(wd_from)
    if dp_drop is not None and dp_drop >= DP_DROP_THRESHOLD and to_oct in ("N", "NE", "NW") and pressure_rising:
        return "cold"
    if to_oct in ("S", "SE", "E") and from_oct in ("N", "NW", "W", "NE"):
        return "sea_breeze"
    if dp_drop is not None and dp_drop < -DP_DROP_THRESHOLD:
        return "warm"
    return "unknown"


def _compact_event(now_local, kind, dp_drop, wd_from, wd_to, p_min, p_now, confidence):
    return {
        "ts": now_local.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M"),
        "type": kind,
        "confidence": confidence,
        "dp_drop_f": round(dp_drop, 1) if dp_drop is not None else None,
        "wd_from": wd_from,
        "wd_from_oct": _octant(wd_from),
        "wd_to": wd_to,
        "wd_to_oct": _octant(wd_to),
        "p_min_inhg": p_min,
        "p_now_inhg": p_now,
    }


def detect_and_log_frontal(now_local=None):
    """
    Returns the frontal block to attach to weather_data:
      {state: "quiet"|"active"|"recent",
       event: {...} | None,
       recent_events: [...]}

    Appends new events to frontal_events_log.json when detected.
    """
    if now_local is None:
        now_local = datetime.now(TZ).replace(tzinfo=None)

    obs_log = load_json(OBS_LOG_PATH, default={"entries": []})
    entries = obs_log.get("entries", [])
    if len(entries) < 4:
        return {"state": "quiet", "event": None, "recent_events": []}

    window = _window_entries(entries, now_local, WINDOW_MIN)
    if len(window) < 4:
        return {"state": "quiet", "event": None, "recent_events": _load_recent_events(now_local)}

    # Sort window by time, just in case
    window = sorted(window, key=lambda e: e["ts"])
    first, last = window[0], window[-1]

    dp_drop = None
    if first.get("dp") is not None and last.get("dp") is not None:
        dp_drop = first["dp"] - last["dp"]  # positive = dropping (cold-front signature)

    wd_shift = _angular_diff(first.get("wd"), last.get("wd"))

    pressures = [e.get("p_inhg") for e in window if e.get("p_inhg") is not None]
    p_min = min(pressures) if pressures else None
    p_now = last.get("p_inhg")
    pressure_inflection = False
    if p_min is not None and p_now is not None and (p_now - p_min) >= PRESSURE_BOUNCE_MIN:
        # Also require min to NOT be the most recent point (we want it behind us)
        p_now_is_min = (p_now == p_min)
        if not p_now_is_min:
            pressure_inflection = True

    signals = {
        "dp_drop":             dp_drop is not None and dp_drop >= DP_DROP_THRESHOLD,
        "wd_shift":            wd_shift is not None and wd_shift >= WD_SHIFT_THRESHOLD,
        "pressure_inflection": pressure_inflection,
    }
    score = sum(1 for v in signals.values() if v)

    state = "quiet"
    event = None
    if score >= 2:
        kind = _classify_type(dp_drop, first.get("wd"), last.get("wd"), pressure_inflection)
        # Confidence: 67% with 2 signals, 100% with 3
        confidence = 67 if score == 2 else 100
        event = _compact_event(
            now_local, kind, dp_drop,
            first.get("wd"), last.get("wd"),
            p_min, p_now, confidence,
        )
        state = "active"
        _append_event(event, now_local)

    recent_events = _load_recent_events(now_local)
    if state != "active" and recent_events:
        last_event = recent_events[-1]
        last_event_ts = _parse_ts(last_event["ts"])
        if (now_local - last_event_ts) <= timedelta(hours=RECENT_HOURS):
            state = "recent"
            event = last_event

    return {"state": state, "event": event, "recent_events": recent_events}


def _append_event(event, now_local):
    cutoff = (now_local - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")
    log = load_json(EVENTS_LOG_PATH, default={"entries": []})
    entries = [e for e in log.get("entries", []) if e.get("ts", "") >= cutoff]

    # Dedupe: if last event is within 60 min of this one and same type, replace it.
    # (Avoids re-logging the same front 9 ticks in a row while it's in window.)
    if entries:
        last = entries[-1]
        last_ts = _parse_ts(last["ts"])
        same_window = (now_local - last_ts) <= timedelta(minutes=WINDOW_MIN)
        if same_window and last.get("type") == event.get("type"):
            entries[-1] = event
            upload_json({"entries": entries}, EVENTS_LOG_PATH, "frontal_events_log.json")
            return

    entries.append(event)
    upload_json({"entries": entries}, EVENTS_LOG_PATH, "frontal_events_log.json")


def _load_recent_events(now_local):
    cutoff = (now_local - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")
    log = load_json(EVENTS_LOG_PATH, default={"entries": []})
    return [e for e in log.get("entries", []) if e.get("ts", "") >= cutoff]

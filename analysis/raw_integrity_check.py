#!/usr/bin/env python3
"""Digest-side companion to the collector's raw_integrity check.

The collector runs verify_raw_integrity(weather_data, snapshot) at the end
of build_weather_data every tick. On any drift, it appends a JSON event to
raw_pollution_log.jsonl in GCS. This script reads that log and emits a
verdict line the daily digest picks up.

Green when the log is empty for the last 24h. Red on any recent drift —
raw_ pollution is the L5-class silent failure that ate a week of solar
analyses ending 2026-07-02 (v0.6.285 fix).
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis._cache import cached_path

URL = "https://data.wymancove.com/raw_pollution_log.jsonl"
WINDOW_HOURS = 24


def _load_events():
    """Log is written as a JSON array (see raw_integrity._append_pollution_events).
    Returns []."""
    try:
        path = cached_path(URL, max_age_hours=1)
    except Exception as e:
        # 404 == log has never been written == no drift ever. Any other
        # error we surface, because CLEAN would be a lie.
        if "404" in str(e):
            return []
        print(f"  ⚠  pollution log fetch failed: {e}")
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception as e:
        print(f"  ⚠  pollution log parse failed: {e}")
    return []


def main():
    events = _load_events()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
    recent = []
    for ev in events:
        ts_raw = ev.get("ts")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts >= cutoff:
            recent.append(ev)

    total_all_time = len(events)
    n_recent = len(recent)

    print(f"raw_integrity_check — window={WINDOW_HOURS}h")
    print(f"  all-time drift events:  {total_all_time}")
    print(f"  recent drift events:    {n_recent}")

    if n_recent == 0:
        print()
        print(f"Verdict: CLEAN — no raw_ drift in the last {WINDOW_HOURS}h.")
        return 0

    by_field = {}
    for ev in recent:
        key = ev.get("field", "?")
        by_field.setdefault(key, []).append(ev)

    print()
    print("  drift by field (last 24h):")
    for field, evs in sorted(by_field.items(), key=lambda kv: -len(kv[1])):
        latest = evs[-1]
        print(
            f"    {field:36s}  n={len(evs):3d}  "
            f"kind={latest.get('kind')}  max_delta={latest.get('max_delta')}"
        )

    print()
    print(
        f"Verdict: DRIFT — {n_recent} raw_ pollution event(s) in the last "
        f"{WINDOW_HOURS}h across {len(by_field)} field(s). Diagnose immediately: "
        f"a correction layer is mutating a source array before the raw_ copy is "
        f"snapshotted. This corrupts every downstream analysis of the affected "
        f"field. See processors/raw_integrity.py."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

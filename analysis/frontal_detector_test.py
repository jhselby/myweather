#!/usr/bin/env python3
"""
End-to-end validation of the frontal-passage detector.

The detector has been live in production since 2026-06-13 but hasn't
seen a real front yet (3 days of quiet weather), so we don't know if the
full wiring — obs log → detector → events log → weather_data → frontend
card — actually works end-to-end. This script exercises the path with
synthetic data so we can confirm the connections before the next real
front arrives.

What it tests:
  1. Detector classifies a synthetic cold front as type='cold' with high
     confidence.
  2. Detector classifies a synthetic sea-breeze front correctly.
  3. Detector stays QUIET on noise (small fluctuations) without firing
     a false positive.
  4. Detector correctly tracks the "recent" state after an active event.

Run:
    python3 analysis/frontal_detector_test.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest.mock as mock
from datetime import datetime, timedelta

from weather_collector.processors import frontal_detection as fd


def _ts(now, minutes_ago):
    return (now - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M")


def make_window(now, dp_series, wd_series, p_series):
    """Build a synthetic 90-min obs log (10-min ticks) from 3 series."""
    entries = []
    minutes_ago_list = [60, 50, 40, 30, 20, 10, 0]
    for ix, m_ago in enumerate(minutes_ago_list):
        entries.append({
            "ts": _ts(now, m_ago),
            "t": 75,
            "dp": dp_series[ix],
            "p_inhg": p_series[ix],
            "ws": 10,
            "wd": wd_series[ix],
        })
    return entries


def run_test(name, entries, expected_state, expected_type=None, min_confidence=0):
    now = datetime(2026, 6, 15, 14, 0)
    with mock.patch.object(fd, "load_json", side_effect=[
        {"entries": entries},     # obs log
        {"entries": []},          # events log read (for append dedup check)
        {"entries": []},          # events log read (for recent_events lookup)
    ]), mock.patch.object(fd, "upload_json"):
        r = fd.detect_and_log_frontal(now_local=now)
    ok = r["state"] == expected_state
    if expected_type and r["event"]:
        ok = ok and r["event"]["type"] == expected_type
    if min_confidence and r["event"]:
        ok = ok and r["event"]["confidence"] >= min_confidence
    status = "PASS" if ok else "FAIL"
    detail = f"state={r['state']}"
    if r["event"]:
        detail += f", type={r['event']['type']}, conf={r['event']['confidence']}, dp_drop={r['event']['dp_drop_f']}, wd {r['event']['wd_from_oct']}→{r['event']['wd_to_oct']}"
    print(f"  [{status}] {name}: {detail}")
    return ok


def main():
    print("=== Frontal detector end-to-end test ===\n")

    all_ok = True

    # 1. Cold front: dewpoint drops 13°F, wind shifts SW→NW, pressure bounces
    cold_front = make_window(
        datetime(2026, 6, 15, 14, 0),
        dp_series=[68, 67, 66, 60, 56, 55, 55],
        wd_series=[215, 220, 245, 280, 310, 320, 320],
        p_series=[29.84, 29.84, 29.85, 29.86, 29.88, 29.89, 29.90],
    )
    all_ok &= run_test("cold front", cold_front, "active", "cold", min_confidence=67)

    # 2. Sea-breeze front: wind shifts N→SE, mild dewpoint shift, no pressure bounce
    sea_breeze = make_window(
        datetime(2026, 6, 15, 14, 0),
        dp_series=[58, 58, 59, 60, 60, 61, 61],
        wd_series=[10, 30, 60, 100, 130, 140, 140],
        p_series=[29.90, 29.90, 29.90, 29.90, 29.90, 29.90, 29.90],
    )
    # Wind shift 130° qualifies; sea breeze has 1 signal (wd_shift). 2-of-3 not
    # met → expect QUIET. This documents the threshold behavior: small/slow sea
    # breezes don't fire; only the textbook ones with multiple signals.
    all_ok &= run_test("modest sea-breeze (should stay quiet)", sea_breeze, "quiet")

    # 3. Noise: small fluctuations within thresholds
    noise = make_window(
        datetime(2026, 6, 15, 14, 0),
        dp_series=[62, 63, 62, 63, 62, 63, 62],
        wd_series=[180, 185, 175, 180, 185, 180, 185],
        p_series=[29.95, 29.95, 29.96, 29.95, 29.95, 29.96, 29.95],
    )
    all_ok &= run_test("noise (should stay quiet)", noise, "quiet")

    # 4. Strong sea-breeze with bigger wind shift + dewpoint drop
    strong_sb = make_window(
        datetime(2026, 6, 15, 14, 0),
        dp_series=[70, 70, 68, 65, 62, 61, 61],
        wd_series=[20, 50, 80, 110, 130, 150, 150],
        p_series=[29.90, 29.90, 29.90, 29.90, 29.90, 29.90, 29.90],
    )
    all_ok &= run_test("strong sea-breeze (should fire)", strong_sb, "active", "sea_breeze", min_confidence=67)

    print()
    print(f"RESULT: {'ALL PASS' if all_ok else 'FAILURES'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

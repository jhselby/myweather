"""NWS gridpoint validTime durations: day parts must count (11-21: P1DT13H POP read as 1 h)."""
from datetime import datetime, timezone

from weather_collector.processors.forecast_text import _extract_nws_value, _extract_nws_interval

PROP = {"values": [
    {"validTime": "2026-11-21T06:00:00+00:00/PT2H", "value": 5},
    {"validTime": "2026-11-21T08:00:00+00:00/P1DT13H", "value": 0},
    {"validTime": "2026-11-22T21:00:00+00:00/P1D", "value": 40},
    {"validTime": "2026-11-23T21:00:00+00:00/PT30M", "value": 70},
]}


def at(s):
    return _extract_nws_value(PROP, datetime.fromisoformat(s).replace(tzinfo=timezone.utc))


def test_hours_only():
    assert at("2026-11-21T07:00") == 5


def test_day_and_hours_covers_whole_interval():
    assert at("2026-11-21T08:00") == 0
    assert at("2026-11-22T20:00") == 0   # 36 h in, was None before the fix


def test_days_only():
    assert at("2026-11-23T20:00") == 40


def test_minutes_and_outside():
    assert at("2026-11-23T21:15") == 70
    assert at("2026-11-23T21:30") is None


def test_interval_length_for_block_totals():
    t = datetime(2026, 11, 21, 10, tzinfo=timezone.utc)
    assert _extract_nws_interval(PROP, t) == (0, 37.0)
    assert _extract_nws_interval(PROP, datetime(2026, 11, 23, 21, 15, tzinfo=timezone.utc)) == (70, 0.5)
    assert _extract_nws_interval(PROP, datetime(2026, 11, 20, tzinfo=timezone.utc)) == (None, None)

"""11-25 7:47 PM: headline said "temps rising to mid-40s" (tomorrow's high quoted as tonight)."""
import os
from datetime import datetime

import pytz

os.environ.setdefault("GEMINI_API_KEY", "test")

from weather_collector.fetchers.briefing_ai import _time_of_day_line, _validate_headline  # noqa: E402

ET = pytz.timezone("America/New_York")
NIGHT = ET.localize(datetime(2026, 11, 25, 19, 47))
NOON = ET.localize(datetime(2026, 11, 26, 12, 0))
WD = {"current": {"weather_description": "Partly Cloudy"}, "hourly": {"cloud_cover": [40] * 24, "precipitation": [0.0]},
      "alerts": [], "pirate_weather": {}}


def check(headline, now):
    return _validate_headline({"headline": headline, "subheadline": "Low near 32."}, "No significant rain expected", WD, now=now)[0]


def test_rising_temps_rejected_at_night():
    assert not check("Partly cloudy, temps rising to mid-40s", NIGHT)


def test_rising_temps_fine_at_noon():
    assert check("Partly cloudy, temps rising to mid-40s", NOON)


def test_future_marker_allowed_at_night():
    assert check("Partly cloudy, tomorrow warming to mid-40s", NIGHT)


def test_night_prompt_line_says_high_has_passed():
    assert "already passed" in _time_of_day_line(NIGHT)
    assert "already passed" not in _time_of_day_line(NOON)

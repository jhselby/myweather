"""The briefing prompt must say whether each NWS alert is in effect now or pending,
and must use the event end (`ends`), not the message expiry. 11-25 incident: a pending
Coastal Flood Advisory was headlined "in effect"."""
import os
from datetime import datetime, timedelta

import pytz

os.environ.setdefault("GEMINI_API_KEY", "test")  # briefing_ai reads it at import

from weather_collector.fetchers.briefing_ai import _alert_line  # noqa: E402

TZ = pytz.timezone("America/New_York")
NOW = TZ.localize(datetime(2026, 11, 25, 10, 0))


def iso(h):
    return (NOW + timedelta(hours=h)).isoformat()


def test_pending_alert_is_not_in_effect():
    line = _alert_line([{"event": "Wind Advisory", "onset": iso(26), "ends": iso(45), "expires": iso(6)}], NOW)
    assert "NOT YET IN EFFECT" in line and "IN EFFECT NOW" not in line
    assert "starts Thu 12:00 PM" in line and "ends Fri 7:00 AM" in line, line


def test_active_alert_is_in_effect_and_uses_ends_not_expires():
    line = _alert_line([{"event": "Wind Advisory", "onset": iso(-1), "ends": iso(30), "expires": iso(2)}], NOW)
    assert "IN EFFECT NOW" in line and "NOT YET" not in line
    assert "ends Thu 4:00 PM" in line and "Wed 12:00 PM" not in line, line


def test_end_falls_back_to_headline_until():
    h = "Wind Advisory issued November 25 at 1:22AM EST until November 27 at 7:00AM EST by NWS Boston/Norton MA"
    line = _alert_line([{"event": "Wind Advisory", "onset": iso(-1), "headline": h, "expires": iso(2)}], NOW)
    assert "ends November 27 at 7:00AM EST" in line, line


def test_no_alerts_gives_empty_line():
    assert _alert_line([], NOW) == ""
    assert _alert_line([{"event": "  "}], NOW) == ""

"""11-25: the app showed headline "Overcast and 38F" beside a sky stat of "Clear". Two causes:
(1) the briefing was written before the correction layers and before the final current sync;
(2) a throttled tick served the cached headline without re-checking it against the current state.
These tests cover the re-check and the final sync."""
import os
from datetime import datetime, timedelta

import pytz

os.environ.setdefault("GEMINI_API_KEY", "test")

from weather_collector.fetchers.briefing_ai import _cached_contradicts_now  # noqa: E402
from weather_collector.processors.current_from_hourly import sync_current_from_hourly_corrected  # noqa: E402

ET = pytz.timezone("America/New_York")


def payload(desc, cloud_now):
    return {
        "current": {"weather_description": desc, "weather_code": 0, "temperature": 38.0, "cloud_cover": cloud_now,
                    "precipitation": 0.0},
        "hourly": {"times": ["2026-11-25T19:00", "2026-11-25T20:00"], "cloud_cover": [cloud_now, cloud_now],
                   "precipitation": [0.0, 0.0], "temperature": [38.0, 37.0]},
        "alerts": [], "pirate_weather": {},
    }


def cached(headline, minutes_ago):
    t = (datetime.now(ET) - timedelta(minutes=minutes_ago)).isoformat()
    return {"headline": headline, "subheadline": "Low in the low 30s tonight.", "cached_at": t}


def test_cached_overcast_headline_contradicts_a_clear_sky():
    assert _cached_contradicts_now(cached("Overcast and 38°F with a calm NE breeze", 20), payload("Clear", 10))


def test_consistent_cached_headline_is_kept():
    assert not _cached_contradicts_now(cached("Clear and 38°F with a calm NE breeze", 20), payload("Clear", 10))


def test_forced_regeneration_is_rate_limited():
    # a headline rejected on every tick must not trigger an LLM call every tick
    assert not _cached_contradicts_now(cached("Overcast and 38°F with a calm NE breeze", 1), payload("Clear", 10))


def test_final_sync_makes_the_sky_card_follow_the_served_hourly():
    p = payload("Clear", 10)
    p["hourly"]["cloud_cover"] = [41, 46]          # a later step rewrote hourly after the first sync
    sync_current_from_hourly_corrected(p)
    assert p["current"]["cloud_cover"] == 41
    assert p["current"]["weather_description"] != "Clear"


def test_collector_runs_final_sync_then_briefing_just_before_upload():
    src = open(os.path.join(os.path.dirname(__file__), "..", "weather_collector", "collector.py")).read()
    sync = src.rindex("sync_current_from_hourly_corrected(weather_data)")
    brief = src.index("    apply_briefing_to_weather_data(weather_data)\n\n    # Upload")
    upload = src.index("upload_json(weather_data, WEATHER_DATA_GCS_PATH")
    assert sync < brief < upload
    assert src.count("apply_briefing_to_weather_data(weather_data)") == 1   # not also run early


def test_overcast_headline_is_rejected_beside_a_partly_cloudy_card():
    # 11-25 19:37 ET: card "Partly Cloudy" (41%), headline "Overcast" -- was accepted (rule only fired at <=30%).
    assert _cached_contradicts_now(cached("Overcast and 38\u00b0F with a calm NE breeze", 20), payload("Partly Cloudy", 41))


def test_overcast_headline_is_accepted_beside_an_overcast_card():
    assert not _cached_contradicts_now(cached("Overcast and 38\u00b0F with a calm NE breeze", 20), payload("Overcast", 95))


def test_clear_headline_is_rejected_beside_a_cloudy_card():
    assert _cached_contradicts_now(cached("Clear and 38\u00b0F with a calm NE breeze", 20), payload("Mostly Cloudy", 70))


def test_clearing_is_not_mistaken_for_clear():
    assert not _cached_contradicts_now(cached("Clouds clearing by evening, 38\u00b0F", 20), payload("Partly Cloudy", 41))

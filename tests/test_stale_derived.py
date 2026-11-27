"""apply_stale_fallbacks fills derived.* from the previous run when current/hourly failed (11-27 fog card blank)."""
from weather_collector.stale_cache import apply_stale_fallbacks

PREV = {"current": {"temperature": 47.5}, "hourly": {"times": ["2026-11-27T07:00"]},
        "derived": {"fog_label": "Likely", "fog_probability": 95, "today_high": 50}}


def test_failed_current_fills_missing_derived_only():
    wd = {"derived": {"today_high": 52}}
    stale = apply_stale_fallbacks(wd, PREV, {"current", "hourly"})
    assert wd["derived"]["fog_label"] == "Likely" and wd["derived"]["fog_probability"] == 95
    assert wd["derived"]["today_high"] == 52          # this run's value kept
    assert "derived" in stale


def test_good_fetch_leaves_derived_alone():
    wd = {"derived": {"today_high": 52}}
    stale = apply_stale_fallbacks(wd, PREV, set())
    assert "fog_label" not in wd["derived"] and "derived" not in stale

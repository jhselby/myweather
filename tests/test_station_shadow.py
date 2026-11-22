"""Shadow stations (v0.7.137) are archived under their own keys and never enter the Mesonet readings."""
from datetime import datetime, timezone

from weather_collector.processors.station_readings_log import build_entry


def _st(sid, t):
    return {"station_id": sid, "station_name": f"s{sid}", "valid": True, "age_minutes": 1.0,
            "temperature_f": t, "wind_avg_mph": 3.0, "relative_humidity": 80, "latitude": 42.5, "longitude": -70.9,
            "distance_mi": 3.1}


def test_shadow_kept_separate():
    tempest = {"stations": [_st(1, 50.0)], "shadow_stations": [_st(99, 52.0)]}
    entry, meta, shadow_meta = build_entry({}, tempest, {}, datetime(2026, 11, 22, 18, 7, tzinfo=timezone.utc))
    assert list(entry["readings"]) == ["1"]          # Mesonet readings untouched
    assert list(entry["shadow"]) == ["99"] and entry["shadow"]["99"]["t"] == 52.0
    assert "99" not in meta and "99" in shadow_meta
    assert "off_t" not in entry["shadow"]["99"]


def test_no_shadow_no_key():
    entry, _, shadow_meta = build_entry({}, {"stations": [_st(1, 50.0)]}, {}, datetime(2026, 11, 22, 18, 7, tzinfo=timezone.utc))
    assert "shadow" not in entry and shadow_meta == {}

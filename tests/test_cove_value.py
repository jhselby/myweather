"""Cove value shadow (v0.7.138): table validation, runtime stamp, and the fit on a synthetic archive."""
from datetime import datetime, timezone

from analysis import mesonet_cove_adjust_fit as fit
from weather_collector.processors import cove_value


def _table(adj_t=1.0, adj_h=-2.0, fitted="2026-11-22T12:00"):
    return {"fitted_at": fitted, "fields": {"t": {"hourly": {str(h): adj_t for h in range(24)}},
                                           "h": {"hourly": {str(h): adj_h for h in range(24)}}}}


def test_validate():
    assert cove_value.validate_table(_table()) is None
    assert cove_value.validate_table({"fields": {}}) is not None
    bad = _table(); bad["fields"]["t"]["hourly"]["3"] = 99
    assert cove_value.validate_table(bad) is not None
    bad = _table(); bad["fields"]["t"]["hourly"]["25"] = 1.0
    assert cove_value.validate_table(bad) is not None


def test_apply_stamps(monkeypatch):
    from weather_collector import runtime_tables
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: _table(1.0, -2.0))
    hyp = {"station_temp": 50.0, "station_humidity": 90.0}
    cove_value.apply(hyp, datetime(2026, 11, 23, 5, 0, tzinfo=timezone.utc))
    assert hyp["cove_temp"] == 51.0 and hyp["cove_humidity"] == 88.0 and hyp["cove_dew_point"] is not None
    assert hyp["cove_adjust_t"] == 1.0


def test_apply_fails_closed_when_stale(monkeypatch):
    from weather_collector import runtime_tables
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: _table(fitted="2026-11-01T12:00"))
    hyp = {"station_temp": 50.0, "station_humidity": 90.0}
    cove_value.apply(hyp, datetime(2026, 11, 23, 5, 0, tzinfo=timezone.utc))
    assert "cove_temp" not in hyp


def test_fit_learns_neptune_minus_mesonet():
    ticks = []
    for day in ("2026-11-20", "2026-11-21", "2026-11-22"):
        for hh in (3, 4):   # UTC 03-04 = 22-23 ET the day before
            for mm in ("07", "17"):
                ticks.append((day, {"ts": f"{day}T{hh:02d}:{mm}Z",
                                    "l2": {"station_temp": 50.0, "station_humidity": 90.0},
                                    "readings": {"192019": {"valid": True, "age_min": 1, "t": 51.0, "rh": 88.0}}}))
    docs = {}
    for day, t in ticks:
        docs.setdefault(day, {"ticks": []})["ticks"].append(t)
    out = fit.build(docs)
    assert set(out["fields"]) == {"t", "h"}
    assert all(abs(v - 1.0) < 1e-9 for v in out["fields"]["t"]["hourly"].values())
    assert all(abs(v + 2.0) < 1e-9 for v in out["fields"]["h"]["hourly"].values())

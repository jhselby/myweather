"""Serve switch for t_urmab (v0.7.114): replaces t, keeps t_pre_urmab, fails closed, kill switch works."""
from weather_collector.processors import urma_blend_shadow as u
from weather_collector import runtime_tables


def _entry():
    return {"t": 50.0, "t_selector_source": "tblend", "t_applied": "tblend", "t_urmab": 48.2}


def test_apply_serves_and_keeps_old(monkeypatch):
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: {"serve": True})
    e = _entry()
    assert u.apply(e) is True
    assert e["t"] == 48.2 and e["t_pre_urmab"] == 50.0
    assert e["t_applied"] == "urmab" and e["t_selector_source"] == "urmab"


def test_kill_switch_off(monkeypatch):
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: {"serve": False})
    e = _entry()
    assert u.apply(e) is False and e["t"] == 50.0 and "t_pre_urmab" not in e


def test_fails_closed_on_read_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("gcs down")
    monkeypatch.setattr(runtime_tables, "get", boom)
    assert u.apply(_entry()) is False


def test_no_t_urmab_no_change(monkeypatch):
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: {"serve": True})
    e = {"t": 50.0}
    assert u.apply(e) is False and e == {"t": 50.0}


def test_bundled_switch_valid():
    import json
    assert u._valid_serve(json.load(open(u.SERVE_PATH))) is None


def _doc(ws=True):
    from datetime import datetime, timezone
    cell = {"w": [0.2, 0.5, 0.3], "bias": [0.0, 0.0, 0.0]}
    d = {"fitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
         "fields": {"t": {"bands": {"6-11": {"w": [0, 1, 0], "bias": [0, 1.0, 0]}}}}}
    if ws:
        d["fields"]["ws"] = {"bands": {"6-11": cell}}
    return d


def test_ws_shadow_stamped_never_served(monkeypatch):
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: _doc())
    e = {"t_l1": 50, "t_raw_nbm": 51, "t_ecmwf": 49, "ws": 9.0, "ws_l1": 10.0, "ws_raw_nbm": 8.0, "ws_ecmwf": 6.0}
    u.stamp(e, 8)
    assert e["t_urmab"] == 50.0
    assert e["ws_urmab"] == round(0.2 * 10 + 0.5 * 8 + 0.3 * 6, 1)
    assert e["ws"] == 9.0


def test_ws_missing_table_or_input(monkeypatch):
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: _doc(ws=False))
    e = {"t_l1": 50, "t_raw_nbm": 51, "t_ecmwf": 49, "ws_l1": 10.0, "ws_raw_nbm": 8.0, "ws_ecmwf": 6.0}
    u.stamp(e, 8)
    assert "t_urmab" in e and "ws_urmab" not in e
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: _doc())
    e = {"ws_l1": 10.0, "ws_raw_nbm": 8.0}
    u.stamp(e, 8)
    assert "ws_urmab" not in e


def test_validate_ws_band():
    d = _doc()
    assert u.validate_table(d) is None
    d["fields"]["ws"]["bands"]["6-11"]["w"] = [0.5, 0.5, 0.5]
    assert "ws band" in u.validate_table(d)

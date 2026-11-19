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

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


def test_wg_shadow_two_way_no_ecmwf(monkeypatch):
    d = _doc()
    d["fields"]["wg"] = {"bands": {"0-5": {"w": [0.5, 0.5, 0.0], "bias": [2.0, -1.0, 0.0]}}}
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: d)
    e = {"wg": 9.0, "wg_l1": 14.0, "wg_raw_nbm": 10.0, "t_l1": 50, "t_raw_nbm": 51, "t_ecmwf": 49}
    u.stamp(e, 2)
    assert e["wg_urmab"] == round(0.5 * 12 + 0.5 * 11, 1)
    assert "t_urmab" not in e and e["wg"] == 9.0


# ---- v0.7.140: dew point served independently (6-23h), humidity untouched ----
def _dp_entry():
    return {"dp": 50.0, "dp_urmab": 51.5, "dp_selector_source": "tblend", "dp_applied": "tblend"}


def test_dp_off_by_default(monkeypatch):
    import json
    assert json.load(open(u.SERVE_PATH))["serve_dp"] is False
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: {"serve": True, "serve_dp": False})
    e = _dp_entry()
    assert u.apply_dp(e, 10) is False and e["dp"] == 50.0 and "dp_urmab_independent" not in e


def test_dp_serves_only_6_to_23h(monkeypatch):
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: {"serve": True, "serve_dp": True})
    for lead, ok in ((3, False), (6, True), (11, True), (12, True), (23, True), (24, False), (40, False)):
        e = _dp_entry()
        assert u.apply_dp(e, lead) is ok, lead
        assert (e["dp"] == 51.5) is ok
    e = _dp_entry(); u.apply_dp(e, 8)
    assert e["dp_pre_dpurmab"] == 50.0 and e["dp_applied"] == "urmab" and e["dp_urmab_independent"] is True


def test_dp_keeps_earlier_pre_urmab(monkeypatch):
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: {"serve": True, "serve_dp": True})
    e = _dp_entry(); e["dp_pre_urmab"] = 49.0
    u.apply_dp(e, 8)
    assert e["dp_pre_urmab"] == 49.0 and e["dp_pre_dpurmab"] == 50.0


def test_dp_fails_closed(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("gcs down")
    monkeypatch.setattr(runtime_tables, "get", boom)
    assert u.apply_dp(_dp_entry(), 8) is False


def test_recompute_skips_humidity_on_independent_hours():
    from weather_collector.processors.decay_apply import recompute_derived_moisture_arrays
    wd = {"hourly": {"corrected_temperature": [60.0, 60.0], "corrected_dew_point": [50.0, 50.0],
                     "corrected_humidity": [11.1, 22.2], "wind_speed": [3, 3], "direct_radiation": [0, 0],
                     "dp_independent": [True, False]}}
    recompute_derived_moisture_arrays(wd)
    assert wd["hourly"]["corrected_humidity"][0] == 11.1          # kept (independent dp)
    assert wd["hourly"]["corrected_humidity"][1] != 22.2          # rebuilt from (t, dp) as before


def _off_doc(off):
    return {"fitted_at": "2999-01-01T00:00", "fields": {"t": {"bands": {"6-11": {"w": [1, 0, 0], "bias": [0, 0, 0]}}},
                                                        "t_off": {"by_hour": off}}}


def test_stnoff_stamped_from_hour_offset(monkeypatch):
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: _off_doc({"22": 1.5}))
    e = {"v": "2026-11-24T22:00", "t": 40.0, "t_l1": 40.0, "t_raw_nbm": 40.0, "t_ecmwf": 40.0}
    u.stamp(e, 8)
    assert e["t_urmab"] == 40.0 and e["t_stnoff"] == 41.5


def test_stnoff_absent_without_offset_for_hour(monkeypatch):
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: _off_doc({"22": 1.5}))
    e = {"v": "2026-11-24T13:00", "t": 40.0, "t_l1": 40.0, "t_raw_nbm": 40.0, "t_ecmwf": 40.0}
    u.stamp(e, 8)
    assert "t_urmab" in e and "t_stnoff" not in e


def test_validate_rejects_absurd_offset():
    assert u.validate_table(_off_doc({"22": 9.0})) is not None
    assert u.validate_table(_off_doc({"22": 1.0})) is None


def _ch_entry():
    return {"ch": 61.0, "ch_l1": 12.0, "ch_applied": "l3", "ch_selector_source": "nbm"}


def test_ch_serves_hrrr_at_6_to_23h_only(monkeypatch):
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: {"serve": True, "serve_ch": True})
    for lead, ok in ((3, False), (6, True), (23, True), (24, False), (40, False)):
        e = _ch_entry()
        assert u.apply_ch(e, lead) is ok, lead
        assert (e["ch"] == 12.0) is ok
    e = _ch_entry(); u.apply_ch(e, 8)
    assert e["ch_pre_hrrr"] == 61.0 and e["ch_applied"] == "hrrr_sat"


def test_ch_off_without_key_or_on_error(monkeypatch):
    monkeypatch.setattr(runtime_tables, "get", lambda *a, **k: {"serve": True})
    assert u.apply_ch(_ch_entry(), 8) is False
    def boom(*a, **k):
        raise RuntimeError("gcs down")
    monkeypatch.setattr(runtime_tables, "get", boom)
    assert u.apply_ch(_ch_entry(), 8) is False

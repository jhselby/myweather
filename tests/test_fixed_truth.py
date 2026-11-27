"""FixedTruth.rebase (analysis/_truth.py): the selector scoring grades on the scorecard's fixed truth."""
from analysis._truth import FixedTruth


def _ft(urma):
    ft = FixedTruth.__new__(FixedTruth)
    ft.urma = urma
    ft._hour = lambda vt: {"2026-11-26T15:00": "2026-11-26T20"}.get(vt[:16])   # ET -> UTC
    return ft


def test_urma_field_shifts_every_error_and_observed():
    ft = _ft({"ws": {"2026-11-26T20": 22.0}})
    row = {"field": "ws", "valid_time": "2026-11-26T15:00", "lead_h": 2, "observed": 19.6, "forecast": 17.9,
           "error": -1.7, "error_l1": 2.1, "error_raw_nbm": 0.5, "error_ecmwf": -3.2, "error_flag": True}
    assert ft.rebase(row)
    assert row["observed"] == 22.0
    assert abs(row["error"] - (17.9 - 22.0)) < 1e-9          # forecast - new truth
    assert abs(row["error_l1"] - (2.1 - 2.4)) < 1e-9
    assert abs(row["error_ecmwf"] - (-3.2 - 2.4)) < 1e-9
    assert row["error_flag"] is True                          # booleans untouched


def test_urma_field_without_truth_hour_is_dropped():
    ft = _ft({"t": {}})
    assert not ft.rebase({"field": "t", "valid_time": "2026-11-26T15:00", "observed": 40.0, "error": 1.0})


def test_h_uses_mesonet_from_6h_and_drops_below():
    ft = _ft({})
    short = {"field": "h", "lead_h": 5, "observed": 80.0, "observed_stations": 78.0, "error": 2.0}
    assert not ft.rebase(short)
    row = {"field": "h", "lead_h": 6, "observed": 80.0, "observed_stations": 78.0, "error": 2.0}
    assert ft.rebase(row)
    assert row["observed"] == 78.0 and abs(row["error"] - 4.0) < 1e-9
    assert not ft.rebase({"field": "h", "lead_h": 12, "observed": 80.0, "error": 2.0})   # no station value


def test_other_fields_pass_unchanged():
    ft = _ft({})
    row = {"field": "sr", "observed": 100.0, "error": 5.0}
    assert ft.rebase(row) and row == {"field": "sr", "observed": 100.0, "error": 5.0}


def test_field_with_failed_urma_load_keeps_observed():
    ft = _ft({})   # t store failed to load
    row = {"field": "t", "valid_time": "2026-11-26T15:00", "observed": 40.0, "error": 1.0}
    assert ft.rebase(row) and row["error"] == 1.0
    assert ft.labels()["t"].startswith("logged observed")

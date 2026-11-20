"""v0.7.124 rain truth: past-hour Tempest accumulation, median of wet stations, wet rule >=3 and >=25%."""
from weather_collector.processors import daily_extremes as de


def _wd(accs, age=1):
    return {"tempest": {"stations": [{"valid": True, "age_minutes": age, "precip_accum_1hr_in": a,
                                      "precip_rate_in": 0.0} for a in accs]}}


def test_wet_median():
    assert de.hour_rain_in(_wd([0, 0, 0.02, 0.04, 0.10, 0, 0, 0])) == 0.04


def test_dry_when_too_few_wet():
    assert de.hour_rain_in(_wd([0, 0, 0.02, 0.04, 0, 0, 0, 0, 0, 0])) == 0.0


def test_none_when_under_three_reporting():
    assert de.hour_rain_in(_wd([0.1, 0.2])) is None
    assert de.hour_rain_in(_wd([0.1, 0.2, 0.3], age=30)) is None


def test_pp_truth_uses_hour_total_even_when_rate_zero():
    wd = _wd([0.03, 0.05, 0.02, 0.0])
    wd["hourly"] = {"times": [], "precipitation": []}
    assert de._current_hour_precip_in(wd, "2026-11-20T08:00") == 0.03

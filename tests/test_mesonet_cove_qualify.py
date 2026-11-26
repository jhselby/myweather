"""Guard and arithmetic of the pre-registered Cove-side scorer (plan 1.8). Synthetic data only."""
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("GEMINI_API_KEY", "test")

from analysis import mesonet_cove_qualify as q  # noqa: E402

UTC = timezone.utc


def hours(start, n):
    return [int((start + timedelta(hours=i)).timestamp()) for i in range(n)]


def test_period_and_night_key():
    # 2026-11-25 23:00 ET and 2026-11-26 03:00 ET are the same calendar night
    et = q.ET
    a = int(datetime(2026, 11, 25, 23, tzinfo=et).timestamp())
    b = int(datetime(2026, 11, 26, 3, tzinfo=et).timestamp())
    noon = int(datetime(2026, 11, 26, 12, tzinfo=et).timestamp())
    assert q.period_of(a) == q.period_of(b) == "night" and q.period_of(noon) == "day"
    assert q.night_key(a) == q.night_key(b) == "2026-11-25"


def test_count_nights_needs_enough_hours_per_night():
    start = datetime(2026, 11, 20, 0, tzinfo=q.ET)
    full = [h for h in hours(start, 24 * 12) if q.period_of(h) == "night"]
    assert q.count_nights(full) == 12 or q.count_nights(full) == 11   # edge nights at the window ends
    sparse = full[:5]
    assert q.count_nights(sparse) == 0


def test_compare_bias_and_rmse():
    hs = [h for h in hours(datetime(2026, 11, 20, 0, tzinfo=q.ET), 48)]
    mes = {h: 40.0 for h in hs}
    ref = {h: 40.0 + (1.0 if i % 2 else -1.0) for i, h in enumerate(hs)}
    r = q.compare(mes, ref, hs)
    for per in ("day", "night"):
        assert r[per]["bias"] == pytest.approx(0.0, abs=0.2) and r[per]["rmse"] == pytest.approx(1.0, abs=0.01)


def test_verdict_not_eligible_without_all_references():
    ok = {"night": {"bias": 0.1, "rmse": 0.5}, "day": {"bias": 0.1, "rmse": 0.5}}
    v = q.verdict("t", None, {"driftwood": ok, "neptune": ok}, True)
    assert v["qualifies"] is None and "not eligible" in v["why"]
    v = q.verdict("t", ok, {"driftwood": ok, "neptune": None}, True)
    assert v["qualifies"] is None


def test_verdict_uses_the_pre_registered_limits():
    def res(b, r=0.5):
        return {"night": {"bias": b, "rmse": r}, "day": {"bias": b, "rmse": r}}
    st_ok = {"driftwood": res(0.9), "neptune": res(-0.9)}
    assert q.verdict("t", res(0.5), st_ok, True)["qualifies"] is True            # bias at the 0.5 limit
    assert q.verdict("t", res(0.51), st_ok, True)["qualifies"] is False          # just over
    assert q.verdict("t", res(0.2, r=1.01), st_ok, True)["qualifies"] is False   # RMSE > 1.0
    assert q.verdict("t", res(0.2), {"driftwood": res(1.01), "neptune": res(0)}, True)["qualifies"] is False
    assert q.verdict("t", res(0.2), st_ok, False)["qualifies"] is False          # precision (A) fails
    assert q.verdict("dp", res(0.7, r=9.9), st_ok, True)["qualifies"] is True    # dp: no RMSE rule, bias limit 0.7
    assert q.verdict("dp", res(0.71), st_ok, True)["qualifies"] is False


def fake_world(n_days, monkeypatch):
    """n_days of hourly ticks; Mesonet (with or without a station) is a constant 40.0 F, Driftwood/Neptune read
    40.3 and the yard 41.0 (so the yard has a fixed +0.7 offset the calibration must remove)."""
    monkeypatch.setattr(q, "station_inputs", lambda meta: {})
    monkeypatch.setattr(q, "recompute_t", lambda tick, inp, drop=(): (40.0, 8))
    monkeypatch.setattr(q, "recompute_dp", lambda tick, inp, drop=(): 30.0)
    start = datetime(2026, 11, 10, 0, tzinfo=UTC)
    ticks, yard = {}, []
    for h in range(24 * n_days):
        t = start + timedelta(hours=h)
        ticks[t.strftime("%Y-%m-%dT%H:%MZ")] = {"readings": {
            "226429": {"valid": True, "t": 40.3, "rh": 60}, "192019": {"valid": True, "t": 40.3, "rh": 60}}}
        yard.append((int(t.timestamp()), {"t": 41.0, "dp": 31.0}))
    return ticks, yard


def test_guard_withholds_all_numbers_before_ten_nights(monkeypatch):
    ticks, yard = fake_world(8, monkeypatch)             # ~8 days: yard has < 10 scored nights after 5 calibration days
    out = q.score(ticks, {}, yard, {"t": True, "dp": True})
    for ref, r in out["references"].items():
        if not r["eligible"]:
            assert "scores" not in r, ref
    assert out["references"]["yard"]["eligible"] is False
    assert out["verdict"]["t"]["qualifies"] is None


def test_yard_offset_is_removed_and_scores_appear_once_eligible(monkeypatch):
    ticks, yard = fake_world(20, monkeypatch)
    out = q.score(ticks, {}, yard, {"t": True, "dp": True})
    y = out["references"]["yard"]
    assert y["eligible"] and y["nights"] >= q.MIN_NIGHTS
    t = y["scores"]["t"]
    assert t["offset_night"] == pytest.approx(0.7, abs=0.01)        # yard 41.0 vs Driftwood/Neptune 40.3
    assert t["night"]["bias"] == pytest.approx(40.0 - (41.0 - 0.7), abs=0.01)   # Mesonet 40.0 vs corrected yard 40.3
    assert out["verdict"]["t"]["qualifies"] is True


def test_no_scores_for_any_reference_until_all_are_eligible(monkeypatch):
    # Driftwood/Neptune have every night, the yard has too few: Neptune's numbers must still be withheld.
    ticks, yard = fake_world(20, monkeypatch)
    yard = yard[: 24 * 8]                                 # yard stops after 8 days: 3 scored days after calibration
    out = q.score(ticks, {}, yard, {"t": True, "dp": True})
    assert out["references"]["neptune"]["nights"] >= q.MIN_NIGHTS
    assert out["references"]["yard"]["eligible"] is False
    assert all("scores" not in r for r in out["references"].values())
    assert out["verdict"]["t"]["qualifies"] is None

"""
WU archive poller: own station polled first, merge dedupes on epoch, a 401/429 stops the
run without hammering the key; the live set polls only at LIVE_SLOTS_LOCAL, the rest only at
the 00/12 UTC slots, and nothing polls in between (11-22: each call returns a whole day).

Run: python3 -m pytest tests/test_wu_archive.py -v
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weather_collector.processors import wu_archive as wa  # noqa: E402

SLOT = datetime(2026, 11, 19, 12, 7, tzinfo=timezone.utc)       # rest slot (07:07 ET)
LIVE = datetime(2026, 11, 19, 16, 7, tzinfo=timezone.utc)       # live slot (11:07 ET)
LATE = datetime(2026, 11, 20, 4, 57, tzinfo=timezone.utc)       # live slot (23:57 ET)


class _Resp:
    def __init__(self, status, obs=None):
        self.status_code = status
        self._obs = obs or []

    def json(self):
        return {"observations": self._obs}


def _obs(ep, t=50.0):
    return {"epoch": ep, "lat": 42.5, "lon": -70.87, "humidityAvg": 60,
            "imperial": {"tempAvg": t, "pressureMax": 30.1, "dewptAvg": 40.0}}


def _run(responder, stations, now=SLOT):
    calls, saved = [], {}

    def get(url, params=None, timeout=None):
        calls.append(params["stationId"])
        return responder(params["stationId"])

    out = wa.append_wu_archive(
        stations, now_utc=now, key="k", get=get,
        load=lambda p, default=None: None,
        save=lambda doc, a, b: saved.update(doc=doc), sleep=lambda s: None)
    return out, calls, saved


def test_enabled():
    assert wa.WU_ARCHIVE_ENABLED is True


REST = ["KMAMARBL69", "KMAMARBL39", "KMAMARBL63"]  # KMAMARBL63 is also live: must not be polled twice


def test_own_station_polled_first_and_archived():
    out, calls, saved = _run(lambda sid: _Resp(200, [_obs(1), _obs(2)]), REST, now=LIVE)
    assert calls[0] == wa.OWN_STATION and calls.count(wa.OWN_STATION) == 1
    assert len(saved["doc"]["obs"][wa.OWN_STATION]) == 2
    assert calls.count("KMAMARBL63") == 1
    assert out["blocked"] is False


def test_live_slots_poll_live_only():
    for now in (LIVE, LATE):
        out, calls, _ = _run(lambda sid: _Resp(200, [_obs(1)]), REST, now=now)
        assert calls == list(wa.LIVE_STATIONS)


def test_rest_slot_polls_rest_only_never_live_twice():
    out, calls, _ = _run(lambda sid: _Resp(200, [_obs(1)]), REST)
    assert calls == ["KMAMARBL69", "KMAMARBL39"]


def test_block_stops_run_but_keeps_own_station():
    def responder(sid):
        return _Resp(200, [_obs(1)]) if sid == wa.OWN_STATION else _Resp(429)

    out, calls, saved = _run(responder, REST, now=LIVE)
    assert calls == [wa.OWN_STATION, wa.LIVE_STATIONS[1]]  # stopped at the first refusal
    assert out["blocked"] is True and out["added"] == 1
    assert wa.OWN_STATION in saved["doc"]["obs"]


def test_outside_slots_polls_nothing():
    out, calls, _ = _run(lambda sid: _Resp(200, [_obs(1)]), REST,
                         now=datetime(2026, 11, 19, 13, 7, tzinfo=timezone.utc))
    assert calls == [] and out is None


def test_live_set_budget():
    # live set 4x a day + the rest twice a day: ~100 calls/day (was ~1,150 with every-tick polling)
    per_day = len(wa.LIVE_STATIONS) * len(wa.LIVE_SLOTS_LOCAL) + 34 * len(wa.SLOT_HOURS_UTC)
    assert per_day <= 120, per_day
    assert wa.LIVE_STATIONS[0] == wa.OWN_STATION and len(set(wa.LIVE_STATIONS)) == len(wa.LIVE_STATIONS)


def test_merge_dedupes_on_epoch():
    doc = {"stations": {}, "obs": {}}
    rows = [{"ep": 1, "t": 50}, {"ep": 2, "t": 51}]
    assert wa.merge(doc, "S", rows, 1, 2) == 2
    assert wa.merge(doc, "S", rows + [{"ep": 3, "t": 52}], 1, 2) == 1
    assert [r["ep"] for r in doc["obs"]["S"]] == [1, 2, 3]

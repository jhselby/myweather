"""
WU archive poller: own station polled first, merge dedupes on epoch, a 401/429 stops the
run without hammering the key, and nothing polls outside the 00/06/12/18 UTC slots.

Run: python3 -m pytest tests/test_wu_archive.py -v
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weather_collector.processors import wu_archive as wa  # noqa: E402

SLOT = datetime(2026, 11, 19, 12, 7, tzinfo=timezone.utc)


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


def test_own_station_polled_first_and_archived():
    out, calls, saved = _run(lambda sid: _Resp(200, [_obs(1), _obs(2)]), ["KMAMARBL63", "KMAMARBL124"])
    assert calls[0] == wa.OWN_STATION and calls.count(wa.OWN_STATION) == 1
    assert len(saved["doc"]["obs"][wa.OWN_STATION]) == 2
    assert out == {"ok": 2, "added": 4, "blocked": False}


def test_block_stops_run_but_keeps_own_station():
    def responder(sid):
        return _Resp(200, [_obs(1)]) if sid == wa.OWN_STATION else _Resp(429)

    out, calls, saved = _run(responder, ["KMAMARBL63", "KMAMARBL69", "KMAMARBL4"])
    assert calls == [wa.OWN_STATION, "KMAMARBL63"]  # stopped at the first refusal
    assert out["blocked"] is True and out["added"] == 1
    assert wa.OWN_STATION in saved["doc"]["obs"]


def test_outside_slot_does_not_poll():
    out, calls, _ = _run(lambda sid: _Resp(200, [_obs(1)]), ["KMAMARBL63"],
                         now=datetime(2026, 11, 19, 13, 7, tzinfo=timezone.utc))
    assert out is None and calls == []


def test_merge_dedupes_on_epoch():
    doc = {"stations": {}, "obs": {}}
    rows = [{"ep": 1, "t": 50}, {"ep": 2, "t": 51}]
    assert wa.merge(doc, "S", rows, 1, 2) == 2
    assert wa.merge(doc, "S", rows + [{"ep": 3, "t": 52}], 1, 2) == 1
    assert [r["ep"] for r in doc["obs"]["S"]] == [1, 2, 3]

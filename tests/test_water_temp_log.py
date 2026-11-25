"""append_water_temp must write once per hour regardless of the minute the collector
reaches it. 11-25 bug: a `minute < 10` gate never passed because runs start at :07 and
reach this step several minutes later, so the log was never written."""
import os
from datetime import datetime

import pytz

os.environ.setdefault("GEMINI_API_KEY", "test")

from weather_collector.processors import water_temp_log as w  # noqa: E402

TZ = pytz.timezone("America/New_York")


class FakeTime(datetime):
    fixed = None

    @classmethod
    def now(cls, tz=None):
        return cls.fixed


def run(monkeypatch, store, minute, hour=10):
    FakeTime.fixed = TZ.localize(datetime(2026, 11, 25, hour, minute))
    monkeypatch.setattr(w, "datetime", FakeTime)
    monkeypatch.setattr(w, "fetch_buoy_44029_water_f", lambda: 51.4)
    monkeypatch.setattr(w, "load_json", lambda p, default=None: store.get(p, default))
    monkeypatch.setattr(w, "upload_json", lambda d, p, label: store.__setitem__(p, d))
    w.append_water_temp({"salem_water_temp_f": 52.1, "buoy_44013": {"water_temp_f": 52.3}})


def test_writes_when_run_reaches_step_after_minute_10(monkeypatch):
    store = {"cove_gradient_log.json": {"entries": []}}
    run(monkeypatch, store, minute=14)
    (row,) = store["water_temp_log.json"]["entries"]
    assert row == {"ts": "2026-11-25T10:00", "gomofs_f": 52.1, "b44013_f": 52.3, "b44029_f": 51.4}


def test_one_row_per_hour_then_next_hour(monkeypatch):
    store = {"cove_gradient_log.json": {"entries": []}}
    run(monkeypatch, store, minute=14)
    run(monkeypatch, store, minute=24)
    assert len(store["water_temp_log.json"]["entries"]) == 1
    run(monkeypatch, store, minute=12, hour=11)
    assert [e["ts"] for e in store["water_temp_log.json"]["entries"]] == ["2026-11-25T10:00", "2026-11-25T11:00"]


def test_seeds_from_cove_gradient_log(monkeypatch):
    old = {"entries": [{"ts": "2026-11-24T09:07", "salem_water_t": 51.0, "buoy_water_t": 51.5},
                       {"ts": "2026-11-24T09:17", "salem_water_t": 51.1, "buoy_water_t": 51.5}]}
    store = {"cove_gradient_log.json": old}
    run(monkeypatch, store, minute=14)
    ts = [e["ts"] for e in store["water_temp_log.json"]["entries"]]
    assert ts == ["2026-11-24T09:00", "2026-11-25T10:00"], ts


def test_first_run_writes_file_even_when_seed_already_has_this_hour(monkeypatch):
    # 11-25: the seed's last row was the current hour, so the "already logged" early-return
    # fired before the seeded file was ever uploaded and the log never existed.
    old = {"entries": [{"ts": "2026-11-25T10:07", "salem_water_t": 52.0, "buoy_water_t": 52.2}]}
    store = {"cove_gradient_log.json": old}
    run(monkeypatch, store, minute=14)
    assert [e["ts"] for e in store["water_temp_log.json"]["entries"]] == ["2026-11-25T10:00"]

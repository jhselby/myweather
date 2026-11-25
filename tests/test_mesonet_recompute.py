"""analysis.mesonet_recompute must reproduce what the collector recorded (l2.station_temp), or
every "Mesonet without station X" number built on it is meaningless.

Two layers:
  * synthetic: exact arithmetic on a hand-built tick (always runs);
  * archive: every archived tick since 11-08 (runs when MESONET_ARCHIVE_DIR points at a folder of
    station_readings/*.json, e.g. gsutil cp gs://myweather-data/station_readings/*.json DIR).
"""
import glob
import json
import os

import pytest

os.environ.setdefault("GEMINI_API_KEY", "test")

from analysis.mesonet_recompute import recompute_t, station_inputs  # noqa: E402
from weather_collector.processors.hyperlocal import station_weight  # noqa: E402

# lat/lon chosen so stations fall in distinct octants of the home point
META = {
    "1": {"latitude": 42.512, "longitude": -70.875, "elevation_ft": 30.0, "distance_mi": 0.8},   # N
    "2": {"latitude": 42.501, "longitude": -70.855, "elevation_ft": 30.0, "distance_mi": 1.1},   # E
    "3": {"latitude": 42.490, "longitude": -70.875, "elevation_ft": 30.0, "distance_mi": 0.8},   # S
    "4": {"latitude": 42.501, "longitude": -70.895, "elevation_ft": 30.0, "distance_mi": 1.1},   # W
}


def tick(vals, offs=None):
    offs = offs or {}
    return {"readings": {k: {"valid": True, "t": v, "off_t": offs.get(k)} for k, v in vals.items()}}


def test_station_weight_inverse_square_and_elevation():
    assert station_weight(1.0, 30.0) == pytest.approx(1.0)
    assert station_weight(2.0, 30.0) == pytest.approx(0.25)
    assert station_weight(1.0, 60.0) == pytest.approx(2.718281828 ** -1, rel=1e-3)
    assert station_weight(1.0, None) == station_weight(1.0, 30.0)


def test_one_station_per_octant_is_plain_mean_of_offset_corrected_values():
    inp = station_inputs(META)
    v, n = recompute_t(tick({"1": 40, "2": 42, "3": 44, "4": 46}, {"2": 1.0}), inp)
    assert n == 4 and v == pytest.approx((40 + 41 + 44 + 46) / 4)


def test_dropping_a_station_drops_its_octant():
    inp = station_inputs(META)
    t = tick({"1": 40, "2": 42, "3": 44, "4": 46})
    v, n = recompute_t(t, inp, drop={"4"})
    assert n == 3 and v == pytest.approx((40 + 42 + 44) / 3)
    assert recompute_t(t, inp, drop={"3", "4"}) == (None, 2)   # below 3 octants


def test_invalid_or_far_stations_are_ignored():
    meta = dict(META, **{"9": {"latitude": 42.6, "longitude": -70.7, "elevation_ft": 30.0, "distance_mi": 9.0}})
    assert "9" not in station_inputs(meta)
    t = tick({"1": 40, "2": 42, "3": 44, "4": 46})
    t["readings"]["4"]["valid"] = False
    assert recompute_t(t, station_inputs(META))[1] == 3


ARCH = os.environ.get("MESONET_ARCHIVE_DIR")


@pytest.mark.skipif(not ARCH or not glob.glob(os.path.join(ARCH or "", "*.json")),
                    reason="set MESONET_ARCHIVE_DIR to a folder of station_readings/*.json")
def test_reproduces_recorded_station_temp_on_every_archived_tick():
    n = bad = 0
    worst = 0.0
    for f in sorted(glob.glob(os.path.join(ARCH, "*.json"))):
        doc = json.load(open(f))
        inp = station_inputs(doc["stations"])
        for t in doc["ticks"]:
            l2 = t.get("l2") or {}
            if l2.get("aggregation") != "octant_balanced" or l2.get("station_temp") is None:
                continue
            v, _ = recompute_t(t, inp)
            if v is None:
                bad += 1
                continue
            n += 1
            err = abs(v - l2["station_temp"])
            worst = max(worst, err)
            if err > 0.051:   # recorded value is rounded to 0.1
                bad += 1
    assert n > 500, f"too few ticks compared: {n}"
    assert bad == 0, f"{bad} of {n + bad} ticks differ from the recorded station_temp (worst {worst:.2f} F)"

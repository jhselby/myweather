"""Recompute the Mesonet temperature from one archived tick, optionally WITHOUT some stations.

Uses the collector's own functions (weather_collector.processors.hyperlocal: station_weight,
octant_balanced_value, _octant_index, MAX_STATION_DIST_MI) so the analysis cannot drift from
what is served. Needed by docs/PLAN_mesonet_model_split.md §1.8: Driftwood Rd and Neptune Rd are
in the Mesonet, so the Mesonet is recomputed without each before it is compared to that station.

The model temperature cancels exactly (station_temp = model_t + mean of octant means of
(value - model_t)), so the recompute needs only the offset-corrected station readings.
tests/test_mesonet_recompute.py proves it reproduces the recorded l2.station_temp.
"""
import collections

from weather_collector.processors.hyperlocal import (MAX_STATION_DIST_MI, _octant_index,
                                                     octant_balanced_value, station_weight)
from weather_collector.processors.station_bias import HUMIDITY_DENYLIST
from weather_collector.utils import magnus_dew_point_f


def station_inputs(stations_meta):
    """{sid: (octant, distance_mi, elevation_ft)} for stations the collector would accept."""
    out = {}
    for sid, m in stations_meta.items():
        d, el = m.get("distance_mi"), m.get("elevation_ft")
        if not d or d > MAX_STATION_DIST_MI or el is None:
            continue
        o = _octant_index(m.get("latitude"), m.get("longitude"))
        if o is None:
            continue
        out[str(sid)] = (o, d, el)
    return out


def _recompute(tick, inputs, drop, value_of):
    lists = collections.defaultdict(list)
    for sid, r in (tick.get("readings") or {}).items():
        sid = str(sid)
        if sid in drop or sid not in inputs or not r.get("valid"):
            continue
        v = value_of(sid, r)
        if v is None:
            continue
        o, d, el = inputs[sid]
        lists[o].append((v, station_weight(d, el)))
    return octant_balanced_value([lists[i] for i in range(8)])


def recompute_t(tick, inputs, drop=()):
    """(station_temp_or_None, octants_used) for one tick, excluding station ids in `drop`."""
    return _recompute(tick, inputs, drop,
                      lambda sid, r: None if r.get("t") is None else r["t"] - (r.get("off_t") or 0.0))


def recompute_h(tick, inputs, drop=()):
    """(station_humidity_or_None, octants_used): same weights and trim on offset-corrected RH,
    skipping the broken-sensor denylist (as hyperlocal.py does)."""
    return _recompute(tick, inputs, drop,
                      lambda sid, r: None if (sid in HUMIDITY_DENYLIST or not r.get("rh"))
                      else r["rh"] - (r.get("off_rh") or 0.0))


def recompute_dp(tick, inputs, drop=()):
    """Magnus dew point of the recomputed temperature and humidity (as the pair log's observed_stations)."""
    t, _ = recompute_t(tick, inputs, drop)
    h, _ = recompute_h(tick, inputs, drop)
    return None if t is None or h is None or not 0 < h <= 100 else magnus_dew_point_f(t, h)

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


def recompute_t(tick, inputs, drop=()):
    """(station_temp_or_None, octants_used) for one tick, excluding station ids in `drop`."""
    lists = collections.defaultdict(list)
    for sid, r in (tick.get("readings") or {}).items():
        sid = str(sid)
        if sid in drop or sid not in inputs or not r.get("valid") or r.get("t") is None:
            continue
        o, d, el = inputs[sid]
        lists[o].append((r["t"] - (r.get("off_t") or 0.0), station_weight(d, el)))
    return octant_balanced_value([lists[i] for i in range(8)])

"""Which truth a fit scores against (v0.7.94).

The pair log's `observed` for t/h/dp/ws/wg is the station aggregate shrunk toward
the model (model + K * bias), so fits on it reward staying near the model and can
never test K. `observed_stations` (model-free, logged since 2026-11-02 18:07) is the
truth Joe set: the station network. A residual re-expressed on it is
    e_stations = e + (observed - observed_stations).

truth_shift(row, stations=True) returns the amount to add to every error_* of the
row, or None when the row must be dropped (a station-truth field without the
column), so one fit never mixes the two truths. Fields without a station column
(sr, cc, pr, ...) keep `observed` and shift 0.
"""
STATION_TRUTH_FIELDS = frozenset({"t", "h", "dp", "ws", "wg"})


def truth_shift(row, stations):
    if not stations or row.get("field") not in STATION_TRUTH_FIELDS:
        return 0.0
    obs, obs_s = row.get("observed"), row.get("observed_stations")
    if obs is None or obs_s is None:
        return None
    return float(obs) - float(obs_s)


def truth_value(row, stations):
    """The observed value a fit should use, or None to drop the row."""
    sh = truth_shift(row, stations)
    if sh is None or row.get("observed") is None:
        return None
    return float(row["observed"]) - sh

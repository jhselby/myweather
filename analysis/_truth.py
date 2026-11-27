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


# 11-27: the fixed truth per field (plan Step 3.1, the table the scorecard grades on), for the
# selector scoring (per_field_scoring, scoreboard_v2). Before this the digest's SELECTOR block
# graded on the model-blended `observed` the scorecard retired on 11-22.
URMA_FIXED = {"t": ("TMP", "urma_truth_t.json"), "dp": ("DPT", "urma_truth_dpt.json"),
              "ws": ("WIND", "urma_truth_wind.json"), "wg": ("GUST", "urma_truth_gust.json"),
              "cc": ("TCDC", "urma_truth_tcdc.json")}
H_MIN_LEAD = 6   # h on the Mesonet only where the stations do not feed the forecast (L2 reads them below 6 h)


class FixedTruth:
    """rebase(row) re-expresses every error_* of a pair-log row on the field's fixed truth
    (e_fixed = e + (observed - truth)) and sets row["observed"] to it. Returns False when the
    row must be dropped (no truth for that hour, or h below H_MIN_LEAD), so a window never
    mixes truths. Fields with no fixed truth (sr, pa, pp, wd, cl, cm, ch, pr) pass unchanged.
    A field whose URMA store fails to load keeps `observed` for every row and says so in labels()."""

    def __init__(self):
        from analysis.truth_compare import _urma, _utc_hour
        self._hour = _utc_hour
        self.urma = {}
        for f, (var, store) in URMA_FIXED.items():
            d = _urma(var, store)
            if d:
                self.urma[f] = d

    def labels(self):
        out = {f: ("URMA" if f in self.urma else "logged observed (URMA unavailable)") for f in URMA_FIXED}
        out["h"] = f"Mesonet (observed_stations), leads {H_MIN_LEAD}-47h"
        return out

    def rebase(self, row):
        f = row.get("field")
        if f in self.urma:
            tv = self.urma[f].get(self._hour(row.get("valid_time") or ""))
        elif f == "h":
            lead = row.get("lead_h")
            if lead is None or lead < H_MIN_LEAD:
                return False
            tv = row.get("observed_stations")
        else:
            return True
        obs = row.get("observed")
        if tv is None or obs is None:
            return False
        shift = float(obs) - float(tv)
        for k, v in row.items():
            if k.startswith("error") and isinstance(v, (int, float)) and not isinstance(v, bool):
                row[k] = v + shift
        row["observed"] = float(tv)
        return True

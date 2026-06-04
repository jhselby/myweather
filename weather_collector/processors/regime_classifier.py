"""
Rule-based regime classifier producing two orthogonal labels per state:

  regime_flow      — pure wind direction (n / ne / e / se / s / sw / w / nw / calm).
                     Describes "which way is the air moving right now," no interpretation.

  regime_synoptic  — coastal-flavored synoptic pattern (nw_flow, sw_flow, se_flow,
                     ne_flow, sea_breeze, nor_easter, frontal, pre_frontal, calm).
                     Describes the synoptic pattern using terms that matter at
                     Marblehead specifically (sea breeze, nor'easter as distinct
                     regimes from a generic "wind from SE" or "wind from NE").

Called by forecast_error_log.py when building state_fc and state_obs dicts
on every pair (post-v0.6.38). The labels are diagnostic only at first —
downstream analytics (analysis/state_stratified_accuracy.py with regime as
a 5th dimension; future regime-stratified correction layers) consume them.

Both classifiers tolerate None inputs and return None when a label cannot
be determined.
"""

FLOW_OCTANTS = ["n", "ne", "e", "se", "s", "sw", "w", "nw"]


def classify_flow_regime(wind_dir_deg, wind_speed_mph):
    """Pure direction. Returns one of FLOW_OCTANTS or 'calm', or None.

    Threshold for calm is 3 mph — below that, direction is meaningless noise
    (calm air swirls). Above 3 mph, bin into one of 8 compass octants of
    width 45° centered on N (337.5–22.5), NE (22.5–67.5), etc.
    """
    if wind_speed_mph is None:
        return None
    if wind_speed_mph < 3:
        return "calm"
    if wind_dir_deg is None:
        return None
    d = (float(wind_dir_deg) + 22.5) % 360
    return FLOW_OCTANTS[int(d // 45)]


def classify_synoptic_regime(wind_dir_deg, wind_speed_mph, pressure_in,
                             pressure_trend_3h, hour_local, temp_f):
    """Coastal-flavored synoptic regime. Tries the special patterns first
    (frontal, sea_breeze, nor'easter) then falls back to direction-named
    flow regimes (nw_flow / sw_flow / se_flow / ne_flow). Returns one of:

      frontal       — rapid pressure drop (|Δ| ≥ 2 hPa/3h)
      pre_frontal   — pressure dropping notably (Δ between −2 and −0.7)
      nor_easter    — NE flow + low pressure + windy
      sea_breeze    — SE flow in summer afternoons, light + warm + steady pressure
      nw_flow       — NW direction outside the above patterns
      sw_flow       — SW direction
      se_flow       — SE direction (when not sea_breeze)
      ne_flow       — NE direction (when not nor_easter)
      calm          — wind < 3 mph
      None          — input insufficient to classify
    """
    if wind_speed_mph is None:
        return None
    if wind_speed_mph < 3:
        return "calm"

    # Frontal passage: rapid pressure swing in the last 3h.
    if pressure_trend_3h is not None:
        if pressure_trend_3h <= -2.0:
            return "frontal"
        if pressure_trend_3h <= -0.7:
            return "pre_frontal"

    if wind_dir_deg is None:
        return None
    d = float(wind_dir_deg) % 360

    # Nor'easter pattern: NE flow + low pressure + strong wind.
    if 30 <= d < 80:
        if (pressure_in is not None and pressure_in < 29.9
                and wind_speed_mph >= 12):
            return "nor_easter"
        return "ne_flow"

    # Sea breeze: SE quadrant flow, summer afternoons, light wind, warm,
    # pressure steady (rules out frontal/post-frontal SE pushes).
    if 90 <= d < 200:
        is_sea_breeze = (
            hour_local is not None and 12 <= hour_local <= 19
            and wind_speed_mph < 14
            and temp_f is not None and temp_f >= 68
            and (pressure_trend_3h is None or abs(pressure_trend_3h) < 0.7)
        )
        if is_sea_breeze:
            return "sea_breeze"
        return "se_flow"

    # SW flow: warm southerly air, often pre-frontal.
    if 200 <= d < 290:
        return "sw_flow"

    # NW flow: post-frontal cold/dry continental.
    if 290 <= d or d < 30:
        return "nw_flow"

    return None

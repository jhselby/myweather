"""
Hyperlocal corrections using Weather Underground station data
"""
import math
import statistics
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from ..config import ELEVATION_FT, LAT as HOME_LAT, LON as HOME_LON

_EASTERN = ZoneInfo("America/New_York")

# Octant labels (compass sectors, 45° each, centered on cardinal/intercardinal).
# Index 0 = N (337.5°–22.5°), 1 = NE, 2 = E, ..., 7 = NW.
OCTANT_LABELS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
MAX_STATION_DIST_MI = 2.5
MIN_OCTANTS_FOR_BALANCED = 3  # need ≥ this many non-empty octants to use octant mean
# Outlier trimming (v0.6.24): drop stations whose value is > OUTLIER_K * MAD from
# the octant's median before computing the octant weighted mean. MAD instead of
# std is critical — std is inflated by the very outliers we want to catch, which
# can make a +5°F sensor protect itself by widening the threshold past its own
# deviation. MAD is unaffected. k=3.5 keeps almost all genuine variation while
# rejecting busted-sensor reads (>~4°F from local median for temperature).
OUTLIER_K = 3.5
MIN_FOR_TRIMMING = 3  # need ≥3 stations in an octant to detect outliers meaningfully


def _octant_index(station_lat, station_lon):
    """Return 0–7 octant index of station relative to home (compass bearing)."""
    if station_lat is None or station_lon is None:
        return None
    lat1 = math.radians(HOME_LAT)
    lat2 = math.radians(station_lat)
    dlon = math.radians(station_lon - HOME_LON)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = (math.degrees(math.atan2(x, y)) + 360.0) % 360.0
    return int(((bearing + 22.5) % 360) / 45)


def _trimmed_weighted_mean(items):
    """MAD-trimmed weighted mean of (value, weight) tuples.

    Returns (mean_or_None, n_trimmed). Used per-octant to drop a single
    busted-sensor reading from corrupting the octant's contribution to the
    network bias. With <MIN_FOR_TRIMMING items, no trimming is applied
    (can't detect outliers from <3 samples); the unweighted-trimmed weighted
    mean of all items is returned with n_trimmed=0.
    """
    if not items:
        return None, 0
    if len(items) < MIN_FOR_TRIMMING:
        total_w = sum(w for _, w in items)
        if total_w <= 0:
            return None, 0
        return sum(v * w for v, w in items) / total_w, 0
    vals = [v for v, _ in items]
    median = statistics.median(vals)
    abs_devs = [abs(v - median) for v in vals]
    mad = statistics.median(abs_devs)
    # MAD = 0 means all values are identical (or all but one); fall back to
    # no trimming so we don't reject every non-median point.
    if mad <= 0:
        kept = items
    else:
        # MAD * 1.4826 ≈ std for normal distributions; OUTLIER_K is multiples of std-equivalent
        threshold = OUTLIER_K * 1.4826 * mad
        kept = [(v, w) for v, w in items if abs(v - median) <= threshold]
    if not kept:
        kept = items  # safety: never trim everything
    n_trimmed = len(items) - len(kept)
    total_w = sum(w for _, w in kept)
    if total_w <= 0:
        return None, n_trimmed
    return sum(v * w for v, w in kept) / total_w, n_trimmed


def _kalman_gain(n_stations, bias_std):
    # Thresholds retuned in v0.6.23 for the v0.6.17 octant-scatter bias_std
    # metric. Old (1.0 / 2.0) were calibrated for per-station scatter (~30
    # individual readings disagreeing). Per-octant means are tighter (averages
    # of averages), so under the new metric typical values land in the 0.3–1.0
    # range — old thresholds always returned K=0.9, over-applying the bias.
    # New (0.4 / 0.8) keep ~the same fraction of days in each bucket as before.
    if n_stations >= 5 and bias_std < 0.4:
        return 0.90
    elif n_stations >= 3 and bias_std < 0.8:
        return 0.65
    else:
        return 0.40


def compute_dew_point_spread(temp_f, dew_point_f):
    """
    Compute dew point spread in Fahrenheit.
    
    Args:
        temp_f: Temperature in Fahrenheit
        dew_point_f: Dew point in Fahrenheit
    
    Returns:
        Dew point spread in F, or None if inputs invalid
    """
    if temp_f is None or dew_point_f is None:
        return None
    return round(temp_f - dew_point_f, 1)


def build_hyperlocal_data(weather_data, wu_data, pws_data, kbos_data, tempest_data=None, station_offsets=None, kbvy_data=None):
    """
    Build complete hyperlocal correction data.
    This modifies weather_data in place by adding a 'hyperlocal' key.
    
    Args:
        weather_data: Main weather data dict
        wu_data: Weather Underground multi-station data
        pws_data: Personal weather station data
        kbos_data: KBOS observation data
    """
    hyperlocal = {}
    
    current = weather_data.get("current", {})
    model_t = current.get("temperature")
    model_h = current.get("humidity")
    model_p = current.get("pressure")
    
    # Convert pressure to inHg
    model_p_in = round(model_p / 33.8639, 2) if model_p else None
    kbos_p = kbos_data.get("pressure_hpa") if kbos_data else None
    kbos_p_in = round(kbos_p / 33.8639, 2) if kbos_p else None
    
    # Temperature - SMART BIAS CORRECTION using individual stations
    wu_stations_attempted = wu_data.get("quality", {}).get("total_stations", 0) if wu_data else 0
    tempest_stations_attempted = len(tempest_data.get("stations", [])) if tempest_data else 0
    stations = wu_data.get("stations", []) if wu_data else []
    # Inject all valid Tempest stations as additional high-quality inputs
    if tempest_data:
        for tb in tempest_data.get("stations", []):
            if tb.get("valid") and tb.get("temperature_f") and tb.get("distance_mi") and tb.get("elevation_ft") is not None:
                stations = list(stations) + [tb]
    
    _offsets = station_offsets or {}
    _is_day = 7 <= datetime.now(timezone.utc).astimezone(_EASTERN).hour < 19
    _temp_split = _offsets.get("temp_day" if _is_day else "temp_night", {})
    temp_offsets = {**_offsets.get("temp", {}), **_temp_split}  # split overrides combined
    humidity_offsets = _offsets.get("humidity", {})
    pressure_offsets = _offsets.get("pressure", {})

    if model_t is not None and stations:
        # Per-octant lists of (value, weight) tuples — collected first, then
        # MAD-trimmed and weighted-averaged per octant (see _trimmed_weighted_mean).
        # Two-pass keeps outlier detection robust: a single +5°F busted sensor
        # in a sparse octant gets dropped before contributing to the network bias.
        oct_temp = [[] for _ in range(8)]
        oct_h    = [[] for _ in range(8)]
        oct_p    = [[] for _ in range(8)]
        oct_station_count = [0] * 8
        station_biases = []  # kept for legacy bias_std fallback
        stations_used = 0

        for station in stations:
            station_temp = station.get('temperature_f')
            station_dist = station.get('distance_mi')
            station_elev = station.get('elevation_ft')
            station_lat  = station.get('latitude')
            station_lon  = station.get('longitude')

            # Skip stations with missing core data
            if station_temp is None or station_dist is None:
                continue
            if station_dist == 0 or station_dist > MAX_STATION_DIST_MI:
                continue
            # No-elevation stations get no elevation penalty (treated as same elev as home)
            if station_elev is None:
                station_elev = ELEVATION_FT
            oct = _octant_index(station_lat, station_lon)
            if oct is None:
                continue

            sid = str(station.get('station_id') or station.get('station_name') or '')

            # Distance weight: 1/distance² (inverse square law)
            dist_weight = 1.0 / (station_dist ** 2)
            elev_diff = abs(station_elev - ELEVATION_FT)
            elev_weight = math.exp(-elev_diff / 30.0)
            weight = dist_weight * elev_weight

            # Temperature bias
            corrected_temp_s = station_temp - temp_offsets.get(sid, 0.0)
            bias_at_station = corrected_temp_s - model_t
            oct_temp[oct].append((bias_at_station, weight))
            oct_station_count[oct] += 1
            station_biases.append(bias_at_station)
            stations_used += 1

            # Humidity
            raw_h = station.get('humidity_pct') or station.get('relative_humidity')
            if raw_h is not None:
                corrected_h = raw_h - humidity_offsets.get(sid, 0.0)
                oct_h[oct].append((corrected_h, weight))

            # Pressure
            raw_p = station.get('pressure_in')
            if raw_p is None:
                p_mb = station.get('sea_level_pressure_mb')
                raw_p = round(p_mb / 33.8639, 3) if p_mb is not None else None
            if raw_p is not None:
                corrected_p = raw_p - pressure_offsets.get(sid, 0.0)
                oct_p[oct].append((corrected_p, weight))

        # Trim outliers per octant, then take the octant weighted mean.
        # n_trimmed_per_octant lets us report total trim count to the debug page.
        temp_results = [_trimmed_weighted_mean(oct_temp[i]) for i in range(8)]
        h_results    = [_trimmed_weighted_mean(oct_h[i])    for i in range(8)]
        p_results    = [_trimmed_weighted_mean(oct_p[i])    for i in range(8)]
        temp_octant_means = [m for m, _ in temp_results if m is not None]
        h_octant_means    = [m for m, _ in h_results    if m is not None]
        p_octant_means    = [m for m, _ in p_results    if m is not None]
        outliers_trimmed  = sum(n for _, n in temp_results)
        octants_used      = len(temp_octant_means)

        if stations_used >= 3 and (octants_used >= MIN_OCTANTS_FOR_BALANCED or stations_used >= 3):
            # Use octant mean when we have ≥3 octants; otherwise fall back to
            # flat mean across whatever bias values we collected (rare with
            # 81-station catchment, but handles winter-sparse periods).
            if octants_used >= MIN_OCTANTS_FOR_BALANCED:
                weighted_bias = sum(temp_octant_means) / octants_used
                aggregation = "octant_balanced"
                # bias_std now measures geographic disagreement between octants
                bias_std = statistics.stdev(temp_octant_means) if octants_used > 1 else None
            else:
                weighted_bias = sum(station_biases) / len(station_biases)
                aggregation = "flat_fallback"
                bias_std = statistics.stdev(station_biases) if len(station_biases) > 1 else None

            if bias_std is None:
                confidence = "Low"
            elif bias_std < 1.0:
                confidence = "High"
            elif bias_std < 2.0:
                confidence = "Moderate"
            else:
                confidence = "Low"

            K = _kalman_gain(stations_used, bias_std if bias_std is not None else 99)
            corrected_temp = model_t + K * weighted_bias

            hyperlocal["model_temp"] = round(model_t, 1)
            hyperlocal["weighted_bias"] = round(weighted_bias, 2)
            hyperlocal["kalman_gain"] = round(K, 2)
            hyperlocal["corrected_temp"] = round(corrected_temp, 1)
            hyperlocal["stations_used"] = stations_used
            hyperlocal["stations_total"] = wu_stations_attempted + tempest_stations_attempted
            hyperlocal["confidence"] = confidence
            hyperlocal["bias_std"] = round(bias_std, 2) if bias_std is not None else None
            hyperlocal["aggregation"] = aggregation
            hyperlocal["octants_used"] = octants_used
            hyperlocal["octant_coverage"] = {
                OCTANT_LABELS[i]: oct_station_count[i] for i in range(8)
            }
            hyperlocal["outliers_trimmed"] = outliers_trimmed
            if _offsets:
                hyperlocal["station_offsets"] = _offsets

            wu_t = wu_data.get("temperature_f") if wu_data else None
            if wu_t is not None:
                hyperlocal["wu_avg_temp"] = round(wu_t, 1)

            # Humidity octant-balanced
            if h_octant_means:
                corrected_humidity = sum(h_octant_means) / len(h_octant_means)
                hyperlocal["corrected_humidity"] = round(corrected_humidity, 1)
                if model_h is not None:
                    hyperlocal["model_humidity"] = model_h
                    hyperlocal["bias_humidity"] = round(corrected_humidity - model_h, 1)

            # Pressure octant-balanced
            if p_octant_means:
                corrected_pressure = sum(p_octant_means) / len(p_octant_means)
                hyperlocal["corrected_pressure_in"] = round(corrected_pressure, 2)
                if model_p_in is not None:
                    hyperlocal["model_pressure_in"] = model_p_in
                    hyperlocal["bias_pressure_in"] = round(corrected_pressure - model_p_in, 3)
    
    # Fallback: WU stations available but model temp missing — use WU average directly
    elif model_t is None and stations:
        weighted_sum = 0.0
        total_weight = 0.0
        for station in stations:
            st = station.get('temperature_f')
            sd = station.get('distance_mi')
            se = station.get('elevation_ft')
            if st is None or sd is None or sd == 0 or sd > MAX_STATION_DIST_MI:
                continue
            if se is None:
                se = ELEVATION_FT
            dist_w = 1.0 / (sd ** 2)
            elev_w = math.exp(-abs(se - ELEVATION_FT) / 30.0)
            w = dist_w * elev_w
            weighted_sum += st * w
            total_weight += w
        if total_weight > 0:
            corrected = weighted_sum / total_weight
            hyperlocal["corrected_temp"] = round(corrected, 1)
            hyperlocal["stations_used"] = len([s for s in stations if s.get('temperature_f') and s.get('distance_mi') and s['distance_mi'] <= MAX_STATION_DIST_MI])
            hyperlocal["confidence"] = "Moderate"
            hyperlocal["note"] = "GFS model unavailable, using WU stations directly"

    # Fallback to PWS if WU not available
    elif model_t is not None and pws_data:
        pws_t = pws_data.get("temperature")
        if pws_t is not None:
            hyperlocal["model_temp"] = round(model_t, 1)
            hyperlocal["pws_temp"] = round(pws_t, 1)
            hyperlocal["simple_bias"] = round(pws_t - model_t, 2)
            hyperlocal["corrected_temp"] = round(pws_t, 1)
    
    # Pressure fallback if per-station average not available
    if "corrected_pressure_in" not in hyperlocal:
        wu_p_in = wu_data.get("pressure_in") if wu_data else None
        hyperlocal["corrected_pressure_in"] = wu_p_in or kbos_p_in or model_p_in
    if model_p_in is not None:
        hyperlocal["model_pressure_in"] = model_p_in
    if kbos_p_in is not None:
        hyperlocal["kbos_pressure_in"] = kbos_p_in
    
    # Wind Speed — current.wind_speed is already max-selected by collector
    # current.model_wind_speed has the original model value (saved before override)
    model_w = current.get("model_wind_speed")
    corrected_w = current.get("wind_speed")  # Max-selected by collector
    wu_w = wu_data.get("wind_speed_mph") if wu_data else None
    if model_w is not None:
        hyperlocal["model_wind_speed"] = model_w
    if corrected_w is not None:
        hyperlocal["corrected_wind_speed"] = corrected_w
    if model_w is not None and corrected_w is not None:
        hyperlocal["bias_wind_speed"] = round(corrected_w - model_w, 1)
    if wu_w is not None:
        hyperlocal["wu_wind_speed"] = wu_w
    
    # Wind Gusts — collector already max-selected from model + KBVY + WU stations
    # current.model_wind_gusts has original model value, current.wind_gusts has max-selected
    model_g = current.get("model_wind_gusts")
    corrected_g = current.get("wind_gusts")
    if model_g is not None:
        hyperlocal["model_wind_gusts"] = round(model_g, 1)
    if corrected_g is not None:
        hyperlocal["corrected_wind_gusts"] = round(corrected_g, 1)
    if model_g is not None and corrected_g is not None:
        hyperlocal["bias_wind_gusts"] = round(corrected_g - model_g, 1)
    
    # WU quality metrics
    if wu_data:
        wu_quality = wu_data.get("quality", {})
        hyperlocal["wu_stations_temp"] = wu_quality.get("stations_used_temp", 0)
        hyperlocal["wu_stations_wind"] = wu_quality.get("stations_used_wind", 0)
    
    # KBVY reference temperature — external calibrated anchor (ASOS, 6.3mi NW)
    if kbvy_data:
        kbvy_t = kbvy_data.get("temp_f")
        if kbvy_t is not None:
            hyperlocal["kbvy_temp_f"] = kbvy_t
            corrected = hyperlocal.get("corrected_temp")
            if corrected is not None:
                hyperlocal["kbvy_local_delta"] = round(corrected - kbvy_t, 2)

    if hyperlocal:
        weather_data["hyperlocal"] = hyperlocal
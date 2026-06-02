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


def _kalman_gain(n_stations, bias_std):
    if n_stations >= 5 and bias_std < 1.0:
        return 0.90
    elif n_stations >= 3 and bias_std < 2.0:
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
        # Per-octant accumulators (8 sectors × {temp_bias, humidity, pressure})
        oct_temp_wsum = [0.0] * 8
        oct_temp_wt   = [0.0] * 8
        oct_h_wsum    = [0.0] * 8
        oct_h_wt      = [0.0] * 8
        oct_p_wsum    = [0.0] * 8
        oct_p_wt      = [0.0] * 8
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
            oct_temp_wsum[oct] += bias_at_station * weight
            oct_temp_wt[oct]   += weight
            oct_station_count[oct] += 1
            station_biases.append(bias_at_station)
            stations_used += 1

            # Humidity
            raw_h = station.get('humidity_pct') or station.get('relative_humidity')
            if raw_h is not None:
                corrected_h = raw_h - humidity_offsets.get(sid, 0.0)
                oct_h_wsum[oct] += corrected_h * weight
                oct_h_wt[oct]   += weight

            # Pressure
            raw_p = station.get('pressure_in')
            if raw_p is None:
                p_mb = station.get('sea_level_pressure_mb')
                raw_p = round(p_mb / 33.8639, 3) if p_mb is not None else None
            if raw_p is not None:
                corrected_p = raw_p - pressure_offsets.get(sid, 0.0)
                oct_p_wsum[oct] += corrected_p * weight
                oct_p_wt[oct]   += weight

        # Octant-balanced means: per-octant weighted mean, then unweighted mean
        # across non-empty octants. Prevents any compass sector with high PWS
        # density from dominating the network bias.
        temp_octant_means = [oct_temp_wsum[i] / oct_temp_wt[i] for i in range(8) if oct_temp_wt[i] > 0]
        h_octant_means    = [oct_h_wsum[i]    / oct_h_wt[i]    for i in range(8) if oct_h_wt[i]    > 0]
        p_octant_means    = [oct_p_wsum[i]    / oct_p_wt[i]    for i in range(8) if oct_p_wt[i]    > 0]
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
                hyperlocal["corrected_pressure_in"] = round(sum(p_octant_means) / len(p_octant_means), 2)
    
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
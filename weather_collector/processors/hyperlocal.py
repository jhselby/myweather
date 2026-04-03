"""
Hyperlocal corrections using Weather Underground station data
"""
import math
import statistics
from ..config import ELEVATION_FT


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


def build_hyperlocal_data(weather_data, wu_data, pws_data, kbos_data):
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
    stations = wu_data.get("stations", []) if wu_data else []
    
    if model_t is not None and stations:
        weighted_bias_sum = 0.0
        total_weight = 0.0
        station_biases = []
        stations_used = 0
        
        for station in stations:
            station_temp = station.get('temperature_f')
            station_dist = station.get('distance_mi')
            station_elev = station.get('elevation_ft')
            
            # Skip stations with missing data
            if station_temp is None or station_dist is None or station_elev is None:
                continue
            if station_dist == 0 or station_dist > 1.5:  # Distance filter
                continue
                
            # Calculate bias at this station
            bias_at_station = station_temp - model_t
            
            # Distance weight: 1/distance² (inverse square law)
            dist_weight = 1.0 / (station_dist ** 2)
            
            # Elevation weight: exp(-|elev_diff|/30)
            # Characteristic scale = 30ft (typical elevation variation in Marblehead)
            elev_diff = abs(station_elev - ELEVATION_FT)
            elev_weight = math.exp(-elev_diff / 30.0)
            
            # Combined weight
            weight = dist_weight * elev_weight
            
            weighted_bias_sum += bias_at_station * weight
            total_weight += weight
            station_biases.append(bias_at_station)
            stations_used += 1
        
        # Calculate weighted average bias
        if total_weight > 0 and stations_used >= 3:
            weighted_bias = weighted_bias_sum / total_weight
            corrected_temp = model_t + weighted_bias
            
            # Calculate confidence based on bias agreement
            if len(station_biases) > 1:
                bias_std = statistics.stdev(station_biases)
                if bias_std < 1.0:
                    confidence = "High"
                elif bias_std < 2.0:
                    confidence = "Moderate"
                else:
                    confidence = "Low"
            else:
                confidence = "Low"
            
            hyperlocal["model_temp"] = round(model_t, 1)
            hyperlocal["weighted_bias"] = round(weighted_bias, 2)
            hyperlocal["corrected_temp"] = round(corrected_temp, 1)
            hyperlocal["stations_used"] = stations_used
            hyperlocal["stations_total"] = len(stations)
            hyperlocal["confidence"] = confidence
            
            # For reference, also show simple WU average
            wu_t = wu_data.get("temperature_f") if wu_data else None
            if wu_t is not None:
                hyperlocal["wu_avg_temp"] = round(wu_t, 1)
    
    # Fallback to PWS if WU not available
    elif model_t is not None and pws_data:
        pws_t = pws_data.get("temperature")
        if pws_t is not None:
            hyperlocal["model_temp"] = round(model_t, 1)
            hyperlocal["pws_temp"] = round(pws_t, 1)
            hyperlocal["simple_bias"] = round(pws_t - model_t, 2)
            hyperlocal["corrected_temp"] = round(pws_t, 1)
    
    # Pressure
    if model_p_in is not None:
        hyperlocal["model_pressure_in"] = model_p_in
    wu_p_in = wu_data.get("pressure_in") if wu_data else None
    if wu_p_in is not None:
        hyperlocal["wu_pressure_in"] = wu_p_in
    if kbos_p_in is not None:
        hyperlocal["kbos_pressure_in"] = kbos_p_in
    hyperlocal["corrected_pressure_in"] = wu_p_in or kbos_p_in or model_p_in
    
    # Humidity
    wu_h = wu_data.get("humidity_pct") if wu_data else None
    if model_h is not None and wu_h is not None:
        hyperlocal["model_humidity"] = model_h
        hyperlocal["wu_humidity"] = wu_h
        hyperlocal["bias_humidity"] = round(wu_h - model_h, 1)
        hyperlocal["corrected_humidity"] = wu_h
    
    # Wind Speed (WU observations but no correction model yet)
    model_w = current.get("wind_speed")
    wu_w = wu_data.get("wind_speed_mph") if wu_data else None
    if model_w is not None:
        hyperlocal["model_wind_speed"] = model_w
    if wu_w is not None:
        hyperlocal["wu_wind_speed"] = wu_w
    hyperlocal["corrected_wind_speed"] = model_w  # Using model until we build wind correction
    
    # Wind Gusts - SMART BIAS CORRECTION using individual stations
    model_g = current.get("wind_gusts")
    if model_g is not None and stations:
        weighted_gust_sum = 0.0
        total_gust_weight = 0.0
        stations_with_gusts = 0
        
        for station in stations:
            station_gust = station.get('wind_gust_mph')
            station_dist = station.get('distance_mi')
            station_elev = station.get('elevation_ft')
            
            # Skip stations with missing data
            if station_gust is None or station_dist is None or station_elev is None:
                continue
            if station_dist == 0 or station_dist > 1.5:
                continue
            
            # Distance and elevation weights (same as temperature)
            dist_weight = 1.0 / (station_dist ** 2)
            elev_diff = abs(station_elev - ELEVATION_FT)
            elev_weight = math.exp(-elev_diff / 30.0)
            weight = dist_weight * elev_weight
            
            weighted_gust_sum += station_gust * weight
            total_gust_weight += weight
            stations_with_gusts += 1
        
        # Calculate weighted average WU gust
        if total_gust_weight > 0 and stations_with_gusts >= 3:
            wu_avg_gust = weighted_gust_sum / total_gust_weight
            bias_gust = wu_avg_gust - model_g
            corrected_gust = model_g + bias_gust  # Same as wu_avg_gust
            
            hyperlocal["model_wind_gusts"] = round(model_g, 1)
            hyperlocal["wu_wind_gusts"] = round(wu_avg_gust, 1)
            hyperlocal["bias_wind_gusts"] = round(bias_gust, 1)
            hyperlocal["corrected_wind_gusts"] = round(corrected_gust, 1)
            
            # CRITICAL FIX: Gusts must always be >= sustained wind
            corrected_speed = hyperlocal.get("corrected_wind_speed")
            if corrected_speed is not None and corrected_gust < corrected_speed:
                corrected_gust = corrected_speed
                hyperlocal["corrected_wind_gusts"] = round(corrected_gust, 1)
    
    # WU quality metrics
    if wu_data:
        wu_quality = wu_data.get("quality", {})
        hyperlocal["wu_stations_temp"] = wu_quality.get("stations_used_temp", 0)
        hyperlocal["wu_stations_wind"] = wu_quality.get("stations_used_wind", 0)
    
    if hyperlocal:
        weather_data["hyperlocal"] = hyperlocal
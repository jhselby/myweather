"""
Fog risk calculation based on dew point spread, humidity, and wind
"""


def calculate_fog_risk(temperature_f, dew_point_f, humidity_pct, wind_speed_mph,
                      wind_direction=None, water_temp_f=None):
    """
    Calculate fog probability and risk label.
    
    Handles two fog types:
    1. Radiation fog: calm winds, small dew point spread (classic inland fog)
    2. Advection fog: warm moist air over cold water, moderate onshore winds
    
    Args:
        temperature_f: Current temperature in °F
        dew_point_f: Current dew point in °F
        humidity_pct: Relative humidity percentage
        wind_speed_mph: Wind speed in mph
        wind_direction: Wind direction in degrees (optional, for advection fog)
        water_temp_f: Water temperature in °F (optional, for advection fog)
    
    Returns:
        dict with 'fog_label', 'fog_probability', and 'fog_type', or None if insufficient data
    """
    # Need at least temp and dew point to calculate
    if temperature_f is None or dew_point_f is None:
        return None
    
    # Check for advection fog first (coastal-specific)
    # Warm moist air flowing over cold water with onshore wind
    if water_temp_f is not None and wind_direction is not None and wind_speed_mph is not None:
        air_water_diff = temperature_f - water_temp_f
        is_onshore = (40 <= wind_direction <= 180)  # NE through S — air coming off open ocean
        moderate_wind = (3 <= wind_speed_mph <= 18)
        
        if air_water_diff > 3 and is_onshore and moderate_wind and humidity_pct is not None and humidity_pct >= 70:
            # Advection fog conditions
            adv_prob = 30
            if air_water_diff > 8:
                adv_prob += 25
            elif air_water_diff > 5:
                adv_prob += 15
            if humidity_pct >= 90:
                adv_prob += 20
            elif humidity_pct >= 80:
                adv_prob += 10
            if 5 <= wind_speed_mph <= 12:
                adv_prob += 10  # Sweet spot for advection fog
            
            adv_prob = min(100, adv_prob)
            
            # Only use advection if it scores higher than radiation
            # (radiation fog check happens below, we'll compare at the end)
    
    spread = temperature_f - dew_point_f
    
    # Base probability on dew point spread
    if spread <= 2.0:
        base_prob = 85  # Very close to saturation
        label = "Likely"
    elif spread <= 3.5:
        base_prob = 60
        label = "Possible"
    elif spread <= 5.0:
        base_prob = 30
        label = "Low chance"
    else:
        # Spread too high for fog
        return {
            "fog_label": "No risk",
            "fog_probability": 0
        }
    
    # Adjust for humidity if available
    if humidity_pct is not None:
        if humidity_pct >= 95:
            base_prob += 10
        elif humidity_pct >= 90:
            base_prob += 5
        elif humidity_pct < 80:
            base_prob -= 15
    
    # Adjust for wind if available
    if wind_speed_mph is not None:
        if wind_speed_mph <= 3:
            base_prob += 10  # Calm winds favor fog
        elif wind_speed_mph >= 10:
            base_prob -= 20  # Strong winds disperse fog
        elif wind_speed_mph >= 7:
            base_prob -= 10
    
    # Clamp to 0-100
    final_prob = max(0, min(100, base_prob))
    
    # Adjust label based on final probability
    if final_prob >= 70:
        final_label = "Likely"
    elif final_prob >= 40:
        final_label = "Possible"
    elif final_prob >= 15:
        final_label = "Low chance"
    else:
        final_label = "No risk"
    
    # Compare with advection fog if calculated
    fog_type = "radiation"
    if water_temp_f is not None and wind_direction is not None and wind_speed_mph is not None:
        air_water_diff = temperature_f - water_temp_f
        is_onshore = (40 <= wind_direction <= 180)
        moderate_wind = (3 <= wind_speed_mph <= 18)
        if air_water_diff > 3 and is_onshore and moderate_wind and humidity_pct is not None and humidity_pct >= 70:
            adv_prob = 30
            if air_water_diff > 8:
                adv_prob += 25
            elif air_water_diff > 5:
                adv_prob += 15
            if humidity_pct >= 90:
                adv_prob += 20
            elif humidity_pct >= 80:
                adv_prob += 10
            if 5 <= wind_speed_mph <= 12:
                adv_prob += 10
            adv_prob = min(100, adv_prob)
            if adv_prob > final_prob:
                final_prob = adv_prob
                fog_type = "advection"
                if final_prob >= 70:
                    final_label = "Likely"
                elif final_prob >= 40:
                    final_label = "Possible"
                elif final_prob >= 15:
                    final_label = "Low chance"
                else:
                    final_label = "No risk"

    return {
        "fog_label": final_label,
        "fog_probability": final_prob,
        "fog_type": fog_type
    }

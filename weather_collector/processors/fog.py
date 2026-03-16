"""
Fog risk calculation based on dew point spread, humidity, and wind
"""


def calculate_fog_risk(temperature_f, dew_point_f, humidity_pct, wind_speed_mph):
    """
    Calculate fog probability and risk label.
    
    Fog forms when:
    - Dew point spread is small (air near saturation)
    - Humidity is high
    - Wind is light (allows fog to form and persist)
    
    Args:
        temperature_f: Current temperature in °F
        dew_point_f: Current dew point in °F
        humidity_pct: Relative humidity percentage
        wind_speed_mph: Wind speed in mph
    
    Returns:
        dict with 'fog_label' and 'fog_probability', or None if insufficient data
    """
    # Need at least temp and dew point to calculate
    if temperature_f is None or dew_point_f is None:
        return None
    
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
    
    return {
        "fog_label": final_label,
        "fog_probability": final_prob
    }

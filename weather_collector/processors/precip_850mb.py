"""
Precipitation type classification based on 850mb temperature
"""


def classify_850mb_precip_type(t_850mb_f):
    """
    Classify precipitation type based on 850mb (~5000 ft) temperature.
    
    Classic thresholds:
    - Above +4°C (39°F): Rain
    - 0°C to +4°C (32-39°F): Mixed (rain/snow/sleet)  
    - -4°C to 0°C (25-32°F): Snow
    - Below -4°C (25°F): Heavy snow (better dendritic crystal growth)
    
    Args:
        t_850mb_f: Temperature at 850mb in °F
        
    Returns:
        str: Classification ("Rain", "Mixed", "Snow", "Heavy snow", or None)
    """
    if t_850mb_f is None:
        return None
    
    if t_850mb_f >= 39:
        return "Rain"
    elif t_850mb_f >= 32:
        return "Mixed"
    elif t_850mb_f >= 25:
        return "Snow"
    else:
        return "Heavy snow"


def add_850mb_precip_type(weather_data):
    """
    Add 850mb precipitation type to hourly and current derived data.
    Modifies weather_data in place.
    
    Args:
        weather_data: Weather data dict with hourly section
    """
    # Get current 850mb temp (first hourly value)
    hourly = weather_data.get("hourly", {})
    temps_850 = hourly.get("temperature_850hPa", [])
    
    # Ensure derived section exists
    if "derived" not in weather_data:
        weather_data["derived"] = {}
    
    # Current 850mb temp and type
    if temps_850 and len(temps_850) > 0:
        t_850_now = temps_850[0]
        weather_data["derived"]["temp_850hpa_now"] = t_850_now
        weather_data["derived"]["col_precip_type"] = classify_850mb_precip_type(t_850_now)
    
    # Column precip type for each hour
    col_types = []
    for t in temps_850:
        col_types.append(classify_850mb_precip_type(t))
    
    weather_data["hourly"]["col_precip_type_850mb"] = col_types

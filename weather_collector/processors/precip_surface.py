import re
"""
Surface precipitation type classification using wet bulb temperature
"""


def classify_surface_precip_type(wet_bulb_f):
    """
    Classify surface precipitation type based on wet bulb temperature.
    
    Wet bulb is more reliable than dry bulb for precip type because it accounts
    for humidity and better represents the actual conditions in the precipitation.
    
    Thresholds based on meteorological consensus:
    - Below 32°F: Snow
    - 32-35°F: Mixed/Sleet (transition zone)
    - Above 35°F: Rain
    
    Args:
        wet_bulb_f: Wet bulb temperature in °F
        
    Returns:
        str: "snow", "mixed", "rain", or None if wet_bulb_f is None
    """
    if wet_bulb_f is None:
        return None
    
    if wet_bulb_f < 32.0:
        return "snow"
    elif wet_bulb_f < 35.0:
        return "mixed"
    else:
        return "rain"


def classify_hybrid_precip_type(wet_bulb_f, temp_850mb_f):
    """
    Classify precipitation type using both surface wet bulb and 850mb temperature.
    
    This hybrid approach catches complex scenarios like freezing rain
    (warm air aloft, cold at surface).
    
    Logic:
    - Both cold (850mb < 32°F, wet bulb < 32°F) → Snow
    - Both warm (850mb > 32°F, wet bulb > 35°F) → Rain
    - Warm aloft, cold surface (850mb > 32°F, wet bulb < 35°F) → Freezing Rain
    - Cold aloft, warm surface (850mb < 32°F, wet bulb > 35°F) → Rain (unlikely but possible)
    - Transition zones → Mixed
    
    Args:
        wet_bulb_f: Surface wet bulb temperature in °F
        temp_850mb_f: Temperature at 850mb (~5000 ft) in °F
        
    Returns:
        str: "snow", "mixed", "freezing_rain", "rain", or None if either input is None
    """
    if wet_bulb_f is None or temp_850mb_f is None:
        return classify_surface_precip_type(wet_bulb_f)  # Fallback to surface only
    
    # Convert 850mb to Celsius for standard meteorological threshold
    temp_850mb_c = (temp_850mb_f - 32) * 5/9
    
    # Classic freezing rain scenario: warm aloft, cold at surface
    if temp_850mb_c > 0 and wet_bulb_f < 35.0:
        return "freezing_rain"
    
    # Both cold → Snow
    if temp_850mb_f < 32.0 and wet_bulb_f < 32.0:
        return "snow"
    
    # Both warm → Rain
    if temp_850mb_f > 32.0 and wet_bulb_f > 35.0:
        return "rain"
    
    # Transition zone → Mixed
    if wet_bulb_f >= 32.0 and wet_bulb_f < 35.0:
        return "mixed"
    
    # Cold surface, warm aloft (rare) → use surface
    return classify_surface_precip_type(wet_bulb_f)


def add_corrected_precip_types(weather_data, hyperlocal_data):
    """
    Add corrected surface precipitation types using corrected wet bulb temps.
    
    For CURRENT conditions: Uses corrected wet bulb from corrected temp + humidity
    For FORECAST: Uses hybrid approach (surface wet bulb + 850mb temp)
    
    Modifies weather_data in place by adding:
    - derived["corrected_wet_bulb"] (current, from corrected data)
    - derived["surface_precip_type"] (current)
    - hourly["corrected_wet_bulb"] (forecast, if we can apply humidity correction)
    - hourly["surface_precip_type"] (forecast, hybrid method)
    
    Args:
        weather_data: Main weather data dict
        hyperlocal_data: Hyperlocal corrections dict with corrected temps/humidity
    """
    from .wet_bulb import calculate_wet_bulb
    
    
    if "derived" not in weather_data:
        weather_data["derived"] = {}
    
    # CURRENT: Use corrected wet bulb from corrected temp + humidity
    corrected_temp = hyperlocal_data.get("corrected_temp")
    corrected_humidity = hyperlocal_data.get("corrected_humidity")
    
    
    if corrected_temp is not None and corrected_humidity is not None:
        corrected_wet_bulb = calculate_wet_bulb(corrected_temp, corrected_humidity)
        weather_data["derived"]["corrected_wet_bulb"] = corrected_wet_bulb
        
        # Current precip type from corrected wet bulb only (no 850mb needed for current)
        current_precip_type = classify_surface_precip_type(corrected_wet_bulb)
        weather_data["derived"]["surface_precip_type"] = current_precip_type
    # FORECAST: Apply humidity bias correction to hourly forecast, then calculate corrected wet bulb
    hourly = weather_data.get("hourly", {})
    hourly_temps = hourly.get("temperature", [])
    hourly_humidity = hourly.get("humidity", [])
    hourly_850mb = hourly.get("temperature_850hPa", [])
    
    # Get humidity bias from hyperlocal
    humidity_bias = hyperlocal_data.get("bias_humidity", 0)
    
    
    corrected_wet_bulbs = []
    surface_precip_types = []
    
    for i, (temp, humidity, temp_850) in enumerate(zip(hourly_temps, hourly_humidity, hourly_850mb)):
        if temp is not None and humidity is not None:
            # Apply humidity correction to forecast
            corrected_hourly_humidity = humidity + humidity_bias
            corrected_hourly_humidity = max(0, min(100, corrected_hourly_humidity))  # Clamp 0-100%
            
            # Calculate corrected wet bulb
            corrected_wb = calculate_wet_bulb(temp, corrected_hourly_humidity)
            corrected_wet_bulbs.append(corrected_wb)
            
            # Classify using hybrid method (surface wet bulb + 850mb)
            precip_type = classify_hybrid_precip_type(corrected_wb, temp_850)
            surface_precip_types.append(precip_type)
        else:
            corrected_wet_bulbs.append(None)
            surface_precip_types.append(None)
    
    weather_data["hourly"]["corrected_wet_bulb"] = corrected_wet_bulbs
    weather_data["hourly"]["surface_precip_type"] = surface_precip_types

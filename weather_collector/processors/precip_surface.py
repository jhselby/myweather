import re
import logging
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


def classify_hybrid_precip_type(wet_bulb_f, temp_850mb_f, freezing_level_ft=None):
    """
    Classify precipitation type using surface wet bulb, 850mb temperature, and
    optionally the actual freezing level altitude.

    Logic:
    - Both cold (850mb < 32°F, wet bulb < 32°F) → Snow
    - Both warm (850mb > 32°F, wet bulb > 35°F) → Rain
    - Warm aloft, cold surface (850mb > 32°F, wet bulb < 35°F) → Freezing Rain
    - Cold aloft, warm surface (850mb < 32°F, wet bulb > 35°F) → Rain
    - Transition zones → Mixed
    - Freezing level overrides: >5000 ft → rain; <1500 ft + cold surface → snow
    """
    if wet_bulb_f is None or temp_850mb_f is None:
        return classify_surface_precip_type(wet_bulb_f)

    # Freezing level overrides: clear-cut cases where altitude settles the question
    if freezing_level_ft is not None:
        if freezing_level_ft > 5000 and wet_bulb_f > 30.0:
            return "rain"  # Warm layer too deep for snow to survive descent
        if freezing_level_ft < 1500 and wet_bulb_f < 33.0:
            return "snow"  # Freezing level near surface, cold throughout

    temp_850mb_c = (temp_850mb_f - 32) * 5 / 9

    if temp_850mb_c > 0 and wet_bulb_f < 35.0:
        return "freezing_rain"

    if temp_850mb_f < 32.0 and wet_bulb_f < 32.0:
        return "snow"

    if temp_850mb_f > 32.0 and wet_bulb_f > 35.0:
        return "rain"

    if wet_bulb_f >= 32.0 and wet_bulb_f < 35.0:
        return "mixed"

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
        synthetic_wet_bulb = calculate_wet_bulb(corrected_temp, corrected_humidity)

        # Prefer Tempest hardware wet bulb (direct measurement) over Stull formula
        tempest_stations = weather_data.get("tempest", {}).get("stations", [])
        tempest_wb_vals = [s["wet_bulb_temperature_f"] for s in tempest_stations
                           if s.get("wet_bulb_temperature_f") is not None]

        if tempest_wb_vals:
            corrected_wet_bulb = sum(tempest_wb_vals) / len(tempest_wb_vals)
            weather_data["derived"]["wet_bulb_source"] = "tempest"
            weather_data["derived"]["wet_bulb_synthetic"] = round(synthetic_wet_bulb, 1)
        else:
            corrected_wet_bulb = synthetic_wet_bulb
            weather_data["derived"]["wet_bulb_source"] = "synthetic"

        weather_data["derived"]["corrected_wet_bulb"] = corrected_wet_bulb

        # Current precip type — use freezing level if available for more accurate classification
        cur_fl_ft = weather_data.get("derived", {}).get("freezing_level_ft")
        if cur_fl_ft is not None:
            cur_850 = (weather_data.get("hourly", {}).get("temperature_850hPa") or [None])[0]
            current_precip_type = classify_hybrid_precip_type(corrected_wet_bulb, cur_850, freezing_level_ft=cur_fl_ft)
        else:
            current_precip_type = classify_surface_precip_type(corrected_wet_bulb)
        weather_data["derived"]["surface_precip_type"] = current_precip_type
    # FORECAST: Use bias-corrected hourly arrays if available
    hourly = weather_data.get("hourly", {})
    hourly_temps = hourly.get("corrected_temperature") or hourly.get("temperature", [])
    hourly_humidity = hourly.get("corrected_humidity") or hourly.get("humidity", [])
    hourly_850mb = hourly.get("temperature_850hPa", [])
    hourly_freeze_ft = hourly.get("freezing_level_ft", [])

    corrected_wet_bulbs = []
    surface_precip_types = []

    for i, (temp, humidity, temp_850) in enumerate(zip(hourly_temps, hourly_humidity, hourly_850mb)):
        if temp is not None and humidity is not None:
            corrected_wb = calculate_wet_bulb(temp, humidity)
            corrected_wet_bulbs.append(corrected_wb)
            fl_ft = hourly_freeze_ft[i] if i < len(hourly_freeze_ft) else None
            precip_type = classify_hybrid_precip_type(corrected_wb, temp_850, freezing_level_ft=fl_ft)
            surface_precip_types.append(precip_type)
        else:
            corrected_wet_bulbs.append(None)
            surface_precip_types.append(None)
    
    if "hourly" not in weather_data:
        logging.warning("  ⚠️ No hourly forecast data; skipping corrected wet-bulb layer")
        return weather_data

    weather_data["hourly"]["corrected_wet_bulb"] = corrected_wet_bulbs
    weather_data["hourly"]["surface_precip_type"] = surface_precip_types

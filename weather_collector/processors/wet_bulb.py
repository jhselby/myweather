"""
Wet bulb temperature calculation for precipitation type classification
"""
import math


def calculate_wet_bulb(t_f, rh_pct):
    """
    Calculate wet bulb temperature in °F from dry bulb (°F) and RH (%).
    
    Uses Stull's formula for psychrometric wet bulb temperature.
    
    Args:
        t_f: Temperature in °F
        rh_pct: Relative humidity in %
        
    Returns:
        float: Wet bulb temperature in °F, or None if inputs invalid
    """
    if t_f is None or rh_pct is None:
        return None
    
    # Convert to Celsius
    t = (t_f - 32) * 5/9
    rh = float(rh_pct)
    
    # Stull's formula
    tw = (t * math.atan(0.151977 * (rh + 8.313659) ** 0.5)
          + math.atan(t + rh)
          - math.atan(rh - 1.676331)
          + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh)
          - 4.686035)
    
    # Convert back to °F
    return round(tw * 9/5 + 32, 1)


def add_wet_bulb_temps(weather_data):
    """
    Add wet bulb temperatures to hourly and current data.
    Modifies weather_data in place.
    
    Args:
        weather_data: Weather data dict with current and hourly sections
    """
    # Hourly wet bulb temps
    hourly = weather_data.get("hourly", {})
    temps = hourly.get("temperature", [])
    humidity = hourly.get("humidity", [])
    
    wb_temps = []
    for t, rh in zip(temps, humidity):
        wb_temps.append(calculate_wet_bulb(t, rh))
    
    weather_data["hourly"]["wet_bulb"] = wb_temps
    
    # Current wet bulb
    current = weather_data.get("current", {})
    cur_wb = calculate_wet_bulb(
        current.get("temperature"),
        current.get("humidity")
    )
    weather_data["current"]["wet_bulb"] = cur_wb
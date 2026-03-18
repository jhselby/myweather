"""
Sea breeze detection for coastal locations
"""
from datetime import datetime


def detect_sea_breeze(weather_data):
    """
    Detect sea breeze likelihood based on land/water temp differential,
    wind speed, direction, and time of day.
    """
    current = weather_data.get("current", {})
    buoy = weather_data.get("buoy_44013", {})
    
    pws_temp = current.get("temperature")
    water_temp = buoy.get("water_temp_f")
    wind_speed = current.get("wind_speed")
    wind_dir = current.get("wind_direction")
    
    now = datetime.now()
    hour = now.hour
    
    result = {
        "active": False,
        "likelihood": 0,
        "reason": ""
    }
    
    # Check data availability
    if None in [pws_temp, water_temp, wind_speed, wind_dir]:
        result["reason"] = "Insufficient data"
        weather_data["sea_breeze"] = result
        return
    
    temp_diff = pws_temp - water_temp
    scores = {}
    
    # Temperature differential
    if temp_diff < 0:
        scores["temp"] = 0
    elif temp_diff < 3:
        scores["temp"] = 20
    elif temp_diff < 5:
        scores["temp"] = 40
    elif temp_diff < 8:
        scores["temp"] = 70
    elif temp_diff < 12:
        scores["temp"] = 90
    else:
        scores["temp"] = 100
    
    # Wind speed
    if wind_speed > 15:
        scores["wind_speed"] = 0
    elif wind_speed > 12:
        scores["wind_speed"] = 30
    elif wind_speed > 10:
        scores["wind_speed"] = 60
    elif wind_speed > 7:
        scores["wind_speed"] = 90
    else:
        scores["wind_speed"] = 100
    
    # Wind direction (270-330° from Salem Harbor)
    onshore_min, onshore_max = 260, 340
    if onshore_min <= wind_dir <= onshore_max:
        scores["direction"] = 100
    elif 240 <= wind_dir < onshore_min or onshore_max < wind_dir <= 360:
        scores["direction"] = 50
    elif 0 <= wind_dir <= 20:
        scores["direction"] = 50
    else:
        scores["direction"] = 0
    
    # Time of day
    if 10 <= hour < 18:
        scores["time"] = 100
    elif 8 <= hour < 10 or 18 <= hour < 20:
        scores["time"] = 60
    else:
        scores["time"] = 0
    
    # Overall likelihood
    likelihood = int(
        scores["temp"] * 0.40 +
        scores["direction"] * 0.30 +
        scores["wind_speed"] * 0.20 +
        scores["time"] * 0.10
    )
    
    result["likelihood"] = likelihood
    
    # Determine if active
    if likelihood >= 60:
        result["active"] = True
        result["reason"] = f"Sea breeze active: Δ{temp_diff:+.1f}°F, {wind_speed:.0f} mph from {int(wind_dir)}°"
    elif likelihood >= 40:
        result["reason"] = f"Possible sea breeze: Δ{temp_diff:+.1f}°F, {wind_speed:.0f} mph from {int(wind_dir)}°"
    elif scores["temp"] < 40:
        result["reason"] = f"Land/water Δ too small ({temp_diff:+.1f}°F)"
    elif scores["direction"] < 50:
        result["reason"] = f"Wind not onshore ({int(wind_dir)}°, need 270-330°)"
    elif scores["wind_speed"] < 50:
        result["reason"] = f"Winds too strong ({wind_speed:.0f} mph)"
    elif scores["time"] == 0:
        result["reason"] = f"Wrong time of day ({hour:02d}:00, need 10am-6pm)"
    else:
        result["reason"] = "Conditions not met"
    
    result["scores"] = scores
    weather_data["sea_breeze"] = result

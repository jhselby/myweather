"""
Calculate 850mb geopotential height tendency (trough signal)
"""


def compute_trough_signal(hourly_data):
    """
    Calculate 6-hour 850mb height tendency.
    
    A drop of ≥30m in 6h indicates a fast-moving trough approaching.
    A rise of ≥30m in 6h indicates ridging/building high pressure.
    
    Args:
        hourly_data: Hourly forecast data dict
    
    Returns:
        dict with trough_signal and height_850hpa_tend_6h, or empty dict
    """
    if not hourly_data:
        return {}
    
    hourly = hourly_data.get("hourly", {})
    z850_arr = hourly.get("geopotential_height_850hPa", [])
    
    # Need at least 7 hours of data (0-6 inclusive)
    if len(z850_arr) < 7:
        return {}
    
    # Check all values are present
    if not all(z is not None for z in z850_arr[:7]):
        return {}
    
    # Calculate 6-hour tendency
    z_tend_6h = round(z850_arr[6] - z850_arr[0], 0)
    
    result = {
        "height_850hpa_tend_6h": int(z_tend_6h)
    }
    
    # Classify signal
    if z_tend_6h <= -30:
        result["trough_signal"] = "Approaching"
    elif z_tend_6h >= 30:
        result["trough_signal"] = "Ridging"
    else:
        result["trough_signal"] = "Steady"
    
    return result
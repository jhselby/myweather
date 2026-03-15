"""
Pressure trend calculations and analysis
"""


def compute_pressure_trend_hpa(hourly_data):
    """
    Compute 3-hour pressure trend from hourly forecast data.
    Uses hours 0-3 (current + next 3 hours).
    
    Args:
        hourly_data: Hourly forecast data from Open-Meteo
        
    Returns:
        float or None: Pressure change in hPa over 3 hours
    """
    if not hourly_data:
        return None

    hourly = hourly_data.get("hourly", {})
    pressures = hourly.get("pressure_msl", [])

    if not pressures or len(pressures) < 4:
        return None

    try:
        p_now = float(pressures[0])
        p_3h = float(pressures[3])
        trend = round(p_3h - p_now, 1)
        return trend
    except (ValueError, TypeError):
        return None


def get_best_pressure_trend(kbos_data, buoy_data, model_trend):
    """
    Select best pressure trend from available sources.
    Priority: KBOS > Buoy > Model
    
    Args:
        kbos_data: KBOS observation data
        buoy_data: Buoy 44013 data
        model_trend: Model-derived trend
        
    Returns:
        tuple: (trend_hpa, source_label) or (None, None)
    """
    kbos_tend = (kbos_data or {}).get("pressure_tend_hpa")
    buoy_tend = (buoy_data or {}).get("pressure_tend_hpa")

    if kbos_tend is not None:
        return kbos_tend, "KBOS"
    elif buoy_tend is not None:
        return buoy_tend, "Buoy"
    elif model_trend is not None:
        return model_trend, "model"
    
    return None, None


def classify_pressure_alarm(trend_hpa):
    """
    Classify pressure trend into alarm categories.
    
    Args:
        trend_hpa: Pressure change in hPa over 3 hours
        
    Returns:
        dict: {"alarm", "alarm_label"} or None values if no alarm
    """
    if trend_hpa is None:
        return {"alarm": None, "alarm_label": None}
    
    if trend_hpa <= -3.0:
        return {
            "alarm": "falling",
            "alarm_label": f"⚠️ Pressure falling fast ({trend_hpa:+.1f} hPa)"
        }
    elif trend_hpa >= 3.0:
        return {
            "alarm": "rising",
            "alarm_label": f"📈 Pressure rising fast ({trend_hpa:+.1f} hPa)"
        }
    
    return {"alarm": None, "alarm_label": None}
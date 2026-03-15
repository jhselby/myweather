"""
Hyperlocal temperature correction using Weather Underground station data
"""


def compute_hyperlocal_temp(model_temp, wu_data):
    """
    Compute hyperlocal temperature correction using WU station bias.
    
    Args:
        model_temp: Model forecast temperature (°F)
        wu_data: Weather Underground multi-station data
        
    Returns:
        dict: {"hyperlocal_temp_f", "bias_applied_f", "stations_used"} or None
    """
    if not wu_data or model_temp is None:
        return None
    
    bias = wu_data.get("bias", {}).get("temp_bias_f")
    stations_used = wu_data.get("quality", {}).get("stations_used_temp", 0)
    
    if bias is None or stations_used == 0:
        return None
    
    hyperlocal_temp = round(model_temp + bias, 1)
    
    return {
        "hyperlocal_temp_f": hyperlocal_temp,
        "bias_applied_f": round(bias, 1),
        "stations_used": stations_used
    }


def compute_dew_point_spread(temp_f, dew_f):
    """
    Compute temperature-dewpoint spread.
    
    Args:
        temp_f: Temperature in °F
        dew_f: Dewpoint in °F
        
    Returns:
        float: Spread in °F, or None if inputs invalid
    """
    if temp_f is None or dew_f is None:
        return None
    
    try:
        spread = round(float(temp_f) - float(dew_f), 1)
        return spread
    except (ValueError, TypeError):
        return None
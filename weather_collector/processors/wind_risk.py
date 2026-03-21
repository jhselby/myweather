"""
Wind risk assessment using house-specific exposure model
"""
from ..config import WIND_EXPOSURE_TABLE, WORRY_NOTICEABLE, WORRY_NOTABLE, WORRY_SIGNIFICANT, WORRY_SEVERE


def get_exposure_factor(deg):
    """Return 0.0–1.0 site exposure for wind from deg degrees."""
    d = int(deg) % 360
    for min_d, max_d, factor in WIND_EXPOSURE_TABLE:
        if min_d <= max_d:
            if min_d <= d < max_d:
                return factor
        else:
            if d >= min_d or d < max_d:
                return factor
    return 0.5  # fallback


def worry_score(speed, exp_factor):
    """Calculate worry score: speed * exposure_factor^1.5"""
    return round(speed * (exp_factor ** 1.5), 2)


def worry_level(score):
    """Classify worry score into severity level."""
    if score >= WORRY_SEVERE:
        return "Very windy"
    if score >= WORRY_SIGNIFICANT:
        return "Windy"
    if score >= WORRY_NOTABLE:
        return "Breezy"
    if score >= WORRY_NOTICEABLE:
        return "Light winds"
    return "Calm"


def safe_num(x):
    """Convert to float, return None on failure."""
    try:
        return float(x)
    except Exception:
        return None


def find_peak(values, dirs, times, n):
    """
    Find peak value in first n slots.
    Returns: (value, direction_deg, time_iso) or (None, None, None)
    """
    best_val, best_dir, best_time = -1.0, None, None
    
    for i in range(n):
        v = safe_num(values[i]) if i < len(values) else None
        d = safe_num(dirs[i]) if i < len(dirs) else None
        t = times[i] if i < len(times) else None
        
        if v is None or d is None:
            continue
        
        if v > best_val:
            best_val, best_dir, best_time = v, d, t
    
    if best_dir is None:
        return None, None, None
    
    return best_val, best_dir, best_time


def compute_wind_risk(weather_data, peak_window_hours=12):
    """
    Compute wind risk from hourly forecast data.
    Calculates separate scores for gusts and sustained winds.
    
    Args:
        weather_data: Full weather data dict with hourly forecast
        peak_window_hours: Hours to look ahead for peak winds
        
    Returns:
        dict: Wind risk assessment with gust and sustained sub-scores
    """
    hourly_h = weather_data.get("hourly", {}) or {}
    hourly_gusts = hourly_h.get("wind_gusts", []) or []
    hourly_speeds = hourly_h.get("wind_speed", []) or []
    hourly_dirs = hourly_h.get("wind_direction", []) or []
    hourly_times = hourly_h.get("times", []) or []

    lookahead = min(peak_window_hours, len(hourly_gusts), len(hourly_dirs))

    gust_val, gust_dir, gust_time = find_peak(hourly_gusts, hourly_dirs, hourly_times, lookahead)
    sus_val, sus_dir, sus_time = find_peak(hourly_speeds, hourly_dirs, hourly_times, lookahead)

    # Fallback to current if hourly unavailable
    if gust_val is None:
        gust_val = safe_num(weather_data.get("current", {}).get("wind_gusts"))
        gust_dir = safe_num(weather_data.get("current", {}).get("wind_direction"))
        gust_time = None
    if sus_val is None:
        sus_val = safe_num(weather_data.get("current", {}).get("wind_speed"))
        sus_dir = safe_num(weather_data.get("current", {}).get("wind_direction"))
        sus_time = None

    wind_risk = {"window_hours": peak_window_hours}

    if gust_val is not None and gust_dir is not None:
        gd = int(gust_dir) % 360
        ef = get_exposure_factor(gd)
        ws = worry_score(gust_val, ef)
        wind_risk["gust"] = {
            "peak_mph": round(gust_val, 1),
            "direction_deg": gd,
            "exposure_factor": round(ef, 2),
            "worry_score": ws,
            "level": worry_level(ws),
            "peak_time": gust_time,
        }

    if sus_val is not None and sus_dir is not None:
        sd = int(sus_dir) % 360
        ef = get_exposure_factor(sd)
        ws = worry_score(sus_val, ef)
        wind_risk["sustained"] = {
            "peak_mph": round(sus_val, 1),
            "direction_deg": sd,
            "exposure_factor": round(ef, 2),
            "worry_score": ws,
            "level": worry_level(ws),
            "peak_time": sus_time,
        }

    return wind_risk if len(wind_risk) > 1 else None
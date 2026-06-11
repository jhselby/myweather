"""
Thunderstorm detector — combines Tempest lightning, Pirate Weather CAPE,
and minutely precip into derived.thunderstorm
"""

CAPE_WEAK     =  500   # J/kg — some instability
CAPE_MODERATE = 1000
CAPE_HIGH     = 2500
CAPE_EXTREME  = 4000


def _cape_label(cape):
    if cape is None:          return "Unknown"
    if cape >= CAPE_EXTREME:  return "Extreme"
    if cape >= CAPE_HIGH:     return "High"
    if cape >= CAPE_MODERATE: return "Moderate"
    if cape >= CAPE_WEAK:     return "Weak"
    return "Low"


def detect_thunderstorm(weather_data):
    """
    Returns dict for derived["thunderstorm"].
    Severity: "clear" | "watch" | "active" | "severe"
    """
    tempest = weather_data.get("tempest", {})
    pirate  = weather_data.get("pirate_weather", {})
    stations = tempest.get("stations", [])

    # Lightning — max across stations (all detect the same strikes)
    lightning_count     = max((s.get("lightning_count_1hr") or 0 for s in stations), default=0)
    lightning_count_3hr = max((s.get("lightning_count_3hr") or 0 for s in stations), default=0)
    distances = [
        s["lightning_last_distance_km"] for s in stations
        if s.get("lightning_last_distance_km") and s["lightning_last_distance_km"] > 0
    ]
    min_distance_km = min(distances) if distances else None
    is_close = min_distance_km is not None and min_distance_km <= 20

    # CAPE
    cape_current = pirate.get("current_cape")
    hourly_cape  = pirate.get("hourly_cape",  [])[:12]
    hourly_times = pirate.get("hourly_times", [])[:12]

    cape_12h = list(zip(hourly_times, hourly_cape))
    cape_values = [c for _, c in cape_12h if c is not None]
    cape_peak_value = max(cape_values) if cape_values else cape_current
    cape_peak_hour  = None
    if cape_values:
        best = max(range(len(cape_12h)), key=lambda i: cape_12h[i][1] or 0)
        cape_peak_hour = cape_12h[best][0]

    # Current precip intensity — max of first 5 minutely points
    minutely = pirate.get("minutely", [])
    cur_precip = max((pt.get("precip_intensity", 0) for pt in minutely[:5]), default=0)
    heavy_precip = cur_precip >= 0.3  # inches/hr

    # Active detection
    lightning_active = lightning_count >= 3 or (lightning_count >= 1 and is_close)

    # Severity. Watch also fires when the daytime peak (next 12h) reaches
    # Moderate even if current CAPE is low — otherwise a hot afternoon setup
    # reads as "clear" at 8am.
    if lightning_active:
        if is_close or (cape_current is not None and cape_current >= CAPE_HIGH and heavy_precip):
            severity = "severe"
        else:
            severity = "active"
    elif (cape_current is not None and cape_current >= CAPE_WEAK) or \
         (cape_peak_value is not None and cape_peak_value >= CAPE_MODERATE):
        severity = "watch"
    else:
        severity = "clear"

    # Sky label override — written back by caller
    sky_override = None
    if severity == "severe":
        sky_override = "Severe Thunderstorm"
    elif severity == "active":
        sky_override = "Thunderstorm"

    hourly_payload = [
        {"time": t, "cape": c}
        for t, c in cape_12h
        if t is not None
    ]

    return {
        "severity":            severity,
        "active":              lightning_active,
        "lightning_count":     lightning_count,
        "lightning_count_3hr": lightning_count_3hr,
        "min_distance_km":     round(min_distance_km) if min_distance_km is not None else None,
        "cape_current":        cape_current,
        "cape_label":          _cape_label(cape_current),
        "cape_peak_value":     cape_peak_value,
        "cape_peak_hour":      cape_peak_hour,
        "cape_peak_label":     _cape_label(cape_peak_value),
        "cape_hourly":         hourly_payload,
        "precip_intensity":    cur_precip,
        "sky_override":        sky_override,
    }

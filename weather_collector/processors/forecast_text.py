"""
Generate human-readable 10-day forecast text.
Days 1-7: Rich day/night periods (14 periods) from hourly data
Days 8-10: Simple daily summaries from ECMWF daily data
Uses local time (America/New_York) to determine period boundaries.
"""
from datetime import datetime, timezone, timedelta
import pytz


WEATHER_CODES = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def generate_forecast_text(hourly_data, daily_data):
    """Generate 10-day forecast: 14 periods (days 1-7) + 3 simple dailies (days 8-10)."""
    # Handle both old format (single dict) and new format (hrrr + gfs)
    if isinstance(hourly_data, dict) and "hrrr" in hourly_data:
        hrrr_data = hourly_data["hrrr"]
        gfs_data = hourly_data["gfs"]
    else:
        # Fallback: treat as single source
        hrrr_data = hourly_data
        gfs_data = hourly_data
    
    if not hrrr_data or not daily_data:
        return []
    forecasts = []
    eastern = pytz.timezone('America/New_York')
    now_local = datetime.now(eastern)
    current_hour = now_local.hour
    
    # Determine starting period for days 1-7
    if current_hour < 18:
        start_with_day = True
    else:
        start_with_day = False  # Start with "Tonight"
    
    # Generate 14 periods (7 days × 2 periods) - rich hourly-based
    for period_num in range(14):
        is_daytime = (period_num % 2 == 0) if start_with_day else (period_num % 2 == 1)
        
        # Calculate which calendar day this period belongs to
        if start_with_day:
            current_day_offset = period_num // 2
        else:
            current_day_offset = (period_num + 1) // 2
        
        target_date = (now_local + timedelta(days=current_day_offset)).date()
        
        # Generate period name
        if period_num == 0:
            period_name = "Today" if start_with_day else "Tonight"
        elif period_num == 1:
            period_name = "Tonight" if start_with_day else target_date.strftime('%A')
        else:
            if is_daytime:
                period_name = target_date.strftime('%A')
            else:
                period_name = target_date.strftime('%A') + " Night"
        
        # Generate forecast for this period
        forecast = _generate_period_forecast(
            hrrr_data,
            gfs_data,
            target_date,
            is_daytime,
            period_name,
            eastern
        )
        
        if forecast:
            forecasts.append(forecast)
    
    # Generate days 8-10 from daily data (simple summaries)
    for day_offset in range(7, 10):
        target_date = (now_local + timedelta(days=day_offset)).date()
        forecast = _generate_daily_forecast(daily_data, target_date)
        if forecast:
            forecasts.append(forecast)
    
    return forecasts


def _generate_period_forecast(hrrr_data, gfs_data, target_date, is_daytime, period_name, eastern):
    """Generate forecast for a single day or night period (days 1-7). Merges HRRR (48h) + GFS (7day)."""
    
    # Merge HRRR and GFS data - prefer HRRR when available
    hourly_data = {}
    
    # Check which source has data for this period
    hrrr_times = hrrr_data.get("times", []) if hrrr_data else []
    gfs_times = gfs_data.get("times", []) if gfs_data else []
    
    # Use HRRR if it covers this period, otherwise GFS
    if hrrr_times and target_date <= datetime.fromisoformat(hrrr_times[-1].replace("Z", "+00:00")).astimezone(eastern).date():
        hourly_data = hrrr_data
    else:
        hourly_data = gfs_data
    
    # Define time bounds for the period
    if is_daytime:
        start_hour = 6
        end_hour = 18
    else:
        start_hour = 18
        end_hour = 6  # Next day
    
    # Extract hours for this period
    period_indices = []
    period_hours = []
    
    for i, time_str in enumerate(hourly_data.get('times', [])):
        dt = datetime.fromisoformat(time_str.replace('Z', '+00:00')).astimezone(eastern)
        
        # Check if this hour belongs to our period
        if is_daytime:
            # Daytime: 6 AM - 6 PM on target_date
            if dt.date() == target_date and start_hour <= dt.hour < end_hour:
                period_indices.append(i)
                period_hours.append(dt.hour)
        else:
            # Nighttime: 6 PM on target_date through 6 AM next day
            if dt.date() == target_date and dt.hour >= start_hour:
                period_indices.append(i)
                period_hours.append(dt.hour)
            elif dt.date() == target_date + timedelta(days=1) and dt.hour < end_hour:
                period_indices.append(i)
                period_hours.append(dt.hour)
    
    if not period_indices:
        return None
    
    # Extract data for this period
    temps = [hourly_data['temperature'][i] for i in period_indices]
    apparent_temps = [hourly_data['apparent_temperature'][i] for i in period_indices]
    wind_speeds = [hourly_data['wind_speed'][i] for i in period_indices]
    wind_gusts = [hourly_data['wind_gusts'][i] for i in period_indices]
    wind_directions = [hourly_data["wind_direction"][i] for i in period_indices]
    
    precip_types = [
        hourly_data.get("col_precip_type_850mb", [])[i] 
        if i < len(hourly_data.get("col_precip_type_850mb", [])) 
        else None 
        for i in period_indices
    ]
    precip_probs = [hourly_data["precipitation_probability"][i] for i in period_indices]
    weather_codes = [hourly_data["weather_code"][i] for i in period_indices]
    cloud_cover = [hourly_data["cloud_cover"][i] for i in period_indices]
    # Fallback: infer precip type from weather_code if col_precip_type_850mb is None
    weather_codes_list = [hourly_data["weather_code"][i] for i in period_indices]
    for idx, ptype in enumerate(precip_types):
        if ptype is None and weather_codes_list[idx] is not None:
            code = weather_codes_list[idx]
            if code in [61, 63, 65, 80, 81, 82]:  # Rain
                precip_types[idx] = "rain"
            elif code in [71, 73, 75, 77, 85, 86]:  # Snow
                precip_types[idx] = "snow"
            elif code in [66, 67]:  # Freezing rain
                precip_types[idx] = "freezing rain"
            elif code in [56, 57]:  # Freezing drizzle
                precip_types[idx] = "freezing drizzle"
            elif code in [51, 53, 55]:  # Drizzle
                precip_types[idx] = "drizzle"
    
    # Temperature (high for day, low for night)
    if is_daytime:
        temp = max(temps)
        temp_label = "High"
    else:
        temp = min(temps)
        temp_label = "Low"
    
    feels_like_low = min(apparent_temps)
    
    # Find timing of high/low temperature
    if is_daytime:
        temp_hour_idx = temps.index(max(temps))
    else:
        temp_hour_idx = temps.index(min(temps))
    temp_hour = period_hours[temp_hour_idx]
    
    def format_temp_time(h):
        if h == 0: return "midnight"
        elif h == 12: return "noon"
        elif h < 12: return f"{h}am"
        else: return f"{h-12}pm"
    
    
    # Build NWS-style flowing narrative
    narrative_parts = []
    
    # Get wind stats and direction
    max_gust = max(wind_gusts)
    avg_wind = sum(wind_speeds) / len(wind_speeds)
    min_wind = min(wind_speeds)
    max_wind = max(wind_speeds)
    
    from collections import Counter
    dir_counts = Counter(wind_directions)
    dominant_dir = dir_counts.most_common(1)[0][0] if dir_counts else None
    
    def degrees_to_compass(deg, full=False):
        if deg is None: return ""
        dirs_short = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
        dirs_full = ["north","north-northeast","northeast","east-northeast","east","east-southeast","southeast","south-southeast",
                     "south","south-southwest","southwest","west-southwest","west","west-northwest","northwest","north-northwest"]
        idx = int((deg + 11.25) / 22.5) % 16
        return dirs_full[idx].capitalize() if full else dirs_short[idx]
    
    wind_dir_short = degrees_to_compass(dominant_dir, full=False)
    wind_dir_full = degrees_to_compass(dominant_dir, full=True)
    
    # Sky condition
    sky_narrative = _build_sky_narrative(cloud_cover, weather_codes, period_hours)
    
    # Precipitation
    precip_narrative = _build_precip_narrative(precip_probs, precip_types, period_hours)
    
    # Build main sentence
    if precip_narrative:
        main_sent = f"{precip_narrative.capitalize()}. {sky_narrative.capitalize()}"
    else:
        main_sent = sky_narrative.capitalize()
    
    # Add temperature with timing
    mid_period = len(period_hours) // 2
    temp_position = period_hours.index(temp_hour) if temp_hour in period_hours else mid_period
    
    # Only add timing if temp occurs notably early or late in period
    temp_timing = ""
    if is_daytime:
        # Only show timing for afternoon/late highs
        if temp_position > len(period_hours) * 0.6 and temp_hour >= 14:
            temp_timing = f" around {format_temp_time(temp_hour)}"
        main_sent += f", with a high near {int(temp)}{temp_timing}."
    else:
        if temp_position < len(period_hours) * 0.3:
            temp_timing = f" in the evening"
        elif temp_position > len(period_hours) * 0.7:
            temp_timing = f" toward morning"
        main_sent += f", with a low around {int(temp)}{temp_timing}."
    
    narrative_parts.append(main_sent)
    
    # Wind sentence
    if avg_wind > 3 or max_gust > 15:
        if min_wind < max_wind - 3:
            wind_sent = f"{wind_dir_full} wind {int(min_wind)} to {int(max_wind)} mph"
        else:
            wind_sent = f"{wind_dir_full} wind around {int(avg_wind)} mph"
        
        if max_gust > avg_wind + 8:
            wind_sent += f", with gusts as high as {int(max_gust)} mph"
        
        wind_sent += "."
        narrative_parts.append(wind_sent)
        wind_full_val = f"{int(avg_wind)} mph {wind_dir_short}"
        if max_gust > avg_wind + 8:
            wind_full_val += f", gusts {int(max_gust)} mph"
    else:
        wind_full_val = ""
    
    # Wind chill note
    if feels_like_low < temp - 8:
        narrative_parts.append(f"Wind chill values as low as {int(feels_like_low)}.")
    
    return {
        "period_name": period_name,
        "date": target_date.isoformat(),
        "is_daytime": is_daytime,
        "text": " ".join(narrative_parts),
        "temperature": int(temp),
        "wind_speed": f"{int(avg_wind)} mph" if avg_wind > 3 else "",
        "wind_direction": wind_dir_short if avg_wind > 3 else "",
        "wind_full": wind_full_val
    }
def _generate_daily_forecast(daily_data, target_date):
    """Generate simple daily summary from ECMWF data (days 8-10)."""
    
    # Find matching day in daily data
    daily_times = daily_data.get('time', [])
    day_index = None
    for i, date_str in enumerate(daily_times):
        if date_str == target_date.isoformat():
            day_index = i
            break
    
    if day_index is None:
        return None
    
    high = daily_data['temperature_max'][day_index]
    low = daily_data['temperature_min'][day_index]
    precip_prob = daily_data.get('precipitation_probability_max', [0] * len(daily_times))[day_index]
    wind_max = daily_data.get('wind_speed_max', [0] * len(daily_times))[day_index]
    
    parts = []
    
    # Temperature
    parts.append(f"High {int(high)}°F, low {int(low)}°F.")
    
    # Precipitation
    if precip_prob > 60:
        parts.append(f"Rain likely ({int(precip_prob)}%).")
    elif precip_prob > 30:
        parts.append(f"Chance of rain ({int(precip_prob)}%).")
    
    # Wind
    if wind_max > 20:
        parts.append(f"Windy, gusts to {int(wind_max)} mph.")
    elif wind_max > 12:
        parts.append(f"Breezy, winds {int(wind_max)} mph.")
    
    return {
        'period_name': target_date.strftime('%A'),
        'date': target_date.isoformat(),
        'is_daytime': True,
        'text': ' '.join(parts),
        'temperature': int(high),
        'is_simple_daily': True
    }


def _build_sky_narrative(cloud_cover, weather_codes, hours):
    """Generate sky condition narrative for a period."""
    if not cloud_cover:
        return None
    
    avg_clouds = sum(cloud_cover) / len(cloud_cover)
    
    # Check for significant weather
    has_fog = any(code in [45, 48] for code in weather_codes)
    has_storms = any(code >= 95 for code in weather_codes)
    
    if has_storms:
        return "thunderstorms"
    
    if has_fog:
        if avg_clouds > 80:
            return "foggy and overcast"
        else:
            return "areas of fog"
    
    # Sky cover based on cloud percentage
    if avg_clouds < 30:
        return "sunny" if any(6 <= h <= 18 for h in hours) else "clear"
    elif avg_clouds < 60:
        return "partly cloudy"
    elif avg_clouds < 85:
        return "mostly cloudy"
    else:
        return "overcast"
def _build_precip_narrative(precip_probs, precip_types, hours):
    """Generate precipitation narrative for a period."""
    if not precip_probs:
        return None
    
    max_prob = max(precip_probs)
    
    if max_prob < 20:
        return None
    
    # Determine precipitation type
    precip_type_counts = {}
    for ptype in precip_types:
        if ptype:
            precip_type_counts[ptype] = precip_type_counts.get(ptype, 0) + 1
    
    if not precip_type_counts:
        precip_desc = "rain or snow"
    else:
        dominant_type = max(precip_type_counts, key=precip_type_counts.get)
        precip_desc = "mixed rain and snow" if dominant_type.lower() == "mixed" else dominant_type
    
    # Build likelihood phrase (lowercase, no period)
    if max_prob > 70:
        likelihood = f"{precip_desc} likely"
    elif max_prob > 50:
        likelihood = f"{precip_desc}"
    else:
        likelihood = f"chance of {precip_desc}"
    
    
    # Add timing if precipitation occurs during specific hours
    timing = None
    high_prob_indices = [i for i, p in enumerate(precip_probs) if p > 50]
    
    if high_prob_indices and len(high_prob_indices) < len(precip_probs) * 0.7:
        # Precip is concentrated in part of the period
        start_hour = hours[high_prob_indices[0]]
        end_hour = hours[high_prob_indices[-1]]
        
        def format_time(h):
            if h == 0: return "midnight"
            elif h == 12: return "noon"
            elif h < 12: return f"{h}am"
            else: return f"{h-12}pm"
        
        if len(high_prob_indices) <= 2:
            # Short window
            if start_hour == end_hour:
                timing = f" around {format_time(start_hour)}"
            else:
                timing = f" between {format_time(start_hour)} and {format_time(end_hour)}"
        elif high_prob_indices[0] > len(hours) // 2:
            timing = f" after {format_time(start_hour)}"
        elif high_prob_indices[-1] < len(hours) // 2:
            timing = f" before {format_time(end_hour)}"
    
    if timing:
        likelihood = likelihood + timing
    return likelihood


def _format_hour(hour_index):
    """Convert 0-23 hour index to 12-hour format."""
    if hour_index == 0:
        return "12 AM"
    elif hour_index < 12:
        return f"{hour_index} AM"
    elif hour_index == 12:
        return "12 PM"
    else:
        return f"{hour_index - 12} PM"

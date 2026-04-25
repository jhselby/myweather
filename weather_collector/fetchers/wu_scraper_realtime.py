#!/usr/bin/env python3
"""
WU Multi-Station Smart Scraper
Intelligently aggregates data from 15 local stations with:
- Distance-based weighting (closer = more weight)
- Outlier detection and filtering
- Sensor failure detection (0.0 wind = broken)
- Quality scoring for each aggregate
"""

import requests
import json
import time
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2

# API Configuration
import os
API_KEY = os.environ["WU_API_KEY"]
BASE_URL = "https://api.weather.com/v2/pws/observations/all/1day"

# Station IDs
STATIONS = [
    "KMAMARBL63", "KMAMARBL69", "KMAMARBL112", "KMAMARBL108",
    "KMAMARBL39", "KMAMARBL4", "KMAMARBL36", "KMAMARBL57",
    "KMAMARBL56", "KMAMARBL89", "KMAMARBL78", "KMAMARBL1",
    "KMASALEM91", "KMASALEM94", "KMAMARBL8", "KMAMARBL22",
    "KMAMARBL40", "KMAMARBL42", "KMAMARBL43", "KMAMARBL61",
    "KMAMARBL64", "KMAMARBL68", "KMAMARBL75", "KMAMARBL76",
    "KMAMARBL82", "KMAMARBL85", "KMAMARBL90", "KMAMARBL92",
    "KMAMARBL95", "KMAMARBL96", "KMAMARBL100", "KMAMARBL113",
    "KMAMARBL114", "KMAMARBL116", "KMAMARBL117", "KMAMARBL118"
]

# Wyman Cove reference point (16 Indianhead Circle)
WYMAN_COVE_LAT = 42.5014
WYMAN_COVE_LON = -70.8750
WYMAN_COVE_ELEV_FT = 30.0  # Basement walkout elevation

# Station elevations (from WU API, fetched 2026-02-28)
# These don't change, so hardcoded for performance
STATION_ELEVATIONS = {
    "KMAMARBL1": 0.0,
    "KMAMARBL100": 20.0,
    "KMAMARBL108": 16.0,
    "KMAMARBL112": 97.0,
    "KMAMARBL113": 12.0,
    "KMAMARBL114": 40.0,
    "KMAMARBL116": 24.0,
    "KMAMARBL117": 69.0,
    "KMAMARBL118": 0.0,
    "KMAMARBL22": 82.0,
    "KMAMARBL36": 69.0,
    "KMAMARBL39": 89.0,
    "KMAMARBL4": 90.0,
    "KMAMARBL40": 79.0,
    "KMAMARBL42": 49.0,
    "KMAMARBL43": 46.0,
    "KMAMARBL56": 79.0,
    "KMAMARBL57": 49.0,
    "KMAMARBL61": 30.0,
    "KMAMARBL63": 85.0,
    "KMAMARBL64": 3.0,
    "KMAMARBL68": 33.0,
    "KMAMARBL69": 69.0,
    "KMAMARBL75": 69.0,
    "KMAMARBL76": 69.0,
    "KMAMARBL78": 9.0,
    "KMAMARBL8": 53.0,
    "KMAMARBL82": 49.0,
    "KMAMARBL85": 30.0,
    "KMAMARBL89": 85.0,
    "KMAMARBL90": 56.0,
    "KMAMARBL92": 30.0,
    "KMAMARBL95": 79.0,
    "KMAMARBL96": 33.0,
    "KMASALEM91": 36.0,
    "KMASALEM94": 22.0,
}

# Filtering thresholds
MAX_DISTANCE_MI = 1.5  # Ignore stations farther than this
MIN_WIND_THRESHOLD = 0.3  # Wind below this = sensor failure
MAX_TEMP_DEVIATION = 4.0  # Exclude temps >4°F from median


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance in miles between two lat/lon points"""
    R = 3959  # Earth radius in miles
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c


def get_current_observation(station_id):
    """Get the most recent observation for a station"""
    url = f"{BASE_URL}?apiKey={API_KEY}&stationId={station_id}&numericPrecision=decimal&format=json&units=e"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        observations = data.get('observations', [])
        if not observations:
            return None
            
        latest = observations[-1]
        imperial = latest.get('imperial', {})
        
        # Calculate distance from Wyman Cove
        lat = latest.get('lat')
        lon = latest.get('lon')
        distance_mi = None
        if lat and lon:
            distance_mi = haversine_distance(WYMAN_COVE_LAT, WYMAN_COVE_LON, lat, lon)
        
        # Get elevation from lookup table
        elevation_ft = STATION_ELEVATIONS.get(station_id)
        
        return {
            'station_id': station_id,
            'latitude': lat,
            'longitude': lon,
            'elevation_ft': elevation_ft,
            'distance_mi': round(distance_mi, 2) if distance_mi else None,
            'timestamp': latest.get('obsTimeLocal'),
            'temperature_f': imperial.get('tempAvg'),
            'humidity_pct': latest.get('humidityAvg'),
            'wind_speed_mph': imperial.get('windspeedAvg'),
            'wind_gust_mph': imperial.get('windgustHigh'),
            'pressure_in': imperial.get('pressureMax')
        }
        
    except Exception as e:
        print(f"❌ {station_id}: {e}")
        return None


def weighted_average(values_with_weights):
    """Calculate weighted average from [(value, weight), ...] tuples"""
    if not values_with_weights:
        return None
    total_weight = sum(w for v, w in values_with_weights)
    if total_weight == 0:
        return None
    weighted_sum = sum(v * w for v, w in values_with_weights)
    return weighted_sum / total_weight


def median(values):
    """Calculate median of a list"""
    if not values:
        return None
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 0:
        return (sorted_vals[n//2 - 1] + sorted_vals[n//2]) / 2
    return sorted_vals[n//2]


def filter_and_aggregate(stations):
    """
    Intelligently filter and aggregate station data
    Returns: aggregated metrics + quality metadata
    """
    
    # Filter 1: Distance
    close_stations = [s for s in stations if s['distance_mi'] and s['distance_mi'] <= MAX_DISTANCE_MI]
    
    # Extract temps for outlier detection
    temps = [s['temperature_f'] for s in close_stations if s['temperature_f'] is not None]
    median_temp = median(temps) if temps else None
    
    # Filter 2: Temperature outliers (if we have median)
    if median_temp:
        close_stations = [s for s in close_stations 
                         if s['temperature_f'] is None or 
                         abs(s['temperature_f'] - median_temp) <= MAX_TEMP_DEVIATION]
    
    # Filter 3: Broken wind sensors (0.0 mph is almost always a sensor failure)
    valid_wind_stations = [s for s in close_stations 
                          if s['wind_speed_mph'] is not None and 
                          s['wind_speed_mph'] >= MIN_WIND_THRESHOLD]
    
    # All valid stations (for temp/humidity/pressure)
    valid_all = close_stations
    
    # Build weighted averages
    # Weight = 1 / distance² (closer = exponentially more weight)
    def get_weight(distance_mi):
        if distance_mi is None or distance_mi == 0:
            return 100.0  # Very high weight for closest
        return 1.0 / (distance_mi ** 2)
    
    # Temperature (all valid stations)
    temp_data = [(s['temperature_f'], get_weight(s['distance_mi'])) 
                 for s in valid_all if s['temperature_f'] is not None]
    
    # Humidity (all valid stations)
    humidity_data = [(s['humidity_pct'], get_weight(s['distance_mi'])) 
                     for s in valid_all if s['humidity_pct'] is not None]
    
    # Pressure (all valid stations)
    pressure_data = [(s['pressure_in'], get_weight(s['distance_mi'])) 
                     for s in valid_all if s['pressure_in'] is not None]
    
    # Wind (only stations with working wind sensors)
    wind_speed_data = [(s['wind_speed_mph'], get_weight(s['distance_mi'])) 
                       for s in valid_wind_stations if s['wind_speed_mph'] is not None]
    
    wind_gust_data = [(s['wind_gust_mph'], get_weight(s['distance_mi'])) 
                      for s in valid_wind_stations if s['wind_gust_mph'] is not None]
    
    # Calculate aggregates
    result = {
        'temperature_f': round(weighted_average(temp_data), 1) if temp_data else None,
        'humidity_pct': round(weighted_average(humidity_data), 1) if humidity_data else None,
        'pressure_in': round(weighted_average(pressure_data), 2) if pressure_data else None,
        'wind_speed_mph': round(weighted_average(wind_speed_data), 1) if wind_speed_data else None,
        'wind_gust_mph': round(weighted_average(wind_gust_data), 1) if wind_gust_data else None,
        
        # Quality metadata
        'quality': {
            'total_stations': len(stations),
            'stations_within_range': len(close_stations),
            'stations_used_temp': len(temp_data),
            'stations_used_wind': len(wind_speed_data),
            'temp_outliers_removed': len(temps) - len([s for s in close_stations if s['temperature_f']]),
            'wind_sensors_failed': len(close_stations) - len(valid_wind_stations),
            'closest_station': min(close_stations, key=lambda s: s['distance_mi'])['station_id'] if close_stations else None,
            'max_distance_used_mi': max([s['distance_mi'] for s in close_stations]) if close_stations else None,
        },
        
        # Range data for debugging
        'ranges': {
            'temp_min_f': min([s['temperature_f'] for s in valid_all if s['temperature_f']]) if valid_all else None,
            'temp_max_f': max([s['temperature_f'] for s in valid_all if s['temperature_f']]) if valid_all else None,
            'wind_min_mph': min([s['wind_speed_mph'] for s in valid_wind_stations if s['wind_speed_mph']]) if valid_wind_stations else None,
            'wind_max_mph': max([s['wind_speed_mph'] for s in valid_wind_stations if s['wind_speed_mph']]) if valid_wind_stations else None,
        },
        
        # Full station detail
        'stations': close_stations
    }
    
    return result


def main():
    print("=" * 80)
    print("WU Multi-Station Smart Scraper")
    print("=" * 80)
    print(f"Reference: Wyman Cove ({WYMAN_COVE_LAT}, {WYMAN_COVE_LON})")
    print(f"Filters: Distance ≤{MAX_DISTANCE_MI}mi | Wind ≥{MIN_WIND_THRESHOLD}mph | Temp ±{MAX_TEMP_DEVIATION}°F")
    print("=" * 80)
    print()
    
    results = []
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    def fetch_station(station_id):
        data = get_current_observation(station_id)
        return station_id, data
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_station, sid): sid for sid in STATIONS}
        for future in as_completed(futures):
            station_id, data = future.result()
            if data:
                results.append(data)
                dist = data['distance_mi'] if data['distance_mi'] else 999
                temp = data['temperature_f'] if data['temperature_f'] else 0
                wind = data['wind_speed_mph'] if data['wind_speed_mph'] else 0
                
                # Flag suspicious data
                flags = []
                if wind < MIN_WIND_THRESHOLD:
                    flags.append("⚠️ WIND")
                if dist > MAX_DISTANCE_MI:
                    flags.append("⚠️ FAR")
                
                flag_str = " ".join(flags) if flags else "✓"
                
                print(f"{station_id:15} {dist:5.2f}mi | {temp:5.1f}°F | {wind:4.1f}mph | {flag_str}")
    
    print()
    print("=" * 80)
    print("SMART AGGREGATION")
    print("=" * 80)
    
    aggregated = filter_and_aggregate(results)
    
    q = aggregated['quality']
    r = aggregated['ranges']
    
    print(f"Temperature:  {aggregated['temperature_f']}°F")
    print(f"  Range: {r['temp_min_f']}°F - {r['temp_max_f']}°F")
    print(f"  Stations used: {q['stations_used_temp']}/{q['total_stations']}")
    print(f"  Outliers removed: {q['temp_outliers_removed']}")
    
    print(f"\nHumidity:     {aggregated['humidity_pct']}%")
    
    print(f"\nWind Speed:   {aggregated['wind_speed_mph']} mph")
    print(f"  Range: {r['wind_min_mph']} - {r['wind_max_mph']} mph")
    print(f"  Stations used: {q['stations_used_wind']}/{q['stations_within_range']}")
    print(f"  Failed sensors: {q['wind_sensors_failed']}")
    
    print(f"\nWind Gust:    {aggregated['wind_gust_mph']} mph")
    
    print(f"\nPressure:     {aggregated['pressure_in']} in")
    
    print(f"\nClosest station: {q['closest_station']}")
    print(f"Max distance used: {q['max_distance_used_mi']}mi")
    
    print("=" * 80)
    
    # Save to file
    output_file = 'wu_stations_realtime.json'
    with open(output_file, 'w') as f:
        json.dump(aggregated, f, indent=2)
    print(f"\n✅ Saved to: {output_file}")

if __name__ == "__main__":
    main()

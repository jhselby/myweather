#!/usr/bin/env python3
"""
WU Multi-Station Real-Time Scraper
Uses the observations API for actual 5-minute interval data
"""

import requests
import json
import time
from datetime import datetime

# API Configuration
API_KEY = "e1f10a1e78da46f5b10a1e78da96f525"
BASE_URL = "https://api.weather.com/v2/pws/observations/all/1day"

# Station IDs
STATIONS = [
    "KMAMARBL63", "KMAMARBL69", "KMAMARBL112", "KMAMARBL108",
    "KMAMARBL39", "KMAMARBL4", "KMAMARBL36", "KMAMARBL57",
    "KMAMARBL56", "KMAMARBL89", "KMAMARBL78", "KMAMARBL1",
    "KMAMARBL17", "KMASALEM91", "KMASALEM94"
]

def get_current_observation(station_id):
    """Get the most recent observation for a station"""
    url = f"{BASE_URL}?apiKey={API_KEY}&stationId={station_id}&numericPrecision=decimal&format=json&units=e"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Get the most recent observation (last in array)
        observations = data.get('observations', [])
        if not observations:
            return None
            
        latest = observations[-1]
        imperial = latest.get('imperial', {})
        
        return {
            'station_id': station_id,
            'timestamp': latest.get('obsTimeLocal'),
            'temperature_f': imperial.get('tempAvg'),
            'humidity_pct': latest.get('humidityAvg'),
            'wind_speed_mph': imperial.get('windspeedAvg'),  # Average over last 5 min
            'wind_gust_mph': imperial.get('windgustHigh'),   # Max gust in last 5 min
            'pressure_in': imperial.get('pressureMax')
        }
        
    except Exception as e:
        print(f"❌ {station_id}: {e}")
        return None

def main():
    print("=" * 60)
    print("WU Multi-Station Real-Time Scraper")
    print("=" * 60)
    print(f"Location: Wyman Cove, Marblehead MA")
    print(f"Stations: {len(STATIONS)}")
    print("=" * 60)
    print()
    
    results = []
    
    for station_id in STATIONS:
        data = get_current_observation(station_id)
        if data:
            results.append(data)
            print(f"📊 {station_id}... ✓ "
                  f"{data['temperature_f']:.1f}°F "
                  f"H:{data['humidity_pct']:.0f}% "
                  f"W:{data['wind_speed_mph']:.1f}mph "
                  f"G:{data['wind_gust_mph']:.1f}mph "
                  f"P:{data['pressure_in']:.2f}in")
        
        time.sleep(1)  # Rate limiting
    
    # Calculate aggregates
    if results:
        print()
        print("=" * 60)
        print(f"Results: {len(results)} successful, {len(STATIONS) - len(results)} failed")
        print("=" * 60)
        
        temps = [r['temperature_f'] for r in results]
        humidity = [r['humidity_pct'] for r in results]
        winds = [r['wind_speed_mph'] for r in results]
        gusts = [r['wind_gust_mph'] for r in results]
        pressures = [r['pressure_in'] for r in results]
        
        print()
        print("📈 AGGREGATED DATA:")
        print("=" * 60)
        print(f"Temperature: {sum(temps)/len(temps):.1f}°F")
        print(f"  Range: {min(temps):.1f}°F - {max(temps):.1f}°F")
        print(f"  Variance: {max(temps) - min(temps):.1f}°F across {len(results)} stations")
        
        print(f"Humidity: {sum(humidity)/len(humidity):.1f}%")
        print(f"  Range: {min(humidity):.1f}% - {max(humidity):.1f}%")
        
        print(f"Wind Speed (5-min avg): {sum(winds)/len(winds):.1f} mph")
        print(f"  Range: {min(winds):.1f} - {max(winds):.1f} mph")
        
        print(f"Wind Gust (5-min max): {sum(gusts)/len(gusts):.1f} mph")
        print(f"  Max: {max(gusts):.1f} mph")
        
        print(f"Pressure: {sum(pressures)/len(pressures):.2f} in")
        print(f"  Range: {min(pressures):.2f} - {max(pressures):.2f} in")
        print("=" * 60)
        
        # Save to file
        output_file = 'wu_stations_realtime.json'
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n✅ Saved to: {output_file}")

if __name__ == "__main__":
    main()

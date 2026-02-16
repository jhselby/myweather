#!/usr/bin/env python3
"""
Wyman Cove Weather Station - Data Collector
Runs on GitHub Actions every 15 minutes
"""

import requests
import json
from datetime import datetime, timezone
from bs4 import BeautifulSoup

# Your location
LAT, LON = 42.5014, -70.8750
LOCATION_NAME = "Wyman Cove, Marblehead MA"

# Station IDs
TIDE_STATION = "8441241"  # Salem, MA
PWS_STATION = "KMAMARBL63"  # Castle Hill, Marblehead


def fetch_open_meteo():
    """Fetch comprehensive weather data from Open-Meteo"""
    print("📡 Fetching Open-Meteo data...")
    
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "current": ",".join([
            "temperature_2m", "relative_humidity_2m", "apparent_temperature",
            "precipitation", "weather_code", "cloud_cover", "pressure_msl",
            "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m"
        ]),
        "hourly": ",".join([
            "temperature_2m", "relative_humidity_2m", "dew_point_2m",
            "apparent_temperature", "precipitation_probability", "precipitation",
            "weather_code", "pressure_msl", "cloud_cover", "visibility",
            "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "uv_index"
        ]),
        "daily": ",".join([
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "apparent_temperature_max", "apparent_temperature_min",
            "sunrise", "sunset", "uv_index_max", "precipitation_sum",
            "precipitation_probability_max", "wind_speed_10m_max", "wind_gusts_10m_max"
        ]),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "America/New_York",
        "forecast_days": 10
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        print("✓ Open-Meteo: Success")
        return data
    except Exception as e:
        print(f"✗ Open-Meteo error: {e}")
        return None


def fetch_pws_current():
    """Scrape current conditions from Weather Underground PWS"""
    print("📡 Fetching Castle Hill PWS...")
    
    url = f"https://www.wunderground.com/weather/us/ma/marblehead/{PWS_STATION}"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        pws_data = {
            "station": PWS_STATION,
            "name": "Castle Hill",
            "updated": datetime.now().isoformat()
        }
        
        # Try to extract temperature - HTML structure may vary
        # This is best-effort scraping
        temp_elem = soup.find('span', class_='wu-value wu-value-to')
        if temp_elem:
            try:
                pws_data['temperature'] = float(temp_elem.text.strip())
            except:
                pass
        
        print(f"✓ PWS: {pws_data.get('temperature', 'N/A')}°F")
        return pws_data
        
    except Exception as e:
        print(f"✗ PWS error: {e}")
        return {"station": PWS_STATION, "name": "Castle Hill", "temperature": None}


def fetch_tides():
    """Fetch tide predictions from NOAA"""
    print("📡 Fetching NOAA tides...")
    
    url = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    
    params = {
        "station": TIDE_STATION,
        "product": "predictions",
        "datum": "MLLW",
        "time_zone": "lst_ldt",
        "units": "english",
        "format": "json",
        "range": "24"
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if 'predictions' in data:
            # Get hourly predictions and find high/low points
            predictions = data['predictions']
            tides = []
            
            # Simple high/low detection: look for local maxima/minima
            for i in range(1, len(predictions) - 1):
                prev_height = float(predictions[i-1]['v'])
                curr_height = float(predictions[i]['v'])
                next_height = float(predictions[i+1]['v'])
                
                # Local maximum (high tide)
                if curr_height > prev_height and curr_height > next_height:
                    time_str = predictions[i]['t'].split()[1]  # Extract time (already local)
                    tides.append({
                        "time": time_str,
                        "height": curr_height,
                        "type": "H"
                    })
                # Local minimum (low tide)
                elif curr_height < prev_height and curr_height < next_height:
                    time_str = predictions[i]['t'].split()[1]  # Extract time (already local)
                    tides.append({
                        "time": time_str,
                        "height": curr_height,
                        "type": "L"
                    })
                
                # Limit to 4 tides
                if len(tides) >= 4:
                    break
            
            print(f"✓ Tides: {len(tides)} events")
            return tides
        return []
        
    except Exception as e:
        print(f"✗ Tides error: {e}")
        return []


def fetch_nws_alerts():
    """Fetch active weather alerts from NWS"""
    print("📡 Fetching NWS alerts...")
    
    url = "https://api.weather.gov/alerts/active"
    params = {
        "point": f"{LAT},{LON}",
        "status": "actual",
        "message_type": "alert"
    }
    
    try:
        headers = {'User-Agent': 'MyWeather/1.0 (github.com)'}
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        alerts = []
        if 'features' in data:
            for feature in data['features']:
                props = feature['properties']
                alerts.append({
                    "event": props.get('event', 'Unknown'),
                    "headline": props.get('headline', ''),
                    "description": props.get('description', ''),
                    "severity": props.get('severity', 'Unknown'),
                    "onset": props.get('onset', ''),
                    "expires": props.get('expires', '')
                })
        
        print(f"✓ Alerts: {len(alerts)} active")
        return alerts
        
    except Exception as e:
        print(f"✗ Alerts error: {e}")
        return []


def get_weather_description(code):
    """Convert WMO weather code to description"""
    codes = {
        0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Overcast",
        45: "Fog", 48: "Freezing Fog",
        51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
        61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
        71: "Light Snow", 73: "Snow", 75: "Heavy Snow",
        77: "Snow Grains", 80: "Light Showers", 81: "Showers", 82: "Heavy Showers",
        85: "Light Snow Showers", 86: "Snow Showers",
        95: "Thunderstorm", 96: "Thunderstorm with Hail", 99: "Severe Thunderstorm"
    }
    return codes.get(code, f"Code {code}")


def get_weather_emoji(code):
    """Convert WMO weather code to emoji"""
    emojis = {
        0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
        45: "🌫️", 48: "🌫️",
        51: "🌦️", 53: "🌧️", 55: "🌧️",
        61: "🌧️", 63: "🌧️", 65: "🌧️",
        71: "🌨️", 73: "🌨️", 75: "🌨️",
        77: "🌨️", 80: "🌦️", 81: "🌦️", 82: "🌧️",
        85: "🌨️", 86: "🌨️",
        95: "⛈️", 96: "⛈️", 99: "⛈️"
    }
    return emojis.get(code, "🌡️")


def process_data(open_meteo, pws, tides, alerts):
    """Process and combine all data sources"""
    print("🔄 Processing data...")
    
    weather_data = {
        "location": {
            "name": LOCATION_NAME,
            "coordinates": {"lat": LAT, "lon": LON},
            "updated": datetime.now().isoformat()
        },
        "alerts": alerts,
        "current": {},
        "hourly": {},
        "daily": {},
        "tides": tides,
        "pws": pws
    }
    
    if open_meteo:
        # Current conditions
        current = open_meteo.get('current', {})
        weather_data['current'] = {
            "time": current.get('time', ''),
            "temperature": current.get('temperature_2m'),
            "feels_like": current.get('apparent_temperature'),
            "humidity": current.get('relative_humidity_2m'),
            "pressure": current.get('pressure_msl'),
            "wind_speed": current.get('wind_speed_10m'),
            "wind_direction": current.get('wind_direction_10m'),
            "wind_gusts": current.get('wind_gusts_10m'),
            "cloud_cover": current.get('cloud_cover'),
            "precipitation": current.get('precipitation'),
            "weather_code": current.get('weather_code'),
            "condition": get_weather_description(current.get('weather_code', 0)),
            "emoji": get_weather_emoji(current.get('weather_code', 0))
        }
        
        # Hourly forecast (48 hours)
        hourly = open_meteo.get('hourly', {})
        weather_data['hourly'] = {
            "times": hourly.get('time', [])[:48],
            "temperature": hourly.get('temperature_2m', [])[:48],
            "feels_like": hourly.get('apparent_temperature', [])[:48],
            "humidity": hourly.get('relative_humidity_2m', [])[:48],
            "dew_point": hourly.get('dew_point_2m', [])[:48],
            "precipitation_probability": hourly.get('precipitation_probability', [])[:48],
            "precipitation": hourly.get('precipitation', [])[:48],
            "wind_speed": hourly.get('wind_speed_10m', [])[:48],
            "wind_gusts": hourly.get('wind_gusts_10m', [])[:48],
            "wind_direction": hourly.get('wind_direction_10m', [])[:48],
            "pressure": hourly.get('pressure_msl', [])[:48],
            "cloud_cover": hourly.get('cloud_cover', [])[:48],
            "visibility": hourly.get('visibility', [])[:48],
            "uv_index": hourly.get('uv_index', [])[:48],
            "weather_code": hourly.get('weather_code', [])[:48]
        }
        
        # Daily forecast (10 days)
        daily = open_meteo.get('daily', {})
        weather_data['daily'] = {
            "dates": daily.get('time', []),
            "temperature_max": daily.get('temperature_2m_max', []),
            "temperature_min": daily.get('temperature_2m_min', []),
            "feels_like_max": daily.get('apparent_temperature_max', []),
            "feels_like_min": daily.get('apparent_temperature_min', []),
            "sunrise": daily.get('sunrise', []),
            "sunset": daily.get('sunset', []),
            "precipitation_sum": daily.get('precipitation_sum', []),
            "precipitation_probability_max": daily.get('precipitation_probability_max', []),
            "wind_speed_max": daily.get('wind_speed_10m_max', []),
            "wind_gusts_max": daily.get('wind_gusts_10m_max', []),
            "uv_index_max": daily.get('uv_index_max', []),
            "weather_code": daily.get('weather_code', [])
        }
    
    print("✓ Processing complete")
    return weather_data


def main():
    print(f"\n{'='*60}")
    print(f"Wyman Cove Weather - GitHub Actions Update")
    print(f"{'='*60}\n")
    
    # Fetch from all sources (failures are handled gracefully)
    open_meteo_data = fetch_open_meteo()
    pws_data = fetch_pws_current()
    tide_data = fetch_tides()
    alert_data = fetch_nws_alerts()
    
    # Process and combine
    weather_data = process_data(open_meteo_data, pws_data, tide_data, alert_data)
    
    # Save to JSON
    with open('weather_data.json', 'w') as f:
        json.dump(weather_data, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✓ Update complete - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

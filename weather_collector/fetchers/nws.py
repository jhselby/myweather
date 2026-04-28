"""
Fetch NWS forecast and alerts
"""
import requests
from ..config import LAT, LON
from ..utils import iso_utc_now

HEADERS_DEFAULT = {"User-Agent": "WymanCoveWeather/1.0"}


def fetch_nws_forecast():
    """Fetch NWS forecast discussion and text forecast."""
    print("📡 Fetching NWS forecast...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        # Get grid point
        point_url = f"https://api.weather.gov/points/{LAT},{LON}"
        r = requests.get(point_url, headers=HEADERS_DEFAULT, timeout=30)
        r.raise_for_status()
        point_data = r.json()

        forecast_url = point_data["properties"]["forecast"]
        
        # Get forecast
        r2 = requests.get(forecast_url, headers=HEADERS_DEFAULT, timeout=30)
        r2.raise_for_status()
        forecast_data = r2.json()

        periods = forecast_data["properties"]["periods"][:14]

        # Normalize field names (NWS uses camelCase, UI expects snake_case)
        normalized_periods = []
        for p in periods:
            normalized_periods.append({
                "name": p.get("name"),
                "start_time": p.get("startTime"),
                "end_time": p.get("endTime"),
                "is_daytime": p.get("isDaytime"),
                "temperature": p.get("temperature"),
                "temperature_unit": p.get("temperatureUnit"),
                "wind_speed": p.get("windSpeed"),
                "wind_direction": p.get("windDirection"),
                "short_forecast": p.get("shortForecast"),
                "detailed": p.get("detailedForecast"),
            })

        meta["status"] = "ok"
        print(f"  ✓ NWS forecast: {len(normalized_periods)} periods")
        return normalized_periods, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ NWS forecast: {e}")
        return None, meta


def fetch_nws_alerts():
    """Fetch active NWS alerts for the area."""
    print("📡 Fetching NWS alerts...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        url = f"https://api.weather.gov/alerts/active?point={LAT},{LON}"
        r = requests.get(url, headers=HEADERS_DEFAULT, timeout=30)
        r.raise_for_status()
        data = r.json()

        features = data.get("features", [])
        
        # Transform to simplified format expected by frontend
        alerts = []
        for f in features:
            props = f.get("properties", {})
            # Skip TEST alerts (NWS transmission tests)
            desc = (props.get('description', '') + ' ' + props.get('headline', '')).upper()
            if 'THIS_MESSAGE_IS_FOR_TEST_PURPOSES_ONLY' in desc or 'THIS IS A TEST' in desc:
                print(f"  ⏭ Skipping TEST alert: {props.get('event', 'Unknown')}")
                continue
            event_type = props.get('event', 'Special Weather Statement').replace(' ', '+')
            web_url = (
                f"https://forecast.weather.gov/showsigwx.php?"
                f"warnzone=MAZ007&warncounty=MAC009&firewxzone=MAZ007"
                f"&local_place1=Marblehead+MA"
                f"&product1={event_type}"
                f"&lat={LAT}&lon={LON}"
            )
            alerts.append({
                "event": props.get('event', 'Unknown'),
                "headline": props.get('headline', ''),
                "description": props.get('description', ''),
                "severity": props.get('severity', 'Unknown'),
                "onset": props.get('onset', ''),
                "expires": props.get('expires', ''),
                "url": web_url
            })

        meta["status"] = "ok"
        print(f"  ✓ NWS alerts: {len(alerts)} active")
        return alerts, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ NWS alerts: {e}")
        return [], meta
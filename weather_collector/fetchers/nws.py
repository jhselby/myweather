"""
Fetch NWS data: alerts and gridpoint forecasts (BOX/76,97)
"""
import requests
from ..config import LAT, LON
from ..utils import iso_utc_now, redact_secrets
import logging

HEADERS = {"User-Agent": "WymanCoveWeather/1.0"}
GRIDPOINT_URL = "https://api.weather.gov/gridpoints/BOX/76,97"


def fetch_nws_alerts():
    """Fetch active NWS alerts for the area."""
    logging.info("📡 Fetching NWS alerts...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        url = f"https://api.weather.gov/alerts/active?point={LAT},{LON}"
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()

        features = data.get("features", [])

        alerts = []
        for f in features:
            props = f.get("properties", {})
            desc = (props.get('description', '') + ' ' + props.get('headline', '')).upper()
            if 'THIS_MESSAGE_IS_FOR_TEST_PURPOSES_ONLY' in desc or 'THIS IS A TEST' in desc:
                logging.info(f"  ⏭ Skipping TEST alert: {props.get('event', 'Unknown')}")
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
        logging.info(f"  ✓ NWS alerts: {len(alerts)} active")
        return alerts, meta

    except Exception as e:
        meta["error"] = redact_secrets(e)
        logging.error(f"  ✗ NWS alerts: {redact_secrets(e)}")
        return [], meta


def fetch_nws_gridpoints():
    """Fetch NWS gridpoint hourly data (temperature, precip, wind)."""
    logging.info("📡 Fetching NWS gridpoint data...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        r = requests.get(GRIDPOINT_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()

        properties = data.get("properties", {})
        result = {
            "temperature": properties.get("temperature", {}),
            "dewpoint": properties.get("dewpoint", {}),
            "probabilityOfPrecipitation": properties.get("probabilityOfPrecipitation", {}),
            "quantitativePrecipitation": properties.get("quantitativePrecipitation", {}),
            "weather": properties.get("weather", {}),
            "windSpeed": properties.get("windSpeed", {}),
            "windDirection": properties.get("windDirection", {}),
        }

        meta["status"] = "ok"
        logging.info(f"  ✓ NWS gridpoints fetched")
        return result, meta

    except Exception as e:
        meta["error"] = redact_secrets(e)
        logging.error(f"  ✗ NWS gridpoints failed: {redact_secrets(e)}")
        return {}, meta

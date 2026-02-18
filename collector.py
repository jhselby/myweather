#!/usr/bin/env python3
"""
Wyman Cove Weather Station - Data Collector
Runs on GitHub Actions every 15 minutes

Robustness upgrades:
- schema_version + generated_at
- per-source status + errors + timestamps
- DST-safe timezone handling (zoneinfo)
- PWS last-known-good caching (last_pws.json)
"""

import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from pathlib import Path

# -----------------------------
# Config
# -----------------------------
LAT, LON = 42.5014, -70.8750
LOCATION_NAME = "Wyman Cove, Marblehead MA"

TIDE_STATION = "8442645"      # Salem Harbor, MA
PWS_STATION = "KMAMARBL63"    # Castle Hill, Marblehead

SCHEMA_VERSION = "1.1"
PWS_CACHE_FILE = Path("last_pws.json")

# -----------------------------
# Wind Exposure Model (House-specific)
# -----------------------------
EXPOSED_SECTOR_MIN = 290  # degrees
EXPOSED_SECTOR_MAX = 350  # degrees
EXPOSURE_MULTIPLIER = 1.2

# Gust thresholds (mph)
GUST_NOTICEABLE = 25
GUST_STRONG = 35
GUST_HIGH = 45
GUST_SEVERE = 55

HEADERS_DEFAULT = {
    "User-Agent": "MyWeather/1.0 (github.com/jhselby/myweather)"
}


# -----------------------------
# Helpers
# -----------------------------
def iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_float(x):
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def load_json(path: Path):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return None


def save_json(path: Path, obj):
    path.write_text(json.dumps(obj, indent=2))


def compute_age_minutes(updated_at_iso: str, now_utc: datetime) -> float | None:
    try:
        # Accept both "Z" and no-Z.
        s = updated_at_iso.replace("Z", "+00:00")
        t = datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        delta = now_utc - t.astimezone(timezone.utc)
        return round(delta.total_seconds() / 60.0, 1)
    except Exception:
        return None


def get_weather_description(code):
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


# -----------------------------
# Fetchers
# -----------------------------
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
            "sunrise", "sunset",
            "uv_index_max", "precipitation_sum",
            "precipitation_probability_max", "wind_speed_10m_max", "wind_gusts_10m_max"
        ]),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "America/New_York",
        "forecast_days": 10
    }

    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        r = requests.get(url, params=params, headers=HEADERS_DEFAULT, timeout=30)
        r.raise_for_status()
        data = r.json()
        meta["status"] = "ok"
        print("✓ Open-Meteo: Success")
        return data, meta
    except Exception as e:
        meta["error"] = str(e)
        print(f"✗ Open-Meteo error: {e}")
        return None, meta


def fetch_pws_current():
    """
    Scrape current conditions from Weather Underground PWS.
    Robustness:
    - If scrape fails, return last-known-good cached value (with stale=true).
    """
    print("📡 Fetching Castle Hill PWS...")

    url = f"https://www.wunderground.com/weather/us/ma/marblehead/{PWS_STATION}"
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    last = load_json(PWS_CACHE_FILE)

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        pws_data = {
            "station": PWS_STATION,
            "name": "Castle Hill",
            "updated": datetime.now().isoformat(),  # local runner time; fine for display
            "temperature": None,
            "stale": False
        }

        # Best-effort selector (WU changes frequently)
        temp_elem = soup.find("span", class_="wu-value wu-value-to")
        if temp_elem:
            pws_data["temperature"] = safe_float(temp_elem.text.strip())

        # If we didn't get a temperature, treat as failure and fall back
        if pws_data["temperature"] is None:
            raise RuntimeError("Could not parse PWS temperature (WU DOM likely changed).")

        # Cache last-known-good
        save_json(PWS_CACHE_FILE, pws_data)

        meta["status"] = "ok"
        print(f"✓ PWS: {pws_data['temperature']}°F")
        return pws_data, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"✗ PWS error: {e}")

        if last and isinstance(last, dict) and last.get("temperature") is not None:
            # Return cached value, marked stale
            last_copy = dict(last)
            last_copy["stale"] = True
            return last_copy, meta

        # Nothing cached
        return {"station": PWS_STATION, "name": "Castle Hill", "updated": None, "temperature": None, "stale": True}, meta


def fetch_tides():
    """Fetch tide predictions from NOAA and extract 4 nearby highs/lows."""
    print("📡 Fetching NOAA tides...")

    url = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    today = datetime.now()
    begin_date = today.strftime("%Y%m%d")
    end_date = (today + timedelta(days=1)).strftime("%Y%m%d")

    params = {
        "begin_date": begin_date,
        "end_date": end_date,
        "station": TIDE_STATION,
        "product": "predictions",
        "datum": "MLLW",
        "time_zone": "lst_ldt",
        "units": "english",
        "format": "json"
    }

    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        r = requests.get(url, params=params, headers=HEADERS_DEFAULT, timeout=30)
        r.raise_for_status()
        data = r.json()

        tides = []
        preds = data.get("predictions", [])
        if not preds:
            meta["status"] = "ok"
            return [], meta

        for i in range(1, len(preds) - 1):
            prev_h = safe_float(preds[i - 1].get("v"))
            curr_h = safe_float(preds[i].get("v"))
            next_h = safe_float(preds[i + 1].get("v"))
            if prev_h is None or curr_h is None or next_h is None:
                continue

            # local max high tide
            if curr_h > prev_h and curr_h > next_h and curr_h > 7.0:
                time_str = preds[i]["t"].split()[1]
                tides.append({"time": time_str, "height": curr_h, "type": "H"})

            # local min low tide
            elif curr_h < prev_h and curr_h < next_h and curr_h < 3.0:
                time_str = preds[i]["t"].split()[1]
                tides.append({"time": time_str, "height": curr_h, "type": "L"})

            if len(tides) >= 4:
                break

        meta["status"] = "ok"
        print(f"✓ Tides: {len(tides)} events")
        return tides, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"✗ Tides error: {e}")
        return [], meta


def fetch_nws_alerts():
    """Fetch active weather alerts from NWS for the lat/lon point."""
    print("📡 Fetching NWS alerts...")

    url = "https://api.weather.gov/alerts/active"
    params = {"point": f"{LAT},{LON}", "status": "actual", "message_type": "alert"}

    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        r = requests.get(url, params=params, headers=HEADERS_DEFAULT, timeout=30)
        r.raise_for_status()
        data = r.json()

        alerts = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            web_url = "https://www.weather.gov/box"  # Boston office
            alerts.append({
                "event": props.get("event", "Unknown"),
                "headline": props.get("headline", ""),
                "description": props.get("description", ""),
                "severity": props.get("severity", "Unknown"),
                "onset": props.get("onset", ""),
                "expires": props.get("expires", ""),
                "url": web_url
            })

        meta["status"] = "ok"
        print(f"✓ Alerts: {len(alerts)} active")
        return alerts, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"✗ Alerts error: {e}")
        return [], meta


# -----------------------------
# Processing
# -----------------------------
def process_data(open_meteo, pws, tides, alerts, source_meta):
    """Combine and normalize data sources into a stable schema."""
    print("🔄 Processing data...")

    now_utc = datetime.now(timezone.utc)
    generated_at = iso_utc_now()

    # Add ages
    for k, meta in source_meta.items():
        meta["age_minutes"] = compute_age_minutes(meta.get("updated_at", ""), now_utc)

    weather_data = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "location": {
            "name": LOCATION_NAME,
            "coordinates": {"lat": LAT, "lon": LON},
            "updated": generated_at
        },
        "sources": source_meta,
        "alerts": alerts if alerts is not None else [],
        "current": {},
        "hourly": {},
        "daily": {},
        "tides": tides if tides is not None else [],
        "pws": pws if pws is not None else {"station": PWS_STATION, "name": "Castle Hill", "temperature": None, "stale": True}
    }

    if open_meteo:
        current = open_meteo.get("current", {}) or {}
        wcode = current.get("weather_code", 0)

        weather_data["current"] = {
            "time": current.get("time", ""),
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "pressure": current.get("pressure_msl"),
            "wind_speed": current.get("wind_speed_10m"),
            "wind_direction": current.get("wind_direction_10m"),
            "wind_gusts": current.get("wind_gusts_10m"),
            "cloud_cover": current.get("cloud_cover"),
            "precipitation": current.get("precipitation"),
            "weather_code": wcode,
            "condition": get_weather_description(wcode),
            "emoji": get_weather_emoji(wcode)
        }

        # Hourly forecast: slice next 48 hours starting from "now" in America/New_York (DST-safe)
        hourly = open_meteo.get("hourly", {}) or {}
        times = hourly.get("time", []) or []
        now_local = datetime.now(ZoneInfo("America/New_York"))

        current_idx = 0
        try:
            # Find first time >= now
            parsed_times = [datetime.fromisoformat(t) for t in times]
            for i, t in enumerate(parsed_times):
                # Open-Meteo provides local times without tzinfo; treat as local
                if t.replace(tzinfo=None) >= now_local.replace(tzinfo=None):
                    current_idx = i
                    break
        except Exception:
            current_idx = 0

        end_idx = current_idx + 48

        def sl(key):
            arr = hourly.get(key, []) or []
            return arr[current_idx:end_idx]

        weather_data["hourly"] = {
            "times": sl("time"),
            "temperature": sl("temperature_2m"),
            "feels_like": sl("apparent_temperature"),
            "humidity": sl("relative_humidity_2m"),
            "dew_point": sl("dew_point_2m"),
            "precipitation_probability": sl("precipitation_probability"),
            "precipitation": sl("precipitation"),
            "wind_speed": sl("wind_speed_10m"),
            "wind_gusts": sl("wind_gusts_10m"),
            "wind_direction": sl("wind_direction_10m"),
            "pressure": sl("pressure_msl"),
            "cloud_cover": sl("cloud_cover"),
            "visibility": sl("visibility"),
            "uv_index": sl("uv_index"),
            "weather_code": sl("weather_code")
        }

        daily = open_meteo.get("daily", {}) or {}
        weather_data["daily"] = {
            "dates": daily.get("time", []) or [],
            "temperature_max": daily.get("temperature_2m_max", []) or [],
            "temperature_min": daily.get("temperature_2m_min", []) or [],
            "feels_like_max": daily.get("apparent_temperature_max", []) or [],
            "feels_like_min": daily.get("apparent_temperature_min", []) or [],
            "sunrise": daily.get("sunrise", []) or [],
            "sunset": daily.get("sunset", []) or [],
            "precipitation_sum": daily.get("precipitation_sum", []) or [],
            "precipitation_probability_max": daily.get("precipitation_probability_max", []) or [],
            "wind_speed_max": daily.get("wind_speed_10m_max", []) or [],
            "wind_gusts_max": daily.get("wind_gusts_10m_max", []) or [],
            "uv_index_max": daily.get("uv_index_max", []) or [],
            "weather_code": daily.get("weather_code", []) or []
        }

        # Hyperlocal correction (simple bias)
        model_t = weather_data["current"].get("temperature")
        pws_t = weather_data["pws"].get("temperature") if isinstance(weather_data["pws"], dict) else None
        if model_t is not None and pws_t is not None:
            bias = round(pws_t - model_t, 2)
            weather_data["hyperlocal"] = {
                "bias_temp": bias,
                "corrected_temp": round(model_t + bias, 2)
            }

        # Pressure trend (next 3 hours from now)
        p = weather_data["hourly"].get("pressure", [])
        if isinstance(p, list) and len(p) >= 3 and all(x is not None for x in p[:3]):
            # h0 -> h2 trend in msl hPa
            trend = p[2] - p[0]
            label = "Steady"
            if trend > 0.6:
                label = "Rising"
            elif trend < -0.6:
                label = "Falling"
            weather_data["derived"] = {"pressure_trend": label, "pressure_trend_hpa_2h": round(trend, 1)}
        
        # -----------------------------
        # Wind Risk Model (House Impact)
        # -----------------------------
        gust = weather_data["current"].get("wind_gusts")
        direction = weather_data["current"].get("wind_direction")

        if gust is not None and direction is not None:
            # Check if wind direction is in exposed sector
            exposed = False
            if EXPOSED_SECTOR_MIN <= direction <= EXPOSED_SECTOR_MAX:
                exposed = True

            impact_gust = gust * (EXPOSURE_MULTIPLIER if exposed else 1.0)

            # Classify risk level
            level = "LOW"
            if impact_gust >= GUST_SEVERE:
                level = "SEVERE"
            elif impact_gust >= GUST_HIGH:
                level = "HIGH"
            elif impact_gust >= GUST_STRONG:
                level = "STRONG"
            elif impact_gust >= GUST_NOTICEABLE:
                level = "NOTICEABLE"

            weather_data["wind_risk"] = {
                "level": level,
                "peak_gust_mph": round(gust, 1),
                "direction_deg": direction,
                "exposed": exposed,
                "impact_gust_mph": round(impact_gust, 1)
            }
    
    print("✓ Processing complete")
    return weather_data


def main():
    print("\n" + "=" * 60)
    print("Wyman Cove Weather - GitHub Actions Update")
    print("=" * 60 + "\n")

    open_meteo_data, open_meteo_meta = fetch_open_meteo()
    pws_data, pws_meta = fetch_pws_current()
    tide_data, tides_meta = fetch_tides()
    alert_data, alerts_meta = fetch_nws_alerts()

    sources = {
        "open_meteo": open_meteo_meta,
        "pws": pws_meta,
        "tides": tides_meta,
        "nws_alerts": alerts_meta
    }

    weather_data = process_data(open_meteo_data, pws_data, tide_data, alert_data, sources)

    # Save to JSON
    with open("weather_data.json", "w") as f:
        json.dump(weather_data, f, indent=2)

    print("\n" + "=" * 60)
    print(f"✓ Update complete - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

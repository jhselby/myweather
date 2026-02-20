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
# Wind Exposure Model (House-specific, 16 Indianhead Circle)
#
# Graduated exposure by direction. Values 0.0–1.0 reflect how exposed
# the structure is to wind from that compass sector, accounting for:
#   - Open water fetch to N/NW (Salem Harbor)
#   - Low neck/cove exposure to WNW
#   - Rising terrain (49–98 ft) providing shelter from SW/S/SE
#
# Each tuple: (min_bearing_inclusive, max_bearing_exclusive, exposure_factor)
# -----------------------------
WIND_EXPOSURE_TABLE = [
    (  0,  20, 1.00),   # N         full water fetch
    ( 20,  60, 0.90),   # NNE–NE    open water, slight angle
    ( 60,  90, 0.70),   # ENE       long water fetch, angled
    ( 90, 130, 0.50),   # E–ESE     water fetch but oblique
    (130, 165, 0.20),   # SE        land starts to shelter
    (165, 200, 0.10),   # S–SSW     well protected, terrain rises
    (200, 255, 0.05),   # SW        max protection: 49–98 ft terrain
    (255, 285, 0.30),   # W–WSW     partial shelter from SW terrain
    (285, 315, 0.70),   # WNW       low neck/cove, increasing exposure
    (315, 360, 0.95),   # NW        open harbor + cold-air acceleration
]

# Wind Worry Score = speed_mph * exposure_factor^1.5
# Non-linear so speed matters much more on exposed sectors.
# Worry thresholds (tuned to site observations):
WORRY_NOTICEABLE  =  5   # may feel it
WORRY_NOTABLE     = 12   # outdoor furniture, loose items
WORRY_SIGNIFICANT = 20   # house shakes, structural concern
WORRY_SEVERE      = 30   # exceptional event

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


def compute_age_minutes(updated_at_iso: str, now_utc: datetime):
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

def _om_get(params, label):
    """GET from Open-Meteo with standard error handling."""
    url  = "https://api.open-meteo.com/v1/forecast"
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None, "model": label}
    try:
        r = requests.get(url, params=params, headers=HEADERS_DEFAULT, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise ValueError(data.get("reason", str(data["error"])))
        meta["status"] = "ok"
        print(f"  ✓ {label}")
        return data, meta
    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ {label}: {e}")
        return None, meta


# Shared units for all Open-Meteo calls
_OM_UNITS = {
    "temperature_unit":   "fahrenheit",
    "wind_speed_unit":    "mph",
    "precipitation_unit": "inch",
    "timezone":           "America/New_York",
}

# HRRR supports these hourly vars (no uv_index, no visibility)
_HRRR_HOURLY = ",".join([
    "temperature_2m", "relative_humidity_2m", "dew_point_2m",
    "apparent_temperature", "precipitation_probability", "precipitation",
    "weather_code", "pressure_msl", "cloud_cover",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
])

# GFS/default supports these additional vars for current + fallback hourly
_GFS_HOURLY = _HRRR_HOURLY + ",visibility,uv_index"

_CURRENT_VARS = ",".join([
    "temperature_2m", "relative_humidity_2m", "apparent_temperature",
    "precipitation", "weather_code", "cloud_cover", "pressure_msl",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
])

_DAILY_VARS = ",".join([
    "weather_code", "temperature_2m_max", "temperature_2m_min",
    "apparent_temperature_max", "apparent_temperature_min",
    "sunrise", "sunset", "uv_index_max", "precipitation_sum",
    "precipitation_probability_max", "wind_speed_10m_max", "wind_gusts_10m_max",
])


def fetch_current_gfs():
    """
    Fetch current conditions from GFS (Open-Meteo default).
    HRRR does not expose a current conditions endpoint, so GFS
    is used for the instantaneous snapshot. GFS updates every 6h
    which is sufficient for current conditions.
    """
    print("📡 Fetching current conditions (GFS)...")
    params = {
        "latitude":  LAT,
        "longitude": LON,
        "current":   _CURRENT_VARS,
        **_OM_UNITS,
    }
    return _om_get(params, "GFS current")


def fetch_hourly_hrrr():
    """
    Fetch 48h hourly forecast from HRRR (ncep_hrrr_conus).
    HRRR runs at ~3km resolution, updates every hour, covers CONUS.
    Significantly better than GFS for short-range coastal forecasts —
    resolves land-sea boundary, local terrain, mesoscale convection.
    Falls back to GFS seamless if HRRR unavailable.
    """
    print("📡 Fetching 48h hourly (HRRR)...")
    params = {
        "latitude":      LAT,
        "longitude":     LON,
        "hourly":        _HRRR_HOURLY,
        "models":        "ncep_hrrr_conus",
        "forecast_days": 2,
        **_OM_UNITS,
    }
    data, meta = _om_get(params, "HRRR hourly")
    if data is None:
        print("  ⚠️  HRRR unavailable — falling back to GFS seamless")
        fb = {k: v for k, v in params.items() if k != "models"}
        fb["hourly"] = _GFS_HOURLY
        data, meta = _om_get(fb, "GFS seamless (HRRR fallback)")
    return data, meta


def fetch_daily_ecmwf():
    """
    Fetch 10-day daily forecast from ECMWF IFS 0.25deg.
    ECMWF is the world's best global NWP model for medium-range
    (3-10 day) forecasts. Used only for the daily summary since
    HRRR covers short-range better.
    Falls back to GFS seamless if ECMWF unavailable.
    """
    print("📡 Fetching 10-day daily (ECMWF)...")
    params = {
        "latitude":      LAT,
        "longitude":     LON,
        "daily":         _DAILY_VARS,
        "models":        "ecmwf_ifs025",
        "forecast_days": 10,
        **_OM_UNITS,
    }
    data, meta = _om_get(params, "ECMWF daily")
    if data is None:
        print("  ⚠️  ECMWF unavailable — falling back to GFS seamless")
        fb = {k: v for k, v in params.items() if k != "models"}
        data, meta = _om_get(fb, "GFS seamless (ECMWF fallback)")
    return data, meta


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
    """
    Fetch tide predictions from NOAA.
    Makes two calls:
      1. High/low events (hilo product) — capped at 8, used for tile display
      2. 6-minute interval curve (predictions product) — 48h, used for chart
    """
    print("\U0001f4e1 Fetching NOAA tides...")

    url   = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    today = datetime.now()
    begin = today.strftime("%Y%m%d")
    end   = (today + timedelta(days=2)).strftime("%Y%m%d")
    base  = {
        "station":   TIDE_STATION,
        "datum":     "MLLW",
        "time_zone": "lst_ldt",
        "units":     "english",
        "format":    "json",
        "begin_date": begin,
        "end_date":   end,
    }
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        # --- Call 1: high/low events ---
        r1 = requests.get(url, params={**base, "product": "predictions",
                                        "interval": "hilo"},
                          headers=HEADERS_DEFAULT, timeout=30)
        r1.raise_for_status()
        hilo_preds = r1.json().get("predictions", [])

        tides = []
        for p in hilo_preds:
            t_parts  = p["t"].split()
            tide_type = "H" if p.get("type", "").upper() == "H" else "L"
            tides.append({
                "date":   t_parts[0],
                "time":   t_parts[1],
                "height": round(safe_float(p.get("v")) or 0, 3),
                "type":   tide_type,
            })
            if len(tides) >= 8:
                break
        print(f"  \u2713 Tide events: {len(tides)}")

        # --- Call 2: 6-minute curve for chart ---
        r2 = requests.get(url, params={**base, "product": "predictions",
                                        "interval": "6"},
                          headers=HEADERS_DEFAULT, timeout=30)
        r2.raise_for_status()
        curve_preds = r2.json().get("predictions", [])

        curve_times   = []
        curve_heights = []
        for p in curve_preds:
            h = safe_float(p.get("v"))
            if h is not None:
                curve_times.append(p["t"])     # "YYYY-MM-DD HH:MM"
                curve_heights.append(round(h, 2))
        print(f"  \u2713 Tide curve: {len(curve_times)} points")

        meta["status"] = "ok"
        return {
            "events": tides,
            "curve":  {"times": curve_times, "heights": curve_heights},
        }, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"  \u2717 Tides error: {e}")
        return {"events": [], "curve": {"times": [], "heights": []}}, meta


def fetch_nws_forecast():
    """
    Fetch NWS plain-English detailed forecast for the location.
    Two-step: first hit /points to get the forecast URL for this
    grid point, then fetch that URL for the period-by-period text.
    Written by NWS Boston meteorologists, not model-generated.
    """
    print("\U0001f4e1 Fetching NWS detailed forecast...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        # Step 1: resolve grid point
        points_url = f"https://api.weather.gov/points/{LAT},{LON}"
        r1 = requests.get(points_url, headers=HEADERS_DEFAULT, timeout=30)
        r1.raise_for_status()
        props = r1.json().get("properties", {})
        forecast_url = props.get("forecast")
        office      = props.get("cwa", "")
        grid_x      = props.get("gridX", "")
        grid_y      = props.get("gridY", "")
        if not forecast_url:
            raise ValueError("No forecast URL returned from /points")

        # Step 2: fetch the forecast
        r2 = requests.get(forecast_url, headers=HEADERS_DEFAULT, timeout=30)
        r2.raise_for_status()
        periods_raw = r2.json().get("properties", {}).get("periods", [])

        periods = []
        for p in periods_raw:
            periods.append({
                "name":           p.get("name", ""),
                "is_daytime":     p.get("isDaytime", True),
                "temperature":    p.get("temperature"),
                "temp_unit":      p.get("temperatureUnit", "F"),
                "wind_speed":     p.get("windSpeed", ""),
                "wind_direction": p.get("windDirection", ""),
                "short_forecast": p.get("shortForecast", ""),
                "detailed":       p.get("detailedForecast", ""),
                "icon":           p.get("icon", ""),
            })

        meta["status"] = "ok"
        meta["office"] = office
        meta["grid"]   = f"{grid_x},{grid_y}"
        print(f"  \u2713 NWS forecast: {len(periods)} periods ({office})")
        return periods, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"  \u2717 NWS forecast error: {e}")
        return [], meta


def fetch_nws_alerts():
    """Fetch active weather alerts from NWS for the lat/lon point."""
    print("📡 Fetching NWS alerts...")

    url = "https://api.weather.gov/alerts/active"
    params = {"point": f"{LAT},{LON}", "status": "actual"}

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
def process_data(current_data, hourly_data, daily_data, pws, tides, nws_forecast, alerts, source_meta):
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
        "tides":      (tides or {}).get("events", []),
        "tide_curve": (tides or {}).get("curve",  {"times": [], "heights": []}),
        "nws_forecast": nws_forecast if nws_forecast is not None else [],
        "pws": pws if pws is not None else {"station": PWS_STATION, "name": "Castle Hill", "temperature": None, "stale": True}
    }

    if current_data:
        current = current_data.get("current", {}) or {}
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
        hourly = (hourly_data or {}).get("hourly", {}) or {}
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

        daily = (daily_data or {}).get("daily", {}) or {}
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
        # Uses PEAK gust over next 12 hours (more useful than instantaneous "current")
        # -----------------------------
        # -----------------------------
        # Wind Risk Model (House Impact)
        # Computes two sub-scores from hourly data over a rolling window:
        #   gust      — peak gust in window (structural stress)
        #   sustained — peak sustained wind in window (dock lines, outdoor use)
        # Both use: worry_score = speed * exposure_factor^1.5
        # -----------------------------

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
            return round(speed * (exp_factor ** 1.5), 2)

        def worry_level(score):
            if score >= WORRY_SEVERE:      return "SEVERE"
            if score >= WORRY_SIGNIFICANT: return "SIGNIFICANT"
            if score >= WORRY_NOTABLE:     return "NOTABLE"
            if score >= WORRY_NOTICEABLE:  return "NOTICEABLE"
            return "LOW"

        peak_window_hours = 12
        hourly_h = weather_data.get("hourly", {}) or {}
        hourly_gusts = hourly_h.get("wind_gusts", []) or []
        hourly_speeds = hourly_h.get("wind_speed", []) or []
        hourly_dirs   = hourly_h.get("wind_direction", []) or []
        hourly_times  = hourly_h.get("times", []) or []

        lookahead = min(peak_window_hours, len(hourly_gusts), len(hourly_dirs))

        def _safe_num(x):
            try:
                return float(x)
            except Exception:
                return None

        def find_peak(values, dirs, n):
            """Return (value, direction_deg, time_iso, index) for max value in first n slots."""
            best_val, best_dir, best_i = -1.0, None, None
            for i in range(n):
                v = _safe_num(values[i]) if i < len(values) else None
                d = _safe_num(dirs[i])   if i < len(dirs)   else None
                if v is None or d is None:
                    continue
                if v > best_val:
                    best_val, best_dir, best_i = v, d, i
            if best_i is None:
                return None, None, None
            t = hourly_times[best_i] if best_i < len(hourly_times) else None
            return best_val, best_dir, t

        gust_val,  gust_dir,  gust_time  = find_peak(hourly_gusts,  hourly_dirs, lookahead)
        sus_val,   sus_dir,   sus_time   = find_peak(hourly_speeds,  hourly_dirs, lookahead)

        # Fallback to current if hourly unavailable
        if gust_val is None:
            gust_val = _safe_num(weather_data.get("current", {}).get("wind_gusts"))
            gust_dir = _safe_num(weather_data.get("current", {}).get("wind_direction"))
            gust_time = None
        if sus_val is None:
            sus_val = _safe_num(weather_data.get("current", {}).get("wind_speed"))
            sus_dir = _safe_num(weather_data.get("current", {}).get("wind_direction"))
            sus_time = None

        wind_risk = {"window_hours": peak_window_hours}

        if gust_val is not None and gust_dir is not None:
            gd = int(gust_dir) % 360
            ef = get_exposure_factor(gd)
            ws = worry_score(gust_val, ef)
            wind_risk["gust"] = {
                "peak_mph":        round(gust_val, 1),
                "direction_deg":   gd,
                "exposure_factor": round(ef, 2),
                "worry_score":     ws,
                "level":           worry_level(ws),
                "peak_time":       gust_time,
            }
            # Store peak gust time in derived for header display
            if gust_time:
                weather_data.setdefault("derived", {})["wind_peak_time"] = gust_time

        if sus_val is not None and sus_dir is not None:
            sd = int(sus_dir) % 360
            ef = get_exposure_factor(sd)
            ws = worry_score(sus_val, ef)
            wind_risk["sustained"] = {
                "peak_mph":        round(sus_val, 1),
                "direction_deg":   sd,
                "exposure_factor": round(ef, 2),
                "worry_score":     ws,
                "level":           worry_level(ws),
                "peak_time":       sus_time,
            }

        if len(wind_risk) > 1:  # has at least one sub-object
            weather_data["wind_risk"] = wind_risk


    
    print("✓ Processing complete")
    return weather_data


def main():
    print("\n" + "=" * 60)
    print("Wyman Cove Weather - GitHub Actions Update")
    print("=" * 60 + "\n")

    current_data,  current_meta  = fetch_current_gfs()
    hourly_data,   hourly_meta   = fetch_hourly_hrrr()
    daily_data,    daily_meta    = fetch_daily_ecmwf()
    pws_data,      pws_meta      = fetch_pws_current()
    tide_data,     tides_meta    = fetch_tides()
    forecast_data, forecast_meta = fetch_nws_forecast()
    alert_data,    alerts_meta   = fetch_nws_alerts()

    sources = {
        "gfs_current": current_meta,
        "hrrr_hourly": hourly_meta,
        "ecmwf_daily": daily_meta,
        "pws":         pws_meta,
        "tides":       tides_meta,
        "nws_forecast": forecast_meta,
        "nws_alerts":  alerts_meta,
    }

    weather_data = process_data(
        current_data, hourly_data, daily_data,
        pws_data, tide_data, forecast_data, alert_data, sources
    )

    # Save to JSON
    with open("weather_data.json", "w") as f:
        json.dump(weather_data, f, indent=2)

    print("\n" + "=" * 60)
    print(f"✓ Update complete - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

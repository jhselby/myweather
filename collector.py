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
PWS_CACHE_FILE  = Path("last_pws.json")
KBOS_CACHE_FILE = Path("last_kbos.json")   # Rolling observed pressure history
KBVY_CACHE_FILE  = Path("last_kbvy.json")   # Beverly Airport observations
BUOY_CACHE_FILE  = Path("last_buoy.json")   # Boston buoy 44013
FROST_LOG_FILE   = Path("frost_log.json")   # Persistent frost/freeze tracker

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
    # Upper-air variables for snow/rain discrimination and trough detection
    "temperature_850hPa", "temperature_700hPa", "geopotential_height_850hPa",
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


def fetch_asos_obs(station_id, cache_file):
    """
    Generic ASOS observation fetcher via NWS API.
    Returns current obs dict + rolling pressure tendency from cache.
    """
    print(f"\U0001f4e1 Fetching {station_id} observation...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    history = []
    if cache_file.exists():
        try:
            history = json.loads(cache_file.read_text()) or []
        except Exception:
            history = []

    try:
        url = f"https://api.weather.gov/stations/{station_id}/observations/latest"
        r = requests.get(url, headers=HEADERS_DEFAULT, timeout=20)
        r.raise_for_status()
        props = r.json().get("properties", {})

        obs_time     = props.get("timestamp", "")
        pressure_pa  = (props.get("seaLevelPressure") or {}).get("value")  # Pa (may be None)
        temp_c       = (props.get("temperature")      or {}).get("value")  # degC
        dewpoint_c   = (props.get("dewpoint")         or {}).get("value")  # degC
        wind_kmh     = (props.get("windSpeed")        or {}).get("value")  # km/h
        wind_dir     = (props.get("windDirection")    or {}).get("value")  # degrees

        pressure_hpa = round(pressure_pa / 100, 1) if pressure_pa is not None else None
        temp_f       = round(temp_c * 9/5 + 32, 1) if temp_c is not None else None
        dewpoint_f   = round(dewpoint_c * 9/5 + 32, 1) if dewpoint_c is not None else None
        wind_mph     = round(wind_kmh / 1.60934, 1) if wind_kmh is not None else None

        obs = {
            "station":      station_id,
            "time":         obs_time,
            "pressure_hpa": pressure_hpa,
            "temp_f":       temp_f,
            "dewpoint_f":   dewpoint_f,
            "wind_mph":     wind_mph,
            "wind_dir":     wind_dir,
        }

        history.append(obs)
        history = history[-6:]
        cache_file.write_text(json.dumps(history))

        tendency_hpa = None
        tendency_label = None
        first_p  = next((h["pressure_hpa"] for h in history if h.get("pressure_hpa") is not None), None)
        newest_p = obs["pressure_hpa"]
        if first_p is not None and newest_p is not None and len(history) >= 2:
            tendency_hpa = round(newest_p - first_p, 1)
            if tendency_hpa >= 3.0:       tendency_label = "Rising fast"
            elif tendency_hpa >= 0.6:     tendency_label = "Rising"
            elif tendency_hpa <= -3.0:    tendency_label = "Falling fast"
            elif tendency_hpa <= -0.6:    tendency_label = "Falling"
            else:                         tendency_label = "Steady"

        obs["tendency_hpa"]   = tendency_hpa
        obs["tendency_label"] = tendency_label

        meta["status"] = "ok"
        print(f"  \u2713 {station_id}: {pressure_hpa} hPa, {temp_f}\u00b0F, tendency={tendency_label}")
        return obs, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"  \u2717 {station_id} error: {e}")
        if history:
            last = dict(history[-1])
            last["stale"] = True
            return last, meta
        return {}, meta


def fetch_kbos_obs():
    return fetch_asos_obs("KBOS", KBOS_CACHE_FILE)


def fetch_kbvy_obs():
    return fetch_asos_obs("KBVY", KBVY_CACHE_FILE)


def fetch_buoy_44013():
    """
    Fetch latest observation from NOAA buoy 44013 (Boston, 16mi ENE).
    Fixed-width text format from NDBC realtime2 API.
    Key fields: wind, pressure, air temp, WATER TEMP, dewpoint, pressure tendency.
    MM = missing data (normal for calm conditions).
    """
    print("\U0001f4e1 Fetching buoy 44013...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    cached = {}
    if BUOY_CACHE_FILE.exists():
        try:
            cached = json.loads(BUOY_CACHE_FILE.read_text()) or {}
        except Exception:
            pass

    try:
        url = "https://www.ndbc.noaa.gov/data/realtime2/44013.txt"
        r = requests.get(url, headers=HEADERS_DEFAULT, timeout=20)
        r.raise_for_status()
        lines = r.text.strip().split("\n")

        # Parse header to get column positions
        headers = lines[0].lstrip("#").split()
        if len(lines) < 3:
            raise ValueError("Insufficient buoy data lines")

        vals = lines[2].split()
        def gv(col, default=None):
            """Get value by column name, return None if MM or missing."""
            try:
                idx = headers.index(col)
                v = vals[idx]
                return None if v == "MM" else float(v)
            except (ValueError, IndexError):
                return default

        wdir    = gv("WDIR")        # degrees true
        wspd_ms = gv("WSPD")        # m/s → convert
        gst_ms  = gv("GST")         # m/s → convert
        wvht    = gv("WVHT")        # meters significant wave height
        dpd     = gv("DPD")         # seconds dominant period
        pres    = gv("PRES")        # hPa
        atmp_c  = gv("ATMP")        # °C air temp
        wtmp_c  = gv("WTMP")        # °C WATER TEMP — key for us
        dewp_c  = gv("DEWP")        # °C dewpoint
        ptdy    = gv("PTDY")        # hPa pressure tendency (3h, pre-computed by NOAA)

        # Unit conversions
        wspd_mph  = round(wspd_ms * 2.237, 1) if wspd_ms is not None else None
        gst_mph   = round(gst_ms  * 2.237, 1) if gst_ms  is not None else None
        atmp_f    = round(atmp_c  * 9/5 + 32, 1) if atmp_c  is not None else None
        wtmp_f    = round(wtmp_c  * 9/5 + 32, 1) if wtmp_c  is not None else None
        dewp_f    = round(dewp_c  * 9/5 + 32, 1) if dewp_c  is not None else None
        wvht_ft   = round(wvht * 3.281, 1) if wvht is not None else None

        obs = {
            "time":       f"{int(vals[0])}-{vals[1]}-{vals[2]}T{vals[3]}:{vals[4]}Z",
            "wind_dir":   wdir,
            "wind_mph":   wspd_mph,
            "gust_mph":   gst_mph,
            "wave_ht_ft": wvht_ft,
            "wave_period_sec": dpd,
            "pressure_hpa": pres,
            "air_temp_f":   atmp_f,
            "water_temp_f": wtmp_f,
            "dewpoint_f":   dewp_f,
            "pressure_tend_hpa": ptdy,   # NOAA pre-computed 3h tendency
        }

        BUOY_CACHE_FILE.write_text(json.dumps(obs))
        meta["status"] = "ok"
        print(f"  \u2713 Buoy 44013: WTMP={wtmp_f}\u00b0F, ATMP={atmp_f}\u00b0F, "
              f"wind={wspd_mph}mph, PTDY={ptdy}")
        return obs, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"  \u2717 Buoy 44013 error: {e}")
        if cached:
            cached["stale"] = True
            return cached, meta
        return {}, meta


def update_frost_log(daily_data):
    """
    Maintain a persistent log of frost/freeze events based on daily min temps.
    Tracks: days below 32°F (freeze), days below 28°F (hard freeze), days below 20°F (severe).
    Stores season-to-date counts and last occurrence dates.
    Season = Oct 1 through current date.
    """
    try:
        log = {}
        if FROST_LOG_FILE.exists():
            try:
                log = json.loads(FROST_LOG_FILE.read_text()) or {}
            except Exception:
                log = {}

        daily = (daily_data or {}).get("daily", {}) or {}
        dates = daily.get("time", []) or []
        mins  = daily.get("temperature_2m_min", []) or []

        # Today's date
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        year      = datetime.now(timezone.utc).year
        # Season start: Oct 1 of current or previous year
        season_start = f"{year}-10-01" if today_str >= f"{year}-10-01" else f"{year-1}-10-01"

        # Initialize season record if new season
        if log.get("season_start") != season_start:
            log = {
                "season_start":    season_start,
                "freeze_days":     0,   # min ≤ 32°F
                "hard_freeze_days": 0,  # min ≤ 28°F
                "severe_days":     0,   # min ≤ 20°F
                "last_freeze":     None,
                "last_hard":       None,
                "last_severe":     None,
                "logged_dates":    [],
            }

        logged = set(log.get("logged_dates", []))

        # Process today's actual min (index 0 = today)
        # Only log past dates to avoid logging forecast lows
        for i, (d, t) in enumerate(zip(dates, mins)):
            if d >= today_str:
                continue   # skip today and future — forecast not actual
            if d < season_start:
                continue   # skip prior season
            if d in logged:
                continue   # already counted

            if t is not None:
                if t <= 20:
                    log["severe_days"]     += 1
                    log["hard_freeze_days"] += 1
                    log["freeze_days"]     += 1
                    log["last_severe"]     = d
                    log["last_hard"]       = d
                    log["last_freeze"]     = d
                elif t <= 28:
                    log["hard_freeze_days"] += 1
                    log["freeze_days"]     += 1
                    log["last_hard"]       = d
                    log["last_freeze"]     = d
                elif t <= 32:
                    log["freeze_days"]     += 1
                    log["last_freeze"]     = d
                logged.add(d)

        log["logged_dates"] = sorted(list(logged))[-60:]  # keep last 60 for memory

        # Add forecast freeze risk (next 10 days from daily forecast)
        upcoming_freeze = []
        for d, t in zip(dates, mins):
            if d < today_str: continue
            if t is not None and t <= 32:
                upcoming_freeze.append({"date": d, "min_f": round(t, 1)})
        log["upcoming_freeze_days"] = upcoming_freeze

        FROST_LOG_FILE.write_text(json.dumps(log, indent=2))
        print(f"  ✓ Frost log: {log['freeze_days']} freeze days this season, "
              f"last freeze: {log['last_freeze']}, "
              f"upcoming: {len(upcoming_freeze)}")
        return log

    except Exception as e:
        print(f"  ✗ Frost log error: {e}")
        return {}


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
def process_data(current_data, hourly_data, daily_data, pws, tides, kbos, kbvy, buoy, nws_forecast, alerts, source_meta, frost_log=None):
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
        "kbos":         kbos if kbos is not None else {},
        "kbvy":         kbvy if kbvy is not None else {},
        "buoy_44013":   buoy if buoy is not None else {},
        "frost_log":    frost_log if frost_log else {},
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
            "weather_code": sl("weather_code"),
            "temp_850hpa": sl("temperature_850hPa"),
            "temp_700hpa": sl("temperature_700hPa"),
            "height_850hpa": sl("geopotential_height_850hPa"),
        }

        daily = (daily_data or {}).get("daily", {}) or {}
        # --- Wet bulb temperature (Stull 2011 approximation) ---
        # Used to classify precipitation type more accurately than weather code
        def wet_bulb(t_f, rh_pct):
            """Wet bulb temp in °F from dry bulb (°F) and RH (%)."""
            if t_f is None or rh_pct is None:
                return None
            t = (t_f - 32) * 5/9   # to Celsius
            rh = float(rh_pct)
            import math
            tw = (t * math.atan(0.151977 * (rh + 8.313659) ** 0.5)
                  + math.atan(t + rh)
                  - math.atan(rh - 1.676331)
                  + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh)
                  - 4.686035)
            return round(tw * 9/5 + 32, 1)   # back to °F

        wb_temps = []
        for t, rh in zip(
            weather_data["hourly"].get("temperature", []),
            weather_data["hourly"].get("humidity", [])
        ):
            wb_temps.append(wet_bulb(t, rh))
        weather_data["hourly"]["wet_bulb"] = wb_temps

        # Current wet bulb
        cur_wb = wet_bulb(
            weather_data["current"].get("temperature"),
            weather_data["current"].get("humidity")
        )
        weather_data["current"]["wet_bulb"] = cur_wb

        # Precip type label based on wet bulb
        def precip_type_label(wb):
            if wb is None:
                return None
            if wb <= 28:
                return "Snow"
            elif wb <= 32:
                return "Snow likely"
            elif wb <= 35:
                return "Mixed/slush"
            elif wb <= 38:
                return "Freezing rain possible"
            else:
                return "Rain"

        weather_data["current"]["precip_type"] = precip_type_label(cur_wb)

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

        # Pressure trend (3h) + fog probability
        p    = weather_data["hourly"].get("pressure", [])
        temp = weather_data["hourly"].get("temperature", [])
        dew  = weather_data["hourly"].get("dew_point", [])
        rh   = weather_data["hourly"].get("humidity", [])
        ws   = weather_data["hourly"].get("wind_speed", [])

        derived = {}

        # --- Pressure tendency (3h change, mariner's rule: ≥3 hPa = significant) ---
        if isinstance(p, list) and len(p) >= 4 and all(x is not None for x in p[:4]):
            trend_3h = p[3] - p[0]   # h0 -> h3
            if trend_3h >= 3.0:
                label = "Rising fast"
            elif trend_3h >= 0.6:
                label = "Rising"
            elif trend_3h <= -3.0:
                label = "Falling fast"
            elif trend_3h <= -0.6:
                label = "Falling"
            else:
                label = "Steady"
            derived["pressure_trend"]       = label
            derived["pressure_trend_hpa_3h"] = round(trend_3h, 1)

        # --- Fog probability (next 12h) ---
        # Fog criteria: dewpoint depression ≤ 2°F AND RH ≥ 93% AND wind ≤ 10 mph
        fog_hours = 0
        fog_window = min(12, len(temp), len(dew), len(rh), len(ws))
        for i in range(fog_window):
            t  = temp[i] if temp[i] is not None else 999
            d  = dew[i]  if dew[i]  is not None else -999
            h  = rh[i]   if rh[i]   is not None else 0
            w  = ws[i]   if ws[i]   is not None else 999
            if (t - d) <= 2.0 and h >= 93 and w <= 10:
                fog_hours += 1

        if fog_window > 0:
            fog_pct = round(fog_hours / fog_window * 100)
            if fog_pct >= 75:
                fog_label = "Likely"
            elif fog_pct >= 40:
                fog_label = "Possible"
            elif fog_pct >= 15:
                fog_label = "Low chance"
            else:
                fog_label = "Unlikely"
            derived["fog_probability"]    = fog_pct
            derived["fog_label"]          = fog_label
            derived["fog_hours_in_12h"]   = fog_hours

        # --- 850mb upper-air analysis ---
        t850_arr = weather_data["hourly"].get("temp_850hpa", [])
        z850_arr = weather_data["hourly"].get("height_850hpa", [])
        cur_t850 = t850_arr[0] if t850_arr and t850_arr[0] is not None else None
        cur_wb   = weather_data["current"].get("wet_bulb")

        if cur_t850 is not None:
            # Snow/rain column classification
            if cur_t850 >= 32:
                col_label = "Rain"
                col_conf  = "High"
            elif cur_t850 >= 28:
                # Marginal — defer to wet bulb
                if cur_wb is not None and cur_wb <= 32:
                    col_label = "Snow likely"
                    col_conf  = "Moderate"
                else:
                    col_label = "Mixed"
                    col_conf  = "Low"
            elif cur_t850 >= 20:
                col_label = "Snow"
                col_conf  = "High"
            else:
                col_label = "Heavy snow"
                col_conf  = "High"
            derived["col_precip_type"]  = col_label
            derived["col_precip_conf"]  = col_conf
            derived["temp_850hpa_now"]  = round(cur_t850, 1)

        # Geopotential height tendency (trough approach indicator)
        # Drop of ≥30m in 6h is a fast-moving trough signal
        if len(z850_arr) >= 7 and all(z is not None for z in z850_arr[:7]):
            z_tend_6h = round(z850_arr[6] - z850_arr[0], 0)
            derived["height_850hpa_tend_6h"] = z_tend_6h
            if z_tend_6h <= -30:
                derived["trough_signal"] = "Approaching"
            elif z_tend_6h >= 30:
                derived["trough_signal"] = "Ridging"
            else:
                derived["trough_signal"] = "Steady"

        # --- Sea breeze / land breeze detector ---
        # Inputs: PWS air temp, buoy water temp, current wind, time of day
        import math as _math
        pws_t    = (weather_data.get("pws") or {}).get("temperature")   # °F
        buoy_wt  = (weather_data.get("buoy_44013") or {}).get("water_temp_f")  # °F
        cur_ws   = weather_data["current"].get("wind_speed")   # mph
        cur_wd   = weather_data["current"].get("wind_direction")  # degrees

        if pws_t is not None and buoy_wt is not None:
            land_sea_diff = pws_t - buoy_wt   # positive = land warmer = sea breeze potential

            # Hour of day in local time
            try:
                from zoneinfo import ZoneInfo as _ZI
                _now_hr = datetime.now(_ZI("America/New_York")).hour
            except Exception:
                _now_hr = datetime.utcnow().hour - 5

            is_daytime   = 9 <= _now_hr <= 19
            is_nighttime = _now_hr >= 21 or _now_hr <= 5
            light_wind   = cur_ws is not None and cur_ws < 12
            calm_wind    = cur_ws is not None and cur_ws < 6

            # Sea breeze: land significantly warmer, daytime, light winds
            # Onshore direction for your site is roughly 0-135° (N through SE)
            onshore = cur_wd is not None and (cur_wd <= 135 or cur_wd >= 315)

            if land_sea_diff >= 8 and is_daytime and calm_wind:
                sb_label = "Sea breeze likely"
                sb_conf  = "High"
            elif land_sea_diff >= 5 and is_daytime and light_wind:
                sb_label = "Sea breeze possible"
                sb_conf  = "Moderate"
            elif land_sea_diff >= 3 and is_daytime and light_wind and onshore:
                sb_label = "Sea breeze developing"
                sb_conf  = "Low"
            elif land_sea_diff <= -5 and is_nighttime and calm_wind:
                # Land breeze: land colder than water at night
                sb_label = "Land breeze"
                sb_conf  = "Moderate"
            else:
                sb_label = "No sea breeze"
                sb_conf  = None

            derived["sea_breeze_label"]    = sb_label
            derived["sea_breeze_conf"]     = sb_conf
            derived["land_sea_diff_f"]     = round(land_sea_diff, 1)
            derived["land_temp_f"]         = pws_t
            derived["water_temp_f"]        = buoy_wt

        # --- Pressure alarm ---
        # Use best available tendency: KBOS observed > model
        best_tend = None
        tend_src  = None
        kbos_tend = (weather_data.get("kbos") or {}).get("tendency_hpa")
        buoy_tend = (weather_data.get("buoy_44013") or {}).get("pressure_tend_hpa")
        model_tend = derived.get("pressure_trend_hpa_3h")

        # Prefer observed (KBOS or buoy) over model
        if kbos_tend is not None:
            best_tend = kbos_tend; tend_src = "KBOS"
        elif buoy_tend is not None:
            best_tend = buoy_tend; tend_src = "Buoy"
        elif model_tend is not None:
            best_tend = model_tend; tend_src = "model"

        if best_tend is not None:
            derived["best_pressure_tend"]     = round(best_tend, 1)
            derived["best_pressure_tend_src"] = tend_src
            if best_tend <= -3.0:
                derived["pressure_alarm"] = "falling"
                derived["pressure_alarm_label"] = f"⚠️ Pressure falling fast ({best_tend:+.1f} hPa, {tend_src})"
            elif best_tend >= 3.0:
                derived["pressure_alarm"] = "rising"
                derived["pressure_alarm_label"] = f"📈 Pressure rising fast ({best_tend:+.1f} hPa, {tend_src})"
            else:
                derived["pressure_alarm"] = None
                derived["pressure_alarm_label"] = None

        if derived:
            weather_data["derived"] = {**weather_data.get("derived", {}), **derived}

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
    kbos_data,     kbos_meta     = fetch_kbos_obs()
    kbvy_data,     kbvy_meta     = fetch_kbvy_obs()
    buoy_data,     buoy_meta     = fetch_buoy_44013()
    forecast_data, forecast_meta = fetch_nws_forecast()
    alert_data,    alerts_meta   = fetch_nws_alerts()

    sources = {
        "gfs_current":  current_meta,
        "hrrr_hourly":  hourly_meta,
        "ecmwf_daily":  daily_meta,
        "pws":          pws_meta,
        "tides":        tides_meta,
        "kbos":         kbos_meta,
        "kbvy":         kbvy_meta,
        "buoy_44013":   buoy_meta,
        "nws_forecast": forecast_meta,
        "nws_alerts":   alerts_meta,
    }

    print("\U0001f321 Updating frost log...")
    frost_log = update_frost_log(daily_data)

    weather_data = process_data(
        current_data, hourly_data, daily_data,
        pws_data, tide_data, kbos_data, kbvy_data, buoy_data, forecast_data, alert_data, sources,
        frost_log=frost_log
    )

    # Save to JSON
    with open("weather_data.json", "w") as f:
        json.dump(weather_data, f, indent=2)

    print("\n" + "=" * 60)
    print(f"✓ Update complete - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

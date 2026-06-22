"""
Fetch hyper-local observations from WeatherFlow Tempest stations near Wyman Cove.
Public station data accessed via the tempestwx.com web API (JSONP endpoint).
API returns SI units: temp in °C, wind in m/s, precip in mm.
"""
import json
import math
import re
import time

import requests

from ..config import LAT, LON
from ..utils import iso_utc_now
import logging

# Public Tempest stations within ~2.5mi of Wyman Cove (expanded from 1.5mi
# on 2026-06-02 alongside the WU sweep). Geo-balanced aggregation in
# hyperlocal.py / wind_blend.py prevents over-representation from any one
# direction. waterfront=True: on the harbor shoreline, most representative
# for wind direction.
TEMPEST_STATIONS = [
    # Original 1.5mi set
    {"id": 204883, "name": "Willow Rd",    "waterfront": True},
    {"id": 192019, "name": "Neptune Rd",   "waterfront": True},
    {"id": 193183, "name": "Baldwin Rd",   "waterfront": False},
    {"id": 193746, "name": "Maple St",     "waterfront": False},
    {"id": 168702, "name": "Forest Ave",   "waterfront": False},
    {"id": 135494, "name": "Lincoln Ave",  "waterfront": False},
    {"id": 192607, "name": "Willard Ln",   "waterfront": False},
    {"id": 86357,  "name": "ColleeninMHD", "waterfront": False},
    # Added 2026-06-02: 1.5–2.5mi expansion (16 new)
    {"id": 130945, "name": "Gallison Ave",                   "waterfront": False},
    {"id": 142949, "name": "Coolidge Rd",                    "waterfront": False},
    {"id": 164230, "name": "Russell St",                     "waterfront": False},
    {"id": 141896, "name": "Front St",                       "waterfront": False},
    {"id": 85616,  "name": "Orleans",                        "waterfront": False},
    {"id": 211335, "name": "Manton Rd",                      "waterfront": False},
    {"id": 178102, "name": "Broad St",                       "waterfront": False},
    {"id": 109319, "name": "South Essex Sewerage District",  "waterfront": False},
    {"id": 92837,  "name": "Harbor Ave",                     "waterfront": False},
    {"id": 165151, "name": "Ocean ave MHD",                  "waterfront": False},
    {"id": 170101, "name": "Marblehead Neck",                "waterfront": False},
]

# Culled 2026-06-04 (v0.6.40 session) — these stations return a partial obs
# record through the public API: only lightning + precip fields, with temp /
# wind / humidity blanked. Confirmed via direct API probe — the stations ARE
# online and show full data on tempestwx.com, but the owners have restricted
# field-level sharing for the developer API. Useless for our mesonet bias
# correction (which requires temp + wind). If we ever want to enhance the
# lightning or rainfall cards with more local sources, re-introduce these
# under a separate code path that tolerates partial records.
CULLED_TEMPEST_STATIONS = [
    {"id": 28679,  "name": "Broadmere Way"},
    {"id": 51384,  "name": "Memorial Dr"},
    {"id": 72262,  "name": "Spray Ave"},
    {"id": 85260,  "name": "Driftwood Rd"},
    {"id": 100037, "name": "Bass Rock Ln"},
    {"id": 159204, "name": "Marblehead"},
    # Culled 2026-06-22 — 7-day uptime 5.7% (57/1008 successes). Either offline
    # or has the same field-level sharing restriction as the 06-04 batch.
    {"id": 85569,  "name": "Preston Ct"},
]

_API_KEY  = "6bff2f89-84ab-463c-886e-fc0f443da4cf"
_BASE_URL = "https://swd.weatherflow.com/swd/rest/observations/station/{sid}"
_HEADERS  = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer":    "https://tempestwx.com/",
    "Origin":     "https://tempestwx.com",
}


def _c_to_f(c):
    return round(c * 9 / 5 + 32, 1) if c is not None else None


def _ms_to_mph(ms):
    return round(ms * 2.23694, 1) if ms is not None else None


def _mm_to_in(mm):
    return round(mm / 25.4, 3) if mm is not None else None


def _haversine_mi(lat1, lon1, lat2, lon2):
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _fetch_station(sid):
    url = _BASE_URL.format(sid=sid)
    r = requests.get(url, params={"callback": "cb", "api_key": _API_KEY},
                     headers=_HEADERS, timeout=10)
    r.raise_for_status()
    m = re.match(r"cb\((.*)\)$", r.text.strip(), re.DOTALL)
    if not m:
        raise ValueError(f"unexpected response format for station {sid}")
    return json.loads(m.group(1))


def fetch_tempest():
    """
    Fetch observations from up to 3 public Tempest stations near Wyman Cove.
    Returns (data, meta). data has 'best' (closest valid station) and 'stations' (all).
    """
    logging.info("📡 Fetching Tempest stations...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}
    now_epoch = time.time()
    results = []
    errors = []

    for station in TEMPEST_STATIONS:
        sid = station["id"]
        try:
            raw = _fetch_station(sid)
            if raw.get("status", {}).get("status_code") != 0:
                errors.append(f"{sid}: {raw.get('status', {}).get('status_message')}")
                continue

            obs = (raw.get("obs") or [{}])[0]
            slat = raw.get("latitude")
            slon = raw.get("longitude")
            dist = _haversine_mi(LAT, LON, slat, slon) if slat and slon else None
            ts = obs.get("timestamp")
            age_min = round((now_epoch - ts) / 60, 1) if ts else None

            temp_c  = obs.get("air_temperature")
            wind_ms = obs.get("wind_avg")
            valid   = temp_c is not None and wind_ms is not None

            entry = {
                "station_id":   sid,
                "station_name": raw.get("station_name", station["name"]),
                "waterfront":   station.get("waterfront", False),
                "latitude":     slat,
                "longitude":    slon,
                "elevation_ft": raw.get("elevation"),
                "distance_mi":  round(dist, 2) if dist is not None else None,
                "valid":        valid,
                "age_minutes":  age_min,
                "timestamp":    ts,
                # Converted observations
                "temperature_f":              _c_to_f(temp_c),
                "dew_point_f":                _c_to_f(obs.get("dew_point")),
                "feels_like_f":               _c_to_f(obs.get("feels_like")),
                "wet_bulb_temperature_f":     _c_to_f(obs.get("wet_bulb_temperature")),
                "wind_avg_mph":               _ms_to_mph(wind_ms),
                "wind_gust_mph":              _ms_to_mph(obs.get("wind_gust")),
                "wind_lull_mph":              _ms_to_mph(obs.get("wind_lull")),
                "wind_direction":             obs.get("wind_direction"),
                "relative_humidity":          obs.get("relative_humidity"),
                "sea_level_pressure_mb":      obs.get("sea_level_pressure"),
                "solar_radiation_wm2":        obs.get("solar_radiation"),
                "uv_index":                   obs.get("uv"),
                "brightness_lux":             obs.get("brightness"),
                "precip_rate_in":             _mm_to_in(obs.get("precip")),
                "precip_accum_1hr_in":        _mm_to_in(obs.get("precip_accum_last_1hr")),
                "precip_accum_today_in":      _mm_to_in(obs.get("precip_accum_local_day_final")
                                                         or obs.get("precip_accum_local_day")),
                "lightning_count_1hr":        obs.get("lightning_strike_count_last_1hr"),
                "lightning_count_3hr":        obs.get("lightning_strike_count_last_3hr"),
                "lightning_last_distance_km": obs.get("lightning_strike_last_distance"),
                "lightning_last_epoch":       obs.get("lightning_strike_last_epoch"),
            }
            results.append(entry)
            status = f"{entry['temperature_f']}°F wind {entry['wind_avg_mph']}mph" if valid else "no temp/wind"
            logging.info(f"  ✓ Tempest {sid} ({station['name']}): {status}")

        except Exception as e:
            errors.append(f"{sid}: {e}")
            logging.error(f"  ✗ Tempest {sid}: {e}")

    if not results:
        meta["error"] = "; ".join(errors) if errors else "no data"
        return None, meta

    # Best = valid station closest to Wyman Cove; fall back to any closest
    results.sort(key=lambda s: (not s["valid"], s["distance_mi"] or 999))

    meta["status"] = "ok"
    meta["stations_fetched"] = len(results)
    meta["best_station"] = results[0]["station_name"]

    return {"best": results[0], "stations": results}, meta

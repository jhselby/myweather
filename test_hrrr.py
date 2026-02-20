#!/usr/bin/env python3
"""
test_hrrr.py — Test correct Open-Meteo model string identifiers.
Run: python3 test_hrrr.py
"""
import requests

LAT, LON = 42.5014, -70.8750
BASE = "https://api.open-meteo.com/v1/forecast"
UNITS = {
    "temperature_unit": "fahrenheit",
    "wind_speed_unit": "mph",
    "precipitation_unit": "inch",
    "timezone": "America/New_York",
}
HOURLY = "temperature_2m,wind_speed_10m,wind_gusts_10m,wind_direction_10m"

def try_model(label, model_str):
    params = {
        "latitude": LAT, "longitude": LON,
        "hourly": HOURLY,
        **UNITS,
    }
    if model_str:
        params["models"] = model_str
    try:
        r = requests.get(BASE, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if "error" in data:
                print(f"  FAIL [{label}] API error: {data.get('reason', data['error'])}")
            else:
                h = data.get("hourly", {})
                slots = len(h.get("time", []))
                temp0 = h.get("temperature_2m", [None])[0]
                model_used = data.get("model", "not reported")
                print(f"  OK   [{label}] {slots} slots, {temp0}°F, model={model_used}")
        else:
            try:
                err = r.json().get("reason", r.text[:80])
            except:
                err = r.text[:80]
            print(f"  FAIL [{label}] HTTP {r.status_code}: {err}")
    except Exception as e:
        print(f"  ERR  [{label}] {e}")

print("\nTesting Open-Meteo model string identifiers...\n")

# No model param — default (GFS)
try_model("default/GFS (no models param)", None)

# Known working alternatives
for name, string in [
    ("best_match",              "best_match"),
    ("ncep_hrrr_conus",         "ncep_hrrr_conus"),
    ("hrrr_conus",              "hrrr_conus"),
    ("gfs_seamless",            "gfs_seamless"),
    ("gfs_global",              "gfs_global"),
    ("ecmwf_ifs025",            "ecmwf_ifs025"),
    ("ecmwf_ifs04",             "ecmwf_ifs04"),
    ("ecmwf_aifs025",           "ecmwf_aifs025"),
]:
    try_model(name, string)

print("\nDone.")

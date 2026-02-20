#!/usr/bin/env python3
"""
test_collector.py — Runs the three new model fetchers and shows
what would end up in weather_data.json without writing anything.
Run: python3 test_collector.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# Import the three new fetchers directly from collector
from collector import fetch_current_gfs, fetch_hourly_hrrr, fetch_daily_ecmwf

def show(label, data, meta):
    print(f"\n{'='*55}")
    print(f"  {label}")
    print(f"  Status : {meta.get('status')}  |  Model: {meta.get('model')}")
    if meta.get('error'):
        print(f"  Error  : {meta['error']}")
    if data is None:
        print("  No data returned")
        return
    cur = data.get("current", {})
    if cur:
        print(f"  Temp   : {cur.get('temperature_2m')}°F  "
              f"Feels: {cur.get('apparent_temperature')}°F")
        print(f"  Wind   : {cur.get('wind_speed_10m')} mph "
              f"from {cur.get('wind_direction_10m')}°  "
              f"Gusts: {cur.get('wind_gusts_10m')} mph")
    h = data.get("hourly", {})
    if h:
        times = h.get("time", [])
        temps = h.get("temperature_2m", [])
        gusts = h.get("wind_gusts_10m", [])
        print(f"  Hourly : {len(times)} slots")
        for i in range(min(4, len(times))):
            print(f"    {times[i]}  {temps[i]}°F  gust {gusts[i]} mph")
    d = data.get("daily", {})
    if d:
        dates = d.get("time", [])
        hi    = d.get("temperature_2m_max", [])
        lo    = d.get("temperature_2m_min", [])
        print(f"  Daily  : {len(dates)} days")
        for i in range(min(5, len(dates))):
            print(f"    {dates[i]}  Hi {hi[i]}°F / Lo {lo[i]}°F")

print("\nWyman Cove — collector fetch test")
print("Testing all three model fetchers...\n")

cur_data,  cur_meta  = fetch_current_gfs()
hrr_data,  hrr_meta  = fetch_hourly_hrrr()
ecm_data,  ecm_meta  = fetch_daily_ecmwf()

show("GFS — current conditions", cur_data, cur_meta)
show("HRRR — 48h hourly",        hrr_data, hrr_meta)
show("ECMWF — 10-day daily",     ecm_data, ecm_meta)

print(f"\n{'='*55}")
all_ok = all(m.get('status') == 'ok' for m in [cur_meta, hrr_meta, ecm_meta])
print(f"  {'✓ All three sources OK — safe to deploy' if all_ok else '⚠  One or more sources failed — check above'}")

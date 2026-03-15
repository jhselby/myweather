#!/usr/bin/env python3
"""
Test the new modular collector
"""

import sys
import os

# Make sure we can import the weather_collector package
sys.path.insert(0, os.path.dirname(__file__))

print("Testing imports...")

try:
    from weather_collector.config import LAT, LON, LOCATION_NAME
    print(f"✓ Config imported: {LOCATION_NAME} ({LAT}, {LON})")
except Exception as e:
    print(f"✗ Config import failed: {e}")
    sys.exit(1)

try:
    from weather_collector.utils import iso_utc_now
    print(f"✓ Utils imported: {iso_utc_now()}")
except Exception as e:
    print(f"✗ Utils import failed: {e}")
    sys.exit(1)

try:
    from weather_collector.fetchers.open_meteo import fetch_current_gfs
    print("✓ Fetchers imported")
except Exception as e:
    print(f"✗ Fetchers import failed: {e}")
    sys.exit(1)

try:
    from weather_collector.processors.frost import update_frost_log
    print("✓ Processors imported")
except Exception as e:
    print(f"✗ Processors import failed: {e}")
    sys.exit(1)

try:
    from weather_collector.collector import main
    print("✓ Main collector imported")
except Exception as e:
    print(f"✗ Main collector import failed: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("All imports successful! Ready to run collector.")
print("="*60 + "\n")

# Now run it
print("Running new modular collector...\n")
main()
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

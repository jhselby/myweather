"""
Fetch Salem Harbor water temperature.
Primary: GoMOFS model (NOAA Gulf of Maine OFS) at ny=392, nx=101 (42.50N, -70.88W)
Fallback: NOAA buoy 44013 scraped from NDBC
"""
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

from ..config import HEADERS_DEFAULT
from ..utils import safe_float


GOMOFS_NY = 392
GOMOFS_NX = 101
GOMOFS_BASE = "https://opendap.co-ops.nos.noaa.gov/thredds/dodsC/NOAA/GOMOFS/MODELS"


def _redact_secrets(value):
    s = str(value)
    s = re.sub(r'([?&]key=)[^&\s]+', r'\1REDACTED', s)
    s = re.sub(r'(AIza[0-9A-Za-z\-_]{20,})', 'REDACTED', s)
    s = re.sub(r"((?:x-goog-api-key|api[_-]?key)[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+", r"\1REDACTED", s, flags=re.IGNORECASE)
    return s


def _candidate_urls(dt=None):
    if dt is None:
        dt = datetime.now(timezone.utc)
    cycle_hours = [18, 12, 6, 0]
    forecast_offsets = ["n000", "n003", "n006", "n009", "n012"]
    candidates = []
    for day_offset in range(2):
        check_dt = dt - timedelta(days=day_offset)
        yyyy = check_dt.strftime("%Y")
        mm = check_dt.strftime("%m")
        dd = check_dt.strftime("%d")
        date_str = check_dt.strftime("%Y%m%d")
        for ch in cycle_hours:
            cycle_time = check_dt.replace(hour=ch, minute=0, second=0, microsecond=0)
            if dt >= cycle_time + timedelta(hours=2):
                for fh in forecast_offsets:
                    filename = f"gomofs.t{ch:02d}z.{date_str}.regulargrid.{fh}.nc"
                    url = f"{GOMOFS_BASE}/{yyyy}/{mm}/{dd}/{filename}.ascii"
                    candidates.append(url)
    return candidates


def _parse_gomofs_temp(raw):
    for line in reversed(raw.strip().split('\n')):
        line = line.strip()
        if line and ',' in line and '[' in line:
            val_str = line.split(',')[-1].strip()
            try:
                val = float(val_str)
                if val > -9999:
                    return val
            except ValueError:
                pass
    return None


def _fetch_gomofs_temp():
    ny, nx = GOMOFS_NY, GOMOFS_NX
    query = f"?temp%5B0%5D%5B0%5D%5B{ny}%5D%5B{nx}%5D"
    for base_url in _candidate_urls():
        full_url = base_url + query
        fname = base_url.split('/')[-1]
        try:
            r = requests.get(full_url, headers=HEADERS_DEFAULT, timeout=30)
            if r.status_code == 404:
                print(f"  - GoMOFS {fname}: 404, skipping")
                continue
            r.raise_for_status()
            temp_c = _parse_gomofs_temp(r.text)
            if temp_c is not None:
                temp_f = round(temp_c * 9 / 5 + 32, 1)
                print(f"  ✓ GoMOFS water temp: {temp_f}°F ({temp_c:.2f}°C) [{fname}]")
                return temp_f
        except Exception as e:
            print(f"  ✗ GoMOFS {fname}: {_redact_secrets(e)}")
            continue
    print("  ✗ GoMOFS: all candidates failed")
    return None


def _fetch_buoy_temp():
    url = "https://www.ndbc.noaa.gov/station_page.php?station=44013"
    try:
        r = requests.get(url, headers=HEADERS_DEFAULT, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2 and "Water Temperature" in cells[0].get_text():
                raw = cells[1].get_text(strip=True)
                if "°F" in raw:
                    val_str = raw.split("°F")[0].strip()
                    temp_f = safe_float(val_str)
                    if temp_f is not None:
                        print(f"  ✓ Buoy 44013 water temp (fallback): {temp_f}°F")
                        return temp_f
        print("  ✗ Buoy 44013: water temp not found in page")
        return None
    except Exception as e:
        print(f"  ✗ Buoy 44013: {_redact_secrets(e)}")
        return None


def fetch_salem_water_temp():
    print("📡 Fetching Salem water temperature...")
    temp = _fetch_gomofs_temp()
    if temp is not None:
        return temp
    print("  ↩ Falling back to buoy 44013...")
    return _fetch_buoy_temp()

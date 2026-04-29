"""
Fetch current conditions from Weather Underground Personal Weather Station
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

from ..config import PWS_STATION, PWS_CACHE_FILE
from ..utils import iso_utc_now, safe_float, load_json, save_json



def _redact_secrets(value):
    s = str(value)
    s = re.sub(r'([?&]key=)[^&\s]+', r'\1REDACTED', s)
    s = re.sub(r'(AIza[0-9A-Za-z\-_]{20,})', 'REDACTED', s)
    s = re.sub(r"((?:x-goog-api-key|api[_-]?key)[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+", r"\1REDACTED", s, flags=re.IGNORECASE)
    return s

def fetch_pws_current():
    """
    Scrape current conditions from Weather Underground PWS.
    Falls back to cached value if scrape fails.
    """
    print("📡 Fetching Castle Hill PWS...")

    url = f"https://www.wunderground.com/weather/us/ma/marblehead/{PWS_STATION}"
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    cache_path = PWS_CACHE_FILE
    last = load_json(cache_path)

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
            "updated": datetime.now().isoformat(),
            "temperature": None,
            "stale": False
        }

        temp_elem = soup.find("span", class_="wu-value wu-value-to")
        if temp_elem:
            pws_data["temperature"] = safe_float(temp_elem.text.strip())

        if pws_data["temperature"] is None:
            raise RuntimeError("Could not parse PWS temperature (WU DOM likely changed).")

        save_json(cache_path, pws_data)

        meta["status"] = "ok"
        print(f"✓ PWS: {pws_data['temperature']}°F")
        return pws_data, meta

    except Exception as e:
        meta["error"] = _redact_secrets(e)
        print(f"✗ PWS error: {_redact_secrets(e)}")

        if last and isinstance(last, dict) and last.get("temperature") is not None:
            last_copy = dict(last)
            last_copy["stale"] = True
            return last_copy, meta

        return {
            "station": PWS_STATION, 
            "name": "Castle Hill", 
            "updated": None, 
            "temperature": None, 
            "stale": True
        }, meta
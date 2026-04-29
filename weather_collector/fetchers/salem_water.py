"""
Fetch Salem Harbor water temperature from NOAA buoy data
"""
import requests
from bs4 import BeautifulSoup

from ..config import HEADERS_DEFAULT
from ..utils import safe_float



def _redact_secrets(value):
    s = str(value)
    s = re.sub(r'([?&]key=)[^&\s]+', r'\1REDACTED', s)
    s = re.sub(r'(AIza[0-9A-Za-z\-_]{20,})', 'REDACTED', s)
    s = re.sub(r'((?:x-goog-api-key|api[_-]?key)['"]?\s*[:=]\s*['"]?)[^'"\s,}]+', r'\1REDACTED', s, flags=re.IGNORECASE)
    return s

def fetch_salem_water_temp():
    """
    Scrape Salem water temperature from NOAA buoy 44013.
    Returns: float (°F) or None on failure
    """
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
                        print(f"  ✓ Salem water temp: {temp_f}°F")
                        return temp_f
        
        print("  ✗ Salem water temp: not found in page")
        return None
        
    except Exception as e:
        print(f"  ✗ Salem water temp: {_redact_secrets(e)}")
        return None
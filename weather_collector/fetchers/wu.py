"""
Fetch Weather Underground multi-station data
"""
import subprocess
import json

from ..utils import iso_utc_now


def fetch_wu_stations():
    """
    Run wu_scraper_realtime.py to fetch multi-station WU data.
    This is optional and fails gracefully if the scraper is unavailable.
    """
    print("📡 Fetching WU stations (optional)...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}

    try:
        result = subprocess.run(
            ["python3", "wu_scraper_realtime.py"],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            raise RuntimeError(f"Scraper failed: {result.stderr}")

        # Load the output file
        with open("wu_stations_realtime.json", "r") as f:
            wu_data = json.load(f)

        meta["status"] = "ok"
        stations_count = wu_data.get("quality", {}).get("stations_used_temp", 0)
        print(f"  ✓ WU stations: {stations_count} stations")
        return wu_data, meta

    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ WU stations (optional): {e}")
        return None, meta
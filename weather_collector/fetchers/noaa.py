"""
Fetch NOAA observations (KBOS, KBVY, Buoy 44013)
"""
import requests
from ..utils import iso_utc_now

def decode_metar_wx(wx_string):
    """Convert METAR weather codes to human-readable text."""
    if not wx_string:
        return None
    
    # Common METAR weather codes
    codes = {
        "-RA": "Light Rain",
        "RA": "Rain",
        "+RA": "Heavy Rain",
        "-SN": "Light Snow",
        "SN": "Snow",
        "+SN": "Heavy Snow",
        "-RASN": "Light Rain/Snow Mix",
        "RASN": "Rain/Snow Mix",
        "-DZ": "Light Drizzle",
        "DZ": "Drizzle",
        "FG": "Fog",
        "BR": "Mist",
        "HZ": "Haze",
        "FU": "Smoke",
        "FZRA": "Freezing Rain",
        "-FZRA": "Light Freezing Rain",
        "TSRA": "Thunderstorm",
        "-TSRA": "Light Thunderstorm",
        "+TSRA": "Heavy Thunderstorm",
    }
    
    # Split on spaces and decode each part
    parts = wx_string.strip().split()
    decoded = []
    for part in parts:
        decoded.append(codes.get(part, part))
    
    return ", ".join(decoded) if decoded else wx_string

def fetch_kbos_obs():
    """Fetch KBOS METAR from Aviation Weather new API."""
    print("📡 Fetching KBOS obs...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}
    
    try:
        url = "https://aviationweather.gov/api/data/metar"
        r = requests.get(url, params={"ids": "KBOS", "format": "json"}, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        if not data or len(data) == 0:
            raise ValueError("No data returned")
        
        obs = data[0]
        temp_c = obs.get("temp")
        
        result = {
            "station": obs.get("icaoId"),
            "temp_f": round(temp_c * 9/5 + 32, 1) if temp_c is not None else None,
            "dewpoint_c": obs.get("dewp"),
            "pressure_hpa": obs.get("altim"),
            "pressure_tend_hpa": obs.get("presTend"),
            "wind_speed_kt": obs.get("wspd"),
            "wind_dir": obs.get("wdir"),
            "present_weather": decode_metar_wx(obs.get("wxString"))
        }
        
        meta["status"] = "ok"
        print(f"  ✓ KBOS: {result.get('temp_f')}°F, {result.get('pressure_hpa')} hPa")
        return result, meta
        
    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ KBOS: {e}")
        return None, meta


def fetch_kbvy_obs():
    """Fetch KBVY METAR from Aviation Weather new API."""
    print("📡 Fetching KBVY obs...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}
    
    try:
        url = "https://aviationweather.gov/api/data/metar"
        r = requests.get(url, params={"ids": "KBVY", "format": "json"}, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        if not data or len(data) == 0:
            raise ValueError("No data returned")
        
        obs = data[0]
        temp_c = obs.get("temp")
        
        result = {
            "station": obs.get("icaoId"),
            "temp_f": round(temp_c * 9/5 + 32, 1) if temp_c is not None else None,
            "dewpoint_c": obs.get("dewp"),
            "pressure_hpa": obs.get("altim"),
            "wind_speed_kt": obs.get("wspd"),
            "wind_dir": obs.get("wdir"),
            "present_weather": decode_metar_wx(obs.get("wxString")),
        }
        
        meta["status"] = "ok"
        print(f"  ✓ KBVY: {result.get('temp_f')}°F")
        return result, meta
        
    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ KBVY: {e}")
        return None, meta


def fetch_buoy_44013():
    """Fetch Buoy 44013 latest observation from NDBC real-time text data."""
    print("📡 Fetching Buoy 44013...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}
    
    try:
        url = "https://www.ndbc.noaa.gov/data/realtime2/44013.txt"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        
        lines = r.text.strip().split('\n')
        if len(lines) < 3:
            raise ValueError("Insufficient data in response")
        
        # Line 0: headers, Line 1: units, Line 2: latest data
        headers = lines[0].split()
        data = lines[2].split()
        
        # Create dict mapping header -> value
        obs = dict(zip(headers, data))
        
        # Helper to convert value, return None if MM (missing)
        def to_float(val):
            return float(val) if val and val != 'MM' else None
        
        # Extract and convert values
        wind_dir = to_float(obs.get('WDIR'))
        wind_speed_ms = to_float(obs.get('WSPD'))  # m/s
        gust_ms = to_float(obs.get('GST'))  # m/s
        wave_ht_m = to_float(obs.get('WVHT'))  # meters
        wave_period = to_float(obs.get('DPD'))  # dominant wave period, sec
        pressure_hpa = to_float(obs.get('PRES'))
        air_temp_c = to_float(obs.get('ATMP'))
        water_temp_c = to_float(obs.get('WTMP'))
        dewpoint_c = to_float(obs.get('DEWP'))
        pressure_tend = to_float(obs.get('PTDY'))
        
        # Get timestamp from data
        yr, mo, dy, hr, mn = obs.get('#YY'), obs.get('MM'), obs.get('DD'), obs.get('hh'), obs.get('mm')
        time_str = f"{yr}-{mo.zfill(2)}-{dy.zfill(2)}T{hr.zfill(2)}:{mn.zfill(2)}Z"
        
        result = {
            "time": time_str,
            "wind_dir": wind_dir,
            "wind_mph": round(wind_speed_ms * 2.23694, 1) if wind_speed_ms else None,
            "gust_mph": round(gust_ms * 2.23694, 1) if gust_ms else None,
            "wave_ht_ft": round(wave_ht_m * 3.28084, 1) if wave_ht_m else None,
            "wave_period_sec": wave_period,
            "pressure_hpa": pressure_hpa,
            "air_temp_f": round(air_temp_c * 9/5 + 32, 1) if air_temp_c else None,
            "water_temp_f": round(water_temp_c * 9/5 + 32, 1) if water_temp_c else None,
            "dewpoint_f": round(dewpoint_c * 9/5 + 32, 1) if dewpoint_c else None,
            "pressure_tend_hpa": pressure_tend
        }
        
        meta["status"] = "ok"
        print(f"  ✓ Buoy: {result.get('air_temp_f')}°F air, {result.get('water_temp_f')}°F water, {result.get('wave_ht_ft')} ft waves")
        return result, meta
        
    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ Buoy: {e}")
        return None, meta

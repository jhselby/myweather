"""
Fetch NOAA observations (KBOS, KBVY, Buoy 44013+44098)
"""
import requests
from ..utils import iso_utc_now, redact_secrets
import logging



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

# METAR sky-condition codes → percent cloud cover (NWS standard mapping)
_METAR_COVER_PCT = {
    "SKC": 0,  "NCD": 0,  "CLR": 0,  "NSC": 0,
    "FEW": 12,
    "SCT": 38,
    "BKN": 75,
    "OVC": 100,
    "VV":  100,  # vertical visibility (indefinite ceiling, fog/heavy precip)
}


def _metar_cloud_cover_pct(clouds):
    """Total sky cover from a METAR clouds[] array.

    The Aviation Weather API returns clouds as a list of {cover, base} layers.
    NWS convention: total sky cover = maximum coverage across all reported
    layers (a single OVC layer at 5000ft means 100% sky cover even if lower
    layers are FEW). Returns 0 when clouds is missing/empty (CLR).
    """
    if not clouds or not isinstance(clouds, list):
        return 0
    best = 0
    for layer in clouds:
        if not isinstance(layer, dict):
            continue
        pct = _METAR_COVER_PCT.get((layer.get("cover") or "").upper())
        if pct is not None and pct > best:
            best = pct
    return best


def _metar_cloud_splits_pct(clouds):
    """Per-altitude cloud cover from a METAR clouds[] array.

    Uses FAA altitude bands: low < 6500ft, mid 6500–20000ft, high > 20000ft.
    For each band, returns the MAX coverage across all layers in that band
    (same NWS total-sky-cover convention applied within each band).
    Returns (low_pct, mid_pct, high_pct), each 0–100 or None if no info.
    """
    if not clouds or not isinstance(clouds, list):
        return 0, 0, 0
    low = mid = high = 0
    for layer in clouds:
        if not isinstance(layer, dict):
            continue
        pct = _METAR_COVER_PCT.get((layer.get("cover") or "").upper())
        if pct is None:
            continue
        base = layer.get("base")
        if base is None:
            # No altitude info (e.g., VV "vertical visibility" — surface fog).
            # Treat as low cloud since that's the user-impact band.
            if pct > low: low = pct
            continue
        try:
            base_ft = float(base)
        except (TypeError, ValueError):
            continue
        if base_ft < 6500:
            if pct > low: low = pct
        elif base_ft < 20000:
            if pct > mid: mid = pct
        else:
            if pct > high: high = pct
    return low, mid, high


def fetch_kbos_obs():
    """Fetch KBOS METAR from Aviation Weather new API."""
    logging.info("📡 Fetching KBOS obs...")
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
        
        cloud_low, cloud_mid, cloud_high = _metar_cloud_splits_pct(obs.get("clouds"))
        result = {
            "station": obs.get("icaoId"),
            "temp_f": round(temp_c * 9/5 + 32, 1) if temp_c is not None else None,
            "dewpoint_c": obs.get("dewp"),
            "pressure_hpa": obs.get("altim"),
            "pressure_tend_hpa": obs.get("presTend"),
            "wind_speed_kt": obs.get("wspd"),
            "wind_gust_kt": obs.get("wgst"),
            "wind_dir": obs.get("wdir"),
            "present_weather": decode_metar_wx(obs.get("wxString")),
            "cloud_cover_pct": _metar_cloud_cover_pct(obs.get("clouds")),
            "cloud_low_pct":  cloud_low,
            "cloud_mid_pct":  cloud_mid,
            "cloud_high_pct": cloud_high,
        }

        meta["status"] = "ok"
        logging.info(f"  ✓ KBOS: {result.get('temp_f')}°F, {result.get('pressure_hpa')} hPa, cloud {result.get('cloud_cover_pct')}% (L{cloud_low}/M{cloud_mid}/H{cloud_high})")
        return result, meta
        
    except Exception as e:
        meta["error"] = redact_secrets(e)
        logging.error(f"  ✗ KBOS: {redact_secrets(e)}")
        return None, meta


def fetch_kbvy_obs():
    """Fetch KBVY METAR from Aviation Weather new API."""
    logging.info("📡 Fetching KBVY obs...")
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
            "wind_gust_kt": obs.get("wgst"),
            "wind_dir": obs.get("wdir"),
            "present_weather": decode_metar_wx(obs.get("wxString")),
        }
        
        meta["status"] = "ok"
        logging.info(f"  ✓ KBVY: {result.get('temp_f')}°F")
        return result, meta
        
    except Exception as e:
        meta["error"] = redact_secrets(e)
        logging.error(f"  ✗ KBVY: {redact_secrets(e)}")
        return None, meta


def _fetch_single_buoy(buoy_id):
    """Fetch a single buoy's latest observation from NDBC real-time text data."""
    try:
        url = f"https://www.ndbc.noaa.gov/data/realtime2/{buoy_id}.txt"
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
        
        return {
            "time": time_str,
            "wind_dir": wind_dir,
            "wind_speed_ms": wind_speed_ms,
            "gust_ms": gust_ms,
            "wave_ht_m": wave_ht_m,
            "wave_period_sec": wave_period,
            "pressure_hpa": pressure_hpa,
            "air_temp_c": air_temp_c,
            "water_temp_c": water_temp_c,
            "dewpoint_c": dewpoint_c,
            "pressure_tend_hpa": pressure_tend
        }
    except Exception as e:
        logging.error(f"  ✗ {buoy_id}: {redact_secrets(e)}")
        return None


def fetch_buoy_44013():
    """Fetch and blend buoy data from 44013 (primary) and 44098 (DPD backup)."""
    logging.info("📡 Fetching buoy data (44013 + 44098)...")
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None}
    
    try:
        # Fetch both buoys
        buoy_13 = _fetch_single_buoy("44013")
        buoy_98 = _fetch_single_buoy("44098")
        
        if not buoy_13 and not buoy_98:
            raise ValueError("Both buoys failed to fetch")
        
        # Use 44013 as primary source (closer, has complete met data)
        if buoy_13:
            result = buoy_13.copy()
            blended = []
            
            # Helper function to blend two values
            def blend_values(name, val_13, val_98, precision=1):
                if val_13 is not None and val_98 is not None:
                    avg = round((val_13 + val_98) / 2, precision)
                    blended.append(f"{name}={avg}")
                    return avg
                elif val_98 is not None:
                    blended.append(f"{name}={val_98}(98only)")
                    return val_98
                else:
                    return val_13
            
            # Blend wave period
            result['wave_period_sec'] = blend_values(
                'DPD',
                buoy_13.get('wave_period_sec'),
                buoy_98.get('wave_period_sec') if buoy_98 else None,
                precision=1
            )
            
            # Blend wave height
            result['wave_ht_m'] = blend_values(
                'WVHT',
                buoy_13.get('wave_ht_m'),
                buoy_98.get('wave_ht_m') if buoy_98 else None,
                precision=2
            )
            
            # Blend water temp
            result['water_temp_c'] = blend_values(
                'WTMP',
                buoy_13.get('water_temp_c'),
                buoy_98.get('water_temp_c') if buoy_98 else None,
                precision=1
            )
            
            # Blend air temp
            result['air_temp_c'] = blend_values(
                'ATMP',
                buoy_13.get('air_temp_c'),
                buoy_98.get('air_temp_c') if buoy_98 else None,
                precision=1
            )
            
            # Wind speed (skip wind direction - circular mean is complex)
            result['wind_speed_ms'] = blend_values(
                'WSPD',
                buoy_13.get('wind_speed_ms'),
                buoy_98.get('wind_speed_ms') if buoy_98 else None,
                precision=1
            )
            
            if blended:
                logging.info(f"  ℹ Blended: {', '.join(blended)}")
            else:
                logging.info(f"  ℹ Using 44013 only (44098 has no overlapping data)")
        
        else:
            # 44013 failed, use 44098 as fallback
            result = buoy_98.copy()
            logging.error("  ⚠ Using 44098 only (44013 failed)")
        
        # Convert to final units
        wind_speed_ms = result.get('wind_speed_ms')
        gust_ms = result.get('gust_ms')
        wave_ht_m = result.get('wave_ht_m')
        air_temp_c = result.get('air_temp_c')
        water_temp_c = result.get('water_temp_c')
        dewpoint_c = result.get('dewpoint_c')
        
        final_result = {
            "time": result.get('time'),
            "wind_dir": result.get('wind_dir'),
            "wind_mph": round(wind_speed_ms * 2.23694, 1) if wind_speed_ms else None,
            "gust_mph": round(gust_ms * 2.23694, 1) if gust_ms else None,
            "wave_ht_ft": round(wave_ht_m * 3.28084, 1) if wave_ht_m else None,
            "wave_period_sec": result.get('wave_period_sec'),
            "pressure_hpa": result.get('pressure_hpa'),
            "air_temp_f": round(air_temp_c * 9/5 + 32, 1) if air_temp_c else None,
            "water_temp_f": round(water_temp_c * 9/5 + 32, 1) if water_temp_c else None,
            "dewpoint_f": round(dewpoint_c * 9/5 + 32, 1) if dewpoint_c else None,
            "pressure_tend_hpa": result.get('pressure_tend_hpa')
        }
        
        meta["status"] = "ok"
        logging.info(f"  ✓ Buoy: {final_result.get('air_temp_f')}°F air, {final_result.get('water_temp_f')}°F water, {final_result.get('wave_ht_ft')} ft waves, {final_result.get('wave_period_sec')}s period")
        return final_result, meta
        
    except Exception as e:
        meta["error"] = redact_secrets(e)
        logging.error(f"  ✗ Buoy fusion failed: {redact_secrets(e)}")
        return None, meta

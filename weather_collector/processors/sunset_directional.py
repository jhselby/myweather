"""
Calculate sunset azimuth and sample clouds directionally for accurate sunset quality prediction.
"""
import math
from datetime import datetime, timezone

def calculate_sunset_azimuth(lat, lon, sunset_time_iso):
    """
    Calculate sunset azimuth using solar position algorithm.
    Returns azimuth in degrees (0° = N, 90° = E, 180° = S, 270° = W)
    """
    dt = datetime.fromisoformat(sunset_time_iso.replace('Z', '+00:00'))
    
    jd = 2440587.5 + dt.timestamp() / 86400.0
    T = (jd - 2451545.0) / 36525.0
    
    L0 = (280.46646 + 36000.76983 * T + 0.0003032 * T * T) % 360
    M = (357.52911 + 35999.05029 * T - 0.0001537 * T * T) % 360
    M_rad = math.radians(M)
    
    C = (1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(M_rad)
    C += (0.019993 - 0.000101 * T) * math.sin(2 * M_rad)
    C += 0.000289 * math.sin(3 * M_rad)
    
    L = L0 + C
    L_rad = math.radians(L)
    
    eps = 23.439291 - 0.0130042 * T
    eps_rad = math.radians(eps)
    
    RA = math.atan2(math.cos(eps_rad) * math.sin(L_rad), math.cos(L_rad))
    dec = math.asin(math.sin(eps_rad) * math.sin(L_rad))
    
    lat_rad = math.radians(lat)
    
    H = math.acos(-math.tan(lat_rad) * math.tan(dec))
    
    sin_az = math.sin(H)
    cos_az = (math.sin(dec) - math.sin(lat_rad) * (-0.0145)) / (math.cos(lat_rad) * math.cos(-0.0145))
    
    azimuth = math.degrees(math.atan2(sin_az, cos_az))
    azimuth = (azimuth + 180) % 360
    
    return round(azimuth, 1)


def calculate_offset_lat_lon(lat, lon, bearing_deg, distance_miles):
    """
    Calculate new lat/lon given starting point, bearing, and distance.
    """
    R = 3959.0
    
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    bearing_rad = math.radians(bearing_deg)
    
    d_R = distance_miles / R
    
    new_lat_rad = math.asin(
        math.sin(lat_rad) * math.cos(d_R) +
        math.cos(lat_rad) * math.sin(d_R) * math.cos(bearing_rad)
    )
    
    new_lon_rad = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(d_R) * math.cos(lat_rad),
        math.cos(d_R) - math.sin(lat_rad) * math.sin(new_lat_rad)
    )
    
    return round(math.degrees(new_lat_rad), 4), round(math.degrees(new_lon_rad), 4)


def build_sunset_directional_data(daily_sunsets, lat, lon, fetch_directional_clouds_func):
    """
    Build sunset directional cloud sampling data for next 5 days.
    """
    print("🌅 Building directional sunset data...")
    
    # Warmup: fetch Day 6 (which we don't use) to establish connection
    # If this times out, we don't care - but it should warm the connection for Day 0
    print("  📡 Warmup: fetching Day 6 to establish connection...")
    try:
        _ = fetch_directional_clouds_func(lat, lon, 0, [10], skip_retry=True)  # No retry on warmup
        print("  ✓ Warmup complete")
    except Exception as e:
        print(f"  ⚠️ Warmup timeout (not critical): {e}")
    
    sunset_data = []
    
    for day_idx, sunset_iso in enumerate(daily_sunsets[:5]):
        if not sunset_iso:
            continue
            
        azimuth = calculate_sunset_azimuth(lat, lon, sunset_iso)
        
        print(f"  Day {day_idx}: sunset {sunset_iso} at {azimuth}°")
        
        directional_clouds = fetch_directional_clouds_func(lat, lon, azimuth, [10, 25, 50])
        
        sunset_data.append({
            "day": day_idx,
            "sunset_time": sunset_iso,
            "azimuth": azimuth,
            "clouds": directional_clouds
        })
    
    print(f"  ✓ Built sunset data for {len(sunset_data)} days")
    return sunset_data

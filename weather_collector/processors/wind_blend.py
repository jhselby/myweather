"""
Wind blending:
  - select_observed_wind: pick the best current wind from model + obs sources
  - blend_observed_into_hourly: bleed that observation into the next N hours
    of the hourly forecast, decaying linearly

Both mutate weather_data in place.
"""
import logging
from datetime import datetime, timezone

import pytz


# Observation freshness limits. Readings older than this are dropped.
WU_STALE_MINUTES = 20
TEMPEST_STALE_MINUTES = 20

# Sanity cap: if WU has at least this many stations and the chosen speed is
# more than CAP_RATIO × the WU aggregate, the model is likely wrong-high.
WU_CAP_MIN_STATIONS = 10
WU_CAP_RATIO = 2.5

# When the sanity cap fires on speed, gusts get capped at this multiplier.
GUST_CAP_FACTOR = 1.3

# Knots to mph (METAR wind units → display units).
KT_TO_MPH = 1.15078

# Hourly blend horizon: weight decays linearly from 100% observed at hour 0
# to 0% observed at hour BLEND_HOURS, replacing the model's wind in between.
BLEND_HOURS = 24

_TZ_EASTERN = pytz.timezone("America/New_York")


def _wu_candidates(wu_data, now_utc):
    """Return fresh WU station readings as candidate dicts."""
    if not (wu_data and wu_data.get("stations")):
        return []
    candidates = []
    for station in wu_data["stations"]:
        if not station.get("wind_gust_mph"):
            continue
        ts_str = station.get("timestamp")
        if ts_str:
            try:
                obs_dt = (
                    datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
                    if ts_str.endswith("Z")
                    else datetime.fromisoformat(ts_str)
                )
                if obs_dt.tzinfo is None:
                    obs_dt = obs_dt.replace(tzinfo=timezone.utc)
                age_min = (now_utc - obs_dt).total_seconds() / 60
                if age_min > WU_STALE_MINUTES:
                    continue
            except (ValueError, TypeError):
                pass  # Unparseable timestamp — include anyway
        candidates.append({
            "source": f"WU_{station.get('station_id', 'unknown')}",
            "gust": station["wind_gust_mph"],
            "speed": station.get("wind_speed_mph", 0),
            "direction": station.get("wind_direction"),
            "waterfront": station.get("waterfront", False),
        })
    return candidates


def _tempest_candidates(tempest_data):
    """Return fresh Tempest station readings as candidate dicts."""
    if not tempest_data:
        return []
    candidates = []
    for tb in tempest_data.get("stations", []):
        if not tb.get("valid") or not tb.get("wind_gust_mph"):
            continue
        if tb.get("age_minutes") is not None and tb["age_minutes"] > TEMPEST_STALE_MINUTES:
            continue
        candidates.append({
            "source": f"Tempest_{tb['station_name']}",
            "gust": tb["wind_gust_mph"],
            "speed": tb.get("wind_avg_mph", 0),
            "direction": tb.get("wind_direction"),
            "waterfront": tb.get("waterfront", False),
        })
    return candidates


def select_observed_wind(weather_data, kbvy_data, wu_data, tempest_data):
    """Override model wind with the best available observation.

    Mutates weather_data["current"] in place, setting:
      - wind_speed, wind_gusts, wind_direction (chosen values)
      - model_wind_speed, model_wind_gusts (preserved original model values)
      - condition_source (e.g., "Tempest_PoolHouse observed")
    """
    current = weather_data["current"]

    # Save model values for the "corrections" display before overriding
    current["model_wind_speed"] = current.get("wind_speed", 0)
    current["model_wind_gusts"] = current.get("wind_gusts", 0)

    # Build candidate list: model + KBVY METAR + fresh WU + fresh Tempest
    candidates = [{
        "source": "model",
        "gust": current.get("wind_gusts", 0),
        "speed": current.get("wind_speed", 0),
        "direction": current.get("wind_direction"),
        "waterfront": False,
    }]
    if kbvy_data and kbvy_data.get("wind_gust_kt"):
        # METARs are issued at :54 past each hour — always < 60 min old
        candidates.append({
            "source": "KBVY",
            "gust": kbvy_data["wind_gust_kt"] * KT_TO_MPH,
            "speed": (kbvy_data["wind_speed_kt"] * KT_TO_MPH) if kbvy_data.get("wind_speed_kt") else 0,
            "direction": kbvy_data.get("wind_dir"),
            "waterfront": False,
        })
    now_utc = datetime.now(timezone.utc)
    candidates.extend(_wu_candidates(wu_data, now_utc))
    candidates.extend(_tempest_candidates(tempest_data))

    if candidates:
        # Max gust and max sustained selected independently
        max_gust_entry = max(candidates, key=lambda x: x["gust"])
        selected_gust = max_gust_entry["gust"]
        max_speed_entry = max(candidates, key=lambda x: x["speed"])
        selected_speed = max_speed_entry["speed"]

        # Sanity cap: if the WU sensor network strongly disagrees with the
        # chosen speed, the model is likely wrong-high — trust the network.
        wu_speed = wu_data.get("wind_speed_mph") if wu_data else None
        wu_stations_wind = wu_data.get("quality", {}).get("stations_used_wind", 0) if wu_data else 0
        if (wu_speed is not None
                and wu_stations_wind >= WU_CAP_MIN_STATIONS
                and selected_speed > wu_speed * WU_CAP_RATIO):
            logging.warning(
                f"  ⚠️ Wind sanity cap: selected {selected_speed:.1f} mph "
                f"> {WU_CAP_RATIO}× WU aggregate {wu_speed:.1f} mph "
                f"({wu_stations_wind} stations) — capping"
            )
            cap = wu_speed * WU_CAP_RATIO
            selected_speed = min(selected_speed, cap)
            selected_gust = min(selected_gust, cap * GUST_CAP_FACTOR)

        current["wind_gusts"] = selected_gust
        current["wind_speed"] = selected_speed

        # Direction: prefer the freshest waterfront Tempest, fall back to max-gust source
        waterfront_tempest = [
            c for c in candidates
            if c["waterfront"]
            and c["source"].startswith("Tempest_")
            and c["direction"] is not None
        ]
        if waterfront_tempest:
            dir_source = max(waterfront_tempest, key=lambda x: x["gust"])
        else:
            dir_source = max_gust_entry
        if dir_source["direction"] is not None:
            try:
                current["wind_direction"] = float(dir_source["direction"])
            except (ValueError, TypeError):
                pass  # Keep existing numeric value from Open-Meteo

        current["condition_source"] = f"{max_gust_entry['source']} observed"

    # Final fallback: if GFS failed and nothing yielded a direction, use KBVY
    if current.get("wind_direction") is None and kbvy_data and kbvy_data.get("wind_dir") is not None:
        try:
            current["wind_direction"] = float(kbvy_data["wind_dir"])
        except (ValueError, TypeError):
            pass


def blend_observed_into_hourly(weather_data):
    """Blend the current observed wind into the next BLEND_HOURS of the
    hourly forecast. Weight decays linearly: 100% observed at the current
    hour → 0% observed BLEND_HOURS out. Compensates for the model
    under-reading wind at exposed coastal locations.

    No-op when there's no hourly data, no current wind to blend in, or
    the hourly arrays don't include wind_gusts.
    """
    hourly = weather_data.get("hourly")
    if not hourly or "wind_gusts" not in hourly:
        return

    # Preserve raw (pre-blend) wind values so downstream (decay debug page,
    # anything else) can show what the forecast would be with NO local
    # corrections applied at all. temp/humidity/POP retain their raw arrays
    # naturally — only wind/gust get mutated in place here.
    if "wind_speed" in hourly and "raw_wind_speed" not in hourly:
        hourly["raw_wind_speed"] = list(hourly["wind_speed"])
    if "raw_wind_gusts" not in hourly:
        hourly["raw_wind_gusts"] = list(hourly["wind_gusts"])

    cur = weather_data.get("current", {})
    observed_gust = cur.get("wind_gusts")
    observed_speed = cur.get("wind_speed")
    if not observed_gust and not observed_speed:
        return

    times = hourly.get("times", [])
    gusts = hourly.get("wind_gusts", [])
    speeds = hourly.get("wind_speed", [])
    blend_speed = bool(observed_speed) and bool(speeds)

    now_local = datetime.now(_TZ_EASTERN)
    current_hour_iso = now_local.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    try:
        current_idx = times.index(current_hour_iso)
    except ValueError:
        current_idx = 0

    end_idx = min(current_idx + BLEND_HOURS, len(gusts))
    for i in range(current_idx, end_idx):
        weight = max(0, 1 - (i - current_idx) / BLEND_HOURS)
        if observed_gust is not None:
            gusts[i] = (observed_gust * weight) + (gusts[i] * (1 - weight))
        if blend_speed and i < len(speeds):
            speeds[i] = (observed_speed * weight) + (speeds[i] * (1 - weight))

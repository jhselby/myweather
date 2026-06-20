"""
Wind blending:
  - select_observed_wind: pick the best current wind from model + obs sources
  - blend_observed_into_hourly: bleed that observation into the next N hours
    of the hourly forecast, decaying linearly

Both mutate weather_data in place.
"""
import logging
import math
import statistics
from datetime import datetime, timezone

import pytz
from ..config import LAT as HOME_LAT, LON as HOME_LON


def _circular_mean(directions):
    """Mean compass bearing in degrees from a list using sin/cos vectors.
    Handles wrap-around correctly (mean of [350, 10] = 0, not 180).
    Returns None if the input is empty or the resulting vector is degenerate.

    Skips non-numeric entries silently (METAR reports "VRB" for variable-direction
    wind; we treat those as "no direction signal" rather than crashing)."""
    valid = []
    for d in directions:
        if d is None:
            continue
        try:
            valid.append(float(d))
        except (TypeError, ValueError):
            continue  # "VRB" from METAR, garbage strings, etc.
    if not valid:
        return None
    sin_sum = sum(math.sin(math.radians(d)) for d in valid)
    cos_sum = sum(math.cos(math.radians(d)) for d in valid)
    if abs(sin_sum) < 1e-9 and abs(cos_sum) < 1e-9:
        return None  # opposing vectors cancel out — no consensus
    return math.degrees(math.atan2(sin_sum, cos_sum)) % 360


def _circular_diff_deg(a, b):
    """Smallest angular difference (0–180°) between two compass bearings."""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def _octant_index(lat, lon):
    """Compass octant 0–7 (0=N) of a station relative to home. None if no coords."""
    if lat is None or lon is None:
        return None
    lat1 = math.radians(HOME_LAT)
    lat2 = math.radians(lat)
    dlon = math.radians(lon - HOME_LON)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = (math.degrees(math.atan2(x, y)) + 360.0) % 360.0
    return int(((bearing + 22.5) % 360) / 45)


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
            "lat": station.get("latitude"),
            "lon": station.get("longitude"),
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
            "lat": tb.get("latitude"),
            "lon": tb.get("longitude"),
        })
    return candidates


def select_observed_wind(weather_data, kbvy_data, wu_data, tempest_data,
                         kbos_data=None):
    """Override model wind with the best available observation.

    Mutates weather_data["current"] in place, setting:
      - wind_speed, wind_gusts, wind_direction (chosen values)
      - model_wind_speed, model_wind_gusts (preserved original model values)
      - condition_source (e.g., "Tempest_PoolHouse observed")

    kbos_data passed in explicitly (added 2026-06-20) because the collector
    writes weather_data["kbos"] AFTER this function runs — looking via
    weather_data.get("kbos") returns None at this point.
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
        # Octant-balanced max selection (added 2026-06-02):
        # 1. Tag each candidate with its compass octant relative to home.
        #    Stations without coords (model, KBVY) are kept in a None bucket
        #    that always participates — these aren't directional outliers.
        # 2. Take the max gust/speed WITHIN each populated octant.
        # 3. Take the MEDIAN across those octant maxes — rejects a single
        #    station spike in one direction while preserving genuinely
        #    regional wind events that show up in multiple octants.
        # If only 1–2 octants have wind data, fall back to flat max (no
        # geographic spread to balance against).
        oct_gust   = {None: []}
        oct_speed  = {None: []}
        for c in candidates:
            oct = _octant_index(c.get("lat"), c.get("lon"))
            oct_gust.setdefault(oct, []).append(c)
            oct_speed.setdefault(oct, []).append(c)
        directional_octants = [o for o in oct_gust if o is not None and oct_gust[o]]
        # Always keep the model/KBVY (None) entries in the max pool
        if len(directional_octants) >= 3:
            # Per-octant max → median across octants. Include None bucket as
            # an additional "reference" octant so model/KBVY aren't ignored.
            per_oct_max_gust  = [max(g["gust"]  for g in oct_gust[o])  for o in directional_octants]
            per_oct_max_speed = [max(s["speed"] for s in oct_speed[o]) for o in directional_octants]
            if oct_gust.get(None):
                per_oct_max_gust.append(max(g["gust"]  for g in oct_gust[None]))
                per_oct_max_speed.append(max(s["speed"] for s in oct_speed[None]))
            selected_gust  = statistics.median(per_oct_max_gust)
            selected_speed = statistics.median(per_oct_max_speed)
            # For the "source" label (and direction lookup), pick the actual
            # candidate whose gust matches the chosen median (closest match).
            max_gust_entry = min(candidates, key=lambda c: abs(c["gust"]  - selected_gust))
            max_speed_entry= min(candidates, key=lambda c: abs(c["speed"] - selected_speed))
            wind_aggregation = f"octant_median ({len(directional_octants)} octants)"
        else:
            max_gust_entry  = max(candidates, key=lambda x: x["gust"])
            max_speed_entry = max(candidates, key=lambda x: x["speed"])
            selected_gust   = max_gust_entry["gust"]
            selected_speed  = max_speed_entry["speed"]
            wind_aggregation = f"flat_max ({len(directional_octants)} octants - sparse)"

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

        # Authoritative-source floor (added 2026-06-20 after octant_median
        # underreported 10/15 mph during a real 17/27 mph W event — every
        # PWS had wind_dir=None and median across sheltered backyard octants
        # dropped well below the true wind).
        #
        # KBOS and KBVY are land airports within ~15 miles, mounted at proper
        # exposure. Buoy 44013 is excluded — it's 25 mi offshore in open
        # water, a different wind regime entirely. When BOTH airports agree
        # AND their mean is materially higher than what the octant logic
        # picked, defer to them. Mirrors the existing WU_CAP guardrail in
        # the opposite direction.
        AUTH_SPEED_RATIO = 1.4
        auth_speeds, auth_gusts, auth_dirs = [], [], []
        kbos = kbos_data or weather_data.get("kbos") or {}
        if kbos.get("wind_speed_kt") is not None:
            auth_speeds.append(kbos["wind_speed_kt"] * KT_TO_MPH)
            if kbos.get("wind_gust_kt") is not None:
                auth_gusts.append(kbos["wind_gust_kt"] * KT_TO_MPH)
            if kbos.get("wind_dir") is not None:
                auth_dirs.append(kbos["wind_dir"])
        if kbvy_data and kbvy_data.get("wind_speed_kt") is not None:
            auth_speeds.append(kbvy_data["wind_speed_kt"] * KT_TO_MPH)
            if kbvy_data.get("wind_gust_kt") is not None:
                auth_gusts.append(kbvy_data["wind_gust_kt"] * KT_TO_MPH)
            if kbvy_data.get("wind_dir") is not None:
                auth_dirs.append(kbvy_data["wind_dir"])
        auth_speed = statistics.median(auth_speeds) if len(auth_speeds) >= 2 else None
        auth_gust = statistics.median(auth_gusts) if len(auth_gusts) >= 2 else None
        if auth_speed is not None and auth_speed > selected_speed * AUTH_SPEED_RATIO:
            logging.warning(
                f"  ⚠️ Wind authoritative-floor: KBOS+KBVY median "
                f"{auth_speed:.1f} mph > {AUTH_SPEED_RATIO}× selected "
                f"{selected_speed:.1f} mph — deferring to airport towers"
            )
            selected_speed = round(auth_speed, 1)
            if auth_gust is not None:
                selected_gust = round(auth_gust, 1)
            current["wind_speed"] = selected_speed
            current["wind_gusts"] = selected_gust
            current["wind_aggregation"] = "authoritative_floor (KBOS+KBVY)"
            current["condition_source"] = "KBOS+KBVY consensus"
            current["wind_authoritative_floor"] = {
                "auth_speed": round(auth_speed, 1),
                "n_sources": len(auth_speeds),
            }

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
        elif len(auth_dirs) >= 2:
            # No PWS provided direction (today's failure mode: all Tempest
            # and WU report wind_dir=None during the 17/27 W event). Don't
            # leave the model's value standing — it was 87° off W. Use the
            # authoritative tower-source mean instead.
            auth_dir = _circular_mean(auth_dirs)
            if auth_dir is not None:
                current["wind_direction"] = round(auth_dir, 1)
                logging.info(
                    f"  ↪ Wind direction: no PWS direction data; using "
                    f"KBOS/KBVY/buoy circular mean {auth_dir:.0f}° "
                    f"(n={len(auth_dirs)}) instead of model {current.get('model_wind_speed')}"
                )

        # Don't clobber condition_source/aggregation if the authoritative
        # floor already labeled them.
        if not current.get("wind_aggregation", "").startswith("authoritative"):
            current["condition_source"] = f"{max_gust_entry['source']} observed"
            current["wind_aggregation"] = wind_aggregation

        # Direction consensus guardrail (added 2026-06-15 after Neptune Rd
        # was seen reporting 92° while every other source said NW ~310°).
        # If the chosen direction is more than DIRECTION_OUTLIER_THRESHOLD
        # off from the circular mean of every reliable direction source,
        # the chosen station's sensor is likely misaligned/drifting — fall
        # back to the consensus instead.
        # Threshold tightened 2026-06-20 from 90° → 60°. Today's failure
        # was chosen=352° (model fallback) vs consensus=265° — circular
        # diff = 87°, which slipped under the old 90° gate. 60° still
        # leaves comfortable room for legitimate boundary-layer turns.
        DIRECTION_OUTLIER_THRESHOLD = 60.0
        DIRECTION_MIN_SOURCES = 3
        consensus_dirs = []
        if kbvy_data and kbvy_data.get("wind_dir") is not None:
            consensus_dirs.append(kbvy_data["wind_dir"])
        kbos = kbos_data or weather_data.get("kbos") or {}
        if kbos.get("wind_dir") is not None:
            consensus_dirs.append(kbos["wind_dir"])
        buoy = weather_data.get("buoy_44013") or {}
        if buoy.get("wind_dir") is not None:
            consensus_dirs.append(buoy["wind_dir"])
        for s in (tempest_data or {}).get("stations", []):
            if s.get("valid") and s.get("wind_direction") is not None:
                consensus_dirs.append(s["wind_direction"])
        chosen = current.get("wind_direction")
        if chosen is not None and len(consensus_dirs) >= DIRECTION_MIN_SOURCES:
            consensus = _circular_mean(consensus_dirs)
            if consensus is not None:
                diff = _circular_diff_deg(chosen, consensus)
                if diff > DIRECTION_OUTLIER_THRESHOLD:
                    logging.warning(
                        f"  ⚠️ Wind direction guardrail: chosen {chosen:.0f}° "
                        f"(from {dir_source.get('source', '?')}) is {diff:.0f}° off "
                        f"consensus {consensus:.0f}° across {len(consensus_dirs)} sources "
                        f"— falling back to consensus"
                    )
                    current["wind_direction"] = round(consensus, 1)
                    current["wind_direction_guardrail"] = {
                        "rejected_value": chosen,
                        "rejected_source": dir_source.get("source"),
                        "consensus_value": round(consensus, 1),
                        "consensus_n": len(consensus_dirs),
                        "offset_deg": round(diff, 1),
                    }

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

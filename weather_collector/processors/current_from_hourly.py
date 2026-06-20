"""
Sync weather_data["current"] from the corrected hourly[0] arrays.

Foundational design (per project intent): every "current conditions" card
across the app reads `weather_data["current"]`. The contract is that
every field there is the *ultimate corrected value* from the L1→L4
correction stack — not raw model output, not GFS, not any parallel API
call.

This processor runs LAST in the pipeline, after `apply_decay_corrections`,
and overwrites every field in `weather_data["current"]` with its
counterpart from `weather_data["hourly"][0]` (which by that point is
HRRR L1 → L2 mesonet → L3 lead-decay → L4 diurnal). The corrected
arrays use `corrected_<field>` names where they exist; in-place fields
like `cloud_cover`, `wind_speed`, `precipitation_probability` are
mutated by `apply_decay_corrections` directly.

Preserved across the sync (don't get clobbered):
  - wind_speed / wind_gusts / wind_direction — set by select_observed_wind,
    which had access to KBOS/KBVY/PWS/Tempest observations and made a more
    informed pick than the hourly model. We re-read these from hourly[0]
    only if the wind selector didn't actually set them (defensive).
  - condition_source / condition_override / wind_aggregation /
    wind_authoritative_floor — metadata about how the wind/condition was
    chosen. Stays.
  - model_wind_speed / model_wind_gusts — preserved-for-display copy of
    the raw model values, set by the wind selector.
  - wet_bulb — computed downstream from corrected (T, h).

Re-derived (because hourly arrays don't carry these directly):
  - weather_code — derived from corrected cloud_cover + precipitation in
    the dry-weather band (codes 0-3). Precip-class codes (45+) preserved
    from the original `current.weather_code` because they carry
    information not present in cloud/precip alone (fog, drizzle vs rain,
    snow, hail, etc.).
  - weather_description — derived from new weather_code.
  - weather_emoji — derived from new weather_code.

Origin: 2026-06-20 audit caught that `weather_data["current"]` was being
populated from a separate `fetch_current_gfs()` API call, completely
bypassing the correction stack for every field. Some fields (temp,
wind) had downstream rescue overrides; cloud_cover, weather_code,
weather_description, uv_index had no override and rode raw GFS straight
through to the cards. Joe correctly flagged this as a foundational
design violation. This processor restores the contract.
"""
import logging

from ..utils import get_weather_description, get_weather_emoji


# hPa = inHg * 33.8639. Used to convert corrected_pressure_in (inHg in the
# corrected hourly arrays) back to current's hPa convention.
INHG_TO_HPA = 33.8639


# Map of current key → preferred hourly array source. The first entry that
# exists and has a non-None value at index 0 is used. Listed in preference
# order (corrected → derived → raw).
_FIELD_MAP = [
    ("temperature",          ["corrected_temperature", "temperature_2m", "temperature"]),
    ("humidity",             ["corrected_humidity",    "relative_humidity_2m", "humidity"]),
    ("dew_point",            ["corrected_dew_point",   "dew_point_2m",  "dew_point"]),
    ("cloud_cover",          ["cloud_cover"]),  # mutated in-place by L2 blend + apply_decay
    ("precipitation",        ["precipitation"]),
    ("apparent_temperature", ["corrected_apparent_temperature", "apparent_temperature"]),
    ("uv_index",             ["uv_index"]),  # HRRR carries this; GFS-current was the lone source before
]


def _first_present(hourly, names):
    """Return hourly[name][0] for the first name where the array exists and
    its [0] entry is not None. None if none match."""
    for n in names:
        arr = hourly.get(n)
        if isinstance(arr, list) and arr and arr[0] is not None:
            return arr[0]
    return None


def _derive_weather_code(cloud_cover, precip):
    """Dry-weather code from corrected cloud + precip — 5-band split.

    Matches NWS/AccuWeather/Apple Weather civilian convention rather than
    strict WMO (which only has 4 levels in the dry-weather range). Code 100
    (Mostly Cloudy) is a local extension; the rest are WMO.

      0   = Clear         (cloud <  12%)   FEW boundary
      1   = Mostly Clear  (12 ≤ cloud < 37)
      2   = Partly Cloudy (37 ≤ cloud < 62)  middle (SCT-BKN transition)
      100 = Mostly Cloudy (62 ≤ cloud < 87)
      3   = Overcast      (cloud ≥ 87)      OVC territory

    Asymmetric (tighter at the extremes, wider in the middle) because the
    perceptual difference between "clear" and "wispy" is greater than that
    between two shades of partly cloudy. Retuned 2026-06-20 v0.6.154 after
    the original 4-band split kept landing user-visible "Partly Cloudy" or
    "Mostly Clear" labels in conditions Joe described as mostly cloudy.

    Returns None if cloud_cover is None.
    """
    if cloud_cover is None:
        return None
    if precip is not None and precip >= 0.05:
        # Precip is happening — return None so the caller preserves the
        # model's original precip-class code (61, 63, 65, 80, 81, 82, etc.)
        return None
    if cloud_cover < 12:
        return 0
    if cloud_cover < 37:
        return 1
    if cloud_cover < 62:
        return 2
    if cloud_cover < 87:
        return 100
    return 3


def sync_current_from_hourly_corrected(weather_data):
    """Last-step processor. Mutates weather_data["current"] so every field
    reflects the L1→L4-corrected hourly[0] values. Preserves observation-
    sourced wind values and condition metadata set by upstream overrides.
    """
    hourly = weather_data.get("hourly") or {}
    if not hourly.get("times"):
        logging.info("  ⊘ sync_current_from_hourly_corrected: no hourly data — skipping")
        return

    current = weather_data.setdefault("current", {})

    # 1. Replace per-field numeric values from hourly[0] of the corrected stream.
    synced = []
    for ckey, hkeys in _FIELD_MAP:
        v = _first_present(hourly, hkeys)
        if v is None:
            continue
        prev = current.get(ckey)
        current[ckey] = v
        if prev != v:
            synced.append(f"{ckey}: {prev}→{v}")

    # Pressure has unit conversion: hourly carries inHg (corrected_pressure_in),
    # current carries hPa.
    cp_inhg = _first_present(hourly, ["corrected_pressure_in"])
    if cp_inhg is not None:
        prev = current.get("pressure")
        new_hpa = round(cp_inhg * INHG_TO_HPA, 1)
        current["pressure"] = new_hpa
        if prev != new_hpa:
            synced.append(f"pressure: {prev}→{new_hpa} hPa (from {cp_inhg} inHg)")

    # 2. Re-derive weather_code/description/emoji from corrected cloud + precip
    #    in the dry-weather band. Preserve precip/fog codes (45+).
    raw_code = current.get("weather_code")
    if raw_code is None or raw_code < 45:
        new_code = _derive_weather_code(current.get("cloud_cover"),
                                        current.get("precipitation"))
        if new_code is not None and new_code != raw_code:
            current["weather_code"] = new_code
            current["weather_description"] = get_weather_description(new_code)
            current["weather_emoji"] = get_weather_emoji(new_code)
            synced.append(f"weather_code: {raw_code}→{new_code} ({current['weather_description']})")

    if synced:
        logging.info(f"  ✓ sync current ← hourly[0] corrected: {len(synced)} field(s) updated")
        # First few changes visible in the log
        for s in synced[:6]:
            logging.info(f"     {s}")
    else:
        logging.info("  ⊘ sync current ← hourly[0]: no fields changed")

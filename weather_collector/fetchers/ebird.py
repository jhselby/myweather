"""
Fetch recent bird observations from eBird API.

Two calls per run:
  - /v2/data/obs/geo/recent         (all recent species, most-recent obs per species)
  - /v2/data/obs/geo/recent/notable (rarities per eBird regional filters)

The /geo/recent endpoint already returns one observation per species (the most
recent one), so no dedupe-by-species is needed within a single call. We merge
the two lists into a unified species[] array with a `notable` flag.
"""
import math
import requests

from ..config import LAT, LON, HEADERS_DEFAULT
from ..utils import iso_utc_now

EBIRD_BASE = "https://api.ebird.org/v2/data/obs/geo"
import os
EBIRD_API_KEY = os.environ.get("EBIRD_API_KEY", "sjjc0p5rqpqg")
RADIUS_KM = 5
BACK_DAYS = 2  # ~48 hours


def _haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _ebird_get(path, api_key, label):
    """GET from eBird with standard error handling. Returns (list, meta)."""
    meta = {"status": "error", "updated_at": iso_utc_now(), "error": None, "endpoint": label}
    url = f"{EBIRD_BASE}/{path}"
    headers = dict(HEADERS_DEFAULT)
    headers["X-eBirdApiToken"] = api_key
    params = {"lat": LAT, "lng": LON, "dist": RADIUS_KM, "back": BACK_DAYS}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            raise ValueError(f"unexpected response shape: {type(data).__name__}")
        meta["status"] = "ok"
        meta["count"] = len(data)
        print(f"  ✓ eBird {label}: {len(data)} obs")
        return data, meta
    except Exception as e:
        meta["error"] = str(e)
        print(f"  ✗ eBird {label}: {e}")
        return None, meta


def _normalize(obs, notable):
    """Map eBird observation to our schema."""
    lat = obs.get("lat")
    lng = obs.get("lng")
    dist_km = None
    if lat is not None and lng is not None:
        dist_km = round(_haversine_km(LAT, LON, lat, lng), 2)
    return {
        "code": obs.get("speciesCode"),
        "name": obs.get("comName"),
        "sci_name": obs.get("sciName"),
        "count": obs.get("howMany"),  # may be None (reported as "X" in eBird)
        "last_seen": obs.get("obsDt"),
        "location": obs.get("locName"),
        "loc_id": obs.get("locId"),
        "lat": obs.get("lat"),
        "lng": obs.get("lng"),
        "loc_private": obs.get("locationPrivate", False),
        "distance_km": dist_km,
        "notable": notable,
    }


def fetch_ebird():
    """
    Fetch recent and notable bird observations within RADIUS_KM of home.

    Returns:
        (data_dict_or_None, meta_dict)

    Output schema (when ok):
        {
          "fetched_at": "2026-04-22T...",
          "radius_km": 5,
          "back_days": 2,
          "species_count": 51,
          "notable_count": 0,
          "species": [
            {"code","name","sci_name","count","last_seen","location","distance_km","notable"},
            ...
          ]
        }
    """
    print("🐦 Fetching eBird observations...")
    recent, recent_meta = _ebird_get("recent", EBIRD_API_KEY, "recent")
    notable, notable_meta = _ebird_get("recent/notable", EBIRD_API_KEY, "notable")

    # Rollup meta: ok if at least recent succeeded. Notable failure is tolerable.
    meta = {
        "status": "ok" if recent is not None else "error",
        "updated_at": iso_utc_now(),
        "error": recent_meta.get("error"),
        "endpoint": "ebird",
        "recent_status": recent_meta["status"],
        "notable_status": notable_meta["status"],
    }

    if recent is None:
        return None, meta

    notable = notable or []

    # Build species list: recent is already one-per-species. Merge notable in,
    # flagging matching species and appending any notable entries not in recent
    # (rare but possible — e.g. notable species seen at a location whose
    # most-recent-per-species entry was a different bird).
    notable_codes = {n.get("speciesCode") for n in notable}
    species = [_normalize(o, notable=o.get("speciesCode") in notable_codes) for o in recent]

    recent_codes = {o.get("speciesCode") for o in recent}
    for n in notable:
        if n.get("speciesCode") not in recent_codes:
            species.append(_normalize(n, notable=True))

    # Sort: notable first, then most recent obsDt descending
    species.sort(key=lambda s: (0 if s["notable"] else 1, -_dt_sortkey(s["last_seen"])))

    data = {
        "fetched_at": iso_utc_now(),
        "radius_km": RADIUS_KM,
        "back_days": BACK_DAYS,
        "species_count": len(species),
        "notable_count": sum(1 for s in species if s["notable"]),
        "species": species,
    }
    print(f"  ✓ eBird combined: {data['species_count']} species, {data['notable_count']} notable")
    return data, meta


def _dt_sortkey(obs_dt):
    """
    eBird obsDt is 'YYYY-MM-DD HH:MM' (sometimes just 'YYYY-MM-DD').
    Return an int suitable for descending sort (larger = more recent).
    """
    if not obs_dt:
        return 0
    s = obs_dt.replace("-", "").replace(" ", "").replace(":", "")
    # Pad to 12 chars (YYYYMMDDHHMM) for date-only entries
    s = (s + "0000")[:12]
    try:
        return int(s)
    except ValueError:
        return 0

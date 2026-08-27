"""
NBM (National Blend of Models) CO 2.5km point extractor for Wyman Cove.

Fetches one NBM cycle's forecast leads from the public NOAA S3 bucket,
extracts values at (LAT, LON) for the fields we care about, returns a
per-lead dict.

Data source:
  https://noaa-nbm-grib2-pds.s3.amazonaws.com/blend.YYYYMMDD/HH/core/blend.tHHz.core.fFFF.co.grib2

Field map (grib param → app field):
  TMP:2 m above ground      → t   (K → °F)
  DPT:2 m above ground      → dp  (K → °F)
  WIND:10 m above ground    → ws  (m/s → mph)
  WDIR:10 m above ground    → wd  (degrees, unchanged)
  GUST:10 m above ground    → wg  (m/s → mph)
  DSWRF:surface             → sr  (W/m², unchanged)
  TCDC:surface              → cc  (%, unchanged)
  TCDC:high cloud layer     → ch  (%, unchanged)
  RH:2 m above ground       → h   (%, unchanged)

Not extracted:
  cl, cm      — NBM CO product does NOT publish low/middle cloud amount.
                Selector will always pick HRRR for these fields (single-source).
  pr          — NBM CO product does NOT publish surface pressure or MSLP
                anywhere in the 208-message inventory. HRRR-only forever.
  pa, pp      — precip amount / POP need separate audit; not extracted yet.

Note: the file also contains three TCDC:reserved messages with NCEP local
level codes 195/196/197 that have no defined meaning; they are NOT low/mid
cloud layers and are ignored.

For byte-range fetching we read the .idx sidecar file, then use HTTP
Range requests to pull only the grib messages we need. This is ~50x
faster than downloading the full ~200MB grib file per lead.
"""
import io
import logging
import tempfile
import urllib.request
from pathlib import Path

from ..config import LAT, LON

NBM_BASE = "https://noaa-nbm-grib2-pds.s3.amazonaws.com"

# Order matters: the 3rd column is our field name; the 1st two are how
# we match the .idx line. `nth` selects among duplicate matches (e.g.
# three TCDC:reserved entries for cl/cm/ch).
#
# Match column is either a substring (str) or a callable(lead) -> str for
# leads where the idx text embeds the hour range (TSTM/APCP: "0-1 hour
# acc fcst" at f001, "1-2 hour acc fcst" at f002, ...).
# Optional 5th element `allow_prob` keeps messages whose idx line contains
# "prob" (needed for TSTM which is `probability forecast`); default is to
# filter them out so APCP picks the accumulation, not the >0.254 prob.
FIELD_SPECS = [
    # (idx_match, nth, app_field, unit_transform[, allow_prob])
    ("TMP:2 m above ground",  0, "t",  lambda k: (k - 273.15) * 9/5 + 32),
    ("DPT:2 m above ground",  0, "dp", lambda k: (k - 273.15) * 9/5 + 32),
    ("WIND:10 m above ground", 0, "ws", lambda mps: mps * 2.23694),
    ("WDIR:10 m above ground", 0, "wd", lambda d: d),
    ("GUST:10 m above ground", 0, "wg", lambda mps: mps * 2.23694),
    ("DSWRF:surface",         0, "sr", lambda v: v),
    ("TCDC:surface",          0, "cc", lambda v: v),
    ("TCDC:high cloud layer", 0, "ch", lambda v: v),
    ("RH:2 m above ground",   0, "h",  lambda v: v),
    # APCP 1h accumulation ending at this lead (inches, from kg/m² = mm)
    (lambda L: f"APCP:surface:{L-1}-{L} hour acc fcst",
     0, "pa", lambda mm: mm / 25.4),
    # TSTM 1h thunder probability for the hour ending at this lead (%)
    (lambda L: f"TSTM:surface:{L-1}-{L} hour acc fcst",
     0, "tstm_prob", lambda v: v, True),
]


def _fetch_idx(cycle_ymd, cycle_hh, lead):
    url = f"{NBM_BASE}/blend.{cycle_ymd}/{cycle_hh}/core/blend.t{cycle_hh}z.core.f{lead:03d}.co.grib2.idx"
    return urllib.request.urlopen(url, timeout=30).read().decode()


def _plan_ranges(idx_text, lead):
    """Parse .idx into a list of (app_field, byte_start, byte_end).

    .idx lines look like: `N:OFFSET:d=YYYYMMDDHH:PARAM:LEVEL:FCST:...`
    Message length = next line's OFFSET - this line's OFFSET (last message
    runs to EOF; we pass byte_end=None for open-ended range).
    """
    entries = []
    for line in idx_text.splitlines():
        parts = line.split(":", 5)
        if len(parts) < 6:
            continue
        try:
            offset = int(parts[1])
        except ValueError:
            continue
        entries.append((offset, line))

    plan = []
    for spec in FIELD_SPECS:
        if len(spec) == 5:
            match, nth, field, transform, allow_prob = spec
        else:
            match, nth, field, transform = spec
            allow_prob = False
        match_str = match(lead) if callable(match) else match
        matches = [i for i, (_, line) in enumerate(entries)
                   if match_str in line
                   and "ens std" not in line
                   and (allow_prob or "prob" not in line)]
        if len(matches) <= nth:
            logging.warning(f"NBM idx: no match for {field} ({match_str} #{nth})")
            continue
        i = matches[nth]
        start = entries[i][0]
        end = entries[i + 1][0] - 1 if i + 1 < len(entries) else None
        plan.append((field, start, end, transform))
    return plan


def _fetch_range(url, start, end):
    range_hdr = f"bytes={start}-{end}" if end is not None else f"bytes={start}-"
    req = urllib.request.Request(url, headers={"Range": range_hdr})
    return urllib.request.urlopen(req, timeout=60).read()


def _extract_point(grib_bytes, lat, lon):
    """cfgrib-open the single-message bytes and pluck nearest-cell value."""
    import xarray as xr
    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as f:
        f.write(grib_bytes)
        tmp_path = f.name
    try:
        ds = xr.open_dataset(tmp_path, engine="cfgrib",
                             backend_kwargs={"indexpath": ""})
        # NBM CO grid is 2D lat/lon; find nearest cell.
        var_name = list(ds.data_vars)[0]
        da = ds[var_name]
        if "latitude" in da.coords and "longitude" in da.coords:
            lats = da.latitude.values
            lons = da.longitude.values
            # Normalize lon to match grid convention (NBM uses 0-360)
            lon_norm = lon + 360 if lon < 0 else lon
            import numpy as np
            dist = (lats - lat) ** 2 + (lons - lon_norm) ** 2
            iy, ix = np.unravel_index(dist.argmin(), dist.shape)
            val = float(da.values[iy, ix])
        else:
            val = float(da.sel(latitude=lat, longitude=lon, method="nearest").values)
        ds.close()
        return val
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def fetch_nbm_lead(cycle_ymd, cycle_hh, lead, lat=LAT, lon=LON):
    """Fetch one NBM lead, return {field: value} dict (or {} on failure)."""
    url = f"{NBM_BASE}/blend.{cycle_ymd}/{cycle_hh}/core/blend.t{cycle_hh}z.core.f{lead:03d}.co.grib2"
    try:
        idx_text = _fetch_idx(cycle_ymd, cycle_hh, lead)
    except Exception as e:
        logging.warning(f"NBM idx fetch failed {cycle_ymd}/{cycle_hh} f{lead:03d}: {e}")
        return {}

    plan = _plan_ranges(idx_text, lead)
    out = {}
    for field, start, end, transform in plan:
        try:
            grib_bytes = _fetch_range(url, start, end)
            raw_val = _extract_point(grib_bytes, lat, lon)
            out[field] = transform(raw_val)
        except Exception as e:
            logging.warning(f"NBM {field} f{lead:03d}: {e}")
    return out


def fetch_nbm_cycle(cycle_ymd, cycle_hh, leads=range(1, 48), lat=LAT, lon=LON):
    """Fetch all leads for a cycle. Returns {lead: {field: value}}."""
    out = {}
    for lead in leads:
        out[lead] = fetch_nbm_lead(cycle_ymd, cycle_hh, lead, lat, lon)
    return out


if __name__ == "__main__":
    import json
    import sys
    from datetime import datetime, timedelta, timezone
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # Smoke test: latest cycle with 3h lag, lead=6
    now = datetime.now(timezone.utc) - timedelta(hours=3)
    ymd = now.strftime("%Y%m%d")
    hh = now.strftime("%H")
    lead = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    print(f"NBM {ymd}/{hh} f{lead:03d} @ ({LAT}, {LON}):")
    result = fetch_nbm_lead(ymd, hh, lead)
    print(json.dumps(result, indent=2))

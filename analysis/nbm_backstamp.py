#!/usr/bin/env python3
"""NBM backstamp — retroactively stamps raw_nbm / l2_nbm / l3_nbm fields
onto historical pair-log rows using the backfilled NBM point extracts at
`gs://myweather-data/nbm_backfill/{ymd}_{hh}.json` (gzip'd point-JSON).

Motivation
----------
`error_l3_nbm` in the pair log only exists on rows post-v0.6.435 (~2026-
08-19). That's ~1 day of data — far below the 30-day / MIN_N=200
selector threshold. The v0.6.432 → v0.6.440 rewrite of the L1 selector
onto Prod-vs-Prod means the chooser currently falls through to HRRR
everywhere because there's no NBM-side data to compare.

The backfill CF spent 2 days pulling ~108 days of point extracts. Each
blob carries raw_nbm for the same lat/lon at every lead. That's enough
to reconstruct `l2_nbm` = raw_nbm + (l2_hrrr − raw_hrrr) for any
historical (field, run_time, lead_h) whose pair-log row already carries
`forecast_l1` + `forecast_l2` (HRRR-side delta). Since L3_NBM is
identity today (no bins fit), historical `l3_nbm = l2_nbm` — good
enough to feed `l3_nbm_fit.py` and `l1_selector_fit.py` with 30 days
of real signal instead of 1.

Semantic notes
--------------
- Fields with an HRRR L2 delta: t/ws/wd/wg/h → `l2_nbm = raw_nbm + Δ`.
  wd uses circular delta on radians via forecast_l1/forecast_l2 back-
  converted (matches forecast_snapshot line 481).
- Fields without HRRR L2: ch/sr/dp/cc → `l2_nbm = raw_nbm` (passthrough,
  matches forecast_snapshot line 476).
- L3_NBM identity: `forecast_l3_nbm = forecast_l2_nbm` and
  `error_l3_nbm = error_l2_nbm`. When fitter subsequently publishes
  L3_NBM bins, a second-pass backstamp would recompute — for now the
  fitter reads `error_l2_nbm` anyway (see l3_nbm_fit.py:115), so the
  identity stamp is a no-op for its purposes.
- NBM cycle selection: for a pair-log row with (run_time, lead_h), we
  find the freshest backfill blob whose cycle_time ≤ run_time (walking
  back up to CYCLE_LOOKBACK_H hours) and re-express the same valid_utc
  as (cycle_time, new_lead_h). Mirrors what the live collector does —
  it uses whichever NBM cycle is available at fetch time.

Output
------
Writes a NEW pair-log-shaped JSONL to `CACHE_DIR/forecast_error_log_
backstamped.jsonl`. Non-destructive — the live pair log on GCS is
untouched. Point fitters at the backstamped file with:

    MYWEATHER_PAIR_LOG=~/.cache/myweather_nbm_backstamp/... \\
      python3 -m analysis.l3_nbm_fit

(l3_nbm_fit.py and l1_selector_fit.py would need a small `cached_path`
override to honor the env var — do that as a follow-up if this run
looks good.)

Runtime
-------
    python3 -m analysis.nbm_backstamp
    MYWEATHER_REFRESH=1 python3 -m analysis.nbm_backstamp   # re-download
"""
import gzip
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
GCS_BLOB_URL = "https://storage.googleapis.com/myweather-data/nbm_backfill/{ymd}_{hh:02d}.json"

CACHE_DIR = Path(os.path.expanduser("~/.cache/myweather_nbm_backstamp"))
BLOB_DIR = CACHE_DIR / "blobs"
OUT_PATH = CACHE_DIR / "forecast_error_log_backstamped.jsonl"

# Fields NBM extracts (per weather_collector/fetchers/nbm_point.py schema
# used by the backfill CF).
NBM_SCOPE = ("t", "ws", "wd", "wg", "h", "ch", "sr", "dp", "cc")
# Which of those have a live HRRR L2 (so the mesonet delta gets shared).
L2_DELTA_FIELDS = ("t", "ws", "wd", "wg", "h")

# Walk back up to this many hours from run_time to find an available
# NBM cycle. Live collector typically finds one within 1-3h.
CYCLE_LOOKBACK_H = 6

# Only backstamp rows this old or newer — older pair-log rows may lack
# forecast_l1 / forecast_l2 (pre-v0.6.25 snapshots).
BACKSTAMP_CUTOFF_DAYS = 100


def _iso_floor_hour(ts):
    """'2026-08-15T04:37' → datetime(2026, 8, 15, 4, 0, 0)."""
    dt = datetime.strptime(ts[:16], "%Y-%m-%dT%H:%M")
    return dt.replace(minute=0, second=0, microsecond=0)


def _blob_local(ymd, hh):
    return BLOB_DIR / f"{ymd}_{hh:02d}.json"


def _fetch_blob(ymd, hh):
    """Download one backfill blob to local cache. Returns dict or None
    (404 or transport error). Idempotent — skips if already cached."""
    local = _blob_local(ymd, hh)
    if local.exists():
        try:
            with open(local) as fin:
                return json.load(fin)
        except Exception:
            local.unlink(missing_ok=True)
    import urllib.request
    url = GCS_BLOB_URL.format(ymd=ymd, hh=hh)
    try:
        req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            enc = resp.headers.get("Content-Encoding", "")
            raw = resp.read()
            if enc == "gzip":
                raw = gzip.decompress(raw)
            data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    local.parent.mkdir(parents=True, exist_ok=True)
    with open(local, "w") as fout:
        json.dump(data, fout, separators=(",", ":"))
    return data


def _find_cycle_for(run_time_iso, lead_h, blob_cache):
    """Given a pair-log row's (run_time, lead_h), find a backfill blob
    covering the same valid_utc. Returns (blob_dict, new_lead_h) or
    (None, None) if no candidate cycle has data.

    Uses freshest cycle ≤ run_time_floor_hour, walking back up to
    CYCLE_LOOKBACK_H hours."""
    run_floor = _iso_floor_hour(run_time_iso)
    valid_utc = run_floor + timedelta(hours=lead_h)
    for offset_h in range(0, CYCLE_LOOKBACK_H + 1):
        cycle_dt = run_floor - timedelta(hours=offset_h)
        new_lead = lead_h + offset_h
        if not (1 <= new_lead <= 47):
            continue
        ymd = cycle_dt.strftime("%Y%m%d")
        hh = cycle_dt.hour
        key = (ymd, hh)
        if key in blob_cache:
            blob = blob_cache[key]
        else:
            blob = _fetch_blob(ymd, hh)
            blob_cache[key] = blob
        if blob is None:
            continue
        leads = blob.get("leads", {})
        lead_data = leads.get(str(new_lead)) or leads.get(new_lead)
        if lead_data:
            return blob, new_lead
    return None, None


_L3_CURATED_PATH = Path(__file__).resolve().parent.parent / "weather_collector" / "data" / "l3_nbm_curated.json"
_L3_CACHE = None


def _l3_bias_for(field, lead_h):
    """Return the fitted L3 scalar bias for (field, lead_h), or 0.0 if the
    curated table has no cell (identity). wd goes through its own sin/cos
    branch inline in _stamp_row and does not consult this function."""
    global _L3_CACHE
    if _L3_CACHE is None:
        try:
            with open(_L3_CURATED_PATH) as fin:
                data = json.load(fin)
            _L3_CACHE = data.get("corrections", {})
        except FileNotFoundError:
            _L3_CACHE = {}
    arr = _L3_CACHE.get(field)
    if not arr:
        return 0.0
    if not (0 <= lead_h < len(arr)):
        return 0.0
    v = arr[lead_h]
    return float(v) if v is not None else 0.0


def _l3_wd_components_for(lead_h):
    """(sin_corr, cos_corr) for the wd L3 branch, or (0, 0) if not fit."""
    global _L3_CACHE
    if _L3_CACHE is None:
        _l3_bias_for("t", 0)  # trigger load
    wd = (_L3_CACHE or {}).get("wd_components") or {}
    sin_arr = wd.get("sin") or []
    cos_arr = wd.get("cos") or []
    s = sin_arr[lead_h] if 0 <= lead_h < len(sin_arr) else None
    c = cos_arr[lead_h] if 0 <= lead_h < len(cos_arr) else None
    return (float(s) if s is not None else 0.0,
            float(c) if c is not None else 0.0)


def _circular_diff_deg(a, b):
    """Signed angular diff in [-180, 180]. Matches forecast_error_log."""
    return (a - b + 180) % 360 - 180


def _stamp_row(row, blob, new_lead):
    """Compute + inject raw_nbm / l2_nbm / l3_nbm fields onto row.
    Returns True if stamped, False if prerequisites missing."""
    field = row.get("field")
    if field not in NBM_SCOPE:
        return False
    obs = row.get("observed")
    if obs is None:
        return False

    lead_data = blob["leads"].get(str(new_lead)) or blob["leads"].get(new_lead)
    if not lead_data:
        return False
    raw_nbm = lead_data.get(field)
    if raw_nbm is None:
        return False
    raw_nbm = float(raw_nbm)
    obs_f = float(obs)

    # Compute l2_nbm.
    if field in L2_DELTA_FIELDS:
        f_l1 = row.get("forecast_l1")
        f_l2 = row.get("forecast_l2")
        if f_l1 is None or f_l2 is None:
            return False
        if field == "wd":
            # Circular: forecast_l2 - forecast_l1 as signed angular delta
            # applied to raw_nbm modulo 360. Matches forecast_snapshot line 481.
            delta_deg = _circular_diff_deg(float(f_l2), float(f_l1))
            l2_nbm = (raw_nbm + delta_deg) % 360.0
        else:
            l2_nbm = raw_nbm + (float(f_l2) - float(f_l1))
    else:
        # ch/sr/dp/cc — no HRRR L2, l2_nbm passes raw_nbm.
        l2_nbm = raw_nbm

    # L3_NBM: apply fitted bias if a curated table is present, else
    # identity. First-pass runs identity (fits L3 from L2 residuals);
    # second-pass reads the fresh L3 table and stamps corrected values
    # so downstream selector fits see honest Prod-NBM.
    l3_nbm = l2_nbm - _l3_bias_for(field, new_lead)

    # Stamp linear fields.
    row["forecast_raw_nbm"] = round(raw_nbm, 3)
    row["forecast_l2_nbm"] = round(l2_nbm, 3)
    row["forecast_l3_nbm"] = round(l3_nbm, 3)
    if field == "wd":
        # For wd, override l3_nbm using circular sin/cos correction from
        # the fitted table (falls back to l2_nbm when uncorrected).
        sin_c, cos_c = _l3_wd_components_for(new_lead)
        if sin_c or cos_c:
            l2_rad = math.radians(l2_nbm)
            corrected_sin = math.sin(l2_rad) - sin_c
            corrected_cos = math.cos(l2_rad) - cos_c
            l3_nbm = math.degrees(math.atan2(corrected_sin, corrected_cos)) % 360.0
            row["forecast_l3_nbm"] = round(l3_nbm, 3)
        row["error_raw_nbm"] = round(_circular_diff_deg(raw_nbm, obs_f), 3)
        row["error_l2_nbm"] = round(_circular_diff_deg(l2_nbm, obs_f), 3)
        row["error_l3_nbm"] = round(_circular_diff_deg(l3_nbm, obs_f), 3)
        # sin/cos residuals for l3_nbm_fit.py's wd branch.
        o_rad = math.radians(obs_f)
        for lyr, v in (("raw_nbm", raw_nbm), ("l2_nbm", l2_nbm), ("l3_nbm", l3_nbm)):
            v_rad = math.radians(v)
            row[f"error_sin_{lyr}"] = round(math.sin(v_rad) - math.sin(o_rad), 5)
            row[f"error_cos_{lyr}"] = round(math.cos(v_rad) - math.cos(o_rad), 5)
    else:
        row["error_raw_nbm"] = round(raw_nbm - obs_f, 3)
        row["error_l2_nbm"] = round(l2_nbm - obs_f, 3)
        row["error_l3_nbm"] = round(l3_nbm - obs_f, 3)
    return True


def backstamp():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    BLOB_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.utcnow().replace(microsecond=0)
    cutoff = (now - timedelta(days=BACKSTAMP_CUTOFF_DAYS)).strftime("%Y-%m-%dT%H:%M")

    print(f"Downloading pair log (via analysis._cache)...")
    pair_path = cached_path(PAIR_LOG_URL)
    print(f"  local: {pair_path}")

    blob_cache = {}  # (ymd, hh) -> dict|None
    n_in = 0
    n_out = 0
    n_already = 0
    n_out_of_scope = 0
    n_too_old = 0
    n_no_prereq = 0
    n_no_blob = 0
    n_stamped = 0
    stamped_by_field = defaultdict(int)

    print(f"Streaming pair log → {OUT_PATH}")
    with open(pair_path) as fin, open(OUT_PATH, "w") as fout:
        for line in fin:
            n_in += 1
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            field = row.get("field")
            if field not in NBM_SCOPE:
                n_out_of_scope += 1
                fout.write(json.dumps(row, separators=(",", ":")) + "\n")
                n_out += 1
                continue

            # Skip rows that already carry NBM stamps (post-v0.6.435).
            if row.get("error_l3_nbm") is not None:
                n_already += 1
                fout.write(json.dumps(row, separators=(",", ":")) + "\n")
                n_out += 1
                continue

            obs_time = row.get("obs_time", "")
            if obs_time < cutoff:
                n_too_old += 1
                fout.write(json.dumps(row, separators=(",", ":")) + "\n")
                n_out += 1
                continue

            run_time = row.get("run_time")
            lead_h = row.get("lead_h")
            if not run_time or lead_h is None:
                n_no_prereq += 1
                fout.write(json.dumps(row, separators=(",", ":")) + "\n")
                n_out += 1
                continue

            blob, new_lead = _find_cycle_for(run_time, lead_h, blob_cache)
            if blob is None:
                n_no_blob += 1
                fout.write(json.dumps(row, separators=(",", ":")) + "\n")
                n_out += 1
                continue

            if _stamp_row(row, blob, new_lead):
                n_stamped += 1
                stamped_by_field[field] += 1

            fout.write(json.dumps(row, separators=(",", ":")) + "\n")
            n_out += 1

            if n_in % 50_000 == 0:
                print(f"  ... {n_in:,} rows scanned, {n_stamped:,} stamped, "
                      f"{len(blob_cache):,} blobs cached")

    print()
    print(f"Backstamp complete:")
    print(f"  {n_in:,} rows scanned, {n_out:,} written")
    print(f"  {n_stamped:,} newly stamped with raw_nbm / l2_nbm / l3_nbm")
    print(f"  {n_already:,} already had error_l3_nbm (passed through)")
    print(f"  {n_out_of_scope:,} out-of-scope field (passed through)")
    print(f"  {n_too_old:,} older than {BACKSTAMP_CUTOFF_DAYS}d cutoff")
    print(f"  {n_no_prereq:,} missing run_time or lead_h")
    print(f"  {n_no_blob:,} had no covering NBM cycle in backfill")
    print()
    print(f"Stamped-by-field:")
    for f in NBM_SCOPE:
        print(f"    {f}: {stamped_by_field[f]:,}")
    print()
    print(f"Blob cache: {len(blob_cache):,} distinct cycles "
          f"({sum(1 for v in blob_cache.values() if v is not None):,} hits)")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    backstamp()

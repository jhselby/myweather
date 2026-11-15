"""
Hourly NBM ingester Cloud Function.

Fetches the freshest available NBM CO cycle, extracts point values for
Wyman Cove across leads 1-55, and writes:

    gs://myweather-data/nbm_point_extract.json

Blob shape:
    {"cycle": "YYYYMMDDHH",
     "fetched_at": "2026-08-18T22:45:00Z",
     "lat": 42.5014, "lon": -70.875,
     "lead_valid_utc": {"1": "YYYY-MM-DDTHH:00:00Z", ...},
     "leads": {"1": {"t": ..., "dp": ..., ...}, ...}}

The collector reads this file each tick and stamps `raw_nbm` into
forecast_snapshot / pair log rows whose lead maps to a `lead_valid_utc`
entry. That wiring is Phase 1.

Cycle selection: try the most recent 3 cycles (T-2h, T-3h, T-4h) and use
the newest one whose .idx sidecar exists for lead 47 — that's a good
proxy for "all leads published."

Horizon (v0.7.102): the cycle is 2-6 h old, so cycle leads 1-47 ended ~44 h from now and
every NBM field fell back to HRRR at 45-47 h (cc on URMA: 27 MAE there vs ~21 for NBM).
Leads now run to 55 (53 needed, 55 so the next 3-hourly step exists). NBM is hourly only to about f049 and 3-hourly after, so the hours
between published steps are filled by linear interpolation (wd on the circle) for the
state fields in INTERP_FIELDS and flagged "_interp": True. v0.7.104: the fill is per field,
so sr (published 3-hourly from ~f034 while other fields stay hourly) is filled too; every
filled field is listed in the lead's "_interp_fields". Amounts and probabilities
(pa, pp, tstm_prob) are period values and are never interpolated.
"""
import json
import logging
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weather_collector.fetchers.nbm_point import (  # noqa: E402
    fetch_nbm_lead, NBM_BASE,
)
from weather_collector.config import LAT, LON  # noqa: E402
from weather_collector.gcs_io import get_client, BUCKET  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _cycle_lead47_ready(ymd, hh):
    """Cheap availability check: HEAD the f047 .idx for this cycle."""
    url = f"{NBM_BASE}/blend.{ymd}/{hh}/core/blend.t{hh}z.core.f047.co.grib2.idx"
    req = urllib.request.Request(url, method="HEAD")
    try:
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception:
        return False


def _pick_cycle(now_utc):
    """Walk back T-2h → T-6h looking for the newest fully-published cycle."""
    for offset_h in range(2, 7):
        cand = now_utc - timedelta(hours=offset_h)
        ymd = cand.strftime("%Y%m%d")
        hh = cand.strftime("%H")
        if _cycle_lead47_ready(ymd, hh):
            return ymd, hh, cand.replace(minute=0, second=0, microsecond=0)
    return None, None, None


MAX_LEAD = 55   # fetch past 53 so the 3-hourly step after the last needed hour exists
INTERP_FIELDS = ("t", "dp", "ws", "wd", "wg", "cc", "h", "sr", "ch")


MAX_GAP = 3   # NBM's widest step inside the horizon; never bridge wider gaps (ch stops at f036)


def _interp_gaps(leads_data):
    """Fill gaps per field (in place): a lead missing field f between two leads that have f,
    at most MAX_GAP apart, gets the linear interpolation. Covers whole empty leads (3-hourly
    steps past ~f049) and single fields NBM publishes 3-hourly earlier (sr from ~f034).
    Returns {lead: [filled fields]}."""
    filled = {}
    for f in INTERP_FIELDS:
        have = sorted(int(k) for k, v in leads_data.items() if v and v.get(f) is not None)
        for a, b in zip(have, have[1:]):
            if b - a > MAX_GAP:
                continue
            va, vb = leads_data[str(a)][f], leads_data[str(b)][f]
            for ld in range(a + 1, b):
                x = (ld - a) / (b - a)
                cell = leads_data.get(str(ld))
                if not cell:
                    cell = leads_data[str(ld)] = {"_interp": True}
                if f == "wd":
                    cell[f] = (va + x * (((vb - va + 180) % 360) - 180)) % 360
                else:
                    cell[f] = va + x * (vb - va)
                cell.setdefault("_interp_fields", []).append(f)
                filled.setdefault(ld, []).append(f)
    return filled


def _upload_json(client, path, payload):
    import gzip
    blob = client.bucket(BUCKET).blob(path)
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_gz = gzip.compress(payload_json.encode("utf-8"))
    blob.content_encoding = "gzip"
    blob.cache_control = "no-cache, max-age=0"
    blob.upload_from_string(payload_gz, content_type="application/json")
    return len(payload_json), len(payload_gz)


def ingest(request):
    args = request.args if request else {}
    parallel = int(args.get("parallel", "12"))
    leads = list(range(1, MAX_LEAD + 1))

    now_utc = datetime.now(timezone.utc)
    ymd, hh, cycle_dt = _pick_cycle(now_utc)
    if ymd is None:
        msg = "no ready NBM cycle in T-2h..T-6h window"
        logging.error(msg)
        return (json.dumps({"error": msg}), 503, {"Content-Type": "application/json"})

    t0 = time.time()
    leads_data = {}
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futs = {ex.submit(fetch_nbm_lead, ymd, hh, ld, LAT, LON): ld for ld in leads}
        for fut in as_completed(futs):
            ld = futs[fut]
            try:
                leads_data[str(ld)] = fut.result()
            except Exception as e:
                logging.warning(f"lead {ld} failed: {e}")
                leads_data[str(ld)] = {}

    filled = _interp_gaps(leads_data)
    lead_valid_utc = {
        str(ld): (cycle_dt + timedelta(hours=ld)).strftime("%Y-%m-%dT%H:00:00Z")
        for ld in leads
    }

    payload = {
        "cycle": f"{ymd}{hh}",
        "fetched_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lat": LAT, "lon": LON,
        "lead_valid_utc": lead_valid_utc,
        "leads": leads_data,
    }

    client = get_client()
    raw_b, gz_b = _upload_json(client, "nbm_point_extract.json", payload)

    n_ok = sum(1 for v in leads_data.values() if v and not v.get("_interp"))
    elapsed = time.time() - t0
    n_sr = sum(1 for v in filled.values() if "sr" in v)
    logging.info(f"NBM ingest cycle={ymd}{hh} n_ok={n_ok}/{MAX_LEAD} interp={sorted(filled)} sr_filled={n_sr} "
                 f"bytes={raw_b:,} gz={gz_b:,} elapsed={elapsed:.1f}s")

    return (json.dumps({"cycle": f"{ymd}{hh}", "n_ok": n_ok, "interp": {str(k): v for k, v in sorted(filled.items())},
                        "elapsed_s": round(elapsed, 1)}),
            200, {"Content-Type": "application/json"})

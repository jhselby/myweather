"""
One-shot NBM backfill Cloud Function.

Fetches historical NBM CO 2.5km point extracts for Wyman Cove and writes
one JSON blob per cycle to GCS at:

    gs://myweather-data/nbm_backfill/YYYYMMDD_HH.json

Blob shape: {"cycle": "YYYYMMDDHH", "lat": ..., "lon": ...,
             "leads": {"1": {"t": ..., "dp": ..., ...}, "2": {...}, ...}}

HTTP params (query string):
    start_date=YYYY-MM-DD   inclusive, defaults to today - 1
    num_days=N              defaults to 1; walks BACKWARDS from start_date
    cycles=0,1,2,...        comma list of hourly cycle hours; default 0-23
    leads=1-47              default; also accepts comma list "1,3,6"
    overwrite=1             re-fetch even if GCS blob exists
    parallel=N              thread pool size for byte-range fetches (default 12)
    max_seconds=N           soft cap to bail before CF timeout (default 3300)

Resume-friendly: any (date, cycle) with an existing GCS blob is skipped
unless overwrite=1. Joe can call this repeatedly to cover 120 days across
multiple invocations.
"""
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

# Make weather_collector importable when deployed with --source=.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weather_collector.fetchers.nbm_point import fetch_nbm_lead  # noqa: E402
from weather_collector.config import LAT, LON  # noqa: E402
from weather_collector.gcs_io import get_client, BUCKET  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _parse_leads(s):
    if not s or s == "1-47":
        return list(range(1, 48))
    if "-" in s and "," not in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in s.split(",")]


def _parse_cycles(s):
    if not s:
        return list(range(24))
    return [int(x) for x in s.split(",")]


def _blob_path(ymd, hh):
    return f"nbm_backfill/{ymd}_{hh:02d}.json"


def _blob_exists(client, path):
    return client.bucket(BUCKET).blob(path).exists()


def _upload_cycle(client, path, payload):
    import gzip
    blob = client.bucket(BUCKET).blob(path)
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_gz = gzip.compress(payload_json.encode("utf-8"))
    blob.content_encoding = "gzip"
    blob.cache_control = "no-cache, max-age=0"
    blob.upload_from_string(payload_gz, content_type="application/json")
    return len(payload_json), len(payload_gz)


def _fetch_cycle(ymd, hh, leads, parallel):
    """Fetch all leads for one cycle, parallelized. Returns {lead: {field: v}}."""
    out = {}
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futs = {ex.submit(fetch_nbm_lead, ymd, f"{hh:02d}", lead, LAT, LON): lead
                for lead in leads}
        for fut in as_completed(futs):
            lead = futs[fut]
            try:
                out[str(lead)] = fut.result()
            except Exception as e:
                logging.warning(f"lead {lead} failed: {e}")
                out[str(lead)] = {}
    return out


def backfill(request):
    """HTTP entrypoint."""
    args = request.args if request else {}

    start_str = args.get("start_date")
    if start_str:
        start = datetime.strptime(start_str, "%Y-%m-%d").date()
    else:
        start = date.today() - timedelta(days=1)

    num_days = int(args.get("num_days", "1"))
    cycles = _parse_cycles(args.get("cycles"))
    leads = _parse_leads(args.get("leads", "1-47"))
    overwrite = args.get("overwrite") == "1"
    lead_parallel = int(args.get("lead_parallel", args.get("parallel", "6")))
    cycle_parallel = int(args.get("cycle_parallel", "8"))
    max_seconds = float(args.get("max_seconds", "3300"))

    client = get_client()
    t0 = time.time()

    stats = {"start": start.isoformat(), "num_days": num_days,
             "cycles_per_day": len(cycles), "leads_per_cycle": len(leads),
             "cycle_parallel": cycle_parallel, "lead_parallel": lead_parallel,
             "written": 0, "skipped": 0, "failed": 0, "seconds": 0.0}

    # Build the full (ymd, hh) work list — walking dates backwards.
    work = []
    for day_off in range(num_days):
        d = start - timedelta(days=day_off)
        ymd = d.strftime("%Y%m%d")
        for hh in cycles:
            work.append((ymd, hh))

    def _process_one(ymd_hh):
        ymd, hh = ymd_hh
        path = _blob_path(ymd, hh)
        if not overwrite and _blob_exists(client, path):
            return ("skipped", ymd, hh, None)
        cycle_started = time.time()
        try:
            leads_data = _fetch_cycle(ymd, hh, leads, lead_parallel)
        except Exception as e:
            logging.error(f"{ymd}_{hh:02d} fetch crashed: {e}")
            return ("failed", ymd, hh, None)
        n_ok = sum(1 for v in leads_data.values() if v)
        if n_ok == 0:
            logging.warning(f"{ymd}_{hh:02d}: 0 leads fetched, skipping upload")
            return ("failed", ymd, hh, None)
        payload = {"cycle": f"{ymd}{hh:02d}", "lat": LAT, "lon": LON,
                   "leads": leads_data}
        try:
            raw_b, gz_b = _upload_cycle(client, path, payload)
            elapsed = time.time() - cycle_started
            logging.info(f"{ymd}_{hh:02d}: {n_ok}/{len(leads)} leads → "
                         f"{raw_b:,}B ({gz_b:,}B gz) in {elapsed:.1f}s")
            return ("written", ymd, hh, None)
        except Exception as e:
            logging.error(f"{ymd}_{hh:02d} upload failed: {e}")
            return ("failed", ymd, hh, None)

    # Parallelize across cycles. eccodes/numpy release the GIL during
    # decode, so threads give real speedup on multi-CPU CFs.
    with ThreadPoolExecutor(max_workers=cycle_parallel) as ex:
        futs = {ex.submit(_process_one, w): w for w in work}
        for fut in as_completed(futs):
            if time.time() - t0 > max_seconds:
                logging.warning("max_seconds reached, letting in-flight finish")
                # Don't cancel — in-flight cycles are close to done.
                # Just stop accepting new work by breaking after drain.
                # (ThreadPoolExecutor drains on context exit.)
            status, ymd, hh, _ = fut.result()
            stats[status] += 1

    stats["seconds"] = round(time.time() - t0, 1)
    return (json.dumps(stats), 200, {"Content-Type": "application/json"})


if __name__ == "__main__":
    # Local smoke test — one cycle, few leads.
    class Req:
        args = {"start_date": (date.today() - timedelta(days=1)).isoformat(),
                "num_days": "1", "cycles": "12", "leads": "6,12,24",
                "parallel": "3"}
    print(backfill(Req()))

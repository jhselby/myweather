#!/usr/bin/env python3
"""Incremental appender for the backstamped pair-log.

Runs in the publisher CF every hour. Reads the live pair-log's byte-offset
high-water mark from gs://myweather-data/backstamp_hwm.json, range-downloads
only the new bytes, passes each row through (post-Aug-19 rows already carry
error_l3_nbm), fills the L4_NBM counterfactual for cc/ch when missing, and
appends to gs://myweather-data/forecast_error_log_backstamped.jsonl via GCS
compose. Updates the HWM.

Zero NBM-backfill blob downloads. Typical delta: a few MB / hour, runtime
well under a minute.

The pre-Aug-19 base (rows that needed NBM backfill blobs) is FROZEN — this
appender never re-processes them. When the L4_NBM curated table changes,
run a full local rebuild + reset:

    make backstamp-rebuild-and-upload

That target rebuilds locally via `analysis.nbm_backstamp`, uploads the
result to GCS, then calls this module with --reset-hwm so the next
appender run re-seeds from the fresh base.

Bootstrap: on first run (no HWM sidecar), the module seeds itself by
finding the newest obs_time in the current backstamped file and scanning
the live pair-log for the first row past it. That one-time seed pays the
full pair-log download cost.
"""
import io
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weather_collector.gcs_io import BUCKET, get_client
from analysis.nbm_backstamp import _maybe_add_l4_nbm

PAIR_LOG_BLOB = "forecast_error_log.jsonl"
BACKSTAMPED_BLOB = "forecast_error_log_backstamped.jsonl"
DELTA_BLOB = "forecast_error_log_backstamped_delta.jsonl"
HWM_BLOB = "backstamp_hwm.json"


def _read_hwm(bucket):
    b = bucket.blob(HWM_BLOB)
    if not b.exists():
        return None
    try:
        return json.loads(b.download_as_bytes())
    except Exception as e:
        logging.warning(f"HWM sidecar exists but unparseable ({e}) — will reseed")
        return None


def _write_hwm(bucket, hwm):
    b = bucket.blob(HWM_BLOB)
    b.cache_control = "no-cache"
    b.upload_from_string(json.dumps(hwm), content_type="application/json")


def _seed_hwm(bucket):
    """Find the byte offset in the live pair-log just past the newest row
    already present in the backstamped file. One-time cost: downloads the
    full pair-log to scan by obs_time. Subsequent runs are range-download only."""
    logging.info("HWM missing — seeding from tail of backstamped file")

    bs = bucket.blob(BACKSTAMPED_BLOB)
    bs.reload()
    tail_start = max(0, bs.size - 256_000)
    tail = bs.download_as_bytes(start=tail_start, end=bs.size)

    last_obs_time = None
    for line in reversed(tail.split(b"\n")):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        ot = row.get("obs_time")
        if ot:
            last_obs_time = ot
            break
    if not last_obs_time:
        raise RuntimeError("could not find obs_time in backstamped tail")
    logging.info(f"backstamped tail last obs_time: {last_obs_time}")

    pb = bucket.blob(PAIR_LOG_BLOB)
    pb.reload()
    data = pb.download_as_bytes()
    offset = 0
    for line in data.split(b"\n"):
        if line.strip():
            try:
                ot = json.loads(line).get("obs_time")
                if ot and ot > last_obs_time:
                    break
            except Exception:
                pass
        offset += len(line) + 1

    # Cap at file size — the trailing split element (b"") past the final
    # \n adds a spurious +1 to offset.
    offset = min(offset, pb.size)
    print(f"nbm_backstamp_append: seeded offset={offset:,} of pair-log size {pb.size:,}", flush=True)
    return {"offset": offset, "last_obs_time": last_obs_time}


def main():
    # Use print() throughout so output is visible in Cloud Function logs
    # (the publisher's logging.info calls are filtered out below WARNING).
    print("nbm_backstamp_append: starting", flush=True)
    client = get_client()
    bucket = client.bucket(BUCKET)

    hwm = _read_hwm(bucket)
    if hwm is None:
        print("nbm_backstamp_append: HWM missing — seeding", flush=True)
        hwm = _seed_hwm(bucket)
        _write_hwm(bucket, hwm)

    pb = bucket.blob(PAIR_LOG_BLOB)
    pb.reload()
    plog_size = pb.size
    hwm_offset = int(hwm.get("offset", 0))
    print(f"nbm_backstamp_append: hwm={hwm_offset:,} plog_size={plog_size:,}", flush=True)

    if plog_size <= hwm_offset:
        print(f"nbm_backstamp_append: no new bytes; done", flush=True)
        return

    n_bytes = plog_size - hwm_offset
    logging.info(f"range-downloading {n_bytes:,} bytes ({hwm_offset:,}..{plog_size:,})")
    raw = pb.download_as_bytes(start=hwm_offset, end=plog_size)

    out = io.BytesIO()
    n_in = 0
    n_out = 0
    n_l4 = 0
    n_no_l3 = 0
    running = 0
    last_complete_end = 0
    for line in raw.split(b"\n"):
        line_len = len(line) + 1
        running += line_len
        if not line.strip():
            last_complete_end = running
            continue
        n_in += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            # Truncated final line — stop; resume from last_complete_end next run.
            break
        if row.get("error_l3_nbm") is None and row.get("field") in (
            "t", "ws", "wd", "wg", "h", "ch", "sr", "dp", "cc"
        ):
            n_no_l3 += 1
        if _maybe_add_l4_nbm(row):
            n_l4 += 1
        out.write(json.dumps(row, separators=(",", ":")).encode())
        out.write(b"\n")
        n_out += 1
        last_complete_end = running

    delta_content = out.getvalue()
    if not delta_content:
        logging.info(f"no complete rows to append (scanned {n_in})")
        return

    new_offset = hwm_offset + last_complete_end

    delta_blob = bucket.blob(DELTA_BLOB)
    delta_blob.upload_from_string(delta_content, content_type="application/x-ndjson")

    main_blob = bucket.blob(BACKSTAMPED_BLOB)
    main_blob.compose([bucket.blob(BACKSTAMPED_BLOB), delta_blob])
    delta_blob.delete()

    # Compose can reset metadata — patch cache-control back on.
    main_blob.reload()
    if main_blob.cache_control != "no-cache":
        main_blob.cache_control = "no-cache"
        main_blob.patch()

    last_obs = hwm.get("last_obs_time")
    for line in delta_content.splitlines():
        try:
            ot = json.loads(line).get("obs_time")
            if ot:
                last_obs = ot
        except Exception:
            pass

    _write_hwm(bucket, {"offset": new_offset, "last_obs_time": last_obs})
    print(
        f"nbm_backstamp_append: appended {n_out:,} rows ({len(delta_content):,}B), "
        f"{n_l4:,} L4-stamped, {n_no_l3:,} lacked error_l3_nbm; "
        f"HWM offset={new_offset:,} last_obs_time={last_obs}",
        flush=True,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if "--reset-hwm" in sys.argv:
        client = get_client()
        bucket = client.bucket(BUCKET)
        b = bucket.blob(HWM_BLOB)
        if b.exists():
            b.delete()
            print(f"deleted gs://{BUCKET}/{HWM_BLOB} — next run will reseed")
        else:
            print(f"gs://{BUCKET}/{HWM_BLOB} did not exist")
    else:
        main()

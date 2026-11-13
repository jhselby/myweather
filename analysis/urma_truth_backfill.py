"""Backfill URMA 2.5 km analysis at the house cell: an independent truth (not built from our forecast).

URMA (NOAA's Unrestricted Mesoscale Analysis) is read from the public AWS bucket noaa-urma-pds,
one byte-range GET per variable-hour (~5.6 MB each). No Google Cloud is touched. For each
variable-hour the four nearest grid points are stored with their distances, so the cell choice
(nearest vs interpolated) stays open. Resumable: variable-hours already in the output are skipped.

    .venv/bin/python -m analysis.urma_truth_backfill 2026-08-25 2026-11-11 TMP
"""
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import eccodes
import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from weather_collector.config import LAT, LON  # noqa: E402

OUT_DIR = ROOT / "analysis" / "output" / "urma_truth"
BUCKET = "https://noaa-urma-pds.s3.amazonaws.com"
WORKERS = 2
PAUSE_S = 0.25
# idx names -> (short name, level prefix)
VARS = {"TMP": "2 m", "DPT": "2 m", "WIND": "10 m", "GUST": "10 m", "WDIR": "10 m",
        "PRES": "surface", "TCDC": "entire"}
_lock = threading.Lock()


def _urls(valid):
    d = valid.strftime("%Y%m%d")
    base = f"{BUCKET}/urma2p5.{d}/urma2p5.t{valid.hour:02d}z.2dvaranl_ndfd.grb2"
    return [base + "_wexp", base]  # newer files carry the _wexp suffix


def fetch(valid, var, tries=3):
    for k in range(tries):
        try:
            u = None
            for cand in _urls(valid):
                r = requests.get(cand + ".idx", timeout=30)
                if r.status_code == 200:
                    u = cand
                    break
            if u is None:
                return None
            rows = [l.split(":") for l in r.text.strip().split("\n")]
            for i, row in enumerate(rows):
                if row[3] == var and row[4].startswith(VARS[var]):
                    a = int(row[1])
                    b = int(rows[i + 1][1]) - 1 if i + 1 < len(rows) else ""
                    g = requests.get(u, headers={"Range": f"bytes={a}-{b}"}, timeout=90).content
                    h = eccodes.codes_new_from_message(g)
                    try:
                        near = eccodes.codes_grib_find_nearest(h, LAT, LON, is_lsm=False, npoints=4)
                    finally:
                        eccodes.codes_release(h)
                    return [[round(n["lat"], 4), round(n["lon"] - 360, 4), round(n["distance"], 2),
                             float(n["value"])] for n in near]
            return None
        except Exception:  # noqa: BLE001
            time.sleep(2 * (k + 1))
    return None


def run(start, end, vars_, step_h=1):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "urma_cell.jsonl"
    done = set()
    if out.exists():
        for line in open(out):
            r = json.loads(line)
            done.add((r["valid"], r["var"]))
    t = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    stop = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(hours=23)
    jobs = []
    while t <= stop:
        for v in vars_:
            if (t.strftime("%Y-%m-%dT%H:00Z"), v) not in done:
                jobs.append((t, v))
        t += timedelta(hours=step_h)
    print(f"{len(jobs)} variable-hours to fetch ({len(done)} already done)", flush=True)

    def work(job):
        valid, v = job
        nb = fetch(valid, v)
        time.sleep(PAUSE_S)
        if nb is None:
            return 0
        with _lock, open(out, "a") as f:
            f.write(json.dumps({"valid": valid.strftime("%Y-%m-%dT%H:00Z"), "var": v, "nb": nb}) + "\n")
        return 1

    n_ok = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for i, ok in enumerate(ex.map(work, jobs), 1):
            n_ok += ok
            if i % 100 == 0:
                print(f"  {i}/{len(jobs)} ({n_ok} ok)", flush=True)
    print(f"done: {n_ok}/{len(jobs)} fetched", flush=True)


if __name__ == "__main__":
    import os
    if len(sys.argv) < 3:   # the digest imports every analysis/*.py: no args = usage, clean exit
        print(__doc__)
        sys.exit(0)
    s, e = sys.argv[1], sys.argv[2]
    run(s, e, sys.argv[3:] or ["TMP"], int(os.environ.get("URMA_STEP_H", "1")))

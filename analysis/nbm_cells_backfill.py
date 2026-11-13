"""Backfill NBM 2 m temperature at the 8 grid cells nearest the house, for cell-choice tests.

Our ingester takes one cell (the nearest, a land cell); the cells 2-4 km away include water cells
that read up to ~11 F warmer in autumn. This stores the 8 nearest cells per (cycle, lead) so the
best cell mix can be fitted against independent truth. Source: public AWS bucket noaa-nbm-grib2-pds
(byte-range GETs, ~5 MB each). No Google Cloud is touched. Resumable.

    .venv/bin/python -m analysis.nbm_cells_backfill 2026-10-01 2026-11-11
"""
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import eccodes
import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from weather_collector.config import LAT, LON  # noqa: E402

OUT = ROOT / "analysis" / "output" / "nbm_cells" / "nbm_tmp_cells.jsonl"
BASE = "https://noaa-nbm-grib2-pds.s3.amazonaws.com"
CYCLES = (0, 6, 12, 18)
LEADS = (6, 12, 24, 36, 47)
WORKERS = 2
PAUSE_S = 0.25
NCELL = 8
_lock = threading.Lock()


def _km(lats, lons):
    la, lo = np.radians(lats), np.radians(lons - (LON + 360))
    p = np.radians(LAT)
    a = np.sin((la - p) / 2) ** 2 + np.cos(p) * np.cos(la) * np.sin(lo / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))


def fetch(cycle_dt, lead, tries=3):
    ymd, hh = cycle_dt.strftime("%Y%m%d"), cycle_dt.strftime("%H")
    u = f"{BASE}/blend.{ymd}/{hh}/core/blend.t{hh}z.core.f{lead:03d}.co.grib2"
    for k in range(tries):
        try:
            r = requests.get(u + ".idx", timeout=30)
            if r.status_code != 200:
                return None
            rows = [l.split(":") for l in r.text.strip().split("\n")]
            for i, row in enumerate(rows):
                if len(row) > 4 and row[3] == "TMP" and row[4].startswith("2 m above"):
                    a = int(row[1])
                    b = int(rows[i + 1][1]) - 1 if i + 1 < len(rows) else ""
                    g = requests.get(u, headers={"Range": f"bytes={a}-{b}"}, timeout=90).content
                    h = eccodes.codes_new_from_message(g)
                    try:
                        lats = eccodes.codes_get_array(h, "latitudes")
                        lons = eccodes.codes_get_array(h, "longitudes")
                        vals = eccodes.codes_get_array(h, "values")
                    finally:
                        eccodes.codes_release(h)
                    d = _km(lats, lons)
                    o = np.argsort(d)[:NCELL]
                    return [[round(float(lats[j]), 4), round(float(lons[j]) - 360, 4),
                             round(float(d[j]), 2), round(float(vals[j]), 2)] for j in o]
            return None
        except Exception:  # noqa: BLE001
            time.sleep(2 * (k + 1))
    return None


def run(start, end):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if OUT.exists():
        for line in open(OUT):
            r = json.loads(line)
            done.add((r["cycle"], r["lead"]))
    t = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    stop = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    jobs = []
    while t <= stop:
        for hh in CYCLES:
            c = t.replace(hour=hh)
            for ld in LEADS:
                if (c.strftime("%Y%m%d%H"), ld) not in done:
                    jobs.append((c, ld))
        t += timedelta(days=1)
    print(f"{len(jobs)} messages to fetch ({len(done)} done)", flush=True)

    def work(job):
        c, ld = job
        cells = fetch(c, ld)
        time.sleep(PAUSE_S)
        if cells is None:
            return 0
        with _lock, open(OUT, "a") as f:
            f.write(json.dumps({"cycle": c.strftime("%Y%m%d%H"), "lead": ld,
                                "valid": (c + timedelta(hours=ld)).strftime("%Y-%m-%dT%H:00Z"),
                                "cells": cells}) + "\n")
        return 1

    ok = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for i, r in enumerate(ex.map(work, jobs), 1):
            ok += r
            if i % 50 == 0:
                print(f"  {i}/{len(jobs)} ({ok} ok)", flush=True)
    print(f"done: {ok}/{len(jobs)}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:   # the digest runs every analysis/*.py: no args = usage, clean exit
        print(__doc__)
        sys.exit(0)
    run(sys.argv[1], sys.argv[2])

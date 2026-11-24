"""GOES-19 ABI cloud-top height (ABI-L2-ACHAC) at the Cove: a satellite read of WHICH LAYER the cloud tops are in.

Per UTC hour (first CONUS scan of the hour), 3x3 pixels at the Cove: fraction of pixels whose top is low (< 2 km, the
model's "below ~6,500 ft"), mid (2-6 km) or high (> 6 km, "above ~20,000 ft"). Pixels with no height (clear or no retrieval) count in
no layer. A satellite sees only the TOPMOST cloud, so a high deck hides what is under it: high is nearly complete, mid and low are
lower bounds. Analysis only; nothing here is served.

    PYTHONPATH=. .venv/bin/python -m analysis.goes_cloud_layers fetch [days_back=14]
    PYTHONPATH=. .venv/bin/python -m analysis.goes_cloud_layers score
"""
import io
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from analysis.goes_cc_truth import LAT, LON, _get, scan_angles

BUCKET = "https://noaa-goes19.s3.amazonaws.com/"
OUT = Path(__file__).resolve().parent / "output" / "goes_cloud_layers.jsonl"
LOW_M, HIGH_M = 2000.0, 6000.0


def list_hour(dt):
    pre = f"ABI-L2-ACHAC/{dt:%Y}/{dt.timetuple().tm_yday:03d}/{dt:%H}/"
    xml = _get(f"{BUCKET}?list-type=2&prefix={pre}").decode()
    return sorted(re.findall(r"<Key>([^<]+\.nc)</Key>", xml))


def read_cove(raw):
    import h5py
    f = h5py.File(io.BytesIO(raw), "r")
    x, y = scan_angles(LAT, LON)
    xs, ys = f["x"], f["y"]
    xv = xs[:].astype("float64") * float(xs.attrs["scale_factor"][0]) + float(xs.attrs["add_offset"][0])
    yv = ys[:].astype("float64") * float(ys.attrs["scale_factor"][0]) + float(ys.attrs["add_offset"][0])
    i, j = int(np.argmin(np.abs(yv - y))), int(np.argmin(np.abs(xv - x)))
    ht = f["HT"]
    sc, fill = float(ht.attrs["scale_factor"][0]), int(ht.attrs["_FillValue"][0])
    a = ht[i - 1:i + 2, j - 1:j + 2].astype("float64")
    ok = a != fill
    m = a * sc
    return {"low": round(float(((m < LOW_M) & ok).sum() / 9), 3),
            "mid": round(float(((m >= LOW_M) & (m < HIGH_M) & ok).sum() / 9), 3),
            "high": round(float(((m >= HIGH_M) & ok).sum() / 9), 3),
            "n_ht": int(ok.sum()),
            "ht": [round(float(v)) if o else None for v, o in zip(m.ravel(), ok.ravel())]}


def fetch(days_back=14):
    OUT.parent.mkdir(exist_ok=True)
    have = {json.loads(l)["hour"] for l in OUT.open() if l.strip()} if OUT.exists() else set()
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    n_new = n_miss = 0
    with OUT.open("a") as fh:
        for dt in sorted(now - timedelta(hours=h) for h in range(1, days_back * 24 + 1)):
            k = dt.strftime("%Y-%m-%dT%H")
            if k in have:
                continue
            try:
                keys = list_hour(dt)
                if not keys:
                    n_miss += 1
                    continue
                rec = read_cove(_get(BUCKET + keys[0]))
                rec["hour"] = k
                fh.write(json.dumps(rec) + "\n")
                n_new += 1
            except Exception as e:  # noqa: BLE001
                n_miss += 1
                print(f"  {k}: {e}")
    print(f"goes_cloud_layers: {n_new} new, {n_miss} missed, {len(have)} stored -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "fetch":
        fetch(int(sys.argv[2]) if len(sys.argv) > 2 else 14)
    else:
        print("usage: fetch [days] | score (see goes_cloud_layers_score.py)")

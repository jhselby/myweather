"""GOES-19 (GOES-East) ABI clear-sky mask at the Cove: an independent cloud-cover observation.

Reads the public NOAA bucket noaa-goes19 (ABI-L2-ACMC, CONUS scan, 5 min, ~2 km pixels), one
file per UTC hour (the scan starting nearest :00), and writes, for the Cove pixel and its 3x3 /
5x5 rings, the fraction of pixels classed cloudy. Append-only jsonl keyed by hour; reruns skip
hours already stored. Analysis only: nothing here is served or deployed.

ACM classes: 0 clear, 1 probably clear, 2 probably cloudy, 3 cloudy. Fraction cloudy = classes
2-3 over valid pixels (a pixel is the satellite's view of cloud TOPS: low cloud under a high
deck is hidden, night low-cloud detection is weaker, tall cloud is parallax-shifted a few km).

    PYTHONPATH=. .venv/bin/python analysis/goes_cc_truth.py [days_back=14]
"""
import io
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

LAT, LON = 42.5014, -70.8750
BUCKET = "https://noaa-goes19.s3.amazonaws.com/"
OUT = Path(__file__).resolve().parent / "output" / "goes_cc_truth.jsonl"
UA = {"User-Agent": "curl"}


def _get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def scan_angles(lat, lon, lon0=-75.0, H=42164160.0, req=6378137.0, rpol=6356752.31414):
    """Geodetic lat/lon (deg) -> GOES fixed-grid (x, y) scan angles in radians (GOES-R PUG)."""
    phi, lam = np.radians(lat), np.radians(lon)
    phic = np.arctan((rpol ** 2 / req ** 2) * np.tan(phi))
    e2 = 1 - rpol ** 2 / req ** 2
    rc = rpol / np.sqrt(1 - e2 * np.cos(phic) ** 2)
    sx = H - rc * np.cos(phic) * np.cos(lam - np.radians(lon0))
    sy = -rc * np.cos(phic) * np.sin(lam - np.radians(lon0))
    sz = rc * np.sin(phic)
    return np.arcsin(-sy / np.sqrt(sx ** 2 + sy ** 2 + sz ** 2)), np.arctan(sz / sx)


def hour_key(dt):
    return dt.strftime("%Y-%m-%dT%H")


def list_hour(dt):
    """Keys of the ACMC files for this UTC hour, sorted by scan start."""
    pre = f"ABI-L2-ACMC/{dt:%Y}/{dt.timetuple().tm_yday:03d}/{dt:%H}/"
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
    acm = f["ACM"]
    scale = acm.attrs.get("scale_factor", [1])[0]
    off = acm.attrs.get("add_offset", [0])[0]
    fill = acm.attrs.get("_FillValue", [255])[0]
    out = {"pix_ij": [i, j]}
    for r, name in ((1, "cf3"), (2, "cf5")):
        a = acm[i - r:i + r + 1, j - r:j + r + 1].astype("float64")
        ok = a != fill
        a = np.round(a * scale + off)
        out[name] = round(float(((a >= 2) & ok).sum() / ok.sum()), 3) if ok.any() else None
    c = int(acm[i, j])
    out["center"] = None if c == fill else int(round(c * scale + off))
    return out


def main(days_back=14):
    OUT.parent.mkdir(exist_ok=True)
    have = set()
    if OUT.exists():
        have = {json.loads(l)["hour"] for l in OUT.open() if l.strip()}
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hrs = [now - timedelta(hours=h) for h in range(1, days_back * 24 + 1)]
    n_new = n_miss = 0
    with OUT.open("a") as fh:
        for dt in sorted(hrs):
            k = hour_key(dt)
            if k in have:
                continue
            try:
                keys = list_hour(dt)
                if not keys:
                    n_miss += 1
                    continue
                rec = read_cove(_get(BUCKET + keys[0]))
                rec.update(hour=k, file=keys[0].rsplit("/", 1)[-1])
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                n_new += 1
            except Exception as e:  # noqa: BLE001
                n_miss += 1
                print(f"  {k}: {e}")
    print(f"goes_cc_truth: {n_new} new hours, {n_miss} missed, {len(have)} already stored -> {OUT}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 14)

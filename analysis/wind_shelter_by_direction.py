"""How sheltered is the Cove, by wind direction? (Joe 11-27: less wind than expected in the E/NE storm.)

URMA (2.5 km grid) has no idea the Cove sits below the Cliffs, so on sheltered directions it should
overstate the Cove's wind. This measures, per flow direction, each wind reader's speed / URMA speed:
  - Cove waterfront anemometers: Driftwood Rd (0.21 mi), Neptune Rd (0.43 mi)
  - all Tempest stations (median), for comparison
  - KBOS and KBVY (open airports), the control: if URMA is fine at open sites their ratio stays flat by direction
Flow direction per hour = vector mean of KBOS + KBVY METAR direction (independent of the Cove stations).
Hours with URMA < MIN_URMA_MPH are dropped (direction and ratio are noise in light air).
Exposure = sector ratio / the same reader's ratio in the exposed W-N sectors, set beside
config.WIND_EXPOSURE_TABLE (a hand-set table that feeds only the wind worry score).

Read-only, nothing served changes. Archive: gs://myweather-data/station_readings/ (from 11-08).

    PYTHONPATH=. .venv/bin/python -m analysis.wind_shelter_by_direction [dir_with_station_readings_json]
"""
import collections
import json
import math
import statistics as st
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis._output import out as _out  # noqa: E402
from analysis.truth_compare import _urma  # noqa: E402
from weather_collector.config import WIND_EXPOSURE_TABLE  # noqa: E402

COVE = {"226429": "Driftwood Rd", "192019": "Neptune Rd"}
MIN_URMA_MPH = 8.0
KT_TO_MPH = 1.15078
SECTORS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
EXPOSED = {"W", "NW", "N"}
OUT = _out("wind_shelter_by_direction.json")


def sector(deg):
    return SECTORS[int(((deg % 360) + 22.5) // 45) % 8]


def station_hours(d):
    """{UTC 'YYYY-MM-DDTHH': {reader: mean ws over the hour's ticks}} from the Tempest archive."""
    acc = collections.defaultdict(lambda: collections.defaultdict(list))
    for f in sorted(Path(d).glob("*.json")):
        for t in json.load(open(f)).get("ticks") or []:
            h = t["ts"][:13]
            vals = []
            for sid, r in (t.get("readings") or {}).items():
                if not r.get("valid") or (r.get("age_min") or 0) >= 15 or r.get("ws") is None:
                    continue
                vals.append(r["ws"])
                if sid in COVE:
                    acc[h][COVE[sid]].append(r["ws"])
            if len(vals) >= 8:
                acc[h]["Tempest median"].append(st.median(vals))
    return {h: {k: st.mean(v) for k, v in rd.items()} for h, rd in acc.items()}


def airports(d0, d1):
    """{UTC hour: {"KBOS": mph, "KBVY": mph, "dir": vector-mean deg}} from the IEM ASOS archive (routine METARs)."""
    out = collections.defaultdict(dict)
    dirs = collections.defaultdict(list)
    for stn in ("BOS", "BVY"):
        url = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=" + stn + "&data=sknt&data=drct"
               f"&year1={d0.year}&month1={d0.month}&day1={d0.day}&year2={d1.year}&month2={d1.month}&day2={d1.day}"
               "&tz=Etc/UTC&format=onlycomma&latlon=no&missing=M&trace=T&direct=no&report_type=3")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        for attempt in range(4):   # IEM answers 429 to back-to-back requests
            try:
                rows = urllib.request.urlopen(req, timeout=60).read().decode().splitlines()
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 3:
                    raise
                time.sleep(10 * (attempt + 1))
        hdr = rows[0].split(",")
        for line in rows[1:]:
            r = dict(zip(hdr, line.split(",")))
            ts = datetime.strptime(r["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            if ts.minute < 45:   # routine METARs land at :51-:54; credit them to the next whole hour
                continue
            h = datetime.fromtimestamp(ts.timestamp() + 3600, timezone.utc).strftime("%Y-%m-%dT%H")
            if r.get("sknt") in (None, "M", ""):
                continue
            kt = float(r["sknt"])
            out[h]["K" + stn] = kt * KT_TO_MPH
            if r.get("drct") not in (None, "M", "", "VRB") and kt >= 5:
                a = math.radians(float(r["drct"]))
                dirs[h].append((kt * math.sin(a), kt * math.cos(a)))
    for h, v in dirs.items():
        u, w = sum(x[0] for x in v), sum(x[1] for x in v)
        out[h]["dir"] = math.degrees(math.atan2(u, w)) % 360
    return out


def table_factor(deg):
    for lo, hi, f in WIND_EXPOSURE_TABLE:
        if lo <= deg < hi:
            return f
    return None


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else None
    if d is None:
        from analysis.mesonet_validation import _download
        d = _download()
    stn = station_hours(d)
    U = {k: v for k, v in _urma("WIND", "urma_truth_wind.json").items()}
    hours = sorted(set(stn) & set(U))
    d0 = datetime.strptime(hours[0][:10], "%Y-%m-%d")
    d1 = datetime.strptime(hours[-1][:10], "%Y-%m-%d")
    ap = airports(d0, datetime.fromordinal(d1.toordinal() + 1))

    ratios = collections.defaultdict(lambda: collections.defaultdict(list))   # reader -> sector -> [ratio]
    n_hours = collections.Counter()
    for h in hours:
        u, a = U[h], ap.get(h) or {}
        if u < MIN_URMA_MPH or "dir" not in a:
            continue
        s = sector(a["dir"])
        n_hours[s] += 1
        readers = dict(stn[h])
        readers.update({k: a[k] for k in ("KBOS", "KBVY") if k in a})
        for k, v in readers.items():
            ratios[k][s].append(v / u)

    res = {"window": f"{hours[0][:10]}..{hours[-1][:10]} UTC", "min_urma_mph": MIN_URMA_MPH,
           "hours_by_sector": dict(n_hours), "readers": {}}
    print(f"Wind / URMA by flow direction (KBOS+KBVY), URMA >= {MIN_URMA_MPH:.0f} mph, {res['window']}")
    print("hours  " + " ".join(f"{s:>6}" for s in SECTORS) + "\n       " + " ".join(f"{n_hours[s]:>6}" for s in SECTORS))
    for k in ["Driftwood Rd", "Neptune Rd", "Tempest median", "KBOS", "KBVY"]:
        med = {s: (st.median(ratios[k][s]) if len(ratios[k][s]) >= 6 else None) for s in SECTORS}
        ex = [x for s in EXPOSED for x in ratios[k][s]]
        base = st.median(ex) if len(ex) >= 12 else None
        rel = {s: (round(med[s] / base, 2) if med[s] is not None and base else None) for s in SECTORS}
        res["readers"][k] = {"ratio_median": {s: (round(v, 2) if v is not None else None) for s, v in med.items()},
                             "n": {s: len(ratios[k][s]) for s in SECTORS},
                             "exposed_ratio": round(base, 2) if base else None, "exposure_vs_W_N": rel}
        print(f"{k:15s} ratio  " + " ".join(f"{med[s]:6.2f}" if med[s] is not None else "     -" for s in SECTORS))
        print(f"{'':15s} vs W-N " + " ".join(f"{rel[s]:6.2f}" if rel[s] is not None else "     -" for s in SECTORS))
    tbl = {s: table_factor(i * 45) for i, s in enumerate(SECTORS)}
    res["config_table_at_sector_centre"] = tbl
    print(f"{'config table':15s}        " + " ".join(f"{tbl[s]:6.2f}" if tbl[s] is not None else "     -" for s in SECTORS))
    Path(OUT).write_text(json.dumps(res, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

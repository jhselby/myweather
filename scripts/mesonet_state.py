#!/usr/bin/env python3
"""Write mesonet.json for the showcase page (public-safe: no station ids, names or exact positions).

  stations     - one dot per working station: kind (tempest | wu_live | wu), position ROUNDED to 0.005 deg
                 (~400 m) so the page never pins a neighbour's house. The homebuilt station is counted,
                 not placed. Positions come from the newest station_readings/ and wu_readings_hourly/ files.
  counts       - working / silent per network (WU: 41 configured, silent = no reading in the last 7 days).
  measurements - dated results parsed from the digest logs of analysis/mesonet_vs_urma.py and
                 analysis/l2_wu_replay.py (analysis/output/runlog/*.log); absent if a log is missing.
Run by build.py after architecture_state.py, or alone:  python3 scripts/mesonet_state.py
"""
import gzip
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("WU_API_KEY", "unset")
BUCKET = "gs://myweather-data/"


def _cat(path):
    out = subprocess.run(["gsutil", "cat", BUCKET + path], capture_output=True)
    if out.returncode:
        return None
    raw = out.stdout
    return json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)


def _round(v):
    return round(round(v / 0.005) * 0.005, 3)


def _verdict(name):
    p = ROOT / "analysis" / "output" / "runlog" / f"{name}.log"
    if not p.exists():
        return None
    for line in p.read_text().splitlines():
        if line.startswith("VERDICT"):
            return line
    return None


def main():
    from weather_collector.fetchers.wu_scraper_realtime import STATIONS, CULLED_STATIONS
    from weather_collector.processors.wu_archive import LIVE_STATIONS, OWN_STATION
    now = datetime.now(timezone.utc)
    days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(0, 8)]

    tempest, last_day = [], None
    for d in days:
        doc = _cat(f"station_readings/{d}.json")
        if doc and doc.get("ticks"):
            last_day = d
            ok_ids = {sid for sid, v in doc["ticks"][-1]["readings"].items() if v.get("valid")}
            for sid, m in doc["stations"].items():
                if m.get("latitude") is not None:
                    tempest.append({"kind": "tempest", "lat": _round(m["latitude"]), "lon": _round(m["longitude"]),
                                    "ok": sid in ok_ids})
            break

    wu_pos = {}
    for d in days:
        for sid, m in ((_cat(f"wu_readings_hourly/{d}.json") or {}).get("stations") or {}).items():
            if m.get("lat") is not None:
                wu_pos.setdefault(sid, (m["lat"], m["lon"]))
        for sid, m in ((_cat(f"wu_readings/{d}.json") or {}).get("stations") or {}).items():
            if m.get("lat") is not None:
                wu_pos.setdefault(sid, (m["lat"], m["lon"]))
    wu = [{"kind": "wu_live" if sid in LIVE_STATIONS else "wu", "lat": _round(la), "lon": _round(lo), "ok": True}
          for sid, (la, lo) in wu_pos.items() if sid != OWN_STATION]

    meas = {}
    v1, v2 = _verdict("mesonet_vs_urma"), _verdict("l2_wu_replay")
    if v1:
        m = re.search(r"Tempest ([\d.]+)F, Tempest\+WU live set ([\d.]+)F, Tempest\+WU all ([\d.]+)F, WU live alone ([\d.]+)F \((\d+) URMA hours", v1)
        if m:
            meas["network_vs_urma"] = {"tempest": float(m[1]), "tempest_plus_wu": float(m[2]), "wu_all": float(m[3]),
                                       "wu_live_alone": float(m[4]), "hours": int(m[5])}
    if v2:
        m = re.search(r"raw model ([\d.]+)F, L2-style with Tempest ([\d.]+)F, with Tempest\+WU live ([\d.]+)F \(WU effect ([+-][\d.]+)%.*?; (\d+) origins", v2)
        if m:
            meas["forecast_replay"] = {"raw": float(m[1]), "tempest": float(m[2]), "tempest_plus_wu": float(m[3]),
                                       "wu_effect_pct": float(m[4]), "origins": int(m[5])}
    out = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%MZ"),
        "tempest_day": last_day,
        "stations": tempest + wu,
        "counts": {
            "tempest_ok": sum(1 for s in tempest if s["ok"]), "tempest_total": len(tempest),
            "wu_ok": len(wu), "wu_live": sum(1 for s in wu if s["kind"] == "wu_live"),
            "wu_configured": len(STATIONS), "wu_silent": len(STATIONS) - len([s for s in wu_pos if s in STATIONS]),
            "wu_retired": len(CULLED_STATIONS), "homebuilt": 1,
        },
        "measurements": meas,
    }
    (ROOT / "mesonet.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"mesonet.json: {len(out['stations'])} dots, counts {out['counts']}, measurements {list(meas)}")


if __name__ == "__main__":
    main()

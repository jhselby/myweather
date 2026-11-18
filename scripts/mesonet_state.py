#!/usr/bin/env python3
"""Write mesonet.json: the station map's data (debug page front + section 2f, showcase).

Public-safe by construction: neighbour stations carry NO id or name and their position is ROUNDED to
0.005 deg (~400 m). The homebuilt station is counted and listed in `own`, never placed. Only the live
WU set (operational, ids already public on WU) carries ids, in `live`, for the 2f status table.

  stations     - one record per working station: k (tempest | wu_live | wu), lat/lon rounded, ok,
                 rmse (held-out error vs URMA, F), od/on (day/night offset vs URMA, F), up (7-day uptime),
                 t/rh/p/ts (latest reading, as of `generated_at`).
  live / own   - the live set and the homebuilt station with the same fields (+ id for live).
  counts       - working / silent / retired per network.
  measurements - dated results parsed from the digest logs of analysis/mesonet_vs_urma.py and
                 analysis/l2_wu_replay.py (analysis/output/runlog/*.log), incl. the replay by lead.
Written to the repo root and (with --upload) to gs://myweather-data/mesonet.json so the page reads it
from data.wymancove.com without a commit. Run by build.py and the digest; or alone:
  python3 scripts/mesonet_state.py [--upload]
"""
import gzip
import json
import math
import os
import re
import statistics as st
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


def _log(name):
    p = ROOT / "analysis" / "output" / "runlog" / f"{name}.log"
    return p.read_text().splitlines() if p.exists() else []


def _iso(ep):
    return datetime.fromtimestamp(ep, timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def measurements():
    meas = {}
    for line in _log("mesonet_vs_urma"):
        if line.startswith("VERDICT"):
            m = re.search(r"Tempest ([\d.]+)F, Tempest\+WU live set ([\d.]+)F, Tempest\+WU all ([\d.]+)F, WU live alone ([\d.]+)F \((\d+) URMA hours", line)
            if m:
                meas["network_vs_urma"] = {"tempest": float(m[1]), "tempest_plus_wu": float(m[2]), "wu_all": float(m[3]),
                                           "wu_live_alone": float(m[4]), "hours": int(m[5])}
    lines = _log("l2_wu_replay")
    rep = {}
    for line in lines:
        m = re.match(r"(Tempest \+ WU live|Tempest|WU live set|none \(raw model\))\s+((?:[\d.]+\s+){6})\s*([\d.]+)", line)
        if m:
            rep[m[1]] = [float(x) for x in m[2].split()]
        if line.startswith("VERDICT"):
            m = re.search(r"raw model ([\d.]+)F, L2-style with Tempest ([\d.]+)F, with Tempest\+WU live ([\d.]+)F \(WU effect ([+-][\d.]+)%.*?; (\d+) origins", line)
            if m:
                meas["forecast_replay"] = {"raw": float(m[1]), "tempest": float(m[2]), "tempest_plus_wu": float(m[3]),
                                           "wu_effect_pct": float(m[4]), "origins": int(m[5])}
    if rep and "forecast_replay" in meas:
        meas["forecast_replay"]["by_lead"] = {"leads_h": [1, 2, 3, 4, 5, 6], "raw": rep.get("none (raw model)"),
                                              "tempest": rep.get("Tempest"), "tempest_plus_wu": rep.get("Tempest + WU live")}
    return meas


def main():
    from analysis import mesonet_vs_urma as M
    from weather_collector.fetchers.wu_scraper_realtime import STATIONS, CULLED_STATIONS
    from weather_collector.processors.wu_archive import LIVE_STATIONS, OWN_STATION
    now = datetime.now(timezone.utc)
    days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(0, 9)]
    d0 = (now - timedelta(days=8)).strftime("%Y-%m-%d")

    urma = M.urma_series()
    series = {**M.tempest_series(days), **M.wu_series(days)}
    table = M.station_table(series, urma, days)

    # ---- Tempest: latest tick for position, status and reading
    tempest = []
    for d in days:
        doc = _cat(f"station_readings/{d}.json")
        if not (doc and doc.get("ticks")):
            continue
        last = doc["ticks"][-1]
        ts = last["ts"]
        valid_frac = {}
        for sid in doc["stations"]:
            rows = [t["readings"].get(sid) for t in doc["ticks"]]
            rows = [r for r in rows if r]
            valid_frac[sid] = round(sum(1 for r in rows if r.get("valid")) / max(len(doc["ticks"]), 1), 2)
        for sid, m in doc["stations"].items():
            if m.get("latitude") is None:
                continue
            r = last["readings"].get(sid) or {}
            sc = table.get("T:" + sid) or {}
            tempest.append({
                "k": "tempest", "lat": _round(m["latitude"]), "lon": _round(m["longitude"]), "ok": bool(r.get("valid")),
                "rmse": round(sc["rmse"], 2) if sc else None,
                "od": round(sc["off_day"], 2) if sc.get("off_day") is not None else None,
                "on": round(sc["off_night"], 2) if sc.get("off_night") is not None else None,
                "up": valid_frac.get(sid), "t": r.get("t"), "rh": r.get("rh"),
                "p": round(r["p_mb"] * 0.02953, 2) if r.get("p_mb") is not None else None, "ts": ts})
        break

    # ---- WU: positions from the backfill/archive, latest reading, 7-day uptime
    pos, latest, count = {}, {}, {}
    for d in days:
        for prefix in ("wu_readings", "wu_readings_hourly"):
            doc = _cat(f"{prefix}/{d}.json") or {}
            for sid, m in (doc.get("stations") or {}).items():
                if m.get("lat") is not None:
                    pos.setdefault(sid, (m["lat"], m["lon"]))
            for sid, rows in (doc.get("obs") or {}).items():
                if prefix == "wu_readings_hourly":
                    count[sid] = count.get(sid, 0) + len(rows)
                for r in rows:
                    if sid not in latest or r["ep"] > latest[sid]["ep"]:
                        latest[sid] = r
    cut = now.timestamp() - 7 * 86400

    def wu_rec(sid):
        sc = table.get(sid) or {}
        r = latest.get(sid) or {}
        return {"lat": _round(pos[sid][0]), "lon": _round(pos[sid][1]), "ok": True,
                "rmse": round(sc["rmse"], 2) if sc else None,
                "od": round(sc["off_day"], 2) if sc.get("off_day") is not None else None,
                "on": round(sc["off_night"], 2) if sc.get("off_night") is not None else None,
                "up": round(min(1.0, count.get(sid, 0) / 168), 2), "t": r.get("t"), "rh": r.get("rh"), "p": r.get("p"),
                "ts": _iso(r["ep"]) if r.get("ep") else None}

    wu, live = [], []
    for sid in pos:
        if sid == OWN_STATION:
            continue
        rec = wu_rec(sid)
        if sid in LIVE_STATIONS:
            rec["k"] = "wu_live"
            live.append({"id": sid, **rec})
        else:
            rec["k"] = "wu"
        wu.append(rec)
    live.sort(key=lambda r: LIVE_STATIONS.index(r["id"]))
    own = None
    if OWN_STATION in latest:
        r = latest[OWN_STATION]
        sc = table.get(OWN_STATION) or {}
        own = {"t": r.get("t"), "rh": r.get("rh"), "p": r.get("p"), "ts": _iso(r["ep"]),
               "rmse": round(sc["rmse"], 2) if sc else None, "n": len(series.get(OWN_STATION, {}))}

    out = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%MZ"),
        "stations": tempest + wu,
        "live": live,
        "own": own,
        "counts": {
            "tempest_ok": sum(1 for s in tempest if s["ok"]), "tempest_total": len(tempest),
            "wu_ok": len(wu), "wu_live": len(live), "wu_configured": len(STATIONS),
            "wu_silent": len(STATIONS) - len([s for s in pos if s in STATIONS]),
            "wu_retired": len(CULLED_STATIONS), "homebuilt": 1,
        },
        "urma_hours": len([h for h in urma if M.day_of(h) in days]),
        "measurements": measurements(),
    }
    text = json.dumps(out, separators=(",", ":"))
    (ROOT / "mesonet.json").write_text(text + "\n")
    scored = sum(1 for s in out["stations"] if s["rmse"] is not None)
    print(f"mesonet.json: {len(out['stations'])} dots ({scored} scored), live {len(live)}, own {'yes' if own else 'no'}, "
          f"measurements {list(out['measurements'])}")
    if "--upload" in sys.argv:
        subprocess.run(["gsutil", "-q", "-h", "Cache-Control:no-cache", "-h", "Content-Type:application/json",
                        "cp", str(ROOT / "mesonet.json"), BUCKET + "mesonet.json"], check=True)
        print("uploaded to", BUCKET + "mesonet.json")


if __name__ == "__main__":
    main()

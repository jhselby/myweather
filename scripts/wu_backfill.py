#!/usr/bin/env python3
"""Backfill WU station history into gs://myweather-data/wu_readings_hourly/<UTC date>.json.

WU never gave us a per-station archive (the collector only kept network aggregates), but its PWS
API returns history: observations/hourly/7day = the last 7 days of hourly rows in ONE call per
station; history/hourly?date=YYYYMMDD = one past day per call (any date the station reported).
Same schema as wu_readings/ ({"schema":1,"stations":{id:{lat,lon}},"obs":{id:[{ep,t,dp,rh,ws,wg,wd,p}]}}),
hourly resolution, deduped on epoch.

Not in analysis/ on purpose: the digest runs every analysis/*.py and this spends API calls.
The key comes from the WU_API_KEY env var (never printed). Stops on the first 401/429.

Usage:
  WU_API_KEY=... python3 scripts/wu_backfill.py week                 # 1 call/station, last 7 days
  WU_API_KEY=... python3 scripts/wu_backfill.py dates 20260901 20260905 [--max-calls 150]
"""
import argparse
import gzip
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("WU_API_KEY", "unset")  # wu_scraper_realtime reads it at import; we pass our own
from weather_collector.fetchers.wu_scraper_realtime import STATIONS  # noqa: E402
from weather_collector.processors.wu_archive import OWN_STATION, _row  # noqa: E402

BUCKET = "gs://myweather-data/wu_readings_hourly/"
PAUSE_S = 2.5
URLS = {"week": "https://api.weather.com/v2/pws/observations/hourly/7day",
        "date": "https://api.weather.com/v2/pws/history/hourly"}


def fetch(sid, key, mode, date=None):
    params = {"stationId": sid, "format": "json", "units": "e", "numericPrecision": "decimal", "apiKey": key}
    if date:
        params["date"] = date
    r = requests.get(URLS[mode], params=params, timeout=25)
    if r.status_code in (401, 429):
        return None, None, None, "blocked"
    if r.status_code != 200:
        return [], None, None, "empty"
    obs = (r.json() or {}).get("observations") or []
    return [_row(o) for o in obs if o.get("epoch")], (obs[-1].get("lat") if obs else None), (obs[-1].get("lon") if obs else None), "ok"


def cat(path):
    out = subprocess.run(["gsutil", "cat", path], capture_output=True)
    if out.returncode:
        return None
    raw = out.stdout
    return json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)


def save_days(per_day):
    for day, add in per_day.items():
        doc = cat(BUCKET + day + ".json") or {"schema": 1, "stations": {}, "obs": {}}
        for sid, (lat, lon, rows) in add.items():
            doc["stations"][sid] = {"lat": lat, "lon": lon}
            have = {x["ep"] for x in doc["obs"].get(sid, [])}
            doc["obs"].setdefault(sid, []).extend(r for r in rows if r["ep"] not in have)
            doc["obs"][sid].sort(key=lambda r: r["ep"])
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(doc, f)
        subprocess.run(["gsutil", "-q", "cp", f.name, BUCKET + day + ".json"], check=True)
        os.unlink(f.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("week", "dates"))
    ap.add_argument("start", nargs="?")
    ap.add_argument("end", nargs="?")
    ap.add_argument("--max-calls", type=int, default=150)
    a = ap.parse_args()
    key = os.environ["WU_API_KEY"]
    ids = [OWN_STATION] + [s for s in STATIONS if s != OWN_STATION]
    jobs = [(s, "week", None) for s in ids]
    if a.mode == "dates":
        d0 = datetime.strptime(a.start, "%Y%m%d")
        d1 = datetime.strptime(a.end or a.start, "%Y%m%d")
        days = [(d0 + timedelta(days=i)).strftime("%Y%m%d") for i in range((d1 - d0).days + 1)]
        jobs = [(s, "date", d) for d in days for s in ids]
    jobs = jobs[: a.max_calls]
    per_day, calls, ok = {}, 0, 0
    for sid, mode, date in jobs:
        rows, lat, lon, st = fetch(sid, key, mode, date)
        calls += 1
        if st == "blocked":
            print(f"BLOCKED (401/429) at {sid} after {calls - 1} calls; saving what we have")
            break
        if st == "ok" and rows:
            ok += 1
            for r in rows:
                day = datetime.fromtimestamp(r["ep"], timezone.utc).strftime("%Y-%m-%d")
                per_day.setdefault(day, {}).setdefault(sid, (lat, lon, []))[2].append(r)
        time.sleep(PAUSE_S)
    save_days(per_day)
    print(f"{calls} calls, {ok} with data, wrote {len(per_day)} day files to {BUCKET}")


if __name__ == "__main__":
    main()

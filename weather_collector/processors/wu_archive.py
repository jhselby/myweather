"""
Low-volume Weather Underground archive (dormant until a working key exists).

Why: WU's ~40 Marblehead/Salem PWS are the densest mesonet around the Cove, but the old scraper
made ~35 calls every 10 min (~5,000/day) and the key was throttled in October. The
`observations/all/1day` endpoint returns a whole day of ~5-min readings per call, so polling each
station 4x a day (00/06/12/18 UTC) is ~160 calls/day and still fills a complete archive.

Off by default (WU_ARCHIVE_ENABLED) and a no-op without WU_API_KEY. Nothing served or scored reads
the archive. It stops the whole run on the first 401/429 so a throttled key is never hammered.
One GCS file per UTC day: `wu_readings/YYYY-MM-DD.json` = {"schema":1, "stations":{id:{lat,lon}},
"obs":{id:[{"ep","t","dp","rh","ws","wg","wd","p"}...]}}, deduped on epoch.
"""
import logging
import os
import time
from datetime import datetime, timezone

import requests

from ..gcs_io import load_json, upload_json
from ..utils import redact_secrets

WU_ARCHIVE_ENABLED = True
# Joe's own station (16 Indianhead Circle, HomeKit sensor: t/rh/p only). Archived with the
# neighbours but kept out of wu_scraper_realtime.STATIONS: at ~0.04 mi its 1/d^2 weight would
# swamp the live aggregate if WU_ENABLED were ever turned back on.
OWN_STATION = "KMAMARBL124"
# Live set (v0.7.112): own station + the best-tracking station in each of seven compass octants
# (N skipped: farthest, sparsest). Ranked on 7 days of hourly WU history (backfilled via
# scripts/wu_backfill.py) by residual vs the Tempest median after a day/night offset, fit on 11-12..15,
# scored on 11-16..18, confirmed on a 11-08..11 holdout (rank correlation 0.69 over 34 stations).
# Polled EVERY tick (~1,150 calls/day). Shadow only: nothing served reads the archive.
LIVE_STATIONS = (OWN_STATION, "KMAMARBL63", "KMAMARBL92", "KMAMARBL76", "KMAMARBL42",
                 "KMAMARBL8", "KMAMARBL57", "KMASALEM91")
SLOT_HOURS_UTC = (0, 12)  # the remaining neighbours: twice a day (each call returns 24 h)
SLOT_MINUTES = 10  # collector ticks at :07; only the first tick of the slot hour polls
PAUSE_S = 2.5  # slot polls: ~24 calls/min, under WU's 30/min cap
LIVE_PAUSE_S = 1.0  # live set is 8 calls per tick, well under 30/min
GCS_PREFIX = "wu_readings/"
BASE_URL = "https://api.weather.com/v2/pws/observations/all/1day"


def in_slot(now_utc):
    return now_utc.hour in SLOT_HOURS_UTC and now_utc.minute < SLOT_MINUTES


def _row(o):
    im = o.get("imperial") or {}
    return {"ep": o.get("epoch"), "t": im.get("tempAvg"), "dp": im.get("dewptAvg"),
            "rh": o.get("humidityAvg"), "ws": im.get("windspeedAvg"), "wg": im.get("windgustHigh"),
            "wd": o.get("winddirAvg"), "p": im.get("pressureMax")}


def fetch_station(sid, key, get=requests.get):
    """Returns (rows, lat, lon, status). status: ok | empty | blocked | error."""
    try:
        r = get(BASE_URL, params={"apiKey": key, "stationId": sid, "numericPrecision": "decimal",
                                  "format": "json", "units": "e"}, timeout=20)
    except Exception as e:  # noqa: BLE001
        logging.warning(f"  ⚠  wu_archive {sid}: {redact_secrets(e)}")
        return [], None, None, "error"
    if r.status_code in (401, 429):
        return [], None, None, "blocked"
    if r.status_code == 204:
        return [], None, None, "empty"
    if r.status_code != 200:
        return [], None, None, "error"
    obs = (r.json() or {}).get("observations") or []
    if not obs:
        return [], None, None, "empty"
    return [_row(o) for o in obs if o.get("epoch")], obs[-1].get("lat"), obs[-1].get("lon"), "ok"


def merge(doc, sid, rows, lat, lon):
    doc["stations"][sid] = {"lat": lat, "lon": lon}
    have = {x["ep"] for x in doc["obs"].get(sid, [])}
    new = [x for x in rows if x["ep"] not in have]
    doc["obs"].setdefault(sid, []).extend(new)
    return len(new)


def append_wu_archive(stations, now_utc=None, key=None, get=requests.get, load=load_json, save=upload_json, sleep=time.sleep):
    """Poll `stations` (WU station ids) once and merge into today's archive. Best-effort."""
    now_utc = now_utc or datetime.now(timezone.utc)
    key = key or os.environ.get("WU_API_KEY")
    if not WU_ARCHIVE_ENABLED or not key:
        return None
    live = list(LIVE_STATIONS)
    rest = [s for s in stations if s not in LIVE_STATIONS] if in_slot(now_utc) else []
    try:
        path = f"{GCS_PREFIX}{now_utc.strftime('%Y-%m-%d')}.json"
        doc = load(path, default=None) or {"schema": 1, "stations": {}, "obs": {}}
        added = ok = 0
        blocked = False
        for sid in live + rest:  # live set first, own station first of all: it survives a mid-run block
            rows, lat, lon, status = fetch_station(sid, key, get)
            if status == "blocked":
                logging.warning("  ⚠  wu_archive: key refused (401/429); stopping this run")
                blocked = True
                break
            if status == "ok":
                ok += 1
                added += merge(doc, sid, rows, lat, lon)
            sleep(LIVE_PAUSE_S if sid in LIVE_STATIONS else PAUSE_S)
        if added:
            save(doc, path, path)
        logging.info(f"  ✓ wu_archive: {ok}/{len(live) + len(rest)} stations, +{added} readings")
        return {"ok": ok, "added": added, "blocked": blocked}
    except Exception as e:  # noqa: BLE001
        logging.warning(f"  ⚠  wu_archive failed: {redact_secrets(e)}")
        return None

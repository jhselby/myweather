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

WU_ARCHIVE_ENABLED = False
SLOT_HOURS_UTC = (0, 6, 12, 18)
SLOT_MINUTES = 10  # collector ticks at :07; only the first tick of the slot hour polls
PAUSE_S = 2.5  # ~24 calls/min, under WU's 30/min cap
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
    if not WU_ARCHIVE_ENABLED or not key or not in_slot(now_utc):
        return None
    try:
        path = f"{GCS_PREFIX}{now_utc.strftime('%Y-%m-%d')}.json"
        doc = load(path, default=None) or {"schema": 1, "stations": {}, "obs": {}}
        added = ok = 0
        for sid in stations:
            rows, lat, lon, status = fetch_station(sid, key, get)
            if status == "blocked":
                logging.warning("  ⚠  wu_archive: key refused (401/429); stopping this run")
                break
            if status == "ok":
                ok += 1
                added += merge(doc, sid, rows, lat, lon)
            sleep(PAUSE_S)
        if added:
            save(doc, path, path)
        logging.info(f"  ✓ wu_archive: {ok}/{len(stations)} stations, +{added} readings")
        return {"ok": ok, "added": added}
    except Exception as e:  # noqa: BLE001
        logging.warning(f"  ⚠  wu_archive failed: {redact_secrets(e)}")
        return None

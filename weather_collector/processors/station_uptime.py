"""
Per-station uptime tracking, stored in GCS.

Each collector tick records whether every attempted station (WU + Tempest)
returned usable data. A rolling 7-day per-station log of (ts, ok) entries
lives in `station_uptime.json`. A summary block (uptime %) is also stamped
into `weather_data["hyperlocal"]["station_uptime"]` each tick so the debug
page can render it without an extra GCS fetch.

Future use: auto-cull stations whose 7d uptime drops below a threshold
(currently displayed only — culling happens manually).
"""
from datetime import datetime, timedelta

import pytz

from ..gcs_io import load_json, upload_json
from ..fetchers.wu_scraper_realtime import CULLED_STATIONS as WU_CULLED
from ..fetchers.tempest import CULLED_TEMPEST_STATIONS as TEMPEST_CULLED


GCS_PATH = "station_uptime.json"
RETENTION_DAYS = 7
TZ = pytz.timezone("America/New_York")
# Culled stations stay in the on-disk log (for manual re-probe later) but are
# hidden from the debug-page summary so the dead-count and mean-uptime aren't
# polluted by stations we've deliberately stopped hitting. Both WU and Tempest
# culls participate (Tempest cull added 2026-06-15 — previously only WU
# culled stations were filtered, so Tempest zombies leaked to the UI).
_CULLED = set(WU_CULLED) | {str(s["id"]) for s in TEMPEST_CULLED}


def update_station_uptime(weather_data, attempted_wu_ids, attempted_tempest_ids):
    """Record success/fail for every attempted station this tick.

    Returns a summary dict {sid: {uptime_pct, n_attempts, n_success}} which the
    caller stamps into weather_data["hyperlocal"]["station_uptime"]. Also
    persists the full rolling log to GCS.
    """
    now = datetime.now(TZ)
    ts = now.strftime("%Y-%m-%dT%H:%M")
    cutoff = (now - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")

    # Which stations actually returned data this tick
    wu_returned = {
        str(s.get("station_id"))
        for s in (weather_data.get("wu_stations") or {}).get("stations", [])
        if s.get("station_id") and s.get("temperature_f") is not None
    }
    tp_returned = {
        str(s.get("station_id"))
        for s in (weather_data.get("tempest") or {}).get("stations", [])
        if s.get("station_id") and s.get("valid")
    }

    log = load_json(GCS_PATH, default={"stations": {}})
    stations = log.get("stations") or {}

    def _record(sid, ok):
        sid = str(sid)
        entries = [e for e in stations.get(sid, []) if e.get("ts", "") >= cutoff]
        entries.append({"ts": ts, "ok": bool(ok)})
        stations[sid] = entries

    for sid in attempted_wu_ids:
        _record(sid, str(sid) in wu_returned)
    for sid in attempted_tempest_ids:
        _record(sid, str(sid) in tp_returned)

    summary = {}
    for sid, entries in stations.items():
        if sid in _CULLED:
            continue
        n = len(entries)
        if n == 0:
            continue
        n_ok = sum(1 for e in entries if e.get("ok"))
        summary[sid] = {
            "uptime_pct": round(100 * n_ok / n, 1),
            "n_attempts": n,
            "n_success": n_ok,
        }

    out = {"updated_at": ts, "retention_days": RETENTION_DAYS,
           "stations": stations, "summary": summary}
    try:
        upload_json(out, GCS_PATH, "station_uptime.json")
    except Exception:
        # Non-critical — fail open. Log left in memory only this tick.
        pass
    return summary

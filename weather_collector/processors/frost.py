"""
Frost/freeze tracking - season-to-date counts with historical backfill.
Season = Oct 1 through Sep 30.
"""
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

from ..config import LAT, LON, FROST_LOG_FILE


def fetch_historical_mins(season_start, today_str):
    try:
        url = (
            f"https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={LAT}&longitude={LON}"
            f"&start_date={season_start}&end_date={today_str}"
            f"&daily=temperature_2m_min&temperature_unit=fahrenheit&timezone=America/New_York"
        )
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        dates = data.get("daily", {}).get("time", [])
        mins  = data.get("daily", {}).get("temperature_2m_min", [])
        return {d: t for d, t in zip(dates, mins) if t is not None}
    except Exception as e:
        print(f"  ✗ Historical mins fetch error: {e}")
        return {}


def update_frost_log(daily_data):
    try:
        log = {}
        frost_log_file = Path(FROST_LOG_FILE)
        if frost_log_file.exists():
            try:
                log = json.loads(frost_log_file.read_text()) or {}
            except Exception:
                log = {}

        today_str    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday    = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        year         = datetime.now(timezone.utc).year
        season_start = f"{year}-10-01" if today_str >= f"{year}-10-01" else f"{year-1}-10-01"

        if log.get("season_start") != season_start:
            log = {
                "season_start":     season_start,
                "freeze_days":      0,
                "hard_freeze_days": 0,
                "severe_days":      0,
                "last_freeze":      None,
                "last_hard":        None,
                "last_severe":      None,
                "logged_dates":     [],
            }

        logged = set(log.get("logged_dates", []))

        needs_backfill = len(logged) < 5
        if needs_backfill:
            print("  ↻ Frost log: backfilling full season from Open-Meteo historical API...")
            date_mins = fetch_historical_mins(season_start, yesterday)
        else:
            daily     = (daily_data or {}).get("daily", {}) or {}
            dates     = daily.get("time", []) or []
            mins      = daily.get("temperature_2m_min", []) or []
            date_mins = {d: t for d, t in zip(dates, mins)
                         if d < today_str and t is not None}

        for d, t in sorted(date_mins.items()):
            if d < season_start or d >= today_str:
                continue
            if d in logged:
                continue
            if t <= 20:
                log["severe_days"]      += 1
                log["hard_freeze_days"] += 1
                log["freeze_days"]      += 1
                log["last_severe"] = log["last_hard"] = log["last_freeze"] = d
            elif t <= 28:
                log["hard_freeze_days"] += 1
                log["freeze_days"]      += 1
                log["last_hard"] = log["last_freeze"] = d
            elif t <= 32:
                log["freeze_days"] += 1
                log["last_freeze"]  = d
            logged.add(d)

        log["logged_dates"] = sorted(list(logged))

        daily   = (daily_data or {}).get("daily", {}) or {}
        dates   = daily.get("time", []) or []
        mins    = daily.get("temperature_2m_min", []) or []
        upcoming_freeze = []
        for d, t in zip(dates, mins):
            if d < today_str: continue
            if t is not None and t <= 32:
                upcoming_freeze.append({"date": d, "min_f": round(t, 1)})
        log["upcoming_freeze_days"] = upcoming_freeze

        frost_log_file.write_text(json.dumps(log, indent=2))
        print(f"  ✓ Frost log: {log['freeze_days']} freeze, {log['hard_freeze_days']} hard, "
              f"{log['severe_days']} severe | last: {log['last_freeze']} | "
              f"upcoming: {len(upcoming_freeze)}")
        return log

    except Exception as e:
        print(f"  ✗ Frost log error: {e}")
        return {}
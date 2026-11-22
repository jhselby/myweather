"""Daily fit of the Cove adjustment (v0.7.138, SHADOW): Mesonet -> Cove value.

The Mesonet (the other stations, calibrated to each other) cannot show the Cove's damped daily swing, so
the adjustment is learned from the Cove-side station Neptune Rd (0.43 mi, waterfront):
    A_t(ET hour) = median over the last WIN_DAYS days of (Neptune temperature - logged Mesonet station_temp)
    A_h(ET hour) = same for humidity (Neptune RH - logged station_humidity)
Each day contributes the median of its ticks in that hour; the table keeps the median across days and needs
>= MIN_DAYS days. The Mesonet value is the one the collector logged in the archive (`l2.station_temp`), so the
adjustment is learned against exactly what production publishes. Walk-forward test (analysis/mesonet_cove_adjust.py,
11-11..11-22): RMSE vs Neptune 1.59 -> 0.99 F; vs the yard sensor (never used to learn) day/night level
+1.6/-1.3 -> +0.3/-0.4 F.

Writes weather_collector/data/mesonet_cove_adjust_curated.json (the refitter publishes it to runtime_tables/).
    PYTHONPATH=. .venv/bin/python -m analysis.mesonet_cove_adjust_fit
"""
import json
import statistics as st
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ET = ZoneInfo("America/New_York")
OUT_PATH = ROOT / "weather_collector" / "data" / "mesonet_cove_adjust_curated.json"
REF_ID = "192019"          # Neptune Rd
REF_NAME = "Neptune Rd"
WIN_DAYS = 14
MIN_DAYS = 3
MIN_TICKS_PER_DAY_HOUR = 2
FIELDS = (("t", "t", "station_temp"), ("h", "rh", "station_humidity"))   # field, reading key, anchor key


def _load(day):
    from weather_collector.gcs_io import load_json
    return load_json(f"station_readings/{day}.json", default=None) or {}


def build(days_docs):
    """days_docs: {day: archive doc}. Returns the table dict (without fitted_at)."""
    fields, rows = {}, 0
    for fname, rkey, akey in FIELDS:
        per_day_hour = {}      # (day, hour) -> [diff]
        for day, doc in days_docs.items():
            for t in doc.get("ticks", []):
                r = (t.get("readings") or {}).get(REF_ID)
                m = (t.get("l2") or {}).get(akey)
                if not r or not r.get("valid") or r.get(rkey) is None or m is None or (r.get("age_min") or 0) > 15:
                    continue
                ts = datetime.strptime(t["ts"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).astimezone(ET)
                per_day_hour.setdefault((day, ts.hour), []).append(r[rkey] - m)
        by_hour = {}
        for (day, hr), v in per_day_hour.items():
            if len(v) >= MIN_TICKS_PER_DAY_HOUR:
                by_hour.setdefault(hr, []).append(st.median(v))
                rows += len(v)
        hourly = {str(h): round(st.median(v), 3) for h, v in by_hour.items() if len(v) >= MIN_DAYS}
        if hourly:
            fields[fname] = {"hourly": hourly, "n_days": max((len(v) for v in by_hour.values()), default=0)}
    return {"ref": REF_NAME, "ref_id": REF_ID, "window_days": WIN_DAYS, "n_rows_kept": rows, "fields": fields}


def fit():
    now = datetime.now(timezone.utc)
    docs = {}
    for i in range(WIN_DAYS + 1):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        d = _load(day)
        if d.get("ticks"):
            docs[day] = d
    out = build(docs)
    out["fitted_at"] = now.strftime("%Y-%m-%dT%H:%M")
    out["days"] = [min(docs), max(docs)] if docs else None
    out["notes"] = ("SHADOW: Cove value = Mesonet + adjustment learned from Neptune Rd (hourly, ET). "
                    "Stamped as hyperlocal.cove_temp / cove_humidity; nothing served reads it.")
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    for fn, v in out["fields"].items():
        print(f"  {fn}: {len(v['hourly'])} hours, up to {v['n_days']} days; "
              + " ".join(f"{h}:{a:+.2f}" for h, a in sorted(v["hourly"].items(), key=lambda kv: int(kv[0]))))
    print(f"  wrote {OUT_PATH}")
    return out


if __name__ == "__main__":
    fit()

"""Digest check (v0.7.100): did the daily cloud refit publish every table?

Reads gs://myweather-data/runtime_tables/_status.json (written by myweather-refitter after
every table since v0.7.100) and the runtime_tables/ object times. Any registered table whose
live copy is older than MAX_AGE_H, or that has never been published, fails this script, so it
shows as FAIL in the digest run table. Exists because the refitter ran out of memory on 11-13
and 11-14 and nothing anywhere said so: the served blend weights went two days stale.

    PYTHONPATH=. .venv/bin/python -m analysis.refitter_status
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MAX_AGE_H = 30   # daily 04:30 run plus slack


def main():
    from refitter.tables import TABLES
    from weather_collector.gcs_io import BUCKET, get_client, load_json
    from weather_collector.runtime_tables import PREFIX

    bucket = get_client().bucket(BUCKET)
    now = datetime.now(timezone.utc)
    status = load_json(PREFIX + "_status.json") or {}
    print(f"refitter last run {status.get('last_run_at')} ok={status.get('last_run_ok')}")
    bad = []
    for spec in TABLES:
        name = spec["name"]
        blob = bucket.get_blob(PREFIX + name)
        st = (status.get("tables") or {}).get(name, {})
        if blob is None:
            age, line = None, "NEVER PUBLISHED"
        else:
            age = (now - blob.updated).total_seconds() / 3600
            line = f"live copy {age:5.1f} h old"
        why = "" if st.get("published") else f"  last attempt: {st.get('reason') or 'no status'}"
        stale = age is None or age > MAX_AGE_H
        print(f"  {'STALE' if stale else 'ok   '} {name:<40} {line}{why if stale else ''}")
        if stale:
            bad.append(name)
    if bad:
        print(f"→ ALERT: {len(bad)} refit table(s) stale or never published: {', '.join(bad)}")
        print(f"VERDICT: ALERT ({len(bad)} stale)")
        sys.exit(1)
    print("VERDICT: OK (every refit table published within the last day)")


if __name__ == "__main__":
    main()

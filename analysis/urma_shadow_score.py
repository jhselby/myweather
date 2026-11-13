"""Forward scoring of the t_urmab shadow blend against URMA truth (rebuild tier-2 ship test).

Reads GCS forecast_log.json snapshots (each tick: hourly `t` = served, `t_urmab` = shadow), keeps
only ticks stamped with t_urmab (collector v0.7.97, first tick 2026-11-13 11:47Z), leads 6-47h,
and scores served vs shadow on IDENTICAL rows against the URMA idw truth at the valid hour.
Per valid day: sum|err| served / shadow. Tier-2 bar: shadow beats served on >= 5 of the last 7
scored days with a positive pooled gain; tripwire: trailing 3 days worse than served.
Day-block interval via analysis/ship_rule.py (informational until >= 14 days).

    PYTHONPATH=. .venv/bin/python -m analysis.urma_shadow_score [path/to/forecast_log.json]
Without an arg it copies the log from GCS (one read, ~25 MB).
"""
import collections
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from analysis.ship_rule import day_block_gain
from analysis.urma_blend_wf import urma_idw

ET = ZoneInfo("America/New_York")
BANDS = (("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48))


def snapshots(path):
    if path:
        return json.load(open(path))["snapshots"]
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "fl.json"
        subprocess.run(["gsutil", "-q", "cp", "gs://myweather-data/forecast_log.json", str(dst)], check=True)
        return json.load(open(dst))["snapshots"]


def score(snaps):
    U = urma_idw()
    per = {b[0]: collections.defaultdict(lambda: [0.0, 0.0, 0]) for b in BANDS}
    ticks = scored = 0
    for s in snaps:
        hs = [h for h in s["hours"] if "t_urmab" in h]
        if not hs:
            continue
        ticks += 1
        run = datetime.strptime(s["run"], "%Y-%m-%dT%H:%M").replace(tzinfo=ET)
        for h in hs:
            v = datetime.strptime(h["v"], "%Y-%m-%dT%H:%M").replace(tzinfo=ET)
            lead = (v - run).total_seconds() / 3600
            tr = U.get(v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H"))
            band = next((n for n, lo, hi in BANDS if lo <= lead < hi), None)
            if tr is None or band is None or h.get("t") is None:
                continue
            a = per[band][h["v"][:10]]
            a[0] += abs(h["t"] - tr)
            a[1] += abs(h["t_urmab"] - tr)
            a[2] += 1
            scored += 1
    return ticks, scored, per


def main():
    ticks, scored, per = score(snapshots(sys.argv[1] if len(sys.argv) > 1 else None))
    print(f"t_urmab shadow vs URMA truth: {ticks} stamped ticks, {scored} scored hour-rows")
    for band, days in per.items():
        d = {k: tuple(v) for k, v in days.items()}
        if not d:
            print(f"  {band}h: no scored days yet (URMA truth has not reached the shadow's valid hours)")
            continue
        g = day_block_gain(d, holdout_only=False)
        last7 = sorted(d)[-7:]
        wins = sum(d[k][1] < d[k][0] for k in last7)
        t3 = sorted(d)[-3:]
        trip = sum(d[k][1] for k in t3) > sum(d[k][0] for k in t3)
        print(f"  {band}h: gain {g['gain']:+.1f}% [{g['lo']:+.1f},{g['hi']:+.1f}] over {g['days']} d, "
              f"shadow wins {wins}/{len(last7)} (last7), n={g['n']}, tripwire {'TRIPPED' if trip else 'ok'}")


if __name__ == "__main__":
    main()

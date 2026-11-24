"""Does a stations-minus-URMA hour-of-day offset on t_urmab beat t_urmab, scored on the Mesonet stations?

Why (11-24): served t (fit on URMA) runs 2.7-3.0 F cold vs the Mesonet stations at 20-23h, while the stations read ~+1.0 F
warmer than URMA from 19h to 08h. Test: add the trailing mean (stations - URMA) for the valid hour of day, estimated only from
valid days before the run's own day (walk-forward, 14 d, >= 7 days in the hour bin), to t_urmab.

Baseline = t_urmab (the served t since v0.7.114); candidate = t_urmab + offset(hour). Truth = observed_stations (Mesonet, stations
only, from the pair log's lead-0 rows), leads 6-47h, IDENTICAL rows, day-block bootstrap through analysis/ship_rule.py.
Also prints the same candidate scored on URMA (it should lose there by construction: this is the truth-choice trade).

    PYTHONPATH=. .venv/bin/python -m analysis.t_night_offset_wf [forecast_log.json]
"""
import collections
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from analysis.ship_rule import day_block_gain, record, verdict
from analysis.urma_blend_wf import urma_idw
from analysis.urma_shadow_score import snapshots

ET = ZoneInfo("America/New_York")
PAIR = os.path.expanduser("~/.cache/myweather/forecast_error_log.jsonl")
BANDS = (("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48), ("night 19-07h", None, None))
WIN, MIN_DAYS = 14, 7


def stations_truth():
    out = {}
    for line in open(PAIR):
        if '"lead_h": 0,' not in line[:200] or '"field": "t"' not in line[:300]:
            continue
        r = json.loads(line)
        if r.get("field") == "t" and r.get("observed_stations") is not None:
            out[r["valid_time"]] = r["observed_stations"]
    return out


def utc_key(v):
    return datetime.strptime(v, "%Y-%m-%dT%H:%M").replace(tzinfo=ET).astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


def main():
    S = stations_truth()
    U = urma_idw()
    diff = {}  # valid local "YYYY-MM-DDTHH:00" -> stations - URMA
    for v, s in S.items():
        u = U.get(utc_key(v))
        if u is not None:
            diff[v] = s - u
    by_hour = collections.defaultdict(dict)  # hour -> {day: diff}
    for v, d in diff.items():
        by_hour[int(v[11:13])][v[:10]] = d

    def offset(run_day, hour):
        lo = (datetime.strptime(run_day, "%Y-%m-%d") - timedelta(days=WIN)).strftime("%Y-%m-%d")
        xs = [d for day, d in by_hour[hour].items() if lo <= day < run_day]
        return sum(xs) / len(xs) if len(xs) >= MIN_DAYS else None

    stn = {b[0]: collections.defaultdict(lambda: [0.0, 0.0, 0]) for b in BANDS}
    urm = {b[0]: collections.defaultdict(lambda: [0.0, 0.0, 0]) for b in BANDS}
    for s in snapshots(sys.argv[1] if len(sys.argv) > 1 else None):
        run = datetime.strptime(s["run"], "%Y-%m-%dT%H:%M").replace(tzinfo=ET)
        for h in s["hours"]:
            if "t_urmab" not in h:
                continue
            v = datetime.strptime(h["v"], "%Y-%m-%dT%H:%M").replace(tzinfo=ET)
            lead = (v - run).total_seconds() / 3600
            if lead < 6 or lead >= 48:
                continue
            hr = v.hour
            off = offset(s["run"][:10], hr)
            tr_s, tr_u = S.get(h["v"]), U.get(utc_key(h["v"]))
            if off is None:
                continue
            names = [n for n, lo, hi in BANDS[:3] if lo <= lead < hi]
            if hr >= 19 or hr < 7:
                names.append("night 19-07h")
            base, cand = h["t_urmab"], h["t_urmab"] + off
            for n in names:
                if tr_s is not None:
                    a = stn[n][h["v"][:10]]; a[0] += abs(base - tr_s); a[1] += abs(cand - tr_s); a[2] += 1
                if tr_u is not None:
                    a = urm[n][h["v"][:10]]; a[0] += abs(base - tr_u); a[1] += abs(cand - tr_u); a[2] += 1
    for title, tab in (("vs Mesonet stations (the test)", stn), ("vs URMA (cost of the truth choice)", urm)):
        print(f"t_urmab + hour offset, scored {title}")
        for band, days in tab.items():
            d = {k: tuple(v) for k, v in days.items()}
            if not d:
                print(f"  {band}: no rows")
                continue
            g = day_block_gain(d)
            print(f"  {band}: {verdict(g)}")
            if tab is stn:
                record("t_night_offset_wf", f"t {band}", g, note="t_urmab + trailing 14d (stations-URMA) by hour; truth observed_stations")


if __name__ == "__main__":
    main()

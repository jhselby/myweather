#!/usr/bin/env python3
"""Would more stations (Weather Underground, different hardware) make the Mesonet temperature better?

Same hours for every group; the Mesonet's own method, no outside truth in the calibration:
  - each station's offset (day / night) = median of (reading - mean of the OTHER stations in the same
    group at that hour), fitted on the other days (leave-one-day-out). URMA is not used to calibrate.
  - estimate = octant-balanced mean (within a direction, 1/d^2 weights; stations beyond MAX_MI dropped,
    as in hyperlocal), no outlier trimming (this test only).
  - the estimate is then scored against URMA, an independent analysis, on the held-out days:
    bias (overall, day, night) says whether the network sits above/below URMA; sd says how noisy it is.
Groups: Tempest (the 18 in the Mesonet), Tempest + WU live set (picked 11-12..15 on Tempest, not URMA),
Tempest + all WU. Rows are restricted to hours where EVERY group has an estimate.

Usage: PYTHONPATH=. .venv/bin/python analysis/mesonet_more_stations.py [--from 2026-11-10 --to 2026-11-21]
"""
import argparse
import math
import statistics as st
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.mesonet_vs_urma import (LIVE, OWN, _cat, day_of, is_day, tempest_series,  # noqa: E402
                                      urma_series, wu_series)

COVE = (42.5014, -70.8750)
MAX_MI = 2.5
MIN_STATIONS = 6


def _mi(lat, lon):
    r = 3958.8
    p1, p2 = math.radians(COVE[0]), math.radians(lat)
    dl = math.radians(lon - COVE[1])
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _oct(lat, lon):
    p1, p2 = math.radians(COVE[0]), math.radians(lat)
    dl = math.radians(lon - COVE[1])
    b = (math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                 math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) + 360) % 360
    return int(((b + 22.5) % 360) // 45)


def locations(days):
    loc = {}
    for day in days:
        for sid, m in ((_cat(f"station_readings/{day}.json") or {}).get("stations") or {}).items():
            if m.get("latitude") is not None:
                loc["T:" + sid] = (m["latitude"], m["longitude"])
        for sid, m in ((_cat(f"wu_readings_hourly/{day}.json") or {}).get("stations") or {}).items():
            if m.get("lat") is not None:
                loc[sid] = (m["lat"], m["lon"])
    return loc


def offsets(group, series, hold_day):
    """{sid: (off_day, off_night)}: median (reading - mean of the other group stations), other days."""
    hours = sorted({h for s in group for h in series[s]})
    out = {}
    for s in group:
        dd, nn = [], []
        for h in hours:
            if day_of(h) == hold_day or h not in series[s]:
                continue
            others = [series[o][h] for o in group if o != s and h in series[o]]
            if len(others) < 3:
                continue
            (dd if is_day(h) else nn).append(series[s][h] - st.mean(others))
        if len(dd) >= 15 and len(nn) >= 15:
            out[s] = (st.median(dd), st.median(nn))
    return out


def estimate(group, series, off, loc, h):
    by = {}
    for s in group:
        if s not in off or h not in series[s]:
            continue
        d = _mi(*loc[s])
        if d > MAX_MI:
            continue
        v = series[s][h] - off[s][0 if is_day(h) else 1]
        by.setdefault(_oct(*loc[s]), []).append((1.0 / max(d, 0.1) ** 2, v))
    if sum(len(v) for v in by.values()) < MIN_STATIONS:
        return None
    return st.mean(sum(w * v for w, v in o) / sum(w for w, _ in o) for o in by.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2026-11-10")
    ap.add_argument("--to", dest="d1", default="2026-11-21")
    a = ap.parse_args()
    d0 = datetime.strptime(a.d0, "%Y-%m-%d")
    days = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((datetime.strptime(a.d1, "%Y-%m-%d") - d0).days + 1)]
    urma = urma_series()
    ser_t, ser_w = tempest_series(days), wu_series(days)
    series = {**ser_t, **{k: v for k, v in ser_w.items() if k != OWN}}
    loc = locations(days)
    series = {k: v for k, v in series.items() if k in loc}
    tem = [s for s in series if s.startswith("T:")]
    wu_all = [s for s in series if not s.startswith("T:")]
    wu_live = [s for s in LIVE if s in series]
    groups = {"Tempest": tem, "Tempest + WU live set": tem + wu_live, "Tempest + all WU": tem + wu_all}
    print(f"stations: Tempest {len(tem)}, WU live {len(wu_live)}, WU all {len(wu_all)} (within {MAX_MI} mi counted)")
    hours = sorted(h for h in urma if day_of(h) in days)
    est = {g: {} for g in groups}
    for D in sorted({day_of(h) for h in hours}):
        for g, ids in groups.items():
            off = offsets(ids, series, D)
            for h in (x for x in hours if day_of(x) == D):
                e = estimate(ids, series, off, loc, h)
                if e is not None:
                    est[g][h] = e
    common = sorted(set.intersection(*(set(v) for v in est.values())))
    print(f"identical hours for all groups: {len(common)} ({sum(is_day(h) for h in common)} day, {sum(not is_day(h) for h in common)} night)\n")
    print(f"{'group':24} {'bias':>6} {'day':>6} {'night':>6} {'sd':>5} {'rmse':>5}")
    res = {}
    for g in groups:
        e = [est[g][h] - urma[h] for h in common]
        ed = [est[g][h] - urma[h] for h in common if is_day(h)]
        en = [est[g][h] - urma[h] for h in common if not is_day(h)]
        res[g] = e
        print(f"{g:24} {st.mean(e):+6.2f} {st.mean(ed):+6.2f} {st.mean(en):+6.2f} {st.pstdev(e):5.2f} {math.sqrt(st.mean(x * x for x in e)):5.2f}")
    # day-block bootstrap on the sd / rmse difference vs Tempest alone
    import random
    random.seed(7)
    byday = {}
    for i, h in enumerate(common):
        byday.setdefault(day_of(h), []).append(i)
    keys = list(byday)
    base = res["Tempest"]
    for g in groups:
        if g == "Tempest":
            continue
        diffs = []
        for _ in range(2000):
            idx = [i for k in random.choices(keys, k=len(keys)) for i in byday[k]]
            r0 = math.sqrt(st.mean(base[i] ** 2 for i in idx))
            r1 = math.sqrt(st.mean(res[g][i] ** 2 for i in idx))
            diffs.append((r0 - r1) / r0 * 100)
        diffs.sort()
        print(f"RMSE gain of '{g}' over Tempest alone: {st.mean(diffs):+.1f}% [{diffs[50]:+.1f}, {diffs[1949]:+.1f}] (day-block bootstrap, {len(keys)} days)")


if __name__ == "__main__":
    main()

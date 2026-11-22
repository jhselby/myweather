#!/usr/bin/env python3
"""Cove-anchored Mesonet: Mesonet + an adjustment learned from the Cove-side station on PRIOR days only.

The Mesonet (the other stations, calibrated to each other) cannot show the Cove's damped daily swing
(warmer nights, cooler days), so the adjustment A is learned from a Cove-side station:
    A(hour-of-day) = median over the last N prior days of (Cove-side reading - Mesonet) at that ET hour
    Cove value C(h) = Mesonet(h) + A
Two forms: "hourly" (24 bins) and "day/night" (2 bins). Walk-forward: day D is scored with an adjustment
learned from days < D only; the Mesonet's own offsets also use days < D only (expanding window).

Scored against: Neptune Rd (the station the adjustment is learned from: tests that it carries forward in time)
and the yard sensor KMAMARBL124 (a DIFFERENT sensor and spot, never used to learn: tests that it is the Cove
and not one station's quirk; provisional and noisy, so read its day/night means, not its scatter).
Mesonet here = current method (consensus offsets, octant mix), all 18 Tempest stations, as in production.

Usage: PYTHONPATH=. .venv/bin/python analysis/mesonet_cove_adjust.py [--from 2026-11-09 --to 2026-11-22]
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

from analysis.mesonet_cove_variants import NEPTUNE, estimate, load, net_wind  # noqa: E402
from analysis.mesonet_vs_urma import day_of, is_day  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

ET = ZoneInfo("America/New_York")
LEARN_DAYS = 14
MIN_DAYS = 3


def hod(h):
    return datetime.fromtimestamp(h, ET).hour


def prior_offsets(group, ser, day):
    """Consensus offsets (day/night) fitted on days BEFORE `day` only."""
    hours = sorted({h for s in group for h in ser[s] if day_of(h) < day})
    out = {}
    for s in group:
        dd, nn = [], []
        for h in hours:
            if h not in ser[s]:
                continue
            others = [ser[o][h] for o in group if o != s and h in ser[o]]
            if len(others) < 3:
                continue
            (dd if is_day(h) else nn).append(ser[s][h] - st.mean(others))
        if len(dd) >= 15 and len(nn) >= 15:
            out[s] = (st.median(dd), st.median(nn))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2026-11-09")
    ap.add_argument("--to", dest="d1", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    a = ap.parse_args()
    d0 = datetime.strptime(a.d0, "%Y-%m-%d")
    days = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((datetime.strptime(a.d1, "%Y-%m-%d") - d0).days + 1)]
    ser, wind, loc, elev, yard = load(days)
    group = [s for s in ser if s in loc]
    hours = sorted({h for s in group for h in ser[s]})
    # Mesonet value for every hour, offsets from prior days only
    M = {}
    for D in sorted({day_of(h) for h in hours}):
        off = prior_offsets(group, ser, D)
        if len(off) < 10:
            continue
        for h in (x for x in hours if day_of(x) == D):
            e = estimate(group, ser, off, loc, elev, h, "octant")
            if e is not None:
                M[h] = e
    nep = ser.get(NEPTUNE, {})
    scored_days = sorted({day_of(h) for h in M})
    res = {"Neptune Rd": {"M": [], "hourly": [], "daynight": []}, "Yard": {"M": [], "hourly": [], "daynight": []}}
    for D in scored_days:
        prior = [d for d in scored_days if d < D][-LEARN_DAYS:]
        if len(prior) < MIN_DAYS:
            continue
        diffs_h, diffs_dn = {}, {True: [], False: []}
        for h, m in M.items():
            if day_of(h) in prior and h in nep:
                dv = nep[h] - m
                diffs_h.setdefault(hod(h), []).append(dv)
                diffs_dn[is_day(h)].append(dv)
        if len(diffs_dn[True]) < 10 or len(diffs_dn[False]) < 10:
            continue
        A_dn = {k: st.median(v) for k, v in diffs_dn.items()}
        A_h = {k: st.median(v) for k, v in diffs_h.items() if len(v) >= MIN_DAYS}
        for h, m in M.items():
            if day_of(h) != D:
                continue
            ah = A_h.get(hod(h))
            for name, ref in (("Neptune Rd", nep), ("Yard", yard)):
                if h not in ref or ah is None:
                    continue
                res[name]["M"].append((h, m - ref[h]))
                res[name]["hourly"].append((h, m + ah - ref[h]))
                res[name]["daynight"].append((h, m + A_dn[is_day(h)] - ref[h]))
    print(f"days scored {scored_days[0] if scored_days else '-'}..{scored_days[-1] if scored_days else '-'}; learned from the last {LEARN_DAYS} prior days (min {MIN_DAYS})\n")
    for name, d in res.items():
        n = len(d["M"])
        print(f"== {name}: {n} hours scored")
        if n < 20:
            print("   too few hours\n")
            continue
        print(f"   {'estimator':22}{'bias':>7}{'day':>7}{'night':>7}{'sd':>6}{'rmse':>6}   (estimate minus {name}, F)")
        for lab, key in (("Mesonet (current)", "M"), ("Cove: day/night adj", "daynight"), ("Cove: hourly adj", "hourly")):
            e = [v for _, v in d[key]]
            ed = [v for h, v in d[key] if is_day(h)]
            en = [v for h, v in d[key] if not is_day(h)]
            print(f"   {lab:22}{st.mean(e):+7.2f}{st.mean(ed):+7.2f}{st.mean(en):+7.2f}{st.pstdev(e):6.2f}{math.sqrt(st.mean(x * x for x in e)):6.2f}")
        # day-block bootstrap of the rmse gain (hourly adj vs Mesonet)
        import random
        random.seed(7)
        byday = {}
        for i, (h, _) in enumerate(d["M"]):
            byday.setdefault(day_of(h), []).append(i)
        keys = list(byday)
        gains = {}
        for key in ("daynight", "hourly"):
            g = []
            for _ in range(2000):
                idx = [i for k in random.choices(keys, k=len(keys)) for i in byday[k]]
                r0 = math.sqrt(st.mean(d["M"][i][1] ** 2 for i in idx))
                r1 = math.sqrt(st.mean(d[key][i][1] ** 2 for i in idx))
                g.append((r0 - r1) / r0 * 100)
            g.sort()
            gains[key] = (st.mean(g), g[50], g[1949])
        for key, (m, lo, hi) in gains.items():
            print(f"   RMSE gain, {key} adjustment vs Mesonet: {m:+.1f}% [{lo:+.1f}, {hi:+.1f}] ({len(keys)} days, day-block bootstrap)")
        print()


if __name__ == "__main__":
    main()

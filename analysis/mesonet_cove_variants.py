#!/usr/bin/env python3
"""Does calibrating the stations differently let the Mesonet see the Cove?

The Mesonet's per-station offset aligns every station to the consensus of the others. That removes sensor
error AND real siting differences, so a waterfront station that is truly warmer on a clear night is pulled
down to the inland consensus. This tests offset methods against Cove-side references, with no outside truth
in the calibration:

  offset method   consensus : median(reading - mean of other stations), day / night split (current Mesonet)
                  raw       : no offset at all (keeps every real siting difference, and every sensor error)
                  windy     : ONE offset per station = median(reading - mean of others) over the windiest
                              third of training hours (well-mixed air: siting differences shrink, sensor
                              error stays), applied to all hours
  direction mix   octant    : within a direction 1/d^2 x exp(-|dz|/30); directions then averaged equally (current)
                  global    : 1/d^2 x exp(-|dz|/30) across all stations, no direction balancing

References (kept apart, raw readings, never pooled): Neptune Rd and Driftwood Rd (each left OUT of the Mesonet
for its own comparison) and the yard station KMAMARBL124 (not in the Mesonet; provisional, see plan 1.8).
Offsets are fitted on the other days only (leave-one-day-out). Same hours for every variant of a reference.
Wind for "windy" = the median of the stations' own wind, so no forecast or analysis enters.

Usage: PYTHONPATH=. .venv/bin/python analysis/mesonet_cove_variants.py [--from 2026-11-09 --to 2026-11-22]
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

from analysis.mesonet_vs_urma import _cat, day_of, is_day, snap  # noqa: E402
from analysis.mesonet_more_stations import _mi, _oct, MAX_MI  # noqa: E402

HOME_ELEV = 30.0
NEPTUNE, DRIFTWOOD = "T:192019", "T:226429"
YARD = "KMAMARBL124"


def load(days):
    ser, wind, loc, elev = {}, {}, {}, {}
    for day in days:
        d = _cat(f"station_readings/{day}.json") or {}
        for sid, m in (d.get("stations") or {}).items():
            if m.get("latitude") is not None:
                loc["T:" + sid] = (m["latitude"], m["longitude"])
                elev["T:" + sid] = m.get("elevation_ft") if m.get("elevation_ft") is not None else HOME_ELEV
        for t in d.get("ticks", []):
            ep = datetime.strptime(t["ts"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).timestamp()
            h = snap(ep)
            if h is None:
                continue
            for sid, v in t["readings"].items():
                if v.get("valid") and v.get("t") is not None and (v.get("age_min") or 0) <= 15:
                    ser.setdefault("T:" + sid, {})[h] = v["t"]
                    if v.get("ws") is not None:
                        wind.setdefault("T:" + sid, {})[h] = v["ws"]
    yard = {}
    for day in days:
        rows = ((_cat(f"wu_readings/{day}.json") or {}).get("obs") or {}).get(YARD, [])
        by = {}
        for r in rows:
            if r.get("t") is None:
                continue
            h = round(r["ep"] / 3600) * 3600
            if abs(r["ep"] - h) <= 600:
                by.setdefault(h, []).append(r["t"])
        for h, v in by.items():
            yard[h] = st.mean(v)
    return ser, wind, loc, elev, yard


def net_wind(wind, hours):
    out = {}
    for h in hours:
        v = [w[h] for w in wind.values() if h in w]
        if len(v) >= 6:
            out[h] = st.median(v)
    return out


def offsets(group, ser, hold_day, method, nw):
    if method == "raw":
        return {s: (0.0, 0.0) for s in group}
    hours = sorted({h for s in group for h in ser[s]})
    train = [h for h in hours if day_of(h) != hold_day]
    if method == "windy":
        wv = sorted(nw[h] for h in train if h in nw)
        if len(wv) < 60:
            return {}
        thr = wv[int(len(wv) * 2 / 3)]
        use = [h for h in train if h in nw and nw[h] >= thr]
    out = {}
    for s in group:
        dd, nn, allv = [], [], []
        for h in (use if method == "windy" else train):
            if h not in ser[s]:
                continue
            others = [ser[o][h] for o in group if o != s and h in ser[o]]
            if len(others) < 3:
                continue
            d = ser[s][h] - st.mean(others)
            allv.append(d)
            (dd if is_day(h) else nn).append(d)
        if method == "windy" and len(allv) >= 15:
            m = st.median(allv)
            out[s] = (m, m)
        elif method == "consensus" and len(dd) >= 15 and len(nn) >= 15:
            out[s] = (st.median(dd), st.median(nn))
    return out


def estimate(group, ser, off, loc, elev, h, mix):
    items = []
    for s in group:
        if s not in off or h not in ser[s]:
            continue
        d = _mi(*loc[s])
        if d > MAX_MI:
            continue
        w = (1.0 / max(d, 0.1) ** 2) * math.exp(-abs(elev[s] - HOME_ELEV) / 30.0)
        items.append((_oct(*loc[s]), w, ser[s][h] - off[s][0 if is_day(h) else 1]))
    if len(items) < 6:
        return None
    if mix == "global":
        return sum(w * v for _, w, v in items) / sum(w for _, w, _ in items)
    by = {}
    for o, w, v in items:
        by.setdefault(o, []).append((w, v))
    return st.mean(sum(w * v for w, v in x) / sum(w for w, _ in x) for x in by.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2026-11-09")
    ap.add_argument("--to", dest="d1", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    a = ap.parse_args()
    d0 = datetime.strptime(a.d0, "%Y-%m-%d")
    days = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((datetime.strptime(a.d1, "%Y-%m-%d") - d0).days + 1)]
    ser, wind, loc, elev, yard = load(days)
    tem = [s for s in ser if s in loc]
    hours_all = sorted({h for s in tem for h in ser[s]})
    nw = net_wind(wind, hours_all)
    variants = [(m, x) for m in ("consensus", "raw", "windy") for x in ("octant", "global")]
    refs = {"Neptune Rd (held out)": (NEPTUNE, ser.get(NEPTUNE, {})),
            "Driftwood Rd (held out)": (DRIFTWOOD, ser.get(DRIFTWOOD, {})),
            "Yard (provisional)": (None, yard)}
    print(f"days {days[0]}..{days[-1]}; Tempest stations {len(tem)}; yard hours {len(yard)}; Driftwood hours {len(ser.get(DRIFTWOOD, {}))}\n")
    for rname, (rid, rser) in refs.items():
        group = [s for s in tem if s != rid]
        est = {v: {} for v in variants}
        for D in sorted({day_of(h) for h in hours_all}):
            for m in ("consensus", "raw", "windy"):
                off = offsets(group, ser, D, m, nw)
                for h in (x for x in hours_all if day_of(x) == D and x in rser):
                    for mix in ("octant", "global"):
                        e = estimate(group, ser, off, loc, elev, h, mix)
                        if e is not None:
                            est[(m, mix)][h] = e
        common = sorted(set.intersection(*(set(v) for v in est.values()))) if all(est.values()) else []
        nd, nn_ = sum(is_day(h) for h in common), sum(not is_day(h) for h in common)
        print(f"== {rname}: {len(common)} identical hours ({nd} day, {nn_} night)")
        if len(common) < 20:
            print("   too few hours to score yet\n")
            continue
        print(f"   {'offset':10}{'mix':8}{'bias':>7}{'day':>7}{'night':>7}{'sd':>6}{'rmse':>6}   (Mesonet minus reference, F)")
        for m, x in variants:
            e = [est[(m, x)][h] - rser[h] for h in common]
            ed = [est[(m, x)][h] - rser[h] for h in common if is_day(h)]
            en = [est[(m, x)][h] - rser[h] for h in common if not is_day(h)]
            print(f"   {m:10}{x:8}{st.mean(e):+7.2f}{st.mean(ed) if ed else float('nan'):+7.2f}{st.mean(en) if en else float('nan'):+7.2f}"
                  f"{st.pstdev(e):6.2f}{math.sqrt(st.mean(v * v for v in e)):6.2f}")
        print()


if __name__ == "__main__":
    main()

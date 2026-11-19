#!/usr/bin/env python3
"""Does the hyperlocal "Confidence" label (High/Moderate/Low) predict the error of the station-corrected
temperature, and does a wider station set (Tempest + WU live set) predict it better?

Label today (hyperlocal.py): std of the per-octant trimmed-weighted means of (station reading - offset),
Tempest only. High < 1.0F, Moderate < 2.0F, else Low. The count of stations is not an input.
Wide label: same code, same thresholds, with the 7 WU live-set neighbours added (offsets = median reading -
URMA by day/night, fitted on the other days; Joe's own station excluded until it passes its gate).

Target (same for both labels, so they are comparable): |corrected temp - URMA| at the tick hour, where
corrected temp = model_temp + kalman_gain * weighted_bias as stored in station_readings (what production
showed). URMA (urma_truth_t.json) is independent of every station. A useful label sorts hours so that
High has a smaller error than Low. Narrow is first checked against the bias_std production stored.

Hours are the ticks within 10 min of the top of the hour (the hours WU hourly history covers).
Usage: python3 analysis/confidence_label_score.py [--from 2026-11-08 --to YYYY-MM-DD]
"""
import argparse
import math
import os
import statistics as st
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mesonet_vs_urma as mv  # noqa: E402
from weather_collector.config import ELEVATION_FT, LAT, LON  # noqa: E402
from weather_collector.processors.hyperlocal import (  # noqa: E402
    MAX_STATION_DIST_MI, MIN_OCTANTS_FOR_BALANCED, _octant_index, _trimmed_weighted_mean)


def label(sd):
    if sd is None or sd >= 2.0:
        return "Low"
    return "High" if sd < 1.0 else "Moderate"


def miles(lat, lon):
    p1, p2 = math.radians(LAT), math.radians(lat)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon - LON) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(a))


def octant_stats(rows):
    """rows: [(value, lat, lon, dist_mi, elev_ft)] -> (weighted_bias_wrt_zero, bias_std, octants_used) using
    production's weights and trimming. Values are readings minus offsets; the model value cancels in the spread."""
    octs = [[] for _ in range(8)]
    for v, lat, lon, d, el in rows:
        if v is None or d is None or d == 0 or d > MAX_STATION_DIST_MI:
            continue
        o = _octant_index(lat, lon)
        if o is None:
            continue
        w = (1.0 / d ** 2) * math.exp(-abs((el if el is not None else ELEVATION_FT) - ELEVATION_FT) / 30.0)
        octs[o].append((v, w))
    means = [m for m, _ in (_trimmed_weighted_mean(o) for o in octs) if m is not None]
    if len(means) < MIN_OCTANTS_FOR_BALANCED:
        return None, None, len(means)
    return sum(means) / len(means), (st.stdev(means) if len(means) > 1 else None), len(means)


def load(days):
    urma = mv.urma_series()
    wu = mv.wu_series(days)
    wu_meta = {}
    for d in days:
        wu_meta.update((mv._cat(f"wu_readings_hourly/{d}.json") or {}).get("stations", {}))
    wu = {s: v for s, v in wu.items() if s in mv.LIVE}
    ticks = []
    for d in days:
        doc = mv._cat(f"station_readings/{d}.json") or {}
        meta = doc.get("stations", {})
        for t in doc.get("ticks", []):
            ep = datetime.strptime(t["ts"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).timestamp()
            h = mv.snap(ep)
            if h is not None and h in urma and t.get("l2", {}).get("model_temp") is not None:
                ticks.append((h, t, meta))
    return urma, wu, wu_meta, ticks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2026-11-08")
    ap.add_argument("--to", dest="d1", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    a = ap.parse_args()
    d0 = datetime.strptime(a.d0, "%Y-%m-%d")
    days = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((datetime.strptime(a.d1, "%Y-%m-%d") - d0).days + 1)]
    urma, wu, wu_meta, ticks = load(days)
    cor_by_day = {D: mv.corrected(wu, urma, D) for D in days}

    recs, mism = [], 0
    for h, t, meta in ticks:
        l2 = t["l2"]
        D = mv.day_of(h)
        base = []
        for sid, r in t["readings"].items():
            if not r.get("valid") or r.get("t") is None:
                continue
            m = meta.get(sid) or {}
            if m.get("latitude") is None or not m.get("distance_mi"):
                continue
            base.append((r["t"] - r.get("off_t", 0.0), m["latitude"], m["longitude"], m["distance_mi"], m.get("elevation_ft")))
        wb_n, sd_n, k_n = octant_stats(base)
        if wb_n is None:
            continue
        if l2.get("bias_std") is not None and sd_n is not None and abs(sd_n - l2["bias_std"]) > 0.02:
            mism += 1
        extra = []
        for sid, vals in cor_by_day[D].items():
            if h in vals and sid in wu_meta and sid in mv.LIVE:
                la, lo = wu_meta[sid]["lat"], wu_meta[sid]["lon"]
                extra.append((vals[h], la, lo, miles(la, lo), None))
        wb_w, sd_w, k_w = octant_stats(base + extra)
        if sd_w is None and wb_w is None:
            continue
        corrected = l2["model_temp"] + (l2.get("kalman_gain") or 0) * (l2["weighted_bias"])
        recs.append({"h": h, "day": D, "err": abs(corrected - urma[h]), "sd_n": sd_n, "sd_w": sd_w,
                     "nw": len(extra), "n_used": len(base)})
    print(f"hours scored {len(recs)}  days {len(set(r['day'] for r in recs))}  "
          f"narrow bias_std differs from stored on {mism} hours (rebuild check; 0 = exact)")
    print(f"WU stations present per hour: mean {st.mean(r['nw'] for r in recs):.1f}; Tempest stations used: "
          f"mean {st.mean(r['n_used'] for r in recs):.1f}")
    low_hours(recs)
    for name, key in (("NARROW (Tempest, production)", "sd_n"), ("WIDE (Tempest + WU live)", "sd_w")):
        print(f"\n{name}")
        print(f"{'label':10} {'hours':>6} {'share':>6} {'MAE vs URMA':>12}")
        groups = {}
        for r in recs:
            groups.setdefault(label(r[key]), []).append(r["err"])
        for lb in ("High", "Moderate", "Low"):
            e = groups.get(lb, [])
            print(f"{lb:10} {len(e):6d} {len(e) / len(recs):6.0%} {(st.mean(e) if e else float('nan')):12.2f}")
        xs = [r[key] if r[key] is not None else 9 for r in recs]
        ys = [r["err"] for r in recs]
        mx, my = st.mean(xs), st.mean(ys)
        c = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
        hi, lo = groups.get("High", []), groups.get("Low", [])
        sep = (st.mean(lo) / st.mean(hi)) if hi and lo else float("nan")
        print(f"corr(bias_std, abs err) = {c:+.2f}   Low/High error ratio = {sep:.2f}")
        big = [r for r in recs if r["err"] >= 1.0]
        small = [r for r in recs if r["err"] < 1.0]
        f = lambda r: r[key] if r[key] is not None else 9
        auc = sum((f(b) > f(sm)) + 0.5 * (f(b) == f(sm)) for b in big for sm in small) / max(1, len(big) * len(small))
        print(f"rank score (AUC) for 'error >= 1.0F' ({len(big)} hours): {auc:.2f}  (0.5 = no skill, 1.0 = perfect)")
        halves = {}
        for r in recs:
            halves.setdefault(r["day"] < sorted({x["day"] for x in recs})[len(set(x["day"] for x in recs)) // 2], []).append(r)
        for k, rs in halves.items():
            g = {}
            for r in rs:
                g.setdefault(label(r[key]), []).append(r["err"])
            print("  " + ("first half " if k else "second half") + "  " + "  ".join(
                f"{lb} {st.mean(g[lb]):.2f} (n={len(g[lb])})" for lb in ("High", "Moderate", "Low") if lb in g))
    verdict(recs)


def low_hours(recs):
    print("\nhours the production label was Low (bias_std >= 2.0):")
    for r in recs:
        if r["sd_n"] is None or r["sd_n"] >= 2.0:
            print(f"  {datetime.fromtimestamp(r['h'], timezone.utc):%m-%d %H}Z narrow sd {r['sd_n']}  wide sd {r['sd_w']}  err {r['err']:.2f}F")


def verdict(recs):
    def stat(key):
        g = {}
        for r in recs:
            g.setdefault(label(r[key]), []).append(r["err"])
        m = lambda lb: f"{st.mean(g[lb]):.2f}F (n={len(g[lb])})" if g.get(lb) else "n/a"
        return f"High {m('High')}, Moderate {m('Moderate')}, Low {m('Low')}"
    print(f"\nVERDICT confidence_label_score: error vs URMA by label, {len(recs)} hours: "
          f"narrow (Tempest) {stat('sd_n')}; wide (+WU live) {stat('sd_w')}")


if __name__ == "__main__":
    main()

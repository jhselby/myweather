"""Does adding the live Weather Underground set to the Mesonet make it better? (plan Step 1, 11-22)

The live WU set (wu_archive.LIVE_STATIONS: one station per compass direction, incl. the only WEST
station KMAMARBL63) is polled every tick since 11-18 but only archived; the Mesonet is Tempest-only.
This rebuilds the Mesonet temperature both ways with hyperlocal's own method (offset-corrected
readings, MAD-trimmed 1/d^2 x elevation weighted mean per octant, mean of octants; model cancels):

  tempest   Tempest stations with their production offsets (off_t in the archive)
  +wu       the same plus the 7 neighbour WU stations (Joe's own station stays OUT of the average:
            at 0.04 mi its 1/d^2 weight would swamp it). WU offsets are fit like station_bias does,
            against the OTHER stations (Tempest network median at the same tick), day/night,
            leave-one-day-out. No forecast or URMA in any fit.

Scored per UTC hour against URMA (independent analysis), KBVY, and Joe's own station (the Cove;
reference only, not an input). Reconstruction check: 'tempest' vs the logged station_temp.

    PYTHONPATH=. .venv/bin/python -m analysis.mesonet_wu_test [station_readings_dir]
"""
import collections
import gzip
import json
import math
import statistics as st
import sys
from datetime import datetime, timedelta, timezone

from analysis.mesonet_validation import _download, kbvy, load, ET
from analysis.mesonet_vs_urma import snap, urma_series
from weather_collector.config import LAT, LON, ELEVATION_FT
from weather_collector.processors.hyperlocal import (MAX_STATION_DIST_MI, MIN_OCTANTS_FOR_BALANCED,
                                                     _octant_index, _trimmed_weighted_mean)
from weather_collector.processors.wu_archive import LIVE_STATIONS, OWN_STATION, TEMPEST_TWINS

FIRST_DAY = "2026-11-18"
MATCH_S = 300


def miles(lat, lon):
    dy = (lat - LAT) * 69.0
    dx = (lon - LON) * 69.0 * math.cos(math.radians(LAT))
    return math.hypot(dx, dy)


def weight(dist, elev):
    return (1.0 / dist ** 2) * math.exp(-abs((ELEVATION_FT if elev is None else elev) - ELEVATION_FT) / 30.0)


def wu_archive():
    from google.cloud import storage
    rows, meta = collections.defaultdict(list), {}
    for bl in storage.Client().bucket("myweather-data").list_blobs(prefix="wu_readings/"):
        raw = bl.download_as_bytes()
        d = json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
        meta.update(d.get("stations") or {})
        for sid, rs in (d.get("obs") or {}).items():
            if sid in TEMPEST_TWINS:
                continue
            rows[sid].extend(r for r in rs if r.get("t") is not None)
    for sid in rows:
        rows[sid].sort(key=lambda r: r["ep"])
    return rows, meta


def nearest(rows, ep):
    lo, hi = 0, len(rows)
    while lo < hi:
        mid = (lo + hi) // 2
        if rows[mid]["ep"] < ep:
            lo = mid + 1
        else:
            hi = mid
    best = None
    for i in (lo - 1, lo):
        if 0 <= i < len(rows) and abs(rows[i]["ep"] - ep) <= MATCH_S:
            if best is None or abs(rows[i]["ep"] - ep) < abs(best["ep"] - ep):
                best = rows[i]
    return best


def combine(items):
    """items: [(value, octant, weight)] -> hyperlocal-style balanced mean, or None."""
    octs = collections.defaultdict(list)
    for v, o, w in items:
        octs[o].append((v, w))
    means = [m for m, _ in (_trimmed_weighted_mean(x) for x in octs.values()) if m is not None]
    if len(items) < 3:
        return None, 0
    if len(means) >= MIN_OCTANTS_FOR_BALANCED:
        return sum(means) / len(means), len(means)
    return sum(v for v, _, _ in items) / len(items), len(means)


def is_day(T):
    return 7 <= T.astimezone(ET).hour < 19


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else _download()
    ticks = {k: v for k, v in load(d).items() if k[:10] >= FIRST_DAY}
    tmeta = {}
    import glob
    for f in glob.glob(d + "/*.json"):
        tmeta.update(json.load(open(f)).get("stations") or {})
    wrows, wmeta = wu_archive()
    neigh = [s for s in LIVE_STATIONS if s != OWN_STATION and wrows.get(s)]

    # Per tick: Tempest corrected items, Tempest network median, raw WU readings.
    per = []
    for ts in sorted(ticks):
        t = ticks[ts]
        T = datetime.strptime(ts, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        items, raw_med = [], []
        for sid, r in t["readings"].items():
            m = tmeta.get(sid) or {}
            if not r.get("valid") or r.get("t") is None or (r.get("age_min") or 0) >= 15:
                continue
            dist = m.get("distance_mi")
            o = _octant_index(m.get("latitude"), m.get("longitude"))
            if not dist or dist > MAX_STATION_DIST_MI or o is None:
                continue
            c = r["t"] - (r.get("off_t") or 0.0)
            items.append((c, o, weight(dist, m.get("elevation_ft"))))
            raw_med.append(c)
        if len(items) < 6:
            continue
        wu = {}
        for s in neigh + [OWN_STATION]:
            row = nearest(wrows.get(s) or [], T.timestamp())
            if row:
                wu[s] = row["t"]
        per.append((T, items, st.median(raw_med), wu, (t.get("l2") or {}).get("station_temp")))

    # WU offsets vs the Tempest network, day/night, leave-one-day-out (station_bias convention:
    # offset = reading - consensus; corrected = reading - offset).
    diffs = collections.defaultdict(list)
    for T, _, med, wu, _ in per:
        for s, v in wu.items():
            diffs[s].append((T.astimezone(ET).strftime("%Y-%m-%d"), is_day(T), v - med))

    def offset(s, hold_day, day):
        x = [e for dd, dy, e in diffs[s] if dd != hold_day and dy == day]
        return st.median(x) if len(x) >= 20 else None

    hourly = collections.defaultdict(lambda: collections.defaultdict(list))
    recon = []
    used = collections.Counter()
    for T, items, med, wu, logged in per:
        D, dy = T.astimezone(ET).strftime("%Y-%m-%d"), is_day(T)
        a, _ = combine(items)
        extra = []
        for s in neigh:
            if s not in wu:
                continue
            m = wmeta.get(s) or {}
            if m.get("lat") is None:
                continue
            dist, o, off = miles(m["lat"], m["lon"]), _octant_index(m["lat"], m["lon"]), offset(s, D, dy)
            if off is None or o is None or not 0 < dist <= MAX_STATION_DIST_MI:
                continue
            extra.append((wu[s] - off, o, weight(max(dist, 0.05), None)))
            used[s] += 1
        b, nb = combine(items + extra)
        if a is not None and logged is not None:
            recon.append(a - logged)
        h = snap(T.timestamp())
        if h is not None and a is not None and b is not None:
            hourly[h]["tempest"].append(a)
            hourly[h]["+wu"].append(b)
            if OWN_STATION in wu:
                hourly[h]["own"].append(wu[OWN_STATION])
    H = {h: {k: st.mean(v) for k, v in g.items()} for h, g in hourly.items()}

    urma = urma_series()
    days = sorted({T.astimezone(ET).strftime("%Y-%m-%d") for T, *_ in per})
    d0 = datetime.strptime(days[0], "%Y-%m-%d")
    kb = {h: v["t"] for h, v in kbvy(d0, d0 + timedelta(days=len(days) + 1)).items() if "t" in v}
    own = {h: v["own"] for h, v in H.items() if "own" in v}

    print(f"Mesonet with / without the live WU set, t, {days[0]}..{days[-1]} ({len(per)} ticks, {len(H)} hours)")
    print(f"reconstruction check (tempest rebuild - logged station_temp): mean {st.mean(recon):+.3f} MAE {st.mean(map(abs, recon)):.3f} F")
    print("WU stations used (ticks):", dict(used))
    print("reference     variant    n    bias   MAE   night bias  midday bias")
    out = {}
    for rname, ref in (("URMA", urma), ("KBVY", kb), ("Joe's yard", own)):
        for k in ("tempest", "+wu"):
            e, n_, m_ = [], [], []
            for h, v in H.items():
                if h in ref:
                    x = v[k] - ref[h]
                    e.append(x)
                    hr = datetime.fromtimestamp(h, ET).hour
                    (n_ if (hr >= 19 or hr < 7) else m_ if 10 <= hr < 16 else []).append(x)
            if e:
                out[(rname, k)] = st.mean(map(abs, e))
                print(f"{rname:12} {k:8} {len(e):4d} {st.mean(e):+6.2f} {st.mean(map(abs, e)):5.2f} "
                      f"{st.mean(n_) if n_ else float('nan'):+8.2f} {st.mean(m_) if m_ else float('nan'):+10.2f}")
    print("VERDICT mesonet_wu_test: " + "; ".join(
        f"{r} MAE {out[(r, 'tempest')]:.2f} -> {out[(r, '+wu')]:.2f}" for r in ("URMA", "KBVY", "Joe's yard") if (r, "tempest") in out)
        + " (exploratory, 5 days)")


if __name__ == "__main__":
    main()

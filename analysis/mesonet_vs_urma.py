#!/usr/bin/env python3
"""Does adding WU stations to Tempest bring the network's temperature closer to INDEPENDENT truth?

Truth = URMA (NOAA hourly analysis, urma_truth_t.json; independent of our stations and of L2),
inverse-distance interpolated to the Cove. The earlier 11-04 test judged WU by L2 gain on station
truth, which is circular. Here every station group is scored against URMA directly.

Estimator(group, hour) = mean over the group's stations of (reading - station offset), where the
offset is the station's median (reading - URMA) split day/night, fitted on all OTHER days
(leave-one-day-out, so no station is scored on the days that set its offset). Score = RMSE(F) of
estimator - URMA over held-out hours. The model value cancels (L2's bias = estimator - model, truth
bias = URMA - model), so this is the error of the network-bias input to L2.
Groups: Tempest, WU live set, WU all, Tempest+WU live, Tempest+WU all. A single-station table ranks
WU stations on the same independent truth (compare with wu_station_rank, which uses Tempest).
Floor: URMA's own representativeness error at the Cove is ~0.4-0.55F (11-13 note).
Hourly WU rows come from wu_readings_hourly/ (scripts/wu_backfill.py); Tempest from station_readings/.

Usage: python3 analysis/mesonet_vs_urma.py [--from 2026-11-10 --to 2026-11-18]
"""
import argparse
import gzip
import json
import math
import statistics as st
import subprocess
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BUCKET = "gs://myweather-data/"
ET = ZoneInfo("America/New_York")
OWN = "KMAMARBL124"
LIVE = ("KMAMARBL63", "KMAMARBL92", "KMAMARBL76", "KMAMARBL42", "KMAMARBL8", "KMAMARBL57", "KMASALEM91")
TOL_S = 600


def _cat(path):
    out = subprocess.run(["gsutil", "cat", BUCKET + path], capture_output=True)
    if out.returncode:
        return None
    raw = out.stdout
    return json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)


def hour_epoch(s):
    return datetime.strptime(s, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc).timestamp()


def urma_series():
    d = _cat("urma_truth_t.json") or {}
    out = {}
    for k, pts in d.items():
        w = [(1.0 / max(p[2], 0.1) ** 2, (p[3] - 273.15) * 9 / 5 + 32) for p in pts if p[3] is not None]
        if w:
            out[hour_epoch(k)] = sum(a * b for a, b in w) / sum(a for a, _ in w)
    return out


def snap(ep):
    """Nearest hour top within TOL_S, else None."""
    h = round(ep / 3600) * 3600
    return h if abs(ep - h) <= TOL_S else None


def tempest_series(days):
    ser = {}
    for day in days:
        for t in (_cat(f"station_readings/{day}.json") or {}).get("ticks", []):
            ep = datetime.strptime(t["ts"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).timestamp()
            h = snap(ep)
            if h is None:
                continue
            for sid, v in t["readings"].items():
                if v.get("valid") and v.get("t") is not None and (v.get("age_min") or 0) <= 15:
                    ser.setdefault("T:" + sid, {})[h] = v["t"]
    return ser


def wu_series(days):
    ser = {}
    for day in days:
        for sid, rows in ((_cat(f"wu_readings_hourly/{day}.json") or {}).get("obs") or {}).items():
            for r in rows:
                h = snap(r["ep"])
                if h is not None and r.get("t") is not None:
                    ser.setdefault(sid, {})[h] = r["t"]
    return ser


def is_day(h):
    return 8 <= datetime.fromtimestamp(h, ET).hour < 18


def day_of(h):
    return datetime.fromtimestamp(h, ET).strftime("%Y-%m-%d")


def corrected(series, urma, hold_day):
    """Per station: {hour: reading - offset} for hours on hold_day, offsets fitted on other days."""
    out = {}
    for sid, s in series.items():
        tr = [(h, v - urma[h]) for h, v in s.items() if h in urma and day_of(h) != hold_day]
        dd = [d for h, d in tr if is_day(h)]
        nn = [d for h, d in tr if not is_day(h)]
        if len(dd) < 15 or len(nn) < 15:
            continue
        od, on = st.median(dd), st.median(nn)
        out[sid] = {h: v - (od if is_day(h) else on) for h, v in s.items() if h in urma and day_of(h) == hold_day}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2026-11-10")
    ap.add_argument("--to", dest="d1", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    a = ap.parse_args()
    d0 = datetime.strptime(a.d0, "%Y-%m-%d")
    days = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((datetime.strptime(a.d1, "%Y-%m-%d") - d0).days + 1)]
    urma = urma_series()
    series = {**tempest_series(days), **wu_series(days)}
    tem = [s for s in series if s.startswith("T:")]
    wu_all = [s for s in series if not s.startswith("T:") and s != OWN]
    wu_live = [s for s in LIVE if s in series]
    groups = {"Tempest": tem, "WU live set": wu_live, "WU all": wu_all,
              "Tempest + WU live": tem + wu_live, "Tempest + WU all": tem + wu_all}
    hours = sorted(h for h in urma if day_of(h) in days)
    errs = {g: [] for g in groups}
    single = {s: [] for s in wu_all}
    held = sorted({day_of(h) for h in hours})
    for D in held:
        cor = corrected(series, urma, D)
        for h in (x for x in hours if day_of(x) == D):
            for g, ids in groups.items():
                vals = [cor[s][h] for s in ids if s in cor and h in cor[s]]
                if len(vals) >= max(3, len(ids) // 2):
                    errs[g].append(st.mean(vals) - urma[h])
            for s in wu_all:
                if s in cor and h in cor[s]:
                    single[s].append(cor[s][h] - urma[h])
    rmse = lambda xs: math.sqrt(st.mean(e * e for e in xs)) if xs else float("nan")
    print(f"URMA hours={len(hours)} held-out days={held} (leave-one-day-out offsets, day/night)")
    print(f"\n{'group':20} {'n hrs':>6} {'RMSE F':>7} {'bias F':>7}")
    for g in groups:
        print(f"{g:20} {len(errs[g]):6d} {rmse(errs[g]):7.2f} {st.mean(errs[g]) if errs[g] else float('nan'):+7.2f}")
    print("\nsingle WU stations vs URMA (offset-corrected, held-out): RMSE F")
    for s, e in sorted(single.items(), key=lambda kv: rmse(kv[1]) if kv[1] else 9):
        if len(e) >= 20:
            print(f"  {s:12} n={len(e):3d} {rmse(e):.2f}" + ("  [live]" if s in LIVE else ""))
    b, w = rmse(errs["Tempest"]), rmse(errs["Tempest + WU live"])
    print(f"\nVERDICT mesonet_vs_urma: network temperature vs URMA (held-out): Tempest {b:.2f}F, "
          f"Tempest+WU live set {w:.2f}F, Tempest+WU all {rmse(errs['Tempest + WU all']):.2f}F, WU live alone "
          f"{rmse(errs['WU live set']):.2f}F ({len(hours)} URMA hours) -> WU adds value only if the + rows beat Tempest by more than ~0.05F")


if __name__ == "__main__":
    main()

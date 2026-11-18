#!/usr/bin/env python3
"""How many stations and how fresh? Replay on the Tempest archive (analysis only).

Question: L2 corrects the model with the network's bias (offset-corrected station mean - model).
If the feed had only k stations, or readings that were s minutes old, how far would that bias
estimate be from what the FULL, FRESH network says, now and h hours later (where the correction is
actually applied)? Answers the polling-cadence vs station-count trade for the WU live set.

Quantity: b_hat(k, s)(t) = mean over k stations of (t_station - off_t) at tick t-s, minus model_temp
at t-s.  Target B(t+h) = the same on ALL valid stations at t+h, h in {0, 1, 3, 5} hours.
Score = RMSE(b_hat - B) in F, over random k-subsets (fixed seed). Temperature only.
Rows: station_readings/<day>.json ticks (10 min, Tempest, with the offsets L2 applied and
l2.model_temp). Stand-in for WU stations (same physics, different siting); not an L2 replay.

Usage: python3 analysis/mesonet_cadence_replay.py [--days 2026-11-16,2026-11-17,2026-11-18]
"""
import argparse
import gzip
import json
import math
import random
import statistics as st
import subprocess
from datetime import datetime, timedelta, timezone

BUCKET = "gs://myweather-data/"
KS = (1, 2, 3, 4, 6, 8, 12)
STALE_MIN = (0, 10, 30, 60)
HORIZONS_H = (0, 1, 3, 5)
DRAWS = 40


def _cat(path):
    out = subprocess.run(["gsutil", "cat", BUCKET + path], capture_output=True)
    if out.returncode:
        return None
    raw = out.stdout
    return json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)


def load(days):
    ticks = []
    for d in days:
        ticks += (_cat(f"station_readings/{d}.json") or {}).get("ticks", [])
    out = {}
    for t in ticks:
        model = (t.get("l2") or {}).get("model_temp")
        if model is None:
            continue
        vals = {sid: v["t"] - v.get("off_t", 0.0) for sid, v in t["readings"].items()
                if v.get("valid") and v.get("t") is not None and (v.get("age_min") or 0) <= 15}
        if len(vals) >= 8:
            out[datetime.strptime(t["ts"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)] = (model, vals)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", default=",".join(
        (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d") for i in (2, 1, 0)))
    days = ap.parse_args().days.split(",")
    data = load(days)
    times = sorted(data)
    print(f"days={days} usable ticks={len(times)} (>=8 valid stations and a model value)")
    if len(times) < 100:
        print("VERDICT mesonet_cadence_replay: not enough ticks yet")
        return
    full = {t: st.mean(v.values()) - m for t, (m, v) in data.items()}  # full-network bias, fresh
    ids = sorted(set.intersection(*(set(v) for _, (_, v) in data.items())))
    print(f"stations present on every tick: {len(ids)}")
    rng = random.Random(11)
    results = {}
    for h in HORIZONS_H:
        print(f"\n== target: full-network bias {h} h later; RMSE in F of the k-station, s-minute-old estimate ==")
        print(f"{'k':>3} " + " ".join(f"{s:>7}min" for s in STALE_MIN))
        for k in KS:
            if k > len(ids):
                continue
            row = []
            for s in STALE_MIN:
                errs = []
                for t in times:
                    tgt_t, src_t = t + timedelta(hours=h), t - timedelta(minutes=s)
                    if tgt_t not in full or src_t not in data:
                        continue
                    m, v = data[src_t]
                    for _ in range(DRAWS):
                        pick = [i for i in rng.sample(ids, k) if i in v]
                        if pick:
                            errs.append(st.mean(v[i] for i in pick) - m - full[tgt_t])
                rmse = math.sqrt(st.mean(e * e for e in errs)) if errs else float("nan")
                results[(h, k, s)] = rmse
                row.append(rmse)
            print(f"{k:3d} " + " ".join(f"{r:10.2f}" for r in row))
    base = results.get((3, max(KS), 0))
    cheap = results.get((3, 6, 60))
    print(f"\nVERDICT mesonet_cadence_replay: bias estimate error vs full network 3 h ahead: "
          f"12 stations fresh {base:.2f}F, 6 stations hourly {cheap:.2f}F; (Tempest stand-in, "
          f"{len(times)} ticks) -> if these are within ~0.1F, hourly polling of a handful costs little")


if __name__ == "__main__":
    main()

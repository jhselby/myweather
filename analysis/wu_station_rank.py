#!/usr/bin/env python3
"""Rank archived WU stations for the live blend (analysis only; nothing served reads it).

Reads wu_readings/<day>.json (WU, ~5-min readings) and station_readings/<day>.json (Tempest ticks)
from the myweather-data bucket and answers, per station and field (t, rh, p):
  1. offset   : median(WU - reference), split day/night. The offset is what L2 would learn.
  2. residual : spread of (WU - reference - offset) = how well the station TRACKS the reference
                once its constant offset is removed. Small = representative. Raw bias is ignored.
  3. uptime   : share of expected 5-min readings present over the station's span.
  4. staleness: RMS change of the station's own series over 10/30/60 min = the error from using a
                reading that old. PROXY for the cadence question, not an L2 replay.
  5. greedy   : forward selection of k stations minimising the RMSE of the offset-corrected subset
                mean against the reference, k = 1..8.
Reference = Tempest median (>=5 valid stations). With --ref own the reference is Joe's station
(KMAMARBL124) once it has enough overlap; its siting bias is a constant offset and drops out.

Usage: python3 analysis/wu_station_rank.py [--days 2026-11-18,2026-11-19] [--ref tempest|own]
"""
import argparse
import gzip
import json
import math
import statistics as st
import subprocess
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BUCKET = "gs://myweather-data/"
OWN = "KMAMARBL124"
ET = ZoneInfo("America/New_York")
FIELDS = ("t", "rh", "p")
MATCH_S = 360  # WU reading must be within 6 min of a reference tick
MIN_N = 20  # matched points needed to score a station


def _cat(path):
    out = subprocess.run(["gsutil", "cat", BUCKET + path], capture_output=True)
    if out.returncode:
        return None
    raw = out.stdout
    return json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)


def load_wu(days):
    obs = {}
    for d in days:
        doc = _cat(f"wu_readings/{d}.json")
        for sid, rows in ((doc or {}).get("obs") or {}).items():
            have = {r["ep"] for r in obs.get(sid, [])}
            obs.setdefault(sid, []).extend(r for r in rows if r["ep"] not in have)
    for rows in obs.values():
        rows.sort(key=lambda r: r["ep"])
    return obs


def tempest_ref(days):
    ref = []
    for d in days:
        for t in (_cat(f"station_readings/{d}.json") or {}).get("ticks", []):
            vals = [v for v in t["readings"].values() if v.get("valid") and (v.get("age_min") or 0) <= 15]

            def med(k, f=lambda x: x):
                xs = [f(v[k]) for v in vals if v.get(k) is not None]
                return st.median(xs) if len(xs) >= 5 else None
            ep = datetime.strptime(t["ts"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).timestamp()
            ref.append({"ep": ep, "t": med("t"), "rh": med("rh"), "p": med("p_mb", lambda m: m * 0.02953)})
    return sorted(ref, key=lambda r: r["ep"])


def match(rows, ref, field):
    """[(ep, wu_value, ref_value)] nearest reference tick within MATCH_S."""
    out, j = [], 0
    for r in rows:
        v = r.get(field)
        if v is None:
            continue
        while j + 1 < len(ref) and abs(ref[j + 1]["ep"] - r["ep"]) <= abs(ref[j]["ep"] - r["ep"]):
            j += 1
        if ref and abs(ref[j]["ep"] - r["ep"]) <= MATCH_S and ref[j][field] is not None:
            out.append((r["ep"], v, ref[j][field]))
    return out


def is_day(ep):
    return 8 <= datetime.fromtimestamp(ep, ET).hour < 18


def sd(xs):
    return st.pstdev(xs) if len(xs) > 1 else float("nan")


def score_station(rows, ref, field):
    m = match(rows, ref, field)
    if len(m) < MIN_N:
        return None
    diffs = [(ep, w - r) for ep, w, r in m]
    off = st.median(d for _, d in diffs)
    day = [d for ep, d in diffs if is_day(ep)]
    night = [d for ep, d in diffs if not is_day(ep)]
    off_d = st.median(day) if len(day) >= 5 else off
    off_n = st.median(night) if len(night) >= 5 else off
    resid = [d - off for _, d in diffs]
    resid_dn = [d - (off_d if is_day(ep) else off_n) for ep, d in diffs]
    return {"n": len(m), "off": off, "off_day": off_d, "off_night": off_n,
            "resid_sd": sd(resid), "resid_sd_dn": sd(resid_dn)}


def uptime(rows):
    if len(rows) < 2:
        return 0.0
    span = rows[-1]["ep"] - rows[0]["ep"]
    return min(1.0, len(rows) / (span / 300 + 1))


def staleness(all_rows, field, lag_min):
    """Median across stations of the RMS change over lag_min minutes (5-min grid)."""
    per = []
    for rows in all_rows.values():
        s = {round(r["ep"] / 300): r[field] for r in rows if r.get(field) is not None}
        k = lag_min // 5
        ch = [s[i] - s[i - k] for i in s if i - k in s]
        if len(ch) >= 20:
            per.append(math.sqrt(st.mean(c * c for c in ch)))
    return st.median(per) if per else float("nan")


def greedy(wu, ref, field, scores, kmax=8):
    """Forward selection by RMSE of the offset-corrected subset mean vs the reference."""
    series = {}
    for sid, rows in wu.items():
        if sid not in scores:
            continue
        for ep, w, r in match(rows, ref, field):
            series.setdefault(round(ep / 300), {})[sid] = (w - scores[sid]["off"], r)
    chosen, curve = [], []
    for _ in range(min(kmax, len(scores))):
        best = None
        for sid in scores:
            if sid in chosen:
                continue
            errs = []
            for cell in series.values():
                got = [cell[s][0] for s in chosen + [sid] if s in cell]
                if len(got) == len(chosen) + 1:
                    ref_v = next(iter(cell.values()))[1]
                    errs.append(st.mean(got) - ref_v)
            if len(errs) >= MIN_N:
                rmse = math.sqrt(st.mean(e * e for e in errs))
                if best is None or rmse < best[1]:
                    best = (sid, rmse)
        if best is None:
            break
        chosen.append(best[0])
        curve.append(best)
    return curve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--ref", default="tempest", choices=("tempest", "own"))
    a = ap.parse_args()
    days = a.days.split(",")
    wu = load_wu(days)
    ref = tempest_ref(days)
    if a.ref == "own":
        ref = [{"ep": r["ep"], "t": r.get("t"), "rh": r.get("rh"), "p": r.get("p")} for r in wu.get(OWN, [])]
        wu = {k: v for k, v in wu.items() if k != OWN}
    print(f"days={days} reference={a.ref} ({len(ref)} ticks) stations={len(wu)}")
    for field in FIELDS:
        scores = {sid: s for sid, rows in wu.items() if (s := score_station(rows, ref, field))}
        print(f"\n== {field}: offset (WU - ref) and residual spread after removing it ==")
        print(f"{'station':12} {'n':>4} {'offset':>7} {'day':>6} {'night':>6} {'resid':>6} {'res d/n':>7} {'uptime':>6}")
        for sid, s in sorted(scores.items(), key=lambda kv: kv[1]["resid_sd"]):
            print(f"{sid:12} {s['n']:4d} {s['off']:+7.2f} {s['off_day']:+6.2f} {s['off_night']:+6.2f} "
                  f"{s['resid_sd']:6.2f} {s['resid_sd_dn']:7.2f} {uptime(wu[sid]):6.2f}")
        curve = greedy(wu, ref, field, scores)
        print("  greedy best-k RMSE:", ", ".join(f"{i + 1}:{sid}={rmse:.2f}" for i, (sid, rmse) in enumerate(curve)))
        print("  staleness RMS change (median station): " +
              ", ".join(f"{lag}min={staleness(wu, field, lag):.2f}" for lag in (10, 30, 60)))


if __name__ == "__main__":
    main()

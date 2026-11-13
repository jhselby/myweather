"""Leave-one-station-out scoring of the L2 idea (network bias correction) on the Tempest archive.

L2 is graded on the same stations that feed it, so its score mixes real skill with the network
agreeing with itself. Here, for every tick T and every valid station j, the correction is built from
the OTHER stations only and scored against j's own reading (truth_j = t_j + off_j, the Cove-normalised
reading L2 uses). Temperature only.

  raw      model_temp(T+k)                                   (the model the correction sits on)
  loo      model_temp(T+k) + exp(-k/TAU) * (median_{i!=j}(t_i+off_i) - model_temp(T))
  incl     same with j included in the median               (the circular, in-sample version)
  deb      model_temp(T+k) + trailing 24 h mean (others' mean - model_temp), stations only, j excluded
  loo+deb  deb + exp(-k/TAU) * (current others' median - model_temp(T) - trailing bias)
Rows are restricted to ticks with >= MIN_HIST trailing ticks so every column scores identical rows.

k = lead in hours (0, 2-5). model_temp(T+k) is the model value the archive logged k hours later (same
rows for all three). Gain/Kalman shrink is not applied: this measures the neighbour signal itself.
Gain over raw per lead through analysis/ship_rule.day_block_gain (resampling unit = UTC day; the
archive started 11-08, so every row is exploratory: ship_rule's holdout is the real bar).

    PYTHONPATH=. .venv/bin/python -m analysis.l2_loo_score [dir_with_station_readings_json]
Without an arg it copies station_readings/*.json from GCS one file at a time.
"""
import collections
import glob
import json
import math
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from analysis.ship_rule import day_block_gain

TAU_H = 6.0
HIST, MIN_HIST = 144, 72
LEADS = (0, 2, 3, 4, 5)


def load(d):
    if d:
        files = sorted(glob.glob(str(Path(d) / "*.json")))
    else:
        d = tempfile.mkdtemp()
        out = subprocess.run(["gsutil", "ls", "gs://myweather-data/station_readings/"], capture_output=True, text=True, check=True)
        for u in out.stdout.split():
            if u.endswith(".json"):
                subprocess.run(["gsutil", "-q", "cp", u, d], check=True, timeout=120)
        files = sorted(glob.glob(d + "/*.json"))
    ticks = {}
    for f in files:
        for t in json.load(open(f))["ticks"]:
            ticks[t["ts"]] = t
    return ticks


def nets(t):
    """{station: Cove-normalised t} for valid stations."""
    return {k: r["t"] + (r.get("off_t") or 0.0) for k, r in t["readings"].items()
            if r.get("valid") and r.get("t") is not None and (r.get("age_min") or 0) < 15}


def trailing_bias(ticks, order, i, j):
    """Mean over the prior HIST ticks of (mean of the other stations - model_temp), j excluded."""
    vals = []
    for ts in order[max(0, i - HIST):i]:
        t = ticks[ts]
        m = (t.get("l2") or {}).get("model_temp")
        a = nets(t)
        if m is None or j not in a or len(a) < 6:
            continue
        vals.append((sum(a.values()) - a[j]) / (len(a) - 1) - m)
    return (sum(vals) / len(vals)) if len(vals) >= MIN_HIST else None


def run(ticks):
    per = {k: collections.defaultdict(lambda: [0.0] * 5 + [0]) for k in LEADS}  # day -> raw, loo, incl, deb, loo+deb, n
    order = sorted(ticks)
    for i, ts in enumerate(order):
        t0 = ticks[ts]
        m0 = (t0.get("l2") or {}).get("model_temp")
        a0 = nets(t0)
        if m0 is None or len(a0) < 6:
            continue
        T = datetime.strptime(ts, "%Y-%m-%dT%H:%MZ")
        tb = {j: trailing_bias(ticks, order, i, j) for j in a0}
        incl_bias = statistics.median(a0.values()) - m0
        for k in LEADS:
            if k == 0:
                tk, mk, ak = t0, m0, a0
            else:
                tk = ticks.get((T + timedelta(hours=k)).strftime("%Y-%m-%dT%H:%MZ"))
                if not tk:
                    continue
                mk = (tk.get("l2") or {}).get("model_temp")
                ak = nets(tk)
                if mk is None:
                    continue
            w = math.exp(-k / TAU_H)
            for j, truth in ak.items():
                if j not in a0:
                    continue
                if tb[j] is None:
                    continue
                med = statistics.median([v for i2, v in a0.items() if i2 != j])
                loo = mk + w * (med - m0)
                incl = mk + w * incl_bias
                deb = mk + tb[j]
                ld = deb + w * (med - m0 - tb[j])
                a = per[k][ts[:10]]
                for c, p in enumerate((mk, loo, incl, deb, ld)):
                    a[c] += abs(p - truth)
                a[5] += 1
    return per


def main():
    per = run(load(sys.argv[1] if len(sys.argv) > 1 else None))
    print(f"leave-one-station-out, t, tau={TAU_H:g}h (exploratory: archive starts 11-08)")
    print("MAE F      raw    loo   incl    deb loo+deb | gain vs deb [95% day-block]: loo | loo+deb")
    for k in LEADS:
        d = per[k]
        n = sum(v[5] for v in d.values())
        if not n:
            print(f"{k:>3}h  no rows"); continue
        m = [sum(v[c] for v in d.values()) / n for c in range(5)]
        g1 = day_block_gain({x: (v[3], v[1], v[5]) for x, v in d.items()}, holdout_only=False)
        g2 = day_block_gain({x: (v[3], v[4], v[5]) for x, v in d.items()}, holdout_only=False)
        print(f"{k:>3}h {n:>6} {m[0]:5.2f} {m[1]:5.2f} {m[2]:5.2f} {m[3]:5.2f} {m[4]:5.2f} | "
              f"{g1['gain']:+5.1f}% [{g1['lo']:+.1f},{g1['hi']:+.1f}] | {g2['gain']:+5.1f}% [{g2['lo']:+.1f},{g2['hi']:+.1f}] {g2['days']}d")


if __name__ == "__main__":
    main()

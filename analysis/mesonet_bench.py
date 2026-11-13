"""Plain mesonet + model benchmark for t at 6-47h, truth = Tempest network median (Cove-normalised).

At 6h+ the station network is not an input to the forecast, so nothing here is circular. Truth for a
valid hour = mean over archive ticks within +-30 min of the median of (t + off_t) over fresh stations.
Rows = forecast_log snapshot hours (GCS) with every source present. Columns, MAE F by lead band:
  served (t), hrrr (t_l1), nbm (t_raw_nbm), ecmwf (t_ecmwf), and each raw model minus its mean error
  over the PRIOR valid days in the same band (walk-forward; the first scored day needs >= 1 prior day).
Gain of each column vs served through analysis/ship_rule.day_block_gain (unit = valid day, exploratory).

    PYTHONPATH=. .venv/bin/python -m analysis.mesonet_bench [station_dir [forecast_log.json]]
    TRUTH=urma ... same, truth = URMA (no station dir needed; pass '' first)
"""
import collections
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from analysis.l2_loo_score import load, nets
from analysis.ship_rule import day_block_gain
from analysis.urma_shadow_score import snapshots

ET = ZoneInfo("America/New_York")
BANDS = (("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48))
SRC = (("served", "t"), ("hrrr", "t_l1"), ("nbm", "t_raw_nbm"), ("ecmwf", "t_ecmwf"))


def truth_by_hour(ticks):
    acc = collections.defaultdict(list)
    for ts, t in ticks.items():
        a = nets(t)
        if len(a) < 6:
            continue
        u = datetime.strptime(ts, "%Y-%m-%dT%H:%MZ")
        acc[(u + timedelta(minutes=13)).strftime("%Y-%m-%dT%H")].append(statistics.median(a.values()))  # :47 -> next hour
    return {k: sum(v) / len(v) for k, v in acc.items() if len(v) >= 4}


def main():
    if os.environ.get("TRUTH") == "urma":
        from analysis.urma_blend_wf import urma_idw
        U = urma_idw()
        print("truth = URMA idw (independent of the station network)")
    else:
        U = truth_by_hour(load(sys.argv[1] if len(sys.argv) > 1 else None))
    rows = collections.defaultdict(list)  # band -> [(day, errors{name: err})]
    for s in snapshots(sys.argv[2] if len(sys.argv) > 2 else None):
        run = datetime.strptime(s["run"], "%Y-%m-%dT%H:%M").replace(tzinfo=ET)
        for h in s["hours"]:
            v = datetime.strptime(h["v"], "%Y-%m-%dT%H:%M").replace(tzinfo=ET)
            lead = (v - run).total_seconds() / 3600
            tr = U.get(v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H"))
            band = next((n for n, lo, hi in BANDS if lo <= lead < hi), None)
            vals = {n: h.get(k) for n, k in SRC}
            if tr is None or band is None or any(x is None for x in vals.values()):
                continue
            rows[band].append((h["v"][:10], {n: x - tr for n, x in vals.items()}))
    print("t vs station-network truth, 6-47h (exploratory; stations archived from 11-08)")
    for band, _, _ in BANDS:
        rs = rows[band]
        days = sorted({d for d, _ in rs})
        by = collections.defaultdict(list)
        for d, e in rs:
            by[d].append(e)
        out = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0]))
        for i, d in enumerate(days):
            if i == 0:
                continue
            prior = [e for p in days[:i] for e in by[p]]
            bias = {n: statistics.mean(e[n] for e in prior) for n in ("hrrr", "nbm", "ecmwf")}
            for e in by[d]:
                for n in ("served", "hrrr", "nbm", "ecmwf"):
                    a = out[n][d]; a[0] += abs(e[n]); a[1] += 1
                for n in ("hrrr", "nbm", "ecmwf"):
                    a = out[n + "-deb"][d]; a[0] += abs(e[n] - bias[n]); a[1] += 1
        if not out["served"]:
            print(f"  {band}h: <2 days of rows"); continue
        n = sum(v[1] for v in out["served"].values())
        print(f"  {band}h  n={n}  days {len(out['served'])}")
        for name, dd in out.items():
            mae = sum(v[0] for v in dd.values()) / n
            if name == "served":
                print(f"     {name:<11} MAE {mae:.2f}")
                continue
            g = day_block_gain({d: (out["served"][d][0], v[0], v[1]) for d, v in dd.items()}, holdout_only=False)
            print(f"     {name:<11} MAE {mae:.2f}  vs served {g['gain']:+5.1f}% [{g['lo']:+.1f},{g['hi']:+.1f}]")


if __name__ == "__main__":
    main()

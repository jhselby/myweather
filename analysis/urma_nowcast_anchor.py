"""Exploratory: does a run's error right at issue time predict its own 6-47h error (vs URMA truth)?

For every pair-log run (run_time) and source (served, HRRR L1, raw NBM) take e0 = mean error at leads 0-1
vs URMA, then regress that run's error at each later lead (per band) on e0. slope = how much of the
current error persists; R2 = share of later-lead error variance explained; plus the MAE gain from
subtracting slope*e0 (fit on the earlier half of runs, scored on the later half). At live issue time e0
would come from the Tempest stations (they read ~0.4F above URMA). Exploratory, not ledgered.

    PYTHONPATH=. .venv/bin/python -m analysis.urma_nowcast_anchor
"""
import collections
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

from analysis import terminal_blend_field_fit as tb
from analysis.urma_blend_wf import LOG, urma_idw

ET = ZoneInfo("America/New_York")
SRC = (("served", None), ("hrrr", "forecast_l1"), ("nbm", "forecast_raw_nbm"))


def main():
    U = urma_idw()
    rx = re.compile(r'"field": ?"t"')
    runs = collections.defaultdict(lambda: collections.defaultdict(dict))  # run -> src -> {lead: err}
    with open(LOG) as fh:
        for line in fh:
            if not rx.search(line):
                continue
            r = json.loads(line)
            vt, rt = r.get("valid_time") or "", r.get("run_time") or ""
            if len(vt) < 13 or len(rt) < 13:
                continue
            u = datetime.strptime(vt[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=ET).astimezone(timezone.utc).strftime("%Y-%m-%dT%H")
            tr = U.get(u)
            if tr is None:
                continue
            L = int(r["lead_h"])
            ap = r.get("applied_layer")
            for name, key in SRC:
                v = (r.get("forecast_" + ap) if ap else None) if key is None else r.get(key)
                if key is None and v is None:
                    v = r.get("forecast")
                if v is not None:
                    runs[rt[:16]][name][L] = float(v) - tr
    print(f"runs with URMA-scored rows: {len(runs):,}")
    for name, _ in SRC:
        print(f"\n[{name}]")
        for band, lo, hi in tb.BANDS:
            X, Y, K = [], [], []
            for rt in sorted(runs):
                e = runs[rt].get(name, {})
                e0 = [e[l] for l in (0, 1) if l in e]
                later = [e[l] for l in range(lo, hi) if l in e]
                if e0 and len(later) >= max(2, (hi - lo) // 3):
                    X.append(np.mean(e0)); Y.append(np.mean(later)); K.append(rt)
            X, Y = np.array(X), np.array(Y)
            if len(X) < 100:
                print(f"  {band}h: n={len(X)} too few"); continue
            h = len(X) // 2
            slope = float((X[:h] * Y[:h]).sum() / (X[:h] ** 2).sum())  # through origin, early half
            ss = np.polyfit(X[:h], Y[:h], 1)
            r2 = float(np.corrcoef(X, Y)[0, 1] ** 2)
            base = float(np.abs(Y[h:]).mean())
            adj = float(np.abs(Y[h:] - slope * X[h:]).mean())
            print(f"  {band:>5}h n={len(X):>5} slope {slope:+.2f} R2 {r2:.2f} | later-half MAE of run-mean error {base:.2f} -> {adj:.2f} ({100*(1-adj/base):+.1f}%)")


if __name__ == "__main__":
    main()

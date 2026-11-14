"""Exploratory: does NWS (forecast_nws, gridpoint BOX 76,97) add a 4th blend input vs URMA truth?

Rows restricted to those with NWS present so B3 and B4n are scored on identical rows. Walk-forward 14 valid
days, per-source bias then weights (simplex step 0.1 for 4 inputs), baseline = served. Not ledgered.

    PYTHONPATH=. .venv/bin/python -m analysis.urma_blend_nws
"""
import collections
import itertools
from datetime import datetime, timedelta

import numpy as np

from analysis import terminal_blend_field_fit as tb
from analysis.ship_rule import HOLDOUT_START, day_block_gain
from analysis.urma_blend_wf import MIN_N, WIN, best_w, load

G4 = np.array([w for w in itertools.product(np.arange(0, 1.01, 0.1), repeat=4) if abs(sum(w) - 1) < 1e-9])


def main():
    data = [r for r in load() if r[8] is not None]
    print(f"rows with NWS: {len(data):,}")
    byband = collections.defaultdict(list)
    for r in data:
        byband[r[1]].append(r)
    for b, _, _ in tb.BANDS:
        rows = byband[b]
        days = sorted({r[0] for r in rows})
        per = {"B3": {}, "B4n (+NWS)": {}}
        nwsonly = {}
        for D in days:
            d0 = datetime.strptime(D, "%Y-%m-%d")
            fd = {d for d in days if d0 - timedelta(days=WIN) <= datetime.strptime(d, "%Y-%m-%d") < d0}
            if len(fd) < WIN - 2:
                continue
            fit = np.array([r[3:6] + (r[8],) for r in rows if r[0] in fd]); te = np.array([r[3:6] + (r[8],) for r in rows if r[0] == D])
            sv = np.array([r[2] for r in rows if r[0] == D])
            if len(fit) < MIN_N or not len(te):
                continue
            base = float(np.abs(sv).sum()); n = len(te)
            b3 = fit[:, :3].mean(0); w3 = best_w(fit[:, :3] - b3)
            per["B3"][D] = (base, float(np.abs((te[:, :3] - b3) @ w3).sum()), n)
            b4 = fit.mean(0); w4 = G4[int(np.abs((fit - b4) @ G4.T).sum(0).argmin())]
            per["B4n (+NWS)"][D] = (base, float(np.abs((te - b4) @ w4).sum()), n)
        print(f"\n== t {b}h vs URMA truth, baseline = served, {len(per['B3'])} scored days ==")
        for nm, pd in per.items():
            g = day_block_gain(pd, holdout_only=False)
            gh = day_block_gain({d: v for d, v in pd.items() if d >= HOLDOUT_START})
            print(f"  {nm:<12} all {g['gain']:+5.1f}% [{g['lo']:+5.1f},{g['hi']:+5.1f}] {g['wins']}/{g['days']}d | holdout {gh['gain']:+5.1f}% [{gh['lo']:+5.1f},{gh['hi']:+5.1f}] {gh['wins']}/{gh['days']}d")


if __name__ == "__main__":
    main()

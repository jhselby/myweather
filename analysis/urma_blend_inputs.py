"""Exploratory: does adding the served t as a 4th blend input improve the URMA-truth shadow blend?

Walk-forward as urma_blend_wf (14 valid-day fit, score next day, identical rows, baseline = served).
  B3   per-source bias + 3-way weights over [hrrr, nbm, ecmwf]              (the shadow as shipped)
  B4s  same over [served, hrrr, nbm, ecmwf], simplex grid step 0.1
Served already carries the station correction, so at 6-11h it may add what the three models lack.
Not ledgered (exploratory).

    PYTHONPATH=. .venv/bin/python -m analysis.urma_blend_inputs
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
    data = load()
    byband = collections.defaultdict(list)
    for r in data:
        byband[r[1]].append(r)
    for b, _, _ in tb.BANDS:
        rows = byband[b]
        days = sorted({r[0] for r in rows})
        per = {"B3": {}, "B4s (+served)": {}}
        for D in days:
            d0 = datetime.strptime(D, "%Y-%m-%d")
            fd = {d for d in days if d0 - timedelta(days=WIN) <= datetime.strptime(d, "%Y-%m-%d") < d0}
            if len(fd) < WIN - 2:
                continue
            fit = np.array([r[2:6] for r in rows if r[0] in fd]); te = np.array([r[2:6] for r in rows if r[0] == D])
            if len(fit) < MIN_N or not len(te):
                continue
            base = float(np.abs(te[:, 0]).sum()); n = len(te)
            e3, t3 = fit[:, 1:4], te[:, 1:4]
            b3 = e3.mean(0); w3 = best_w(e3 - b3)
            per["B3"][D] = (base, float(np.abs((t3 - b3) @ w3).sum()), n)
            e4, t4 = fit, te            # columns: served, hrrr, nbm, ecmwf
            b4 = e4.mean(0); w4 = G4[int(np.abs((e4 - b4) @ G4.T).sum(0).argmin())]
            per["B4s (+served)"][D] = (base, float(np.abs((t4 - b4) @ w4).sum()), n)
        print(f"\n== t {b}h vs URMA truth, baseline = served ==")
        for nm, pd in per.items():
            g = day_block_gain(pd, holdout_only=False)
            gh = day_block_gain({d: v for d, v in pd.items() if d >= HOLDOUT_START})
            print(f"  {nm:<15} all {g['gain']:+5.1f}% [{g['lo']:+5.1f},{g['hi']:+5.1f}] {g['wins']}/{g['days']}d | holdout {gh['gain']:+5.1f}% [{gh['lo']:+5.1f},{gh['hi']:+5.1f}] {gh['wins']}/{gh['days']}d")


if __name__ == "__main__":
    main()

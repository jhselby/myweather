"""Exploratory ceiling for the t shadow blend vs URMA truth: how much is left if the daily bias were known?

Per band, on the same rows as urma_blend_wf (baseline = served):
  walk-forward  B3 as shipped (14 d bias + weights)
  oracle bias   each valid day's own mean per-source error subtracted (not knowable at issue time), weights as walk-forward
  oracle both   same-day bias AND same-day best weights
The gap walk-forward -> oracle bias is the most that better bias PREDICTION (regime/weather conditioning)
could add; oracle both bounds what the three inputs can do at all. Exploratory, not ledgered.

    PYTHONPATH=. .venv/bin/python -m analysis.urma_blend_ceiling
"""
import collections
from datetime import datetime, timedelta

import numpy as np

from analysis import terminal_blend_field_fit as tb
from analysis.ship_rule import day_block_gain
from analysis.urma_blend_wf import MIN_N, WIN, best_w, load


def main():
    data = load()
    byband = collections.defaultdict(list)
    for r in data:
        byband[r[1]].append(r)
    for b, _, _ in tb.BANDS:
        rows = byband[b]
        days = sorted({r[0] for r in rows})
        per = {"walk-forward": {}, "oracle bias": {}, "oracle bias+weights": {}}
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
            per["walk-forward"][D] = (base, float(np.abs((t3 - b3) @ w3).sum()), n)
            bo = t3.mean(0)
            per["oracle bias"][D] = (base, float(np.abs((t3 - bo) @ w3).sum()), n)
            wo = best_w(t3 - bo)
            per["oracle bias+weights"][D] = (base, float(np.abs((t3 - bo) @ wo).sum()), n)
        print(f"\n== t {b}h vs URMA truth, baseline = served ==")
        for nm, pd in per.items():
            g = day_block_gain(pd, holdout_only=False)
            print(f"  {nm:<20} {g['gain']:+5.1f}% [{g['lo']:+5.1f},{g['hi']:+5.1f}] {g['wins']}/{g['days']}d")


if __name__ == "__main__":
    main()

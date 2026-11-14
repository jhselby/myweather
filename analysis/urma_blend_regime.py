"""Exploratory: flow-regime-conditioned bias on top of the shadow blend (walk-forward vs URMA truth).

Baseline = served. B3 = shipped shape (14 d bias + 3-way weights). B3+regime = same weights, per-source bias
= 14 d overall bias + k_shrink * (flow-regime group mean over the last LONG days - overall mean over the same
days), groups need >= MIN_G rows, shrink n/(n+K). Regime = forecast state_fc regime_flow of each row.
Not ledgered; a winner must still pass ship_rule on forward days.

    PYTHONPATH=. .venv/bin/python -m analysis.urma_blend_regime
"""
import collections
from datetime import datetime, timedelta

import numpy as np

from analysis import terminal_blend_field_fit as tb
from analysis.ship_rule import HOLDOUT_START, day_block_gain
from analysis.urma_blend_wf import MIN_N, WIN, best_w, load

LONG, MIN_G, K = 45, 150, 300.0


def main():
    data = load()
    byband = collections.defaultdict(list)
    for r in data:
        byband[r[1]].append(r)
    for b, _, _ in tb.BANDS:
        rows = byband[b]
        days = sorted({r[0] for r in rows})
        per = {"B3": {}, "B3+regime": {}}
        for D in days:
            d0 = datetime.strptime(D, "%Y-%m-%d")
            age = lambda d: (d0 - datetime.strptime(d, "%Y-%m-%d")).days
            fr = [r for r in rows if 0 < age(r[0]) <= WIN]
            if len({r[0] for r in fr}) < WIN - 2 or len(fr) < MIN_N:
                continue
            te = [r for r in rows if r[0] == D]
            if not te:
                continue
            e3 = np.array([r[3:6] for r in fr]); b3 = e3.mean(0); w3 = best_w(e3 - b3)
            tt = np.array([r[3:6] for r in te]); base = float(np.abs(np.array([r[2] for r in te])).sum()); n = len(te)
            per["B3"][D] = (base, float(np.abs((tt - b3) @ w3).sum()), n)
            lr = [r for r in rows if 0 < age(r[0]) <= LONG]
            lall = np.array([r[3:6] for r in lr]); lmean = lall.mean(0)
            grp = collections.defaultdict(list)
            for r in lr:
                grp[r[7]].append(r[3:6])
            adj = {}
            for g, v in grp.items():
                if len(v) >= MIN_G:
                    adj[g] = (len(v) / (len(v) + K)) * (np.array(v).mean(0) - lmean)
            bt = np.array([b3 + adj.get(r[7], 0.0) for r in te])
            per["B3+regime"][D] = (base, float(np.abs((tt - bt) @ w3).sum()), n)
        print(f"\n== t {b}h vs URMA truth, baseline = served, {len(per['B3'])} scored days ==")
        for nm, pd in per.items():
            g = day_block_gain(pd, holdout_only=False)
            gh = day_block_gain({d: v for d, v in pd.items() if d >= HOLDOUT_START})
            print(f"  {nm:<10} all {g['gain']:+5.1f}% [{g['lo']:+5.1f},{g['hi']:+5.1f}] {g['wins']}/{g['days']}d | holdout {gh['gain']:+5.1f}% [{gh['lo']:+5.1f},{gh['hi']:+5.1f}] {gh['wins']}/{gh['days']}d")


if __name__ == "__main__":
    main()

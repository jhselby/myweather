"""Exploratory bias/weight variants for the t shadow blend, walk-forward vs URMA truth.

Same rows and baseline (served) as urma_blend_wf. Fit window 14 valid days for weights; variants differ
in how the per-source bias is estimated: window length, recency weighting, valid-hour-of-day. Results
are NOT ledgered (exploratory); a winner still has to pass ship_rule on forward days.

    PYTHONPATH=. .venv/bin/python -m analysis.urma_blend_variants
"""
import collections
import sys
from datetime import datetime, timedelta

import numpy as np

from analysis import terminal_blend_field_fit as tb
from analysis.ship_rule import HOLDOUT_START, day_block_gain
from analysis.urma_blend_wf import MIN_N, WIN, best_w, load


def wmean(x, ages, half):
    w = 0.5 ** (ages / half) if half else np.ones(len(x))
    return (x * w[:, None]).sum(0) / w.sum()


def main():
    data = load()
    byband = collections.defaultdict(list)
    for r in data:
        byband[r[1]].append(r)
    names = ["B14 (shipped shape)", "B7", "B3", "B14 hl3", "B14 hl5", "B+diurnal(6h blocks)", "B hl3 + diurnal shrunk"]
    for b, _, _ in tb.BANDS:
        rows = byband[b]
        days = sorted({r[0] for r in rows})
        per = {n: {} for n in names}
        for D in days:
            d0 = datetime.strptime(D, "%Y-%m-%d")
            age = lambda d: (d0 - datetime.strptime(d, "%Y-%m-%d")).days
            fr = [r for r in rows if 0 < age(r[0]) <= WIN]
            if len({r[0] for r in fr}) < WIN - 2 or len(fr) < MIN_N:
                continue
            fit = np.array([r[2:6] for r in fr]); ages = np.array([age(r[0]) for r in fr], float)
            hrs = np.array([r[6] for r in fr])
            tr_ = [r for r in rows if r[0] == D]
            if not tr_:
                continue
            test = np.array([r[2:6] for r in tr_]); th = np.array([r[6] for r in tr_])
            base = float(np.abs(test[:, 0]).sum()); n = len(test)
            e3, t3 = fit[:, 1:4], test[:, 1:4]
            wB = best_w(e3 - e3.mean(0))

            def score(bias_fit, bias_test, w):
                return float(np.abs((t3 - bias_test) @ w).sum())

            b14 = e3.mean(0)
            per[names[0]][D] = (base, score(None, b14, wB), n)
            for nm, lim in ((names[1], 7), (names[2], 3)):
                m = ages <= lim
                per[nm][D] = (base, score(None, e3[m].mean(0) if m.sum() > 50 else b14, wB), n)
            for nm, hl in ((names[3], 3), (names[4], 5)):
                bh = wmean(e3, ages, hl)
                per[nm][D] = (base, score(None, bh, wB), n)
            # diurnal: bias by 6 h block of valid hour, shrunk toward overall mean by n/(n+k)
            blk = lambda h: h // 6
            bt = np.zeros_like(t3)
            bt_s = np.zeros_like(t3)
            bh = wmean(e3, ages, 3)
            for i, h in enumerate(th):
                m = (hrs // 6) == blk(h)
                bd = e3[m].mean(0) if m.sum() > 30 else b14
                bt[i] = bd
                k = 60.0
                bt_s[i] = bh + (m.sum() / (m.sum() + k)) * (bd - b14)
            per[names[5]][D] = (base, float(np.abs((t3 - bt) @ wB).sum()), n)
            per[names[6]][D] = (base, float(np.abs((t3 - bt_s) @ wB).sum()), n)
        print(f"\n== t {b}h vs URMA truth, baseline = served, {len(per[names[0]])} scored days ==")
        for nm, pd in per.items():
            g = day_block_gain(pd, holdout_only=False)
            gh = day_block_gain({d: v for d, v in pd.items() if d >= HOLDOUT_START})
            print(f"  {nm:<26} all {g['gain']:+5.1f}% [{g['lo']:+5.1f},{g['hi']:+5.1f}] {g['wins']}/{g['days']}d | holdout {gh['gain']:+5.1f}% [{gh['lo']:+5.1f},{gh['hi']:+5.1f}] {gh['wins']}/{gh['days']}d")


if __name__ == "__main__":
    main()

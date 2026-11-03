"""Walk-forward test: per-model bias correction on ECMWF and NBM BEFORE the 3-way blend.

Baseline A = the shipped rule: per-lead-band 3-way weights (HRRR terminal, NBM terminal,
ECMWF raw) fit on the prior 14 days, scored on the next valid day.
Variants subtract a shrunk mean error (per lead band x 4h local block, or per band only)
from ECMWF, from ECMWF + NBM, or from all three, then refit the weights on the corrected
errors. Fit window = 14 days before the scored day; bias is estimated on the same window.
ECMWF errors come from the Open-Meteo previous-runs archive on the live (lag 1h) convention,
exactly as terminal_blend_field_fit.py does. Truth = pair-log `observed` (the shrunk value; see
the v0.7.86 truth audit; rescore on observed_stations once it has weeks of rows).

Results are exploratory until HOLDOUT_START days exist (analysis/ship_rule.py).

    .venv/bin/python -m analysis.bias_before_blend_wf
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis._cache import cached_path, PAIR_LOG_URL  # noqa: E402
from analysis import terminal_blend_field_fit as tb  # noqa: E402
from analysis.ship_rule import day_block_gain, verdict, record  # noqa: E402

FIELDS = ("t", "h", "ws")
WIN = 14
SHRINK_K = 50
GRID3 = np.asarray(tb.GRID3)


def load():
    rows = []
    days = set()
    with open(cached_path(PAIR_LOG_URL)) as fin:
        for line in fin:
            if '"field"' not in line:
                continue
            r = json.loads(line)
            f = r.get("field")
            if f not in FIELDS or r.get("observed") is None or r.get("lead_h") is None:
                continue
            vt = r.get("valid_time") or ""
            if len(vt) < 13:
                continue
            eh = tb._first(r, tb.HRRR_KEYS.get(f, tb.HRRR_DEFAULT))
            en = tb._first(r, tb.NBM_KEYS)
            if eh is None or en is None:
                continue
            rows.append((f, vt[:10], int(vt[11:13]), int(r["lead_h"]), vt, eh, en, float(r["observed"])))
            days.add(vt[:10])
    lo, hi = min(days), max(days)
    ehist = tb.ecmwf_history(lo, hi)
    out = []
    for f, day, hr, lead, vt, eh, en, obs in rows:
        fe = (ehist.get(tb._ecmwf_key(vt)) or {}).get(f)
        fe = fe[tb._ecmwf_day(lead)] if fe else None
        if fe is None:
            continue
        band = next((b for b, a, z in tb.BANDS if a <= lead < z), None)
        if band is None:
            continue
        out.append((f, day, hr // 4 * 4, band, eh, en, float(fe) - obs))
    return out


def bias_table(rows, col, cellfn):
    s, n = defaultdict(float), defaultdict(int)
    for r in rows:
        c = cellfn(r)
        s[c] += r[col]
        n[c] += 1
    return {c: s[c] / (n[c] + SHRINK_K) for c in s}


def best_w(a):
    return GRID3[int(np.abs(a @ GRID3.T).sum(0).argmin())]


def run():
    data = load()
    print(f"rows {len(data):,}")
    # variants: name -> (columns to correct (4=hrrr,5=nbm,6=ecmwf), cell function)
    cells = {"band": lambda r: r[3], "band x 4h": lambda r: (r[3], r[2])}
    variants = {"A raw": ((), None)}
    for cn, cf in cells.items():
        variants[f"B ecmwf [{cn}]"] = ((6,), cf)
        variants[f"C ecmwf+nbm [{cn}]"] = ((5, 6), cf)
        variants[f"D all three [{cn}]"] = ((4, 5, 6), cf)
    byf = defaultdict(list)
    for r in data:
        byf[r[0]].append(r)
    for f in FIELDS:
        rows = byf[f]
        days = sorted({r[1] for r in rows})
        per = {v: {} for v in variants}
        standalone = {v: [0.0, 0.0, 0] for v in variants}
        for D in days:
            fit_days = {d for d in days if (datetime.strptime(D, "%Y-%m-%d") - timedelta(days=WIN))
                        <= datetime.strptime(d, "%Y-%m-%d") < datetime.strptime(D, "%Y-%m-%d")}
            if len(fit_days) < WIN - 2:
                continue
            fit = [r for r in rows if r[1] in fit_days]
            test = [r for r in rows if r[1] == D]
            if not test:
                continue
            for vn, (cols, cf) in variants.items():
                tabs = {c: bias_table(fit, c, cf) for c in cols} if cols else {}

                def corr(r, c):
                    return r[c] - (tabs[c].get(cf(r), 0.0) if c in tabs else 0.0)

                abs_err = 0.0
                n = 0
                for b, _, _ in tb.BANDS:
                    fb = [r for r in fit if r[3] == b]
                    tbnd = [r for r in test if r[3] == b]
                    if len(fb) < 300 or not tbnd:
                        continue
                    w = best_w(np.asarray([[corr(r, 4), corr(r, 5), corr(r, 6)] for r in fb]))
                    a = np.asarray([[corr(r, 4), corr(r, 5), corr(r, 6)] for r in tbnd]) @ w
                    abs_err += float(np.abs(a).sum())
                    n += len(tbnd)
                per[vn][D] = [abs_err, n]
        # aligned comparison: days/rows where both baseline and variant exist
        print(f"\n== {f} ({len(days)} days, walk-forward fit prior {WIN}d) ==")
        base = per["A raw"]
        for vn in variants:
            if vn == "A raw":
                continue
            pd = {d: (base[d][0], per[vn][d][0], per[vn][d][1]) for d in per[vn]
                  if d in base and base[d][1] == per[vn][d][1] and base[d][1] > 0}
            g = day_block_gain(pd, holdout_only=False)
            print(f"  {vn:<28} {verdict(g)}")
            record("bias_before_blend_wf", f"{f} {vn}", g, note="exploratory, observed (shrunk) truth")


if __name__ == "__main__":
    run()

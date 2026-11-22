"""Walk-forward dp blend fitted and scored against URMA dew point (independent truth).

Why: served dp inherits the old `observed` truth's dry bias (-0.7..-0.95 F vs URMA, analysis/urma_field_score.py),
and raw HRRR dp runs -2.7 F, raw NBM +0.7 F. t was fixed the same way (urma_blend_wf.py, served as t_urmab).
Same rows per band: served (forecast_{applied_layer}), weather.gov (forecast_nws, the bar), and candidates fit on the
prior 14 valid days and scored on the next day, on identical rows (sources: HRRR L1, NBM raw, ECMWF dew_point_2m):
  A  3-way weights fit on URMA error
  B  per-source trailing bias subtracted, then 3-way weights
  C  served minus its trailing bias
Gain vs served and vs weather.gov through analysis/ship_rule.py (holdout days >= HOLDOUT_START). Exploratory:
nothing is written to the ledger unless URMA_WF_RECORD=1.

    PYTHONPATH=. .venv/bin/python -m analysis.urma_blend_wf_dp
"""
import collections
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis import terminal_blend_field_fit as tb  # noqa: E402
from analysis.ship_rule import HOLDOUT_START, day_block_gain, record, verdict  # noqa: E402
from analysis.urma_blend_wf import LOG, URMA, WIN, MIN_N, best_w  # noqa: E402

ET = ZoneInfo("America/New_York")
tb.E_VARS["dp"] = "dew_point_2m"   # ecmwf_history reads E_VARS; adds the dew point to the same previous-runs pull


def urma_dpt():
    out = {}
    for line in open(URMA):
        if '"DPT"' not in line:
            continue
        r = json.loads(line)
        nb = r["nb"]
        w = np.array([1 / max(x[2], 0.1) ** 2 for x in nb])
        out[r["valid"][:13]] = ((sum(wi * x[3] for wi, x in zip(w, nb)) / w.sum()) - 273.15) * 9 / 5 + 32
    return out


def load():
    U = urma_dpt()
    rx = re.compile(r'"field": ?"dp"')
    rows = []
    with open(LOG) as fh:
        for line in fh:
            if not rx.search(line):
                continue
            r = json.loads(line)
            vt = r.get("valid_time") or ""
            ap = r.get("applied_layer")
            sv = r.get("forecast_" + ap) if ap else None
            if sv is None:
                sv = r.get("forecast")
            if sv is None or r.get("forecast_l1") is None or r.get("forecast_raw_nbm") is None or r.get("forecast_nws") is None or len(vt) < 13:
                continue
            u = datetime.strptime(vt[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=ET).astimezone(timezone.utc)
            k = u.strftime("%Y-%m-%dT%H")
            if k not in U:
                continue
            rows.append((vt[:10], int(r["lead_h"]), vt, float(sv), float(r["forecast_l1"]),
                         float(r["forecast_raw_nbm"]), U[k], float(r["forecast_nws"])))
    days = sorted({r[0] for r in rows})
    eh = tb.ecmwf_history(days[0], days[-1])
    out = []
    for day, lead, vt, sv, hr, nb, tr, nws in rows:
        fe = (eh.get(tb._ecmwf_key(vt)) or {}).get("dp")
        fe = fe[tb._ecmwf_day(lead)] if fe else None
        band = next((b for b, lo, hi in tb.BANDS if lo <= lead < hi), None)
        if fe is None or band is None:
            continue
        out.append((day, band, sv - tr, hr - tr, nb - tr, float(fe) - tr, nws - tr))
    return out


def run():
    data = load()
    print(f"rows {len(data):,}; days {min(r[0] for r in data)}..{max(r[0] for r in data)}")
    byband = collections.defaultdict(list)
    for r in data:
        byband[r[1]].append(r)
    for b, _, _ in tb.BANDS:
        rows = byband[b]
        days = sorted({r[0] for r in rows})
        per = {"A weights": {}, "B bias+weights": {}, "C served-bias": {}}
        pern = {k: {} for k in per}   # same candidates vs weather.gov
        for D in days:
            d0 = datetime.strptime(D, "%Y-%m-%d")
            fit_days = {d for d in days if d0 - timedelta(days=WIN) <= datetime.strptime(d, "%Y-%m-%d") < d0}
            if len(fit_days) < WIN - 2:
                continue
            fit = np.array([r[2:6] for r in rows if r[0] in fit_days])
            test = np.array([r[2:7] for r in rows if r[0] == D])
            if len(fit) < MIN_N or len(test) == 0:
                continue
            base = float(np.abs(test[:, 0]).sum())
            nws = float(np.abs(test[:, 4]).sum())
            wA = best_w(fit[:, 1:4])
            bias = fit[:, 1:4].mean(0)
            wB = best_w(fit[:, 1:4] - bias)
            cand = {"A weights": float(np.abs(test[:, 1:4] @ wA).sum()),
                    "B bias+weights": float(np.abs((test[:, 1:4] - bias) @ wB).sum()),
                    "C served-bias": float(np.abs(test[:, 0] - fit[:, 0].mean()).sum())}
            for k, v in cand.items():
                per[k][D] = (base, v, len(test))
                pern[k][D] = (nws, v, len(test))
        print(f"\n== dp {b}h vs URMA dew point ==")
        for name in per:
            for label, pd in (("vs served", per[name]), ("vs weather.gov", pern[name])):
                g = day_block_gain(pd, holdout_only=False)
                gh = day_block_gain({d: v for d, v in pd.items() if d >= HOLDOUT_START})
                print(f"  {name:<15} {label:<14} ALL     {verdict(g)}")
                print(f"  {'':<15} {'':<14} HOLDOUT {verdict(gh)}")
                if os.environ.get("URMA_WF_RECORD") == "1" and label == "vs served":
                    record("urma_blend_wf_dp", f"dp {b}h {name} vs served (URMA truth)", gh,
                           note="walk-forward 14d, truth=URMA DPT idw, rows with hrrr+nbm+ecmwf+nws")


if __name__ == "__main__":
    run()

"""Walk-forward ws blend fitted and scored against URMA 10 m wind (independent truth).

Joe 11-20: wind is scored on URMA (Neptune Rd, the only live waterfront anemometer, tracks URMA
worst of 17 stations, corr 0.35; the scored `observed` 0.84). The live ws blend (terminal_blend_field_fit)
is fit on `observed` and gives ECMWF 0.35-0.45 at 6-47h; on URMA served loses to raw NBM at 6-23h.
Same rows per band: served (forecast_{applied_layer}), raw NBM (the normal source), and candidates
fit on the prior 14 valid days, scored on the next day:
  A  3-way weights fit on URMA error
  B  per-source trailing bias subtracted, then 3-way weights
Gain vs served and vs raw NBM through analysis/ship_rule.py (holdout days >= HOLDOUT_START).

    PYTHONPATH=. .venv/bin/python -m analysis.urma_blend_wf_ws
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
from analysis._truth import wind_open  # noqa: E402

# 11-28: score only hours whose forecast wind blows from a direction the Cove is open to (the
# scorecard's ws rule since v0.7.172). WS_ALL_DIRS=1 scores every hour as before.
OPEN_ONLY = os.environ.get("WS_ALL_DIRS") != "1"

ET = ZoneInfo("America/New_York")
MS_TO_MPH = 2.23694


def urma_wind(var="WIND"):
    out = {}
    for line in open(URMA):
        if f'"{var}"' not in line:
            continue
        r = json.loads(line)
        nb = r["nb"]
        w = np.array([1 / max(x[2], 0.1) ** 2 for x in nb])
        out[r["valid"][:13]] = float(sum(wi * x[3] for wi, x in zip(w, nb)) / w.sum()) * MS_TO_MPH
    return out


def load():
    U = urma_wind()
    rx = re.compile(r'"field": ?"ws"')
    rows = []
    with open(LOG) as fh:
        for line in fh:
            if not rx.search(line):
                continue
            r = json.loads(line)
            if OPEN_ONLY and not wind_open(r):
                continue
            vt = r.get("valid_time") or ""
            ap = r.get("applied_layer")
            sv = r.get("forecast_" + ap) if ap else None
            if sv is None:
                sv = r.get("forecast")
            if sv is None or r.get("forecast_l1") is None or r.get("forecast_raw_nbm") is None or len(vt) < 13:
                continue
            k = datetime.strptime(vt[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=ET).astimezone(timezone.utc).strftime("%Y-%m-%dT%H")
            if k not in U:
                continue
            rows.append((vt[:10], int(r["lead_h"]), vt, float(sv), float(r["forecast_l1"]), float(r["forecast_raw_nbm"]), U[k]))
    days = sorted({r[0] for r in rows})
    eh = tb.ecmwf_history(days[0], days[-1])
    out = []
    for day, lead, vt, sv, hr, nb, tr in rows:
        fe = (eh.get(tb._ecmwf_key(vt)) or {}).get("ws")
        fe = fe[tb._ecmwf_day(lead)] if fe else None
        band = next((b for b, lo, hi in tb.BANDS if lo <= lead < hi), None)
        if fe is None or band is None:
            continue
        out.append((day, band, sv - tr, hr - tr, nb - tr, float(fe) - tr))
    return out


def run():
    data = load()
    print(f"rows {len(data):,}" + (" (open directions only; WS_ALL_DIRS=1 for all)" if OPEN_ONLY else " (all directions)"))
    byband = collections.defaultdict(list)
    for r in data:
        byband[r[1]].append(r)
    for b, _, _ in tb.BANDS:
        rows = byband[b]
        days = sorted({r[0] for r in rows})
        per = collections.defaultdict(dict)
        wlog = []
        for D in days:
            d0 = datetime.strptime(D, "%Y-%m-%d")
            fit_days = {d for d in days if d0 - timedelta(days=WIN) <= datetime.strptime(d, "%Y-%m-%d") < d0}
            if len(fit_days) < WIN - 2:
                continue
            fit = np.array([r[2:6] for r in rows if r[0] in fit_days])
            test = np.array([r[2:6] for r in rows if r[0] == D])
            if len(fit) < MIN_N or len(test) == 0:
                continue
            srv = float(np.abs(test[:, 0]).sum())
            nbm = float(np.abs(test[:, 2]).sum())
            wA = best_w(fit[:, 1:4])
            a = float(np.abs(test[:, 1:4] @ wA).sum())
            bias = fit[:, 1:4].mean(0)
            wB = best_w(fit[:, 1:4] - bias)
            bb = float(np.abs((test[:, 1:4] - bias) @ wB).sum())
            n = len(test)
            per["A weights vs served"][D] = (srv, a, n)
            per["A weights vs NBM"][D] = (nbm, a, n)
            per["B bias+weights vs served"][D] = (srv, bb, n)
            per["B bias+weights vs NBM"][D] = (nbm, bb, n)
            per["raw NBM vs served"][D] = (srv, nbm, n)
            wlog.append(tuple(wA))
        print(f"\n== ws {b}h vs URMA wind, walk-forward {WIN}d ==")
        if wlog:
            print(f"  A weights [hrrr, nbm, ecmwf] mean {np.round(np.mean(wlog, 0), 2).tolist()}, last {list(wlog[-1])}")
        for name, pd in per.items():
            g = day_block_gain(pd, holdout_only=False)
            gh = day_block_gain({d: v for d, v in pd.items() if d >= HOLDOUT_START})
            print(f"  {name:<26} ALL     {verdict(g)}")
            print(f"  {'':<26} HOLDOUT {verdict(gh)}")
            if os.environ.get("URMA_WF_RECORD") == "1":
                record("urma_blend_wf_ws", f"ws {b}h {name} (URMA truth)", gh,
                       note="walk-forward 14d, truth=URMA WIND idw, rows with hrrr+nbm+ecmwf"
                       + (", open directions only" if OPEN_ONLY else ""))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
    else:
        run()

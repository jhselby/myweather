"""Walk-forward h (relative humidity) blend fitted on URMA truth: does the t recipe carry over to h?

Same design as urma_blend_wf (t): per pair-log row HRRR raw (forecast_l1), NBM raw (forecast_raw_nbm),
ECMWF raw (Open-Meteo previous-runs, live 1 h lag via terminal_blend_field_fit). URMA h from URMA T/Td
(urma_field_score.urma_truth). Fit on the prior 14 valid days per lead band, score the next day.
Baseline = served (forecast_{applied_layer}). Candidates:
  A  3-way weights fit on URMA error
  B  per-source trailing bias (vs URMA) subtracted, then 3-way weights
Scored on URMA (all days and holdout) AND, where the row has observed_stations, on the station truth,
because NBM is calibrated to URMA and the two truths disagree on moisture (11-14: stations ~2.5% RH drier).
Exploratory; ledger only with URMA_WF_H_RECORD=1.

    PYTHONPATH=. .venv/bin/python -m analysis.urma_blend_wf_h
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
from analysis.urma_blend_wf import LOG  # noqa: E402
from analysis.urma_field_score import urma_truth  # noqa: E402

ET = ZoneInfo("America/New_York")
WIN, MIN_N = 14, 300
GRID3 = np.asarray(tb.GRID3)


def load():
    U = urma_truth()
    rx = re.compile(r'"field": ?"h"')
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
            if sv is None or r.get("forecast_l1") is None or r.get("forecast_raw_nbm") is None or len(vt) < 13:
                continue
            u = datetime.strptime(vt[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=ET).astimezone(timezone.utc)
            tr = U.get(u.strftime("%Y-%m-%dT%H"), {}).get("h")
            if tr is None:
                continue
            rows.append((vt[:10], int(r["lead_h"]), vt, float(sv), float(r["forecast_l1"]),
                         float(r["forecast_raw_nbm"]), tr, r.get("observed_stations")))
    days = sorted({r[0] for r in rows})
    eh = tb.ecmwf_history(days[0], days[-1])
    out = []
    for day, lead, vt, sv, hr, nb, tr, st in rows:
        fe = (eh.get(tb._ecmwf_key(vt)) or {}).get("h")
        fe = fe[tb._ecmwf_day(lead)] if fe else None
        band = next((b for b, lo, hi in tb.BANDS if lo <= lead < hi), None)
        if fe is None or band is None:
            continue
        # forecasts, URMA truth, station truth (or nan)
        out.append((day, band, sv, hr, nb, float(fe), tr, float("nan") if st is None else float(st)))
    return out


def best_w(e3):
    return GRID3[int(np.abs(e3 @ GRID3.T).sum(0).argmin())]


def run():
    data = load()
    print(f"rows {len(data):,}")
    byband = collections.defaultdict(list)
    for r in data:
        byband[r[1]].append(r)
    rec = os.environ.get("URMA_WF_H_RECORD") == "1"
    for b, _, _ in tb.BANDS:
        rows = byband[b]
        days = sorted({r[0] for r in rows})
        per = {k: {} for k in ("A weights", "B bias+weights")}
        per_st = {k: {} for k in per}
        for D in days:
            d0 = datetime.strptime(D, "%Y-%m-%d")
            fit_days = {d for d in days if d0 - timedelta(days=WIN) <= datetime.strptime(d, "%Y-%m-%d") < d0}
            if len(fit_days) < WIN - 2:
                continue
            fit = np.array([r[2:8] for r in rows if r[0] in fit_days])
            test = np.array([r[2:8] for r in rows if r[0] == D])
            if len(fit) < MIN_N or len(test) == 0:
                continue
            fe = fit[:, 1:4] - fit[:, [4]]          # source errors vs URMA
            wA = best_w(fe)
            bias = fe.mean(0)
            wB = best_w(fe - bias)
            candA = test[:, 1:4] @ wA
            candB = (test[:, 1:4] - bias) @ wB
            for name, c in (("A weights", candA), ("B bias+weights", candB)):
                per[name][D] = (float(np.abs(test[:, 0] - test[:, 4]).sum()), float(np.abs(c - test[:, 4]).sum()), len(test))
                m = ~np.isnan(test[:, 5])
                if m.sum():
                    per_st[name][D] = (float(np.abs(test[m, 0] - test[m, 5]).sum()), float(np.abs(c[m] - test[m, 5]).sum()), int(m.sum()))
        print(f"\n== h {b}h, baseline = served ==")
        for name in per:
            g = day_block_gain(per[name], holdout_only=False)
            gh = day_block_gain({d: v for d, v in per[name].items() if d >= HOLDOUT_START})
            gs = day_block_gain(per_st[name], holdout_only=False)
            print(f"  {name:<15} URMA ALL      {verdict(g)}")
            print(f"  {'':<15} URMA HOLDOUT  {verdict(gh)}")
            print(f"  {'':<15} STATIONS      {verdict(gs)}")
            if rec:
                record("urma_blend_wf_h", f"h {b}h {name} vs served (URMA truth)", gh,
                       note="walk-forward 14d, truth=URMA T/Td idw, rows with hrrr+nbm+ecmwf")


if __name__ == "__main__":
    run()

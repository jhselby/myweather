"""Walk-forward t blend fitted and scored against URMA (independent truth), not the shrunk `observed`.

Inputs per pair-log row: HRRR raw (forecast_l1), NBM raw (forecast_raw_nbm), ECMWF (Open-Meteo
previous-runs archive on the live 1 h lag convention, as terminal_blend_field_fit does).
Baseline = the served value (forecast_{applied_layer}). Candidates, all fit on the prior 14 valid
days per lead band and scored on the next day, on identical rows:
  A  3-way weights fit on URMA error (no bias term)
  B  per-source trailing bias subtracted, then 3-way weights
  C  served minus its trailing bias (the earlier debias test, same rows)
Results go through analysis/ship_rule.py (day-block bootstrap, holdout days >= 2026-11-03) and the ledger.

    PYTHONPATH=. .venv/bin/python -m analysis.urma_blend_wf
"""
import ast
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

ET = ZoneInfo("America/New_York")
URMA = ROOT / "analysis" / "output" / "urma_truth" / "urma_cell.jsonl"
LOG = Path.home() / ".cache" / "myweather" / "forecast_error_log_backstamped.jsonl"
WIN, MIN_N = 14, 300
GRID3 = np.asarray(tb.GRID3)


def urma_idw():
    out = {}
    for line in open(URMA):
        r = json.loads(line)
        nb = r["nb"]
        w = np.array([1 / max(x[2], 0.1) ** 2 for x in nb])
        out[r["valid"][:13]] = ((sum(wi * x[3] for wi, x in zip(w, nb)) / w.sum()) - 273.15) * 9 / 5 + 32
    return out


def load():
    U = urma_idw()
    rx = re.compile(r'"field": ?"t"')
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
            k = u.strftime("%Y-%m-%dT%H")
            if k not in U:
                continue
            sfc = r.get("state_fc")
            if isinstance(sfc, str):
                try:
                    sfc = ast.literal_eval(sfc)
                except Exception:  # noqa: BLE001
                    sfc = {}
            rows.append((vt[:10], int(r["lead_h"]), vt, float(sv), float(r["forecast_l1"]),
                         float(r["forecast_raw_nbm"]), U[k], (sfc or {}).get("regime_flow") or "?", r.get("forecast_nws")))
    days = sorted({r[0] for r in rows})
    eh = tb.ecmwf_history(days[0], days[-1])
    out = []
    for day, lead, vt, sv, hr, nb, tr, flow, nws in rows:
        fe = (eh.get(tb._ecmwf_key(vt)) or {}).get("t")
        fe = fe[tb._ecmwf_day(lead)] if fe else None
        band = next((b for b, lo, hi in tb.BANDS if lo <= lead < hi), None)
        if fe is None or band is None:
            continue
        out.append((day, band, sv - tr, hr - tr, nb - tr, float(fe) - tr, int(vt[11:13]), flow, None if nws is None else float(nws) - tr))  # errors vs URMA, valid hour (ET), forecast flow regime
    return out


def best_w(e3):
    return GRID3[int(np.abs(e3 @ GRID3.T).sum(0).argmin())]


def run():
    data = load()
    print(f"rows {len(data):,}")
    byband = collections.defaultdict(list)
    for r in data:
        byband[r[1]].append(r)
    for b, _, _ in tb.BANDS:
        rows = byband[b]
        days = sorted({r[0] for r in rows})
        per = {"A weights": {}, "B bias+weights": {}, "C served-bias": {}}
        for D in days:
            d0 = datetime.strptime(D, "%Y-%m-%d")
            fit_days = {d for d in days if d0 - timedelta(days=WIN) <= datetime.strptime(d, "%Y-%m-%d") < d0}
            if len(fit_days) < WIN - 2:
                continue
            fit = np.array([r[2:6] for r in rows if r[0] in fit_days])
            test = np.array([r[2:6] for r in rows if r[0] == D])
            if len(fit) < MIN_N or len(test) == 0:
                continue
            base = float(np.abs(test[:, 0]).sum())
            wA = best_w(fit[:, 1:4])
            per["A weights"][D] = (base, float(np.abs(test[:, 1:4] @ wA).sum()), len(test))
            bias = fit[:, 1:4].mean(0)
            wB = best_w(fit[:, 1:4] - bias)
            per["B bias+weights"][D] = (base, float(np.abs((test[:, 1:4] - bias) @ wB).sum()), len(test))
            per["C served-bias"][D] = (base, float(np.abs(test[:, 0] - fit[:, 0].mean()).sum()), len(test))
        print(f"\n== t {b}h vs URMA truth, baseline = served ==")
        for name, pd in per.items():
            g = day_block_gain(pd, holdout_only=False)
            gh = day_block_gain({d: v for d, v in pd.items() if d >= HOLDOUT_START})
            print(f"  {name:<15} ALL    {verdict(g)}")
            print(f"  {'':<15} HOLDOUT {verdict(gh)}")
            if os.environ.get("URMA_WF_RECORD") == "1":   # digest re-runs must not inflate the ledger's look count
                record("urma_blend_wf", f"t {b}h {name} vs served (URMA truth)", gh,
                       note="walk-forward 14d, truth=URMA idw, rows with hrrr+nbm+ecmwf")


if __name__ == "__main__":
    run()

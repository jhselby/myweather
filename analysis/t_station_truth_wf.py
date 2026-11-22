"""~11-17 STATION_TRUTH flip test for t (run early 11-14).

Walk-forward per obs day D, per lead band, t 3-way weights (HRRR side, NBM side, ECMWF archive on the
live 1 h lag), simplex grid as terminal_blend_field_fit:
  LIVE  fit on the prior 14 days on the shrunk `observed` (what the refitter does today)
  CAND  fit on the prior days' rows that carry observed_stations, on station truth (STATION_TRUTH=True),
        needs >= MIN_ST_DAYS station days
Both scored on D on the SAME rows (rows with observed_stations), on station truth, and on URMA where
the hour has it. Gain = CAND vs LIVE through ship_rule (holdout = obs days >= 11-03). Ledger only with
T_ST_RECORD=1.

    PYTHONPATH=. .venv/bin/python -m analysis.t_station_truth_wf
    FIELD=h ... same for humidity (11-22: h is the one field the Mesonet qualified for). h is scored on
    leads 6-47h only (L2 reads the same stations below that), on station truth only (no URMA RH), and
    also against HRRR alone, the source that beat the blend on 11-18..21.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis import terminal_blend_field_fit as tb  # noqa: E402
from analysis._cache import PAIR_LOG_URL, cached_path  # noqa: E402
from analysis.ship_rule import day_block_gain, record, verdict  # noqa: E402
from analysis.urma_blend_wf import urma_idw  # noqa: E402

ET = ZoneInfo("America/New_York")
WIN, MIN_ST_DAYS, FIRST = int(os.environ.get("WIN", 14)), 5, "2026-10-15"
FIELD = os.environ.get("FIELD", "t")
MIN_SCORE_LEAD = 6 if FIELD == "h" else 0
G = np.asarray(tb.GRID3)


def load():
    U = urma_idw()
    eh_hist = tb.ecmwf_history(FIRST, datetime.now().strftime("%Y-%m-%d"))
    rows = []
    with open(cached_path(PAIR_LOG_URL, max_age_hours=6)) as fh:
        for line in fh:
            if f'"field":"{FIELD}"' not in line and f'"field": "{FIELD}"' not in line:
                continue
            r = json.loads(line)
            day = (r.get("obs_time") or "")[:10]
            vt = r.get("valid_time") or ""
            lead = r.get("lead_h")
            if day < FIRST or len(vt) < 13 or lead is None or r.get("observed") is None:
                continue
            eh = tb._first(r, tb.HRRR_KEYS.get(FIELD, tb.HRRR_DEFAULT))
            en = tb._first(r, tb.NBM_KEYS)
            fe = (eh_hist.get(tb._ecmwf_key(vt)) or {}).get(FIELD)
            fe = fe[tb._ecmwf_day(lead)] if fe else None
            band = next((b for b, lo, hi in tb.BANDS if lo <= lead < hi), None)
            if eh is None or en is None or fe is None or band is None:
                continue
            obs = float(r["observed"])
            st = r.get("observed_stations")
            u = datetime.strptime(vt[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=ET).astimezone(timezone.utc)
            # forecasts are recoverable: f = err + observed
            fc = (float(eh) + obs, float(en) + obs, float(fe))
            rows.append((day, band, fc, obs, None if st is None else float(st),
                         U.get(u.strftime("%Y-%m-%dT%H")) if FIELD == "t" else None, lead))
    return rows


def best(F, truth):
    e = F - truth[:, None]
    return G[int(np.abs(e @ G.T).sum(0).argmin())]


def main():
    rows = load()
    print(f"rows {len(rows):,}")
    per = {k: defaultdict(lambda: [0.0, 0.0, 0]) for k in ("stations", "urma", "hrrr_vs_cand")}
    byb = defaultdict(list)
    for r in rows:
        byb[r[1]].append(r)
    for b, rs in byb.items():
        days = sorted({r[0] for r in rs})
        st_days = sorted({r[0] for r in rs if r[4] is not None})
        for D in st_days:
            d0 = datetime.strptime(D, "%Y-%m-%d")
            lo = (d0 - timedelta(days=WIN)).strftime("%Y-%m-%d")
            fit_live = [r for r in rs if lo <= r[0] < D]
            fit_st = [r for r in fit_live if r[4] is not None]
            if len({r[0] for r in fit_st}) < MIN_ST_DAYS or len(fit_live) < 300:
                continue
            wL = best(np.array([r[2] for r in fit_live]), np.array([r[3] for r in fit_live]))
            wC = best(np.array([r[2] for r in fit_st]), np.array([r[4] for r in fit_st]))
            test = [r for r in rs if r[0] == D and r[4] is not None and r[6] >= MIN_SCORE_LEAD]
            for r in test:
                F = np.array(r[2])
                fl, fcand = float(F @ wL), float(F @ wC)
                for k, tr in (("stations", r[4]), ("urma", r[5])):
                    if tr is None:
                        continue
                    p = per[k][D]
                    p[0] += abs(fl - tr); p[1] += abs(fcand - tr); p[2] += 1
                p = per["hrrr_vs_cand"][D]   # baseline HRRR alone vs the station-fit blend, station truth
                p[0] += abs(float(F[0]) - r[4]); p[1] += abs(fcand - r[4]); p[2] += 1
        print(f"  band {b}: last weights LIVE {wL.tolist()} CAND {wC.tolist()}")
    for k in per:
        pd = {d: tuple(v) for d, v in per[k].items()}
        if not pd:
            continue
        print(f"{FIELD} ({'HRRR alone' if k == 'hrrr_vs_cand' else 'LIVE'} as base) CAND (station-fit) vs LIVE (shrunk-fit), scored on {k:<8} ALL     {verdict(day_block_gain(pd, holdout_only=False))}")
        gh = day_block_gain(pd)
        print(f"{'':<58} HOLDOUT {verdict(gh)}")
        if os.environ.get("T_ST_RECORD") == "1":
            record("t_station_truth_wf", f"{FIELD} station-fit vs {'HRRR alone' if k == 'hrrr_vs_cand' else 'shrunk-fit w3'}, scored on {'stations' if k == 'hrrr_vs_cand' else k}", gh,
                   note=f"per band, scored leads >= {MIN_SCORE_LEAD}h")


if __name__ == "__main__":
    main()

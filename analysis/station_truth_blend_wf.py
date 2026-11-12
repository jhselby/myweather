"""Walk-forward: fit the t/h 3-way blend on STATION truth vs on shrunk `observed` truth.

Both candidates are scored on the same rows of the next valid day against station truth
(`observed_stations`, model-free), the truth Joe set on 11-08.
  Baseline  = per-lead-band 3-way weights (HRRR terminal, NBM terminal, ECMWF) fit on the
              prior 14 days against the shrunk `observed` (what the refitter does today).
  Candidate = same fit on the prior days that have `observed_stations`, against stations.
Test days are valid days >= HOLDOUT_START that have >= MIN_TRAIN_DAYS station days before
them. Gains go through analysis/ship_rule.py and the ledger.

    .venv/bin/python -m analysis.station_truth_blend_wf
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
from analysis.ship_rule import day_block_gain, verdict, record, HOLDOUT_START  # noqa: E402

FIELDS = ("t", "h")
WIN = 14
MIN_TRAIN_DAYS = 4
MIN_BAND_N = 300
GRID3 = np.asarray(tb.GRID3)


def load():
    rows, days = [], set()
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
            obs = float(r["observed"])
            obs_s = r.get("observed_stations")
            rows.append((f, vt[:10], int(r["lead_h"]), vt, eh, en, obs,
                         None if obs_s is None else float(obs_s)))
            days.add(vt[:10])
    ehist = tb.ecmwf_history(min(days), max(days))
    out = []
    for f, day, lead, vt, eh, en, obs, obs_s in rows:
        fe = (ehist.get(tb._ecmwf_key(vt)) or {}).get(f)
        fe = fe[tb._ecmwf_day(lead)] if fe else None
        band = next((b for b, a, z in tb.BANDS if a <= lead < z), None)
        if fe is None or band is None:
            continue
        # errors on shrunk truth: [hrrr, nbm, ecmwf]; on station truth shift by obs - obs_s
        shr = (eh, en, float(fe) - obs)
        sta = None if obs_s is None else tuple(e + (obs - obs_s) for e in shr)
        out.append((f, day, band, shr, sta))
    return out


def best_w(a):
    return GRID3[int(np.abs(a @ GRID3.T).sum(0).argmin())]


def run():
    data = load()
    byf = defaultdict(list)
    for r in data:
        byf[r[0]].append(r)
    for f in FIELDS:
        rows = byf[f]
        sdays = sorted({r[1] for r in rows if r[4] is not None})
        print(f"\n== {f}: {len(sdays)} station days {sdays[0]}..{sdays[-1]} ==")
        per = {"station-fit vs shrunk-fit (scored on stations)": {},
               "station-fit vs shrunk-fit (scored on shrunk)": {}}
        keys = list(per)
        for D in sdays:
            if D < HOLDOUT_START:
                continue
            d0 = datetime.strptime(D, "%Y-%m-%d")
            fit_ok = lambda d: d0 - timedelta(days=WIN) <= datetime.strptime(d, "%Y-%m-%d") < d0  # noqa: E731
            fit = [r for r in rows if fit_ok(r[1])]
            fit_s = [r for r in fit if r[4] is not None]
            if len({r[1] for r in fit_s}) < MIN_TRAIN_DAYS:
                continue
            test = [r for r in rows if r[1] == D and r[4] is not None]
            tot = {k: [0.0, 0.0, 0] for k in keys}
            for b, _, _ in tb.BANDS:
                fb = [r for r in fit if r[2] == b]
                fbs = [r for r in fit_s if r[2] == b]
                tb_ = [r for r in test if r[2] == b]
                if len(fb) < MIN_BAND_N or len(fbs) < MIN_BAND_N or not tb_:
                    continue
                w_base = best_w(np.asarray([r[3] for r in fb]))
                w_cand = best_w(np.asarray([r[4] for r in fbs]))
                for k, col in ((keys[0], 4), (keys[1], 3)):
                    x = np.asarray([r[col] for r in tb_])
                    tot[k][0] += float(np.abs(x @ w_base).sum())
                    tot[k][1] += float(np.abs(x @ w_cand).sum())
                    tot[k][2] += len(tb_)
            for k in keys:
                if tot[k][2]:
                    per[k][D] = tuple(tot[k])
        for k in keys:
            g = day_block_gain(per[k])
            print(f"  {k:<48} {verdict(g)}")
        record("station_truth_blend_wf", f"{f} station-fit vs shrunk-fit, scored on stations",
               day_block_gain(per[keys[0]]), note="holdout days with >=4 station train days")


if __name__ == "__main__":
    run()

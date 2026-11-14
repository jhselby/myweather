"""Exploratory: does another model family add information as a 4th input to the URMA-truth t blend?

Open-Meteo previous-runs archive (same source/convention as the ECMWF input: previous_day1/2/3 by lead
band via tb._ecmwf_day; NO live-lag shift, so a model that is in fact live-lagged is not credited fairly).
Candidates: GFS, ICON, GEM, each alone added to [HRRR, NBM, ECMWF]; B3 vs B4 on identical rows, walk-forward
14 valid days, per-source bias then weights (simplex step 0.1), baseline = served. Not ledgered.
Model correlation of daily bias with HRRR is printed: low correlation = independent information.

    PYTHONPATH=. .venv/bin/python -m analysis.urma_blend_models
"""
import collections
import itertools
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import numpy as np

from analysis import terminal_blend_field_fit as tb
from analysis.ship_rule import HOLDOUT_START, day_block_gain
from analysis.urma_blend_wf import MIN_N, WIN, best_w, load

MODELS = ("gfs_seamless", "icon_seamless", "gem_seamless")
G4 = np.array([w for w in itertools.product(np.arange(0, 1.01, 0.1), repeat=4) if abs(sum(w) - 1) < 1e-9])


def history(model, start, end):
    from weather_collector.config import LAT, LON
    hourly = ",".join(f"temperature_2m_previous_day{n}" for n in (1, 2, 3))
    q = urllib.parse.urlencode({"latitude": LAT, "longitude": LON, "hourly": hourly, "models": model,
                                "temperature_unit": "fahrenheit", "timezone": "America/New_York",
                                "start_date": start, "end_date": end})
    try:
        with urllib.request.urlopen(f"{tb.PREV_RUNS_URL}?{q}", timeout=90) as resp:
            h = json.load(resp)["hourly"]
    except Exception as e:  # noqa: BLE001
        print(f"  {model}: fetch failed ({e})", file=sys.stderr)
        return {}
    return {t[:13]: [None] + [h[f"temperature_2m_previous_day{n}"][i] for n in (1, 2, 3)] for i, t in enumerate(h["time"])}


def main():
    data = load()
    days_all = sorted({r[0] for r in data})
    hist = {m: history(m, days_all[0], days_all[-1]) for m in MODELS}
    # r: (day, band, served_err, hrrr_err, nbm_err, ecmwf_err, hour, flow, nws_err); need valid_time + lead per row
    # load() drops them, so rebuild the (day, hour, lead) key from the band midpoint is not exact:
    # re-read lead and valid hour via a parallel pass.
    import re
    from datetime import timezone
    from zoneinfo import ZoneInfo
    from analysis.urma_blend_wf import LOG, urma_idw
    ET = ZoneInfo("America/New_York"); U = urma_idw(); rx = re.compile(r'"field": ?"t"')
    rows = []
    with open(LOG) as fh:
        for line in fh:
            if not rx.search(line):
                continue
            r = json.loads(line); vt = r.get("valid_time") or ""
            if len(vt) < 13 or r.get("lead_h") is None or not 6 <= r["lead_h"] < 48:
                continue
            u = datetime.strptime(vt[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=ET).astimezone(timezone.utc).strftime("%Y-%m-%dT%H")
            if u not in U or r.get("forecast_l1") is None or r.get("forecast_raw_nbm") is None:
                continue
            ap = r.get("applied_layer"); sv = r.get("forecast_" + ap) if ap else None
            if sv is None:
                sv = r.get("forecast")
            if sv is None:
                continue
            rows.append((vt, int(r["lead_h"]), float(sv), float(r["forecast_l1"]), float(r["forecast_raw_nbm"]), U[u]))
    eh = tb.ecmwf_history(days_all[0], days_all[-1])
    out = collections.defaultdict(list)
    for vt, lead, sv, hr, nb, tr in rows:
        fe = (eh.get(tb._ecmwf_key(vt)) or {}).get("t")
        fe = fe[tb._ecmwf_day(lead)] if fe else None
        band = next((b for b, lo, hi in tb.BANDS if lo <= lead < hi), None)
        if fe is None or band is None:
            continue
        ex = {}
        for m in MODELS:
            v = (hist[m].get(vt[:13]) or [None] * 4)[tb._ecmwf_day(lead)]
            ex[m] = None if v is None else float(v) - tr
        out[band].append((vt[:10], sv - tr, hr - tr, nb - tr, float(fe) - tr, ex))
    for m in MODELS:
        pairs = [(r[2], r[5][m]) for b in out for r in out[b] if r[5][m] is not None]
        if pairs:
            a = np.array(pairs)
            print(f"{m}: rows {len(a):,}, MAE {np.abs(a[:,1]).mean():.2f} vs HRRR {np.abs(a[:,0]).mean():.2f}, error corr with HRRR {np.corrcoef(a[:,0], a[:,1])[0,1]:.2f}")
    for m in MODELS:
        print(f"\n######## + {m}")
        for b, _, _ in tb.BANDS:
            rs = [r for r in out[b] if r[5][m] is not None]
            days = sorted({r[0] for r in rs})
            per = {"B3": {}, "B4": {}}
            for D in days:
                d0 = datetime.strptime(D, "%Y-%m-%d")
                fd = {d for d in days if d0 - timedelta(days=WIN) <= datetime.strptime(d, "%Y-%m-%d") < d0}
                if len(fd) < WIN - 2:
                    continue
                fit = np.array([r[2:5] + (r[5][m],) for r in rs if r[0] in fd], float)
                te = np.array([r[2:5] + (r[5][m],) for r in rs if r[0] == D], float)
                sv = np.array([r[1] for r in rs if r[0] == D])
                if len(fit) < MIN_N or not len(te):
                    continue
                base = float(np.abs(sv).sum()); n = len(te)
                # B3 here = HRRR, NBM, ECMWF (cols 0-2); the 4th column is the candidate model
                b3 = fit[:, :3].mean(0); w3 = best_w(fit[:, :3] - b3)
                per["B3"][D] = (base, float(np.abs((te[:, :3] - b3) @ w3).sum()), n)
                b4 = fit.mean(0); w4 = G4[int(np.abs((fit - b4) @ G4.T).sum(0).argmin())]
                per["B4"][D] = (base, float(np.abs((te - b4) @ w4).sum()), n)
            if not per["B3"]:
                print(f"  {b}h: no scored days"); continue
            for nm, pd in per.items():
                g = day_block_gain(pd, holdout_only=False)
                gh = day_block_gain({d: v for d, v in pd.items() if d >= HOLDOUT_START})
                print(f"  {b:>5}h {nm:<3} all {g['gain']:+5.1f}% [{g['lo']:+5.1f},{g['hi']:+5.1f}] {g['wins']}/{g['days']}d | holdout {gh['gain']:+5.1f}% [{gh['lo']:+5.1f},{gh['hi']:+5.1f}]")


if __name__ == "__main__":
    main()

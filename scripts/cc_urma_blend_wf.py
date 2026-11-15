"""cc on URMA TCDC: can any HRRR / NBM / ECMWF blend (with or without per-source bias vs URMA)
beat raw NBM, the normal source? Walk-forward: fit on the prior 14 days, score the next day.
Per lead band; ship_rule on holdout days (>= 2026-11-03). Exploratory; nothing is recorded
unless CC_URMA_RECORD=1.

    PYTHONPATH=. .venv/bin/python scripts/cc_urma_blend_wf.py
"""
import collections
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

from analysis.ship_rule import day_block_gain, record, verdict
from analysis.terminal_blend_field_fit import GRID3, PREV_RUNS_URL, _ecmwf_day, _ecmwf_key
from analysis.urma_blend_wf import LOG, URMA
from weather_collector.config import LAT, LON

ET = ZoneInfo("America/New_York")
BANDS = (("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48))
WIN = 14
G3 = np.asarray(GRID3)


def urma_cc():
    out = {}
    for line in open(URMA):
        r = json.loads(line)
        if r["var"] == "TCDC":
            w = np.array([1 / max(x[2], 0.1) ** 2 for x in r["nb"]])
            out[r["valid"][:13]] = float(sum(wi * x[3] for wi, x in zip(w, r["nb"])) / w.sum())
    return out


def ecmwf_cc(start, end):
    q = urllib.parse.urlencode({
        "latitude": LAT, "longitude": LON,
        "hourly": ",".join(f"cloud_cover_previous_day{n}" for n in (1, 2, 3)),
        "models": "ecmwf_ifs025", "timezone": "America/New_York", "start_date": start, "end_date": end})
    with urllib.request.urlopen(f"{PREV_RUNS_URL}?{q}", timeout=90) as resp:
        h = json.load(resp)["hourly"]
    return {t[:13]: [None] + [h[f"cloud_cover_previous_day{n}"][i] for n in (1, 2, 3)]
            for i, t in enumerate(h["time"])}


def load():
    U = urma_cc()
    rows = collections.defaultdict(list)  # band -> (day, hrrr, nbm, ecmwf, urma)
    keep = []
    with open(LOG) as fh:
        for line in fh:
            if '"field":"cc"' not in line and '"field": "cc"' not in line:
                continue
            r = json.loads(line)
            vt, lead = r.get("valid_time") or "", r.get("lead_h")
            hr, nb = r.get("forecast_l1"), r.get("forecast_raw_nbm")
            if lead is None or hr is None or nb is None or not 0 <= lead < 48:
                continue
            u = datetime.strptime(vt[:13], "%Y-%m-%dT%H").replace(tzinfo=ET).astimezone(timezone.utc)
            tc = U.get(u.strftime("%Y-%m-%dT%H"))
            if tc is None:
                continue
            keep.append((vt, int(lead), float(hr), float(nb), tc))
    days = sorted({k[0][:10] for k in keep})
    E = ecmwf_cc(days[0], days[-1])
    miss = 0
    for vt, lead, hr, nb, tc in keep:
        e = (E.get(_ecmwf_key(vt)) or [None] * 4)[_ecmwf_day(lead)]
        if e is None:
            miss += 1
            continue
        band = next(n for n, lo, hi in BANDS if lo <= lead < hi)
        rows[band].append((vt[:10], hr, nb, float(e), tc))
    print(f"rows {len(keep):,}, no ECMWF {miss:,}, days {days[0]}..{days[-1]}")
    return rows


def run():
    rows = load()
    for band, rs in rows.items():
        by_day = collections.defaultdict(list)
        for d, *v in rs:
            by_day[d].append(v)
        days = sorted(by_day)
        res = {k: {} for k in ("w3", "w3_bias", "nbm_bias", "ecmwf", "hrrr")}
        wsum = []
        for i, d in enumerate(days):
            prior = days[max(0, i - WIN):i]
            if len(prior) < 10:
                continue
            tr = np.asarray([v for p in prior for v in by_day[p]])
            te = np.asarray(by_day[d])
            e_tr = tr[:, :3] - tr[:, 3:4]
            e_te = te[:, :3] - te[:, 3:4]
            base = np.abs(e_te[:, 1]).sum()
            w = G3[int(np.abs(e_tr @ G3.T).sum(0).argmin())]
            b = e_tr.mean(0)
            wb = G3[int(np.abs((e_tr - b) @ G3.T).sum(0).argmin())]
            wsum.append(wb)
            n = len(te)
            res["w3"][d] = (base, np.abs(e_te @ w).sum(), n)
            res["w3_bias"][d] = (base, np.abs((e_te - b) @ wb).sum(), n)
            res["nbm_bias"][d] = (base, np.abs(e_te[:, 1] - b[1]).sum(), n)
            res["ecmwf"][d] = (base, np.abs(e_te[:, 2]).sum(), n)
            res["hrrr"][d] = (base, np.abs(e_te[:, 0]).sum(), n)
        allr = np.asarray([v for vs in by_day.values() for v in vs])
        mae = np.abs(allr[:, :3] - allr[:, 3:4]).mean(0)
        print(f"\n== cc {band}  n={len(allr):,}  MAE vs URMA  HRRR {mae[0]:.2f}  NBM {mae[1]:.2f}  ECMWF {mae[2]:.2f}"
              f"  | mean bias+w [h,n,e] {np.round(np.mean(wsum, 0), 2).tolist() if wsum else None}")
        for k, pd in res.items():
            ga, gh = day_block_gain(pd, holdout_only=False), day_block_gain(pd)
            print(f"  {k:9} vs raw NBM  all: {verdict(ga)}")
            print(f"  {'':9}            {verdict(gh)}")
            if os.environ.get("CC_URMA_RECORD") == "1" and k in ("w3", "w3_bias"):
                record("cc_urma_blend_wf", f"cc/{band}/{k}", gh, note="truth URMA TCDC; base raw NBM")


if __name__ == "__main__":
    run()

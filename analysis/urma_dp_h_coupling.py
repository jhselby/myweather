"""If dp_urmab were served, what happens to humidity? (plan step 5, dew point)

Served humidity is derived: corrected_humidity = RH(t_served, dp_served) via Magnus (decay_apply). So serving a
URMA-trained dew point (together with the URMA-trained temperature t_urmab) changes humidity. Walk-forward, per
lead band, on identical rows:
  t_hat  = sum_i w_i (src_i - bias_i)   t blend fit on the prior 14 valid days vs URMA (urma_blend_wf, variant B)
  dp_hat = sum_i w_i src_i              dp blend fit on the prior 14 valid days vs URMA dew point (urma_blend_wf_dp, A)
  h_hat  = RH(t_hat, dp_hat)            Magnus
Scored on humidity against the Mesonet (observed_stations, the humidity truth) at 6-47 h, vs the humidity actually
served (forecast_{applied_layer}) and vs raw NBM, through analysis/ship_rule.py (holdout days >= HOLDOUT_START).
Also scores dp_hat itself vs URMA dew point and vs served dp (same rows). Exploratory: ledger only with URMA_WF_RECORD=1.

    PYTHONPATH=. .venv/bin/python -m analysis.urma_dp_h_coupling
"""
import collections
import json
import math
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
tb.E_VARS["dp"] = "dew_point_2m"
BANDS = tb.BANDS


def _idw(nb):
    w = np.array([1 / max(x[2], 0.1) ** 2 for x in nb])
    return float(sum(wi * x[3] for wi, x in zip(w, nb)) / w.sum())


def urma_series():
    t, d = {}, {}
    for line in open(URMA):
        r = json.loads(line)
        k = r["valid"][:13]
        if r.get("var") == "TMP":
            t[k] = (_idw(r["nb"]) - 273.15) * 9 / 5 + 32
        elif r.get("var") == "DPT":
            d[k] = (_idw(r["nb"]) - 273.15) * 9 / 5 + 32
    return t, d


def rh(tf, dpf):
    tc, dc = (tf - 32) * 5 / 9, (dpf - 32) * 5 / 9
    a, b = 17.625, 243.04
    return float(np.clip(100 * math.exp(a * dc / (b + dc)) / math.exp(a * tc / (b + tc)), 1, 100))


def load():
    Ut, Ud = urma_series()
    rx = re.compile(r'"field": ?"(t|dp|h)"')
    rows = collections.defaultdict(dict)   # (run, valid, lead) -> {field: row}
    with open(LOG) as fh:
        for line in fh:
            m = rx.search(line)
            if not m:
                continue
            r = json.loads(line)
            vt = r.get("valid_time") or ""
            if len(vt) < 13 or vt[:10] < "2026-08-25":
                continue
            lead = r.get("lead_h")
            if lead is None or lead < 6:
                continue
            f = r["field"]
            ap = r.get("applied_layer")
            sv = r.get("forecast_" + ap) if ap else None
            if sv is None:
                sv = r.get("forecast")
            keep = {"sv": sv, "l1": r.get("forecast_l1"), "nb": r.get("forecast_raw_nbm"),
                    "os": r.get("observed_stations"), "nws": r.get("forecast_nws")}
            rows[(r.get("run_time"), vt, int(lead))][f] = keep
    eh_days = sorted({k[1][:10] for k in rows})
    eh = tb.ecmwf_history(eh_days[0], eh_days[-1])
    out = []
    for (run, vt, lead), fl in rows.items():
        if not all(f in fl for f in ("t", "dp", "h")):
            continue
        t, d, h = fl["t"], fl["dp"], fl["h"]
        if None in (t["l1"], t["nb"], d["l1"], d["nb"], h["sv"], d["sv"]):   # h["os"] may be None: such rows still train the blends
            continue
        u = datetime.strptime(vt[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=ET).astimezone(timezone.utc)
        k = u.strftime("%Y-%m-%dT%H")
        if k not in Ut or k not in Ud:
            continue
        e = eh.get(tb._ecmwf_key(vt)) or {}
        et = (e.get("t") or [None] * 4)[tb._ecmwf_day(lead)] if e.get("t") else None
        ed = (e.get("dp") or [None] * 4)[tb._ecmwf_day(lead)] if e.get("dp") else None
        band = next((b for b, lo, hi in BANDS if lo <= lead < hi), None)
        if et is None or ed is None or band is None:
            continue
        out.append(dict(day=vt[:10], band=band,
                        t=np.array([t["l1"], t["nb"], et], float), dp=np.array([d["l1"], d["nb"], ed], float),
                        ut=Ut[k], ud=Ud[k], h_sv=float(h["sv"]), h_os=(None if h["os"] is None else float(h["os"])), h_nb=h["nb"],
                        dp_sv=float(d["sv"]), dp_nws=d["nws"]))
    return out


def run():
    data = load()
    print(f"rows {len(data):,}; days {min(r['day'] for r in data)}..{max(r['day'] for r in data)}")
    byband = collections.defaultdict(list)
    for r in data:
        byband[r["band"]].append(r)
    for b, _, _ in BANDS:
        rows = byband[b]
        days = sorted({r["day"] for r in rows})
        pd_h, pd_nb, pd_dp = {}, {}, {}
        for D in days:
            d0 = datetime.strptime(D, "%Y-%m-%d")
            fd = {d for d in days if d0 - timedelta(days=WIN) <= datetime.strptime(d, "%Y-%m-%d") < d0}
            if len(fd) < WIN - 2:
                continue
            fit = [r for r in rows if r["day"] in fd]
            test = [r for r in rows if r["day"] == D]
            if len(fit) < MIN_N or not test:
                continue
            et = np.array([r["t"] - r["ut"] for r in fit]); bias = et.mean(0); wt = best_w(et - bias)
            ed = np.array([r["dp"] - r["ud"] for r in fit]); wd = best_w(ed)
            e_h, e_sv, e_nb, e_dpn, e_dps = 0.0, 0.0, 0.0, 0.0, 0.0
            n = 0
            for r in test:
                if r["h_os"] is None:
                    continue
                t_hat = float(((r["t"] - bias) * np.asarray(wt)).sum())
                dp_hat = float((r["dp"] * np.asarray(wd)).sum())
                h_hat = rh(t_hat, min(dp_hat, t_hat))
                e_h += abs(h_hat - r["h_os"]); e_sv += abs(r["h_sv"] - r["h_os"])
                if r["h_nb"] is not None:
                    e_nb += abs(float(r["h_nb"]) - r["h_os"])
                e_dpn += abs(dp_hat - r["ud"]); e_dps += abs(r["dp_sv"] - r["ud"]); n += 1
            pd_h[D] = (e_sv, e_h, n); pd_nb[D] = (e_nb, e_h, n); pd_dp[D] = (e_dps, e_dpn, n)
        print(f"\n== {b}h")
        for lab, pd in (("humidity from (t_hat, dp_hat) vs SERVED humidity, Mesonet truth", pd_h),
                        ("humidity from (t_hat, dp_hat) vs RAW NBM humidity, Mesonet truth", pd_nb),
                        ("dp_hat vs SERVED dp, URMA truth", pd_dp)):
            g = day_block_gain(pd, holdout_only=False)
            gh = day_block_gain({d: v for d, v in pd.items() if d >= HOLDOUT_START})
            print(f"  {lab}\n     ALL     {verdict(g)}\n     HOLDOUT {verdict(gh)}")
            if os.environ.get("URMA_WF_RECORD") == "1" and "SERVED" in lab:
                record("urma_dp_h_coupling", f"{b}h {lab}", gh, note="walk-forward 14d, t_hat dp_hat -> Magnus h")


if __name__ == "__main__":
    run()

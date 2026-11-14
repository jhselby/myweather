"""Score served h / dp / ws against URMA (independent truth) next to the raw sources a normal user sees.

Truth: URMA 2.5 km analysis, inverse-distance mean of the 4 cells around the Cove
(analysis/output/urma_truth/urma_cell.jsonl, vars TMP/DPT/WIND from urma_truth_backfill).
h = RH from URMA T and Td (Magnus); ws = URMA 10 m WIND, m/s -> mph; cc = URMA TCDC (total cloud
cover %, GOES satellite + surface obs, sees high cloud the airport ceilometers cannot; added 11-14).
Columns per field x lead band, identical rows: served (forecast_{applied_layer}), raw HRRR
(forecast_l1), raw NBM (forecast_raw_nbm = the normal source for these fields), and the
scored `observed` (the pair log's own truth) read as if it were a forecast, to show how far the
two truths sit apart. Gain = served vs raw NBM through ship_rule (day-block bootstrap), all days
and holdout days. Exploratory: nothing is written to the ledger unless URMA_FIELD_RECORD=1.

    PYTHONPATH=. .venv/bin/python -m analysis.urma_field_score
"""
import collections
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.ship_rule import HOLDOUT_START, day_block_gain, record, verdict  # noqa: E402
from analysis.urma_blend_wf import LOG, URMA  # noqa: E402

ET = ZoneInfo("America/New_York")
BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]
FIELDS = ("h", "dp", "ws", "cc")


def _idw(nb):
    w = np.array([1 / max(x[2], 0.1) ** 2 for x in nb])
    return float(sum(wi * x[3] for wi, x in zip(w, nb)) / w.sum())


def _rh(tc, tdc):
    a, b = 17.625, 243.04
    return 100 * math.exp(a * tdc / (b + tdc)) / math.exp(a * tc / (b + tc))


def urma_truth():
    raw = collections.defaultdict(dict)
    for line in open(URMA):
        r = json.loads(line)
        raw[r["valid"][:13]][r["var"]] = _idw(r["nb"])
    out = {}
    for k, v in raw.items():
        d = {}
        if "DPT" in v:
            d["dp"] = (v["DPT"] - 273.15) * 9 / 5 + 32
            if "TMP" in v:
                d["h"] = min(100.0, _rh(v["TMP"] - 273.15, v["DPT"] - 273.15))
        if "WIND" in v:
            d["ws"] = v["WIND"] * 2.23694
        if "TCDC" in v:
            d["cc"] = v["TCDC"]
        out[k] = d
    return out


def load():
    U = urma_truth()
    rx = re.compile(r'"field": ?"(h|dp|ws|cc)"')
    rows = collections.defaultdict(list)
    with open(LOG) as fh:
        for line in fh:
            m = rx.search(line)
            if not m:
                continue
            r = json.loads(line)
            f = r["field"]
            vt = r.get("valid_time") or ""
            ap = r.get("applied_layer")
            sv = r.get("forecast_" + ap) if ap else None
            if sv is None:
                sv = r.get("forecast")
            hr, nb, ob = r.get("forecast_l1"), r.get("forecast_raw_nbm"), r.get("observed")
            if None in (sv, hr, nb, ob) or len(vt) < 13:
                continue
            u = datetime.strptime(vt[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=ET).astimezone(timezone.utc)
            tr = U.get(u.strftime("%Y-%m-%dT%H"), {}).get(f)
            band = next((b for b, lo, hi in BANDS if lo <= int(r["lead_h"]) < hi), None)
            if tr is None or band is None:
                continue
            rows[(f, band)].append((vt[:10], float(sv) - tr, float(hr) - tr, float(nb) - tr, float(ob) - tr))
    return rows


def run():
    rows = load()
    rec = os.environ.get("URMA_FIELD_RECORD") == "1"
    for f in FIELDS:
        print(f"\n== {f} vs URMA truth (MAE / mean bias), served vs raw NBM gain ==")
        print(f"  {'band':<6} {'n':>6} {'days':>4}  {'served':>12} {'HRRR raw':>12} {'NBM raw':>12} {'observed':>12}")
        for b, _, _ in BANDS:
            rs = rows.get((f, b), [])
            if not rs:
                continue
            a = np.array([r[1:] for r in rs])
            mae, bias = np.abs(a).mean(0), a.mean(0)
            cols = "".join(f" {m:>6.2f}/{bi:+5.2f}" for m, bi in zip(mae, bias))
            days = sorted({r[0] for r in rs})
            print(f"  {b:<6} {len(rs):>6} {len(days):>4} {cols}")
            per = collections.defaultdict(lambda: [0.0, 0.0, 0])
            for d, es, _, en, _ in rs:
                p = per[d]
                p[0] += abs(en)
                p[1] += abs(es)
                p[2] += 1
            per = {d: tuple(v) for d, v in per.items()}
            g = day_block_gain(per, holdout_only=False)
            gh = day_block_gain({d: v for d, v in per.items() if d >= HOLDOUT_START})
            print(f"  {'':<6} served vs NBM  ALL     {verdict(g)}")
            print(f"  {'':<6}                HOLDOUT {verdict(gh)}")
            if rec:
                record("urma_field_score", f"{f} {b}h served vs raw NBM (URMA truth)", gh,
                       note="truth=URMA idw; h from URMA T/Td; ws URMA 10m WIND")


if __name__ == "__main__":
    run()

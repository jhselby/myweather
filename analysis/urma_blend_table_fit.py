"""Daily fit of the URMA-truth bias-then-blend table for t (shadow; see
weather_collector/processors/urma_blend_shadow.py).

Per lead band (6-11, 12-23, 24-47h): over the last 14 valid days that have URMA truth,
  bias_i = mean(source_i - URMA) for source_i in (HRRR L1, NBM raw, ECMWF raw)
  w      = simplex weights (0.05 grid) minimising sum |sum_i w_i (source_i - bias_i - URMA)|
Writes weather_collector/data/urma_blend_shadow_curated.json (the refitter publishes it to
runtime_tables/). URMA hours come from the public AWS bucket, fetched incrementally (URMA lags ~6 h).

    PYTHONPATH=. .venv/bin/python -m analysis.urma_blend_table_fit
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis import terminal_blend_field_fit as tb  # noqa: E402
from analysis._cache import PAIR_LOG_URL, cached_path  # noqa: E402

ET = ZoneInfo("America/New_York")
URMA_FILE = ROOT / "analysis" / "output" / "urma_truth" / "urma_cell.jsonl"
OUT_PATH = ROOT / "weather_collector" / "data" / "urma_blend_shadow_curated.json"
WIN = 14
MIN_N = 300
MIN_HOURS_PER_DAY = 20
URMA_LAG_H = 8
MAX_FETCH_H = 96
BANDS = (("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48))
GRID3 = np.asarray(tb.GRID3)


def _idw_f(nb):
    w = np.array([1 / max(x[2], 0.1) ** 2 for x in nb])
    return ((sum(wi * x[3] for wi, x in zip(w, nb)) / w.sum()) - 273.15) * 9 / 5 + 32


def load_truth():
    out = {}
    if URMA_FILE.exists():
        for line in open(URMA_FILE):
            r = json.loads(line)
            if r.get("var") == "TMP":
                out[r["valid"][:13]] = _idw_f(r["nb"])
    return out


def update_truth(truth):
    """Fetch URMA TMP for hours missing between the newest stored hour and now - lag. Best effort."""
    try:
        from analysis.urma_truth_backfill import fetch
    except Exception as e:  # noqa: BLE001
        print(f"  URMA fetch unavailable ({e}); using stored truth")
        return
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    last = datetime.strptime(max(truth) + ":00", "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc) if truth else now - timedelta(days=WIN + 2)
    t, n = last + timedelta(hours=1), 0
    URMA_FILE.parent.mkdir(parents=True, exist_ok=True)
    while t <= now - timedelta(hours=URMA_LAG_H) and n < MAX_FETCH_H:
        k = t.strftime("%Y-%m-%dT%H")
        if k not in truth:
            nb = fetch(t, "TMP")
            if nb is not None:
                with open(URMA_FILE, "a") as f:
                    f.write(json.dumps({"valid": t.strftime("%Y-%m-%dT%H:00Z"), "var": "TMP", "nb": nb}) + "\n")
                truth[k] = _idw_f(nb)
                n += 1
        t += timedelta(hours=1)
    print(f"  URMA: fetched {n} new hours")


def best_w(e3):
    return [float(x) for x in GRID3[int(np.abs(e3 @ GRID3.T).sum(0).argmin())]]


def fit():
    truth = load_truth()
    update_truth(truth)
    by_day = {}
    for k in truth:
        d = datetime.strptime(k, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc).astimezone(ET).strftime("%Y-%m-%d")
        by_day[d] = by_day.get(d, 0) + 1
    days = sorted(d for d, n in by_day.items() if n >= MIN_HOURS_PER_DAY)[-WIN:]
    dset = set(days)
    rows = []
    with open(cached_path(PAIR_LOG_URL)) as fin:
        for line in fin:
            if '"field": "t"' not in line and '"field":"t"' not in line:
                continue
            r = json.loads(line)
            vt = r.get("valid_time") or ""
            if r.get("field") != "t" or vt[:10] not in dset or r.get("lead_h") is None:
                continue
            hr, nb = r.get("forecast_l1"), r.get("forecast_raw_nbm")
            if hr is None or nb is None:
                continue
            u = datetime.strptime(vt[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=ET).astimezone(timezone.utc)
            tr = truth.get(u.strftime("%Y-%m-%dT%H"))
            if tr is None:
                continue
            rows.append((vt, int(r["lead_h"]), float(hr), float(nb), tr))
    eh = tb.ecmwf_history(days[0], days[-1]) if days else {}
    bands = {}
    used = 0
    for b, lo, hi in BANDS:
        e = []
        for vt, lead, hr, nb, tr in rows:
            if not lo <= lead < hi:
                continue
            fe = (eh.get(tb._ecmwf_key(vt)) or {}).get("t")
            fe = fe[tb._ecmwf_day(lead)] if fe else None
            if fe is None:
                continue
            e.append((hr - tr, nb - tr, float(fe) - tr))
        if len(e) < MIN_N:
            print(f"  {b}: n={len(e)} < {MIN_N}, no cell")
            continue
        e = np.asarray(e)
        bias = e.mean(0)
        w = best_w(e - bias)
        used += len(e)
        bands[b] = {"bias": [round(float(x), 3) for x in bias], "w": w, "n": len(e),
                    "mae_corrected_blend": round(float(np.abs((e - bias) @ np.asarray(w)).mean()), 3)}
        print(f"  {b}: n={len(e):,} bias(h,n,e)={[round(float(x), 2) for x in bias]} w={w} "
              f"in-sample MAE {bands[b]['mae_corrected_blend']}")
    out = {"fitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"), "window_days": WIN,
           "truth": "urma_idw_4cell", "days": [days[0], days[-1]] if days else None,
           "n_rows_kept": used, "fields": {"t": {"bands": bands}},
           "notes": "SHADOW: stamps t_urmab only. Sources: HRRR L1, NBM raw, ECMWF raw; "
                    "out = sum_i w_i (source_i - bias_i); bias vs URMA over the window."}
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  wrote {OUT_PATH}")
    return out


if __name__ == "__main__":
    fit()

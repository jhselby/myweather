"""Daily fit of the URMA-truth blend table for t (bias-then-blend, served) and ws (weights only, shadow; see
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


def _idw_raw(nb):
    w = np.array([1 / max(x[2], 0.1) ** 2 for x in nb])
    return float(sum(wi * x[3] for wi, x in zip(w, nb)) / w.sum())


def _idw_f(nb):
    w = np.array([1 / max(x[2], 0.1) ** 2 for x in nb])
    return ((sum(wi * x[3] for wi, x in zip(w, nb)) / w.sum()) - 273.15) * 9 / 5 + 32


GCS_STORE = "urma_truth_t.json"   # cloud mode: {"YYYY-MM-DDTHH": [[lat, lon, km, K] x4]}, ~50 KB for 14 days
GCS_STORE_DPT = "urma_truth_dpt.json"   # same shape, dew point (v0.7.100): h/dp scored on URMA; not used by the fit
GCS_STORE_TCDC = "urma_truth_tcdc.json"   # same shape, total cloud cover % (v0.7.102): cc scored on URMA; not used by the fit
GCS_STORE_WIND = "urma_truth_wind.json"   # same shape, 10 m wind m/s (v0.7.123): ws_urmab fit + ws scored on URMA
GCS_STORE_GUST = "urma_truth_gust.json"   # same shape, 10 m gust m/s (v0.7.125): wg_urmab fit
AUX_STORES = (("DPT", GCS_STORE_DPT), ("TCDC", GCS_STORE_TCDC), ("WIND", GCS_STORE_WIND), ("GUST", GCS_STORE_GUST))
WG_BANDS = (("0-5", 0, 6),) + BANDS
MS_TO_MPH = 2.23694
KEEP_DAYS = 25


def _cloud():
    import os
    return os.environ.get("MYWEATHER_CACHE_MODE") == "gcs"


def load_truth():
    out = {}
    if _cloud():
        from weather_collector.gcs_io import load_json
        for k, nb in (load_json(GCS_STORE) or {}).items():
            out[k] = _idw_f(nb)
    elif URMA_FILE.exists():
        for line in open(URMA_FILE):
            r = json.loads(line)
            if r.get("var") == "TMP":
                out[r["valid"][:13]] = _idw_f(r["nb"])
    return out


def _save_cloud(new, name=GCS_STORE):
    """Merge newly fetched hours into a GCS store (trimmed to KEEP_DAYS)."""
    from weather_collector.gcs_io import load_json, upload_json
    store = load_json(name) or {}
    store.update(new)
    cut = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%dT%H")
    store = {k: v for k, v in store.items() if k >= cut}
    upload_json(store, name, "urma truth store")


LOCAL_AUX_VARS = ("DPT", "TCDC", "WIND", "GUST")   # urma_field_score + truth_compare read these locally


def update_aux():
    """Keep the URMA dew point and cloud cover stores current (cloud), or append DPT/TCDC/WIND
    to urma_cell.jsonl (local digest; before 11-20 only TMP advanced, so local h/dp/ws/cc
    scores on URMA froze at the last manual backfill, 11-13)."""
    if not _cloud():
        for var in LOCAL_AUX_VARS:
            _update_aux_local(var)
        return
    for var, store in AUX_STORES:
        _update_aux(var, store)


def _update_aux_local(var):
    """Append missing hours of `var` to URMA_FILE, same window/lag/cap as TMP. Best effort."""
    try:
        from analysis.urma_truth_backfill import fetch
        have = set()
        if URMA_FILE.exists():
            for line in open(URMA_FILE):
                if f'"{var}"' in line:
                    have.add(json.loads(line)["valid"][:13])
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        t = now - timedelta(days=WIN + 2)
        if have:
            t = max(t, datetime.strptime(max(have) + ":00", "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc) + timedelta(hours=1))
        n = 0
        while t <= now - timedelta(hours=URMA_LAG_H) and n < MAX_FETCH_H:
            k = t.strftime("%Y-%m-%dT%H")
            if k not in have:
                nb = fetch(t, var)
                if nb is not None:
                    with open(URMA_FILE, "a") as f:
                        f.write(json.dumps({"valid": t.strftime("%Y-%m-%dT%H:00Z"), "var": var, "nb": nb}) + "\n")
                    n += 1
            t += timedelta(hours=1)
        print(f"  URMA {var} (local): fetched {n} new hours")
    except Exception as e:  # noqa: BLE001
        print(f"  URMA {var} local update failed ({type(e).__name__}: {e})")


def _update_aux(var, store):
    """Same hours/lag/cap as TMP. Best effort; a failure here never touches the t fit."""
    if not _cloud():
        return
    try:
        from analysis.urma_truth_backfill import fetch
        from weather_collector.gcs_io import load_json
        have = load_json(store) or {}
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        t = now - timedelta(days=WIN + 2)
        if have:
            t = max(t, datetime.strptime(max(have) + ":00", "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc) + timedelta(hours=1))
        new, n = {}, 0
        while t <= now - timedelta(hours=URMA_LAG_H) and n < MAX_FETCH_H:
            k = t.strftime("%Y-%m-%dT%H")
            if k not in have:
                nb = fetch(t, var)
                if nb is not None:
                    new[k] = nb
                    n += 1
            t += timedelta(hours=1)
        if new:
            _save_cloud(new, store)
        print(f"  URMA {var}: fetched {n} new hours")
    except Exception as e:  # noqa: BLE001
        print(f"  URMA {var} update failed ({type(e).__name__}: {e})")


def update_truth(truth):
    """Fetch URMA TMP for hours missing between the newest stored hour and now - lag. Best effort."""
    try:
        from analysis.urma_truth_backfill import fetch
    except Exception as e:  # noqa: BLE001
        print(f"  URMA fetch unavailable ({e}); using stored truth")
        return
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    last = datetime.strptime(max(truth) + ":00", "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc) if truth else now - timedelta(days=WIN + 2)
    t, n, new = last + timedelta(hours=1), 0, {}
    if not _cloud():
        URMA_FILE.parent.mkdir(parents=True, exist_ok=True)
    while t <= now - timedelta(hours=URMA_LAG_H) and n < MAX_FETCH_H:
        k = t.strftime("%Y-%m-%dT%H")
        if k not in truth:
            nb = fetch(t, "TMP")
            if nb is not None:
                if _cloud():
                    new[k] = nb
                else:
                    with open(URMA_FILE, "a") as f:
                        f.write(json.dumps({"valid": t.strftime("%Y-%m-%dT%H:00Z"), "var": "TMP", "nb": nb}) + "\n")
                truth[k] = _idw_f(nb)
                n += 1
        t += timedelta(hours=1)
    if new:
        _save_cloud(new)
    print(f"  URMA: fetched {n} new hours")


def best_w(e3):
    return [float(x) for x in GRID3[int(np.abs(e3 @ GRID3.T).sum(0).argmin())]]


def load_wind(var="WIND", store=None):
    """{UTC 'YYYY-MM-DDTHH': URMA 10 m wind (or GUST), mph} from the cloud store or the local file."""
    store = store or (GCS_STORE_GUST if var == "GUST" else GCS_STORE_WIND)
    out = {}
    if _cloud():
        from weather_collector.gcs_io import load_json
        for k, nb in (load_json(store) or {}).items():
            out[k] = _idw_raw(nb) * MS_TO_MPH
    elif URMA_FILE.exists():
        for line in open(URMA_FILE):
            if f'"{var}"' in line:
                r = json.loads(line)
                out[r["valid"][:13]] = _idw_raw(r["nb"]) * MS_TO_MPH
    return out


def _rows(field, truth, dset):
    """(valid_time, lead, hrrr, nbm, truth) for `field` pair-log rows on the fit days."""
    rows = []
    with open(cached_path(PAIR_LOG_URL)) as fin:
        for line in fin:
            if f'"field": "{field}"' not in line and f'"field":"{field}"' not in line:
                continue
            r = json.loads(line)
            vt = r.get("valid_time") or ""
            if r.get("field") != field or vt[:10] not in dset or r.get("lead_h") is None:
                continue
            hr, nb = r.get("forecast_l1"), r.get("forecast_raw_nbm")
            if hr is None or nb is None:
                continue
            u = datetime.strptime(vt[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=ET).astimezone(timezone.utc)
            tr = truth.get(u.strftime("%Y-%m-%dT%H"))
            if tr is None:
                continue
            rows.append((vt, int(r["lead_h"]), float(hr), float(nb), tr))
    return rows


def _fit_bands_2way(field, rows, bands_def):
    """wg (no ECMWF gust input): per band, debias HRRR and NBM on the window, then the HRRR weight
    (0.05 grid) minimising sum |w e_h + (1-w) e_n|. Stored as 3-way with ECMWF weight 0."""
    bands, used = {}, 0
    grid = np.linspace(0, 1, 21)
    for b, lo, hi in bands_def:
        e = np.asarray([(hr - tr, nb - tr) for vt, lead, hr, nb, tr in rows if lo <= lead < hi])
        if len(e) < MIN_N:
            print(f"  {field} {b}: n={len(e)} < {MIN_N}, no cell")
            continue
        bias = e.mean(0)
        d = e - bias
        wh = float(grid[int(np.argmin([np.abs(w * d[:, 0] + (1 - w) * d[:, 1]).sum() for w in grid]))])
        w = [round(wh, 2), round(1 - wh, 2), 0.0]
        used += len(e)
        bands[b] = {"bias": [round(float(bias[0]), 3), round(float(bias[1]), 3), 0.0], "w": w, "n": len(e),
                    "mae_corrected_blend": round(float(np.abs(wh * d[:, 0] + (1 - wh) * d[:, 1]).mean()), 3)}
        print(f"  {field} {b}: n={len(e):,} bias(h,n)={[round(float(x), 2) for x in bias]} w={w} "
              f"in-sample MAE {bands[b]['mae_corrected_blend']}")
    return bands, used


def _fit_bands(field, rows, eh, use_bias, bands_def=BANDS):
    """Per band: bias (or zeros) and simplex weights on (HRRR, NBM, ECMWF) errors vs URMA."""
    bands, used = {}, 0
    for b, lo, hi in bands_def:
        e = []
        for vt, lead, hr, nb, tr in rows:
            if not lo <= lead < hi:
                continue
            fe = (eh.get(tb._ecmwf_key(vt)) or {}).get(field)
            fe = fe[tb._ecmwf_day(lead)] if fe else None
            if fe is None:
                continue
            e.append((hr - tr, nb - tr, float(fe) - tr))
        if len(e) < MIN_N:
            print(f"  {field} {b}: n={len(e)} < {MIN_N}, no cell")
            continue
        e = np.asarray(e)
        bias = e.mean(0) if use_bias else np.zeros(3)
        w = best_w(e - bias)
        used += len(e)
        bands[b] = {"bias": [round(float(x), 3) for x in bias], "w": w, "n": len(e),
                    "mae_corrected_blend": round(float(np.abs((e - bias) @ np.asarray(w)).mean()), 3)}
        print(f"  {field} {b}: n={len(e):,} bias(h,n,e)={[round(float(x), 2) for x in bias]} w={w} "
              f"in-sample MAE {bands[b]['mae_corrected_blend']}")
    return bands, used


def fit():
    truth = load_truth()
    update_truth(truth)
    update_aux()
    by_day = {}
    for k in truth:
        d = datetime.strptime(k, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc).astimezone(ET).strftime("%Y-%m-%d")
        by_day[d] = by_day.get(d, 0) + 1
    days = sorted(d for d, n in by_day.items() if n >= MIN_HOURS_PER_DAY)[-WIN:]
    dset = set(days)
    eh = tb.ecmwf_history(days[0], days[-1]) if days else {}
    fields = {}
    bands, used = _fit_bands("t", _rows("t", truth, dset), eh, use_bias=True)
    fields["t"] = {"bands": bands}
    # v0.7.126: ws shadow also covers 0-5h (holdout vs served +10.6%, vs raw NBM +9.7%, both pass).
    # v0.7.123 ws shadow (ws_urmab): weights only on URMA 10 m wind. Walk-forward 76 days
    # (analysis/urma_blend_wf_ws.py): +10..+15% vs served every band; bias step lost on holdout.
    wind = load_wind()
    wbands, wused = _fit_bands("ws", _rows("ws", wind, dset), eh, use_bias=False, bands_def=WG_BANDS) if wind else ({}, 0)
    if wbands:
        fields["ws"] = {"bands": wbands}
    # v0.7.125 wg shadow (wg_urmab): debiased HRRR/NBM 2-way on URMA 10 m gust, 0-47h. Walk-forward
    # 20 days: vs served +42/+27/+22/+17% (0-5/6-11/12-23/24-47, holdout all pass); vs raw NBM +15% at 0-5.
    gust = load_wind("GUST")
    gbands, gused = _fit_bands_2way("wg", _rows("wg", gust, dset), WG_BANDS) if gust else ({}, 0)
    if gbands:
        fields["wg"] = {"bands": gbands}
    wused += gused
    out = {"fitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"), "window_days": WIN,
           "truth": "urma_idw_4cell", "days": [days[0], days[-1]] if days else None,
           "n_rows_kept": used + wused, "fields": fields,
           "notes": "t: SERVED as t_urmab (v0.7.114); ws: SHADOW ws_urmab (weights only, bias 0); wg: SHADOW wg_urmab (debiased HRRR/NBM, 0-47h). "
                    "Sources: HRRR L1, NBM raw, ECMWF raw; out = sum_i w_i (source_i - bias_i); bias vs URMA over the window."}
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  wrote {OUT_PATH}")
    return out


if __name__ == "__main__":
    fit()

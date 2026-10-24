"""Field-level terminal blend weight (v0.7.71).

served = w * HRRR_terminal + (1 - w) * NBM_terminal on EVERY row of the field,
one w per field, fit on the last WINDOW_DAYS of the pair log. Terminals are
the ones forecast_snapshot blends (HRRR l6/l5/l4 for t, l5/l4 for sr, l4/l3/l2
otherwise; NBM l3_nbm/l2_nbm/raw_nbm), read here as their pair-log residuals.

Why: 10-20 walk-forward (w fit on the prior 14d, scored on the next day,
17 days) against what shipped: h +12.2% (16/17 days), sr +11.2% (12/17),
t +4.2% (11/17), wg +3.3% (12/17). The per-cell curated blend covered only
8.5% of t rows and 37% of sr; the uncovered rows carried the Selector Score
gap. Weights drift (h 0.40→0.65, sr 0.30→0.50), so the refitter refits this
daily (refitter/tables.py); the repo copy is the fallback.

v0.7.73: h and sr also get one w per 4-hour block of local valid time
(`w_by_block`, keyed by block start hour). 10-20 walk-forward vs the single
field w, 17 days: h +4.3% (16/17 days, halves +3.9/+5.0), sr +5.8% (11/17,
halves +6.8/+4.4). Regime, regime x band, band (except wg +0.6) and
3/7/28-day windows did not beat the field w. A block with n < MIN_BLOCK_N
is left out and the runtime falls back to the field w.

v0.7.74: t gets one w per lead band (`w_by_band`, keyed "0-5", "6-11",
"12-23", "24-47"). At short lead the HRRR terminal carries the L2 obs nudge
and NBM's does not, so one field w gave the shipped blend 1.14 at 0-5h vs
HRRR-only 0.93. 10-21 walk-forward, 17 days: t +1.8% (halves +1.2/+2.3,
9/17 days), 0-5h 1.14 -> 0.94. Per-band w for h, sr, wg, ws was flat or
mixed. A band with n < MIN_BLOCK_N falls back to the field w.

v0.7.75: ECMWF IFS (Open-Meteo ecmwf_ifs025) as a third input on t and h.
`w3` = [w_hrrr, w_nbm, w_ecmwf] per field, plus `w3_by_band` (t) and
`w3_by_block` (h). 10-22 walk-forward (fit prior 14d, next day scored,
17 days) vs the shipped 2-way rule: t +19.1% (halves +14.4/+23.0, 13/17
days), h +11.5% (halves +7.3/+16.2, 13/17). ECMWF errors for the fit come
from Open-Meteo's previous-runs archive, using a run at least 24/48/72h
older than the valid hour (day N = 1 for lead <= 17h, 2 for <= 41h, else 3)
so the fit never sees an ECMWF run the collector could not have had. The
runtime serves the freshest run, so live ECMWF is at least this good. A
missing archive leaves w3 out and the runtime serves the 2-way blend.

v0.7.81: ws joins the field blend with the same 3-way rule (band-keyed w and
w3_by_band, like t). 10-24 walk-forward on terminal inputs (fit prior 14d,
next day scored, 17 days) vs what was served: pooled +6.4%, vs NBM raw (the
normal source) +9.3%; every band has both halves positive. Before this ws was
NBM-terminal at 6-47h (zero edge over NBM there).

Writes weather_collector/data/terminal_blend_field_curated.json.
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis._cache import cached_path, PAIR_LOG_URL  # noqa: E402

OUT_PATH = ROOT / "weather_collector" / "data" / "terminal_blend_field_curated.json"
FIELDS = ("t", "h", "sr", "wg", "ws")
WINDOW_DAYS = 14
GRID = [i / 20 for i in range(21)]
MIN_N = 2000
BLOCK_FIELDS = ("h", "sr")
BAND_FIELDS = ("t", "ws")
BANDS = (("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48))
BLOCK_HOURS = 4
MIN_BLOCK_N = 300

HRRR_KEYS = {"t": ("error_l6", "error_l5", "error_l4"),
             "sr": ("error_l5", "error_l4")}
HRRR_DEFAULT = ("error_l4", "error_l3", "error_l2")
NBM_KEYS = ("error_l3_nbm", "error_l2_nbm", "error_raw_nbm")

E_VARS = {"t": "temperature_2m", "h": "relative_humidity_2m", "ws": "wind_speed_10m"}
E_KEY = {"t": "band", "h": "block", "ws": "band"}
GRID3 = [(i / 20, j / 20, round(1 - (i + j) / 20, 2)) for i in range(21) for j in range(21 - i)]
PREV_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"


def _ecmwf_day(lead):
    return 1 if lead <= 17 else 2 if lead <= 41 else 3


def ecmwf_history(start, end):
    """{"YYYY-MM-DDTHH": {field: [None, day1, day2, day3]}} in local time,
    from Open-Meteo's previous-runs archive. {} on any failure."""
    from weather_collector.config import LAT, LON
    hourly = [f"{v}_previous_day{n}" for v in E_VARS.values() for n in (1, 2, 3)]
    q = urllib.parse.urlencode({
        "latitude": LAT, "longitude": LON, "hourly": ",".join(hourly),
        "models": "ecmwf_ifs025", "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
        "timezone": "America/New_York", "start_date": start, "end_date": end})
    try:
        with urllib.request.urlopen(f"{PREV_RUNS_URL}?{q}", timeout=60) as resp:
            h = json.load(resp)["hourly"]
    except Exception as e:  # noqa: BLE001
        print(f"  ECMWF previous-runs fetch failed ({e}); no w3")
        return {}
    out = {}
    for i, t in enumerate(h["time"]):
        out[t[:13]] = {f: [None] + [h[f"{v}_previous_day{n}"][i] for n in (1, 2, 3)]
                       for f, v in E_VARS.items()}
    return out


def _best3(rows):
    import numpy as np
    a = np.asarray(rows, dtype=float)
    w = np.asarray(GRID3)
    s = np.abs(a @ w.T).sum(0)
    k = int(s.argmin())
    return [float(x) for x in GRID3[k]], float(s[k])


def _first(row, keys):
    for k in keys:
        v = row.get(k)
        if v is not None:
            return float(v)
    return None


def fit():
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    since = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M")
    sums = {f: [0.0] * len(GRID) for f in FIELDS}
    n = {f: 0 for f in FIELDS}
    bsums = {}  # (field, block start hour) -> grid sums
    bn = {}
    dsums = {}  # (field, lead band) -> grid sums
    dn = {}
    n_rows = 0
    ehist = ecmwf_history((now - timedelta(days=WINDOW_DAYS + 1)).strftime("%Y-%m-%d"),
                          now.strftime("%Y-%m-%d"))
    e3 = {}  # (field, key or None) -> [(eh, en, ee)]
    with open(cached_path(PAIR_LOG_URL)) as fin:
        for line in fin:
            if '"field"' not in line:
                continue
            r = json.loads(line)
            f = r.get("field")
            if f not in FIELDS or (r.get("obs_time") or "") < since:
                continue
            eh = _first(r, HRRR_KEYS.get(f, HRRR_DEFAULT))
            en = _first(r, NBM_KEYS)
            if eh is None or en is None:
                continue
            n[f] += 1
            n_rows += 1
            s = sums[f]
            for i, w in enumerate(GRID):
                s[i] += abs(w * eh + (1.0 - w) * en)
            vt = r.get("valid_time") or ""
            if f in BLOCK_FIELDS and len(vt) >= 13:
                bk = (f, int(vt[11:13]) // BLOCK_HOURS * BLOCK_HOURS)
                bs = bsums.setdefault(bk, [0.0] * len(GRID))
                bn[bk] = bn.get(bk, 0) + 1
                for i, w in enumerate(GRID):
                    bs[i] += abs(w * eh + (1.0 - w) * en)
            lead = r.get("lead_h")
            band = next((b for b, lo, hi in BANDS if lead is not None and lo <= lead < hi), None)
            if f in E_VARS and ehist and lead is not None and r.get("observed") is not None:
                fe = (ehist.get(vt[:13]) or {}).get(f)
                fe = fe[_ecmwf_day(lead)] if fe else None
                if fe is not None:
                    ee = float(fe) - float(r["observed"])
                    sub = band if E_KEY[f] == "band" else (
                        str(int(vt[11:13]) // BLOCK_HOURS * BLOCK_HOURS) if len(vt) >= 13 else None)
                    e3.setdefault((f, None), []).append((eh, en, ee))
                    if sub is not None:
                        e3.setdefault((f, sub), []).append((eh, en, ee))
            if f in BAND_FIELDS and band:
                bk = (f, band)
                bs = dsums.setdefault(bk, [0.0] * len(GRID))
                dn[bk] = dn.get(bk, 0) + 1
                for i, w in enumerate(GRID):
                    bs[i] += abs(w * eh + (1.0 - w) * en)

    fields = {}
    for f in FIELDS:
        if n[f] < MIN_N:
            print(f"  {f}: n={n[f]} < {MIN_N}, no weight")
            continue
        s = sums[f]
        i = min(range(len(GRID)), key=lambda k: s[k])
        fields[f] = {"w": GRID[i], "n": n[f],
                     "mae_blend": round(s[i] / n[f], 4),
                     "mae_hrrr": round(s[-1] / n[f], 4),
                     "mae_nbm": round(s[0] / n[f], 4)}
        x = fields[f]
        print(f"  {f}: w_hrrr={x['w']:.2f}  n={x['n']:,}  blend {x['mae_blend']:.3f}  "
              f"hrrr {x['mae_hrrr']:.3f}  nbm {x['mae_nbm']:.3f}")
        if f in BLOCK_FIELDS:
            blocks = {}
            for (bf, h), bs in sorted(bsums.items()):
                if bf != f or bn[(bf, h)] < MIN_BLOCK_N:
                    continue
                j = min(range(len(GRID)), key=lambda k: bs[k])
                blocks[str(h)] = GRID[j]
            x["w_by_block"] = blocks
            x["block_hours"] = BLOCK_HOURS
            bmae = sum(min(bs) for (bf, h), bs in bsums.items()
                       if bf == f and str(h) in blocks)
            bfield = sum(bs[i] for (bf, h), bs in bsums.items()
                         if bf == f and str(h) in blocks)
            x["mae_block"] = round(bmae / n[f], 4) if blocks else None
            print(f"     by {BLOCK_HOURS}h block: {blocks}  "
                  f"in-sample {100 * (bfield - bmae) / bfield:+.1f}% vs field w" if bfield else "")
        if f in BAND_FIELDS:
            bands = {}
            for b, _, _ in BANDS:
                bs = dsums.get((f, b))
                if bs and dn[(f, b)] >= MIN_BLOCK_N:
                    bands[b] = GRID[min(range(len(GRID)), key=lambda k: bs[k])]
            x["w_by_band"] = bands
            bmae = sum(min(dsums[(f, b)]) for b in bands)
            x["mae_band"] = round(bmae / n[f], 4) if bands else None
            print(f"     by lead band: {bands}")
        rows3 = e3.get((f, None)) or []
        if len(rows3) >= MIN_N:
            w3, s3 = _best3(rows3)
            subs = {}
            for (ef, sub), rr in sorted(e3.items(), key=lambda kv: str(kv[0])):
                if ef == f and sub is not None and len(rr) >= MIN_BLOCK_N:
                    subs[sub] = _best3(rr)[0]
            x["w3"] = w3
            x[f"w3_by_{E_KEY[f]}"] = subs
            x["n3"] = len(rows3)
            x["mae_3way"] = round(s3 / len(rows3), 4)
            print(f"     3-way (hrrr, nbm, ecmwf) {w3} n={len(rows3):,} mae {x['mae_3way']:.3f}; "
                  f"by {E_KEY[f]}: {subs}")

    out = {"fitted_at": now.strftime("%Y-%m-%dT%H:%M"), "window_days": WINDOW_DAYS,
           "n_rows_kept": n_rows, "fields": fields,
           "notes": "w = HRRR weight on the terminal blend, served on every row of the field "
                    "(weather_collector/processors/terminal_static_blend.py FIELD_APPLIED). "
                    "w_by_block (h, sr) = w per block of local valid hour, keyed by block "
                    "start; missing blocks use w. w_by_band (t, ws) = w per lead band; "
                    "missing bands use w. w3 (t, h, ws) = [hrrr, nbm, ecmwf] weights, "
                    "w3_by_band (t, ws) / w3_by_block (h); served when the ECMWF hourly is "
                    "present, else the 2-way w."}
    with open(OUT_PATH, "w") as fout:
        json.dump(out, fout, indent=2)
    print(f"  wrote {OUT_PATH}")
    return out


if __name__ == "__main__":
    fit()

"""Terminal blend fit (v0.7.57). Writes weather_collector/data/terminal_static_blend_curated.json.

Terminal blend fit: served = w * HRRR_terminal + (1 - w) * NBM_terminal.

Terminals mirror the runtime shadow blender (forecast_snapshot ~1131):
  HRRR: t -> l6 > l5 > l4 ; sr -> l5 > l4 ; ws/wg/h -> l4 > l3 > l2  (then l1)
  NBM : l3_nbm > l2_nbm > raw_nbm
Blend error = w*e_h + (1-w)*e_n (signed errors share the obs).

Per field: universal w, and per (regime_runtime, band) cells. Halves-stable:
w fit on half A scored on half B and vice versa; lift vs SERVED (error of the
applied layer) on the same rows. Gate: both cross-half lifts >= 5%, 30d
n >= 400, 0.05 < w < 0.95.
"""
import json, sys, collections
from datetime import date, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from analysis._cache import pair_log_paths, RegimeRuntime
from analysis.per_field_scoring import _prod_error, _band_for

FIELDS = ("t", "sr", "ws", "wg", "h")
_today = date.today()
FROM = (_today - timedelta(days=30)).isoformat()
MID = (_today - timedelta(days=15)).isoformat()
TO = (_today + timedelta(days=1)).isoformat()
OUT = ROOT / "weather_collector" / "data" / "terminal_static_blend_curated.json"
GRID = [i / 20 for i in range(21)]
HRRR_TERM = {"t": ("l6", "l5", "l4", "l1"), "sr": ("l5", "l4", "l1")}
NBM_TERM = ("l3_nbm", "l2_nbm", "raw_nbm")

def first(r, keys):
    for k in keys:
        v = r.get(f"error_{k}")
        if v:  # runtime uses `or`, so 0 falls through; mirror it
            return float(v)
    for k in keys:
        v = r.get(f"error_{k}")
        if v is not None:
            return float(v)
    return None

rr = RegimeRuntime()
paths = pair_log_paths()
rr.prime(paths)
data = collections.defaultdict(list)  # field -> [(regime, band, half, eh, en, es)]
for p in paths:
    with open(p) as fh:
        for line in fh:
            if line.startswith('{"obs_time": "') and line[14:24] < FROM:
                continue
            r = json.loads(line)
            f = r.get("field")
            if f not in FIELDS or not (FROM <= (r.get("obs_time") or "") < TO):
                continue
            band = _band_for(r.get("lead_h"))
            eh = first(r, HRRR_TERM.get(f, ("l4", "l3", "l2", "l1")))
            en = first(r, NBM_TERM)
            es = _prod_error(r)
            if band is None or eh is None or en is None or es is None:
                continue
            reg = rr.get(r)
            data[f].append((reg, band, "a" if r["obs_time"] < MID else "b", eh, en, abs(float(es))))

def best_w(rows):
    return min(GRID, key=lambda w: sum(abs(w * eh + (1 - w) * en) for *_, eh, en, _ in rows))

def score(rows, w):
    n = len(rows)
    if not n:
        return None
    blend = sum(abs(w * eh + (1 - w) * en) for *_, eh, en, _ in rows) / n
    served = sum(es for *_, es in rows) / n
    return 100 * (served - blend) / served if served else None, n

def cross(rows):
    A = [x for x in rows if x[2] == "a"]; B = [x for x in rows if x[2] == "b"]
    if len(A) < 100 or len(B) < 100:
        return None
    wa, wb = best_w(A), best_w(B)
    return wa, wb, score(B, wa)[0], score(A, wb)[0]

curated = {"generated_at": _today.isoformat(), "window": [FROM, TO], "halves_split": MID,
           "gate": {"min_n": 400, "min_cross_half_lift_pct": 5.0, "w_range": [0.05, 0.95]},
           "note": "served = w*HRRR_terminal + (1-w)*NBM_terminal per (field, regime_runtime, band). "
                   "Lift is vs the served (applied-layer) error on the same rows.",
           "fields": {}}
for f in FIELDS:
    rows = data[f]
    if not rows:
        continue
    w = best_w(rows)
    lift, n = score(rows, w)
    c = cross(rows)
    print(f"\n{f}  n={n:,}  universal w={w:.2f}  lift vs served {lift:+.1f}%  "
          f"cross-half wA={c[0]:.2f} wB={c[1]:.2f} lift B|wA {c[2]:+.1f}% A|wB {c[3]:+.1f}%")
    cells = collections.defaultdict(list)
    for x in rows:
        cells[(x[0], x[1])].append(x)
    passing = []
    for (reg, band), cr in sorted(cells.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        if len(cr) < 400:
            continue
        c = cross(cr)
        if not c:
            continue
        wc = best_w(cr)
        lc, nc = score(cr, wc)
        lu, _ = score(cr, w)  # universal w on this cell
        ok = c[2] >= 5 and c[3] >= 5 and 0.05 < wc < 0.95
        mark = "PASS" if ok else "    "
        print(f"  {mark} {str(reg):12} {band:6} n={nc:5}  w={wc:.2f} lift {lc:+6.1f}%  univ-w lift {lu:+6.1f}%  "
              f"cross {c[2]:+6.1f} / {c[3]:+6.1f}  (wA {c[0]:.2f} wB {c[1]:.2f})")
        if ok:
            passing.append((reg, band, wc, nc))
    print(f"  -> {len(passing)} cells pass")
    curated["fields"][f] = {"universal_w": w, "universal_lift_pct": round(lift, 2),
                            "cells": [{"regime": reg, "band": band, "w": wc, "n": nc} for reg, band, wc, nc in passing]}

OUT.write_text(json.dumps(curated, indent=1))
print(f"\nwrote {OUT}")

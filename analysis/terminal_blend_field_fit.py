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

Writes weather_collector/data/terminal_blend_field_curated.json.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis._cache import cached_path, PAIR_LOG_URL  # noqa: E402

OUT_PATH = ROOT / "weather_collector" / "data" / "terminal_blend_field_curated.json"
FIELDS = ("t", "h", "sr", "wg")
WINDOW_DAYS = 14
GRID = [i / 20 for i in range(21)]
MIN_N = 2000

HRRR_KEYS = {"t": ("error_l6", "error_l5", "error_l4"),
             "sr": ("error_l5", "error_l4")}
HRRR_DEFAULT = ("error_l4", "error_l3", "error_l2")
NBM_KEYS = ("error_l3_nbm", "error_l2_nbm", "error_raw_nbm")


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
    n_rows = 0
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

    out = {"fitted_at": now.strftime("%Y-%m-%dT%H:%M"), "window_days": WINDOW_DAYS,
           "n_rows_kept": n_rows, "fields": fields,
           "notes": "w = HRRR weight on the terminal blend, served on every row of the field "
                    "(weather_collector/processors/terminal_static_blend.py FIELD_APPLIED)."}
    with open(OUT_PATH, "w") as fout:
        json.dump(out, fout, indent=2)
    print(f"  wrote {OUT_PATH}")
    return out


if __name__ == "__main__":
    fit()

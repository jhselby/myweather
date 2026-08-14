#!/usr/bin/env python3
"""Diagnostic: does shorter Lc fit window recover from the recent bias shift?

Live `lc_fit.py` uses the whole pair log (~30 days). Diagnosis 2026-07-30
showed cl's historical bias per (regime, bin) has shrunk 4-38× or
sign-flipped vs the pre-07-20 fit — so the current shifts are calibrated
on stale HRRR behavior and drag accurate forecasts into wrong territory.

This script sweeps rolling fit windows W ∈ {3, 5, 7, 10, 14, 21, all}
days, refits pooled Lc on rows with `obs_time ∈ [today-W-Hold, today-Hold)`,
evaluates on the held-out last HOLD_DAYS days, reports:

  - Per-field held-out MAE for raw / Lc-corrected at each window
  - Per-bin shift comparison across windows (does W=7 shift half of W=30?)
  - Verdict: shortest window where every field beats raw on held-out

If a short window recovers cl (and doesn't hurt cc/cm/ch), we lift the
`_FIELD_SKIP={"cl"}` bandage AND change `lc_fit.py` to use that window.

Run:
    python3 -m analysis.h_lc_rolling_window
    python3 -m analysis.h_lc_rolling_window --hold-days 3
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path

# Runtime skip list — Lc is a no-op on these fields regardless of table shape.
# Import so the "shortest window all fields beat raw" verdict is computed over
# runtime-active fields, not the full 4-field sweep. Falls back to empty set on
# import failure (the sweep still runs; the verdict just answers the wrong
# question, matching legacy behavior).
try:
    from weather_collector.processors.cloud_saturation_correction import _FIELD_SKIP as RUNTIME_FIELD_SKIP
except Exception:
    RUNTIME_FIELD_SKIP = frozenset()

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = Path(__file__).resolve().parent / "output" / "h_lc_rolling_window.txt"

CLOUD_FIELDS = ["cc", "cl", "cm", "ch"]
BINS = [(0,5,"0-5"),(5,20,"5-20"),(20,50,"20-50"),(50,80,"50-80"),(80,95,"80-95"),(95,100.01,"95-100")]
MIN_N = 200
MAG_FLOOR_PP = 5.0
MAE_IMPROVE_FLOOR_PCT = 2.0

# Windows to sweep (days). None = full log.
WINDOWS = [3, 5, 7, 10, 14, 21, None]


def binof(v):
    for lo, hi, lab in BINS:
        if lo <= v < hi:
            return lab
    return None


def load_forecast(r):
    return r.get("forecast_l4") or r.get("forecast_l3") or r.get("forecast_l2") or r.get("forecast_l1")


def fit_pool(rows):
    """rows = [(fc, obs)] per (field, bin) → return {(field, bin): (shift, verdict)}"""
    pairs = defaultdict(list)
    for field, fc, obs in rows:
        b = binof(fc)
        if b is None: continue
        pairs[(field, b)].append((fc, obs))
    table = {}
    for k, ps in pairs.items():
        n = len(ps)
        if n < MIN_N:
            table[k] = (None, "thin")
            continue
        mean_bias = sum(fc-obs for fc,obs in ps) / n
        shift = -mean_bias
        mae_pre = sum(abs(fc-obs) for fc,obs in ps) / n
        mae_post = sum(abs(max(0.0, min(100.0, fc+shift))-obs) for fc,obs in ps) / n
        improve = 100.0 * (mae_pre-mae_post) / mae_pre if mae_pre > 0 else 0.0
        if abs(mean_bias) < MAG_FLOOR_PP:
            v = "SKIP-mag"
        elif improve < MAE_IMPROVE_FLOOR_PCT:
            v = "SKIP-Δ"
        else:
            v = "SHIP"
        table[k] = (shift, v)
    return table


def apply_and_score(rows, table):
    """rows = [(field, fc, obs)] → aggregate raw + corrected MAE per field."""
    per = defaultdict(lambda: {"n": 0, "raw": 0.0, "cor": 0.0})
    for field, fc, obs in rows:
        b = binof(fc)
        if b is None: continue
        cell = table.get((field, b))
        shift = cell[0] if (cell and cell[1] == "SHIP") else 0.0
        cor = max(0.0, min(100.0, fc + shift))
        d = per[field]
        d["n"] += 1
        d["raw"] += abs(fc - obs)
        d["cor"] += abs(cor - obs)
    return per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold-days", type=int, default=3, help="held-out tail (default 3d)")
    args = ap.parse_args()

    print(f"reading {URL}")
    rows = []
    with open(cached_path(URL), "rb") as fh:
        for line in fh:
            try: r = json.loads(line)
            except: continue
            if r.get("field") not in CLOUD_FIELDS: continue
            fc = load_forecast(r)
            obs = r.get("observed")
            if fc is None or obs is None: continue
            t = (r.get("obs_time") or "")[:10]
            if not t: continue
            rows.append((t, r["field"], float(fc), float(obs)))
    rows.sort()
    print(f"  rows: {len(rows):,}")

    t_max = rows[-1][0]
    max_dt = datetime.strptime(t_max, "%Y-%m-%d")
    hold_from = (max_dt - timedelta(days=args.hold_days - 1)).strftime("%Y-%m-%d")
    test_rows_all = [(f, fc, obs) for (t, f, fc, obs) in rows if t >= hold_from]
    test_days = sorted({t for (t, *_ ) in rows if t >= hold_from})
    print(f"  held-out: {len(test_rows_all):,} rows over {len(test_days)}d ({hold_from} → {t_max})")

    tables_by_w = {}
    results = []
    for W in WINDOWS:
        if W is None:
            train_from = "0000-00-00"
            label = "all"
        else:
            train_from_dt = max_dt - timedelta(days=args.hold_days + W - 1)
            train_from = train_from_dt.strftime("%Y-%m-%d")
            label = f"{W}d"
        train_rows = [(f, fc, obs) for (t, f, fc, obs) in rows
                      if train_from <= t < hold_from]
        table = fit_pool(train_rows)
        tables_by_w[label] = table
        per = apply_and_score(test_rows_all, table)
        n_ship = sum(1 for v in table.values() if v[1] == "SHIP")
        results.append((label, W, train_from, len(train_rows), n_ship, per))

    out = []
    def p(*a):
        line = " ".join(str(x) for x in a)
        print(line); out.append(line)

    active_fields = [f for f in CLOUD_FIELDS if f not in RUNTIME_FIELD_SKIP]
    skipped_fields = sorted(f for f in CLOUD_FIELDS if f in RUNTIME_FIELD_SKIP)

    p("=" * 100)
    p("h_lc_rolling_window — pool Lc held-out MAE across fit windows")
    p("=" * 100)
    p(f"held-out: {args.hold_days}d ({hold_from} → {t_max})")
    if skipped_fields:
        p(f"runtime _FIELD_SKIP (Lc is a no-op on these): {skipped_fields}")
        p(f"→ verdict computed over runtime-active fields: {active_fields}")
    else:
        p(f"runtime _FIELD_SKIP: (empty) — verdict spans all 4 fields")
    p()

    p(f"{'W':>5} {'train_from':<12} {'n_train':>9} {'nSHIP':>5} "
      f"{'cc raw→cor (Δ%)':>22} {'cl raw→cor (Δ%)':>22} {'cm raw→cor (Δ%)':>22} {'ch raw→cor (Δ%)':>22}")
    for label, W, train_from, n_train, n_ship, per in results:
        cells = [label, train_from, f"{n_train:,}", str(n_ship)]
        for field in CLOUD_FIELDS:
            f = per.get(field)
            if not f or f["n"] == 0:
                cells.append("n/a")
                continue
            raw = f["raw"] / f["n"]
            cor = f["cor"] / f["n"]
            imp = 100.0 * (raw - cor) / raw if raw > 0 else 0.0
            cells.append(f"{raw:5.2f}→{cor:5.2f} ({imp:+5.1f}%)")
        p(f"{cells[0]:>5} {cells[1]:<12} {cells[2]:>9} {cells[3]:>5} "
          f"{cells[4]:>22} {cells[5]:>22} {cells[6]:>22} {cells[7]:>22}")
    p()

    # Best window per field
    p("=" * 100)
    p("Best window per field (largest improve% on held-out):")
    p("=" * 100)
    for field in CLOUD_FIELDS:
        best = None
        for label, W, _, _, _, per in results:
            f = per.get(field)
            if not f or f["n"] == 0: continue
            raw = f["raw"] / f["n"]
            cor = f["cor"] / f["n"]
            imp = 100.0 * (raw - cor) / raw if raw > 0 else 0.0
            if best is None or imp > best[1]:
                best = (label, imp)
        if best:
            p(f"  {field}: W={best[0]:<5} improve={best[1]:+6.2f}%")
    p()

    # Shift comparison for a few interesting cells
    p("=" * 100)
    p("Shift comparison across windows — key cells:")
    p("=" * 100)
    interesting = [("cl","95-100"),("cl","80-95"),("cl","50-80"),("cl","20-50"),
                   ("cc","95-100"),("cc","80-95"),("cc","0-5"),
                   ("cm","95-100"),("cm","80-95"),("ch","95-100"),("ch","80-95")]
    p(f"{'field':<4} {'bin':<8}  " + "  ".join([f"W={w:>4}" for w in [str(w) if w else "all" for w in [3,5,7,10,14,21,None]]]))
    for field, b in interesting:
        cells = [field, b]
        for label in ["3d","5d","7d","10d","14d","21d","all"]:
            t = tables_by_w[label].get((field, b))
            if t is None or t[0] is None:
                cells.append("thin ")
            else:
                verd = "S" if t[1] == "SHIP" else ("m" if t[1]=="SKIP-mag" else ("d" if t[1]=="SKIP-Δ" else "?"))
                cells.append(f"{t[0]:+5.1f}{verd}")
        p(f"{cells[0]:<4} {cells[1]:<8}  " + "  ".join(f"{c:>7}" for c in cells[2:]))
    p("  (S = SHIP, m = SKIP-mag, d = SKIP-Δ)")
    p()

    # Verdict — computed over runtime-active fields only. If _FIELD_SKIP is
    # non-empty, verdict answers "shortest window all runtime-active fields
    # beat raw" rather than the full 4-field sweep. Additionally, verdict
    # requires the winning window to be within 1pp of best-per-field so a
    # "regressive win" (all fields positive but well below their per-field
    # best) doesn't get labelled SWITCH.
    p("=" * 100)
    if not active_fields:
        p("VERDICT: NULL — all cloud fields in runtime _FIELD_SKIP; sweep has no runtime effect.")
        p("=" * 100)
    else:
        # Best per-field improvement across all windows (for the regressive-win check)
        best_by_field = {}
        for field in active_fields:
            best = 0.0
            for _, _, _, _, _, per in results:
                f = per.get(field)
                if not f or f["n"] == 0: continue
                raw = f["raw"] / f["n"]
                cor = f["cor"] / f["n"]
                imp = 100.0 * (raw - cor) / raw if raw > 0 else 0.0
                if imp > best:
                    best = imp
            best_by_field[field] = best

        verdict = None
        regressive_win = None
        for label, W, _, _, _, per in results:
            all_good = True
            all_near_best = True
            for field in active_fields:
                f = per.get(field)
                if not f or f["n"] == 0:
                    all_good = False; break
                raw = f["raw"] / f["n"]
                cor = f["cor"] / f["n"]
                imp = 100.0 * (raw - cor) / raw if raw > 0 else 0.0
                if imp < 0:
                    all_good = False; break
                # Regressive-win guard: this window's improvement must be
                # within 5pp of the field's best across windows.
                if best_by_field[field] - imp > 5.0:
                    all_near_best = False
            if all_good and all_near_best and verdict is None:
                verdict = (label, W)
            if all_good and not all_near_best and regressive_win is None:
                regressive_win = (label, W, {
                    field: (
                        100.0 * (per[field]["raw"]/per[field]["n"] - per[field]["cor"]/per[field]["n"])
                        / (per[field]["raw"]/per[field]["n"])
                    ) if per.get(field) and per[field]["n"] > 0 else None
                    for field in active_fields
                })

        if verdict:
            p(f"VERDICT: SWITCH TO W={verdict[0]} — shortest window where all "
              f"runtime-active fields ({active_fields}) beat raw AND stay "
              f"within 5pp of best-per-field on held-out.")
        elif regressive_win:
            label, W, imps = regressive_win
            deltas = ", ".join(
                f"{f}={imps[f]:+.1f}% vs best {best_by_field[f]:+.1f}%"
                for f in active_fields if imps.get(f) is not None
            )
            p(f"VERDICT: HOLD — shortest all-positive window is W={label} but "
              f"regresses at least one runtime-active field vs best-per-field "
              f"by >5pp: {deltas}. Switching would hurt more than it helps.")
        else:
            p(f"VERDICT: NULL — no rolling window makes every runtime-active "
              f"field beat raw on held-out (active: {active_fields}).")
        p("=" * 100)

    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(out) + "\n")
    print(f"\nwrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Simpson-guard shadow measurement.

Reads `weather_collector/data/l1_selector_table_curated.json` for cells
tagged `simpson_guard_would_veto: True`, then re-scans the pair-log over
the last 7 days to compute pooled prod-MAE under two scenarios:

  · current  — pick per cell.source (what the runtime uses today)
  · guarded  — pick per cell.source_under_simpson_guard (what the guard
               would enforce)

Prod-MAE per side uses the same deepest-applied-layer walker as the fit
(`_hrrr_prod_error` / `_nbm_prod_error`). This is the honest counter-
factual: same rows, same pair-log, different L1 pick → different prod
row error.

Positive `delta_mae_pct` = guard would improve prod (guarded MAE lower).

Runtime pick_source is unaffected. This script only writes to
`analysis/output/simpson_guard_shadow.json` and publishes to GCS.

Runtime:
    python3 -m analysis.simpson_guard_shadow
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import pair_log_paths
from analysis.l1_selector_fit import (
    _band_for, _hrrr_prod_error, _nbm_prod_error, RECENT_WINDOW_DAYS,
)

CURATED_PATH = (Path(__file__).resolve().parent.parent
                / "weather_collector" / "data" / "l1_selector_table_curated.json")
OUT_PATH = Path(__file__).resolve().parent / "output" / "simpson_guard_shadow.json"

WINDOW_DAYS = RECENT_WINDOW_DAYS  # symmetric to the override's own eval window


def _pick_source_error(pick, row, field):
    if pick == "nbm":
        return _nbm_prod_error(row)
    return _hrrr_prod_error(row, field)


def main():
    with open(CURATED_PATH) as f:
        curated = json.load(f)

    # Gather the vetoed cells + their two candidate picks.
    vetoed = []
    table = curated.get("table", {})
    for field, bands in table.items():
        for band, cell in (bands or {}).items():
            if not cell.get("simpson_guard_would_veto"):
                continue
            vetoed.append({
                "field": field, "band": band,
                "source_current": cell.get("source"),
                "source_guarded": cell.get("source_under_simpson_guard"),
                "override_reason": cell.get("override_reason"),
                "simpson_guard_note": cell.get("simpson_guard_note"),
            })

    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    window_start = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M")

    # Accumulator per (field, band): abs error sums + n for current + guarded.
    acc = defaultdict(lambda: {
        "current_abs": 0.0, "current_n": 0,
        "guarded_abs": 0.0, "guarded_n": 0,
        "hrrr_abs": 0.0, "hrrr_n": 0,
        "nbm_abs":  0.0, "nbm_n":  0,
        "paired_n": 0,
    })
    target_keys = {(v["field"], v["band"]): v for v in vetoed}

    n_in = 0
    n_kept = 0
    for path in pair_log_paths():
        with open(path) as fin:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                n_in += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                field = row.get("field")
                if field is None:
                    continue
                lead_h = row.get("lead_h")
                band = _band_for(lead_h)
                if band is None:
                    continue
                key = (field, band)
                if key not in target_keys:
                    continue
                obs_time = row.get("obs_time", "")
                if obs_time < window_start:
                    continue
                n_kept += 1
                h = _hrrr_prod_error(row, field)
                n = _nbm_prod_error(row)
                if h is not None:
                    acc[key]["hrrr_abs"] += h; acc[key]["hrrr_n"] += 1
                if n is not None:
                    acc[key]["nbm_abs"] += n; acc[key]["nbm_n"] += 1
                if h is not None and n is not None:
                    acc[key]["paired_n"] += 1
                v = target_keys[key]
                e_cur = _pick_source_error(v["source_current"], row, field)
                e_grd = _pick_source_error(v["source_guarded"], row, field)
                if e_cur is not None:
                    acc[key]["current_abs"] += e_cur; acc[key]["current_n"] += 1
                if e_grd is not None:
                    acc[key]["guarded_abs"] += e_grd; acc[key]["guarded_n"] += 1

    # Emit per-cell shadow rows.
    cell_rows = []
    for v in vetoed:
        key = (v["field"], v["band"])
        b = acc.get(key) or {}
        cur_mae = (b["current_abs"] / b["current_n"]) if b.get("current_n") else None
        grd_mae = (b["guarded_abs"] / b["guarded_n"]) if b.get("guarded_n") else None
        hrrr_mae = (b["hrrr_abs"] / b["hrrr_n"]) if b.get("hrrr_n") else None
        nbm_mae  = (b["nbm_abs"]  / b["nbm_n"])  if b.get("nbm_n")  else None
        delta_pct = None
        if cur_mae is not None and grd_mae is not None and cur_mae > 0:
            delta_pct = 100.0 * (cur_mae - grd_mae) / cur_mae
        cell_rows.append({
            "field": v["field"], "band": v["band"],
            "source_current": v["source_current"],
            "source_guarded": v["source_guarded"],
            "current_mae_7d": round(cur_mae, 4) if cur_mae is not None else None,
            "guarded_mae_7d": round(grd_mae, 4) if grd_mae is not None else None,
            "delta_mae_pct":  round(delta_pct, 2) if delta_pct is not None else None,
            "hrrr_mae_7d":    round(hrrr_mae, 4) if hrrr_mae is not None else None,
            "nbm_mae_7d":     round(nbm_mae,  4) if nbm_mae  is not None else None,
            "n_current":      b.get("current_n", 0),
            "n_guarded":      b.get("guarded_n", 0),
            "n_paired":       b.get("paired_n", 0),
            "override_reason": v["override_reason"],
            "simpson_guard_note": v["simpson_guard_note"],
        })

    # Aggregate row-weighted delta across all vetoed cells.
    tot_cur_abs = sum((r["current_mae_7d"] or 0.0) * r["n_current"] for r in cell_rows)
    tot_grd_abs = sum((r["guarded_mae_7d"] or 0.0) * r["n_guarded"] for r in cell_rows)
    tot_cur_n = sum(r["n_current"] for r in cell_rows)
    tot_grd_n = sum(r["n_guarded"] for r in cell_rows)
    pooled_cur_mae = (tot_cur_abs / tot_cur_n) if tot_cur_n else None
    pooled_grd_mae = (tot_grd_abs / tot_grd_n) if tot_grd_n else None
    pooled_delta_pct = None
    if pooled_cur_mae is not None and pooled_grd_mae is not None and pooled_cur_mae > 0:
        pooled_delta_pct = 100.0 * (pooled_cur_mae - pooled_grd_mae) / pooled_cur_mae

    payload = {
        "generated_at": now.isoformat() + "Z",
        "source": "analysis/simpson_guard_shadow.py",
        "curated_table_fitted_at": curated.get("fitted_at"),
        "window_days": WINDOW_DAYS,
        "n_vetoed_cells": len(vetoed),
        "n_rows_scanned": n_in,
        "n_rows_kept_in_target_cells": n_kept,
        "pooled_across_vetoed": {
            "current_mae_7d": round(pooled_cur_mae, 4) if pooled_cur_mae is not None else None,
            "guarded_mae_7d": round(pooled_grd_mae, 4) if pooled_grd_mae is not None else None,
            "delta_mae_pct":  round(pooled_delta_pct, 2) if pooled_delta_pct is not None else None,
            "n_current": tot_cur_n, "n_guarded": tot_grd_n,
            "conventions": "positive delta_mae_pct = guarded MAE lower than current = Simpson guard would improve prod",
        },
        "cells": cell_rows,
        "runtime_effect": "none (shadow only) — pick_source still uses cell.source",
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as fout:
        json.dump(payload, fout, indent=2)
        fout.write("\n")
    print(f"wrote {OUT_PATH} ({os.path.getsize(OUT_PATH) / 1024:.1f} KB)")

    try:
        from weather_collector.gcs_io import upload_json  # noqa: E402
        upload_json(payload, "simpson_guard_shadow.json", "simpson_guard_shadow.json")
        print("  ✓ Published to gs://myweather-data/simpson_guard_shadow.json")
    except Exception as e:
        print(f"  ⚠ GCS upload skipped ({type(e).__name__}: {e}) — local file still written")

    print()
    print("=" * 96)
    print(f"Simpson-guard shadow — {WINDOW_DAYS}d window · {len(vetoed)} vetoed cells")
    print("=" * 96)
    print(f"{'cell':<12} {'cur':<5} {'grd':<5} "
          f"{'cur MAE':>9} {'grd MAE':>9} {'Δ%':>7} "
          f"{'hrrr':>9} {'nbm':>9} {'n':>6}")
    for r in cell_rows:
        def f(x, w=9, dp=3):
            return "—".rjust(w) if x is None else f"{x:.{dp}f}".rjust(w)
        def p(x, w=7):
            return "—".rjust(w) if x is None else f"{x:+.1f}%".rjust(w)
        print(f"{r['field']+'/'+r['band']:<12} "
              f"{r['source_current']:<5} {r['source_guarded']:<5} "
              f"{f(r['current_mae_7d'])} {f(r['guarded_mae_7d'])} {p(r['delta_mae_pct'])} "
              f"{f(r['hrrr_mae_7d'])} {f(r['nbm_mae_7d'])} {r['n_paired']:>6}")
    print("-" * 96)
    pd = payload["pooled_across_vetoed"]
    def f(x, w=9): return "—".rjust(w) if x is None else f"{x:.3f}".rjust(w)
    def p(x, w=7): return "—".rjust(w) if x is None else f"{x:+.1f}%".rjust(w)
    print(f"{'POOLED':<12} {'':<5} {'':<5} "
          f"{f(pd['current_mae_7d'])} {f(pd['guarded_mae_7d'])} {p(pd['delta_mae_pct'])}")
    print("=" * 96)
    print("Positive Δ% = guard would improve prod. Runtime unaffected (SHADOW).")


if __name__ == "__main__":
    main()

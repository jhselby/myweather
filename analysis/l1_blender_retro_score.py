"""Retro shadow-scoring for the L1 blender.

Companion to `l1_blender_shadow_verify.py`. Where shadow_verify reads live
`blend_shadow` stamps from the pair log (needs post-v0.7.0 rows only), this
tool RECONSTRUCTS ω from the curated table's stored ridge coefficients on
ANY historical pair-log row — including months predating the ship.

That collapses the "wait 7-30 days for shadow to accumulate" cycle to
seconds. Two uses:

  1. Backfill confirmation for cells that shipped shadow-only. When
     shadow_verify says THIN (n_7d < 50), retro can score 30-90 days of
     historical rows in the same window shape and give an early read.
     If retro halves-stable lift agrees with the stage1 fitter's held-out
     numbers, that's independent walk-forward evidence and can shorten
     the flip gate.

  2. Pre-ship validation of candidate cells. Point at a Stage 1 output
     (`analysis/output/l1_blender_stage1_{field}.json`) instead of the
     curated file; score its `cells[]` on the pair log; see which cells
     that Stage 1 called STABLE also survive retro on a longer window
     than the two 25%-quartile test halves stage1 uses.

The retro score is NOT a substitute for live shadow — the pair log's
selector routing changes over time, and old rows may have been served by
different upstream layers than what runs today. But it's a fast,
directionally-honest independent check.

Reads:
  - pair log via `_cache.cached_path`
  - curated table (default) OR a Stage 1 output (`--stage1 PATH`)

Emits:
  analysis/output/l1_blender_retro_score.txt
  analysis/output/l1_blender_retro_score.json

CLI:
  python3 analysis/l1_blender_retro_score.py
  python3 analysis/l1_blender_retro_score.py --since 2026-07-01
  python3 analysis/l1_blender_retro_score.py --stage1 analysis/output/l1_blender_stage1_dp.json
"""
import argparse, json, math, os, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CURATED_PATH = REPO / "weather_collector" / "data" / "l1_blender_curated.json"
PAIR_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"
OUT_TXT = HERE / "output" / "l1_blender_retro_score.txt"
OUT_JSON = HERE / "output" / "l1_blender_retro_score.json"

BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]

# HRRR / NBM terminal selection — MUST match l1_blender_stage1.py exactly, or
# retro reconstructs a different blend than the one that was fit / would run.
HRRR_TERMINAL = {"ch": "forecast_l6", "t": "forecast_l6",
                 "sr": "forecast_l5",
                 "dp": "forecast_l4", "h": "forecast_l4", "wg": "forecast_l4"}
HRRR_FALLBACK = ["forecast_l6", "forecast_l5", "forecast_l4", "forecast_l3", "forecast_l2"]
NBM_FALLBACK = ["forecast_l3_nbm", "forecast_l2_nbm", "forecast_raw_nbm"]

# Feature vector order — MUST match l1_blender_stage1.py FEATURE_NAMES.
# Any drift here silently mis-scores every cell.
FEATURE_NAMES = [
    "ims", "xr_spread", "lead_h",
    "sin_hod", "cos_hod",
    "cc_inter_sigma", "pressure_trend",
    "wd_sin", "wd_cos",
    "ws_fc", "cloud_low_fc", "solar_wm2_fc",
]

MIN_N_CELL_REPORT = 30   # skip cells with fewer than this many rows in window


def _band_for(lead_h):
    for name, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return name
    return None


def _hour_local(t):
    try: return int(t[11:13])
    except (TypeError, ValueError, IndexError): return 12


def _get_hrrr(r, field):
    v = r.get(HRRR_TERMINAL.get(field, "forecast_l4"))
    if v is not None: return v
    for k in HRRR_FALLBACK:
        v = r.get(k)
        if v is not None: return v
    return None


def _get_nbm(r):
    for k in NBM_FALLBACK:
        v = r.get(k)
        if v is not None: return v
    return None


def _extract_features(r, xr_spread, lead):
    """Same feature build as l1_blender_stage1._load_cells inner loop. If any
    required piece is missing, return None so caller skips the row."""
    sfc = r.get("state_fc") or {}
    if not sfc.get("regime_synoptic"):
        return None
    cc_sigma = float(r.get("cloud_inter_source_sigma") or 0.0)
    p_trend = float(sfc.get("pressure_trend_hpa_3h") or 0.0)
    hh = _hour_local(r.get("obs_time", ""))
    wd = sfc.get("wind_dir")
    wd_sin = math.sin(math.radians(float(wd))) if wd is not None else 0.0
    wd_cos = math.cos(math.radians(float(wd))) if wd is not None else 0.0
    ws_fc = float(sfc.get("wind_speed") or 0.0)
    cloud_low_fc = float(sfc.get("cloud_low") or 0.0)
    solar_fc = float(sfc.get("solar_wm2") or 0.0)
    fc_h = _get_hrrr(r, r.get("field")); fc_n = _get_nbm(r)
    if fc_h is None or fc_n is None:
        return None
    ims = abs(float(fc_h) - float(fc_n))
    return [ims, float(xr_spread), float(lead),
            math.sin(2*math.pi*hh/24.0), math.cos(2*math.pi*hh/24.0),
            cc_sigma, p_trend, wd_sin, wd_cos, ws_fc, cloud_low_fc, solar_fc]


def _parse_time(ts):
    if not ts: return None
    ts = ts.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try: return datetime.strptime(ts[:19], fmt)
        except ValueError: continue
    return None


def _load_cells_from_curated(path):
    """Return list of (field, regime, band, beta, mu, sd) tuples."""
    with open(path) as fh:
        d = json.load(fh)
    out = []
    for c in d.get("cells", []):
        out.append((c["field"], c["regime"], c["band"],
                    np.array(c["beta"], dtype=float),
                    np.array(c["mu"], dtype=float),
                    np.array(c["sd"], dtype=float)))
    return out


def _load_cells_from_stage1(path):
    """A Stage 1 output has field top-level and cells[] with coefficients."""
    with open(path) as fh:
        d = json.load(fh)
    field = d["field"]
    out = []
    for c in d.get("cells", []):
        coef = c.get("coefficients") or {}
        if "beta" not in coef: continue
        out.append((field, c["regime"], c["band"],
                    np.array(coef["beta"], dtype=float),
                    np.array(coef["mu"], dtype=float),
                    np.array(coef["sd"], dtype=float)))
    return out


def _predict_omega(x, beta, mu, sd):
    z = (np.array(x, dtype=float) - mu) / sd
    z[~np.isfinite(z)] = 0.0
    v = float(beta[0] + np.dot(beta[1:], z))
    if v < 0.0: return 0.0
    if v > 1.0: return 1.0
    return v


def _scan(cells, since, until, verbose):
    """One pass over the pair log. Groups rows by cell then computes ω and
    blend forecast per row. Returns {(field, regime, band): [row_dict, ...]}."""
    by_field = defaultdict(list)
    coefs = {}
    for f, r, b, beta, mu, sd in cells:
        coefs[(f, r, b)] = (beta, mu, sd)
        by_field[f].append((r, b))

    # First pass: gather xr_spread per valid_time per field (variance across
    # ensemble members / re-runs for the same valid_time). Same shape as
    # stage1.load_cells uses.
    fc_by_vtfield = defaultdict(list)
    path = cached_path(PAIR_URL)
    with open(path) as fh:
        for line in fh:
            try: r = json.loads(line)
            except Exception: continue
            fld = r.get("field")
            if fld not in by_field: continue
            vt, fc = r.get("valid_time"), r.get("forecast")
            if vt is not None and fc is not None:
                try: fc_by_vtfield[(fld, vt)].append(float(fc))
                except (TypeError, ValueError): pass
    vt_spread = {k: max(v) - min(v) for k, v in fc_by_vtfield.items() if len(v) >= 2}
    if verbose:
        print(f"  built vt_spread over {len(vt_spread):,} (field, valid_time) keys")

    # Second pass: score each row against its cell (if any)
    out = defaultdict(list)
    n_scanned = 0
    n_scored = 0
    n_no_regime = 0
    n_no_terminal = 0
    n_no_spread = 0
    n_out_of_window = 0
    with open(path) as fh:
        for line in fh:
            try: r = json.loads(line)
            except Exception: continue
            n_scanned += 1
            fld = r.get("field")
            if fld not in by_field: continue
            lead = r.get("lead_h")
            if lead is None: continue
            band = _band_for(int(lead))
            if band is None: continue
            regime = (r.get("state_fc") or {}).get("regime_synoptic")
            if not regime:
                n_no_regime += 1; continue
            key = (fld, regime, band)
            if key not in coefs: continue
            obs_t = _parse_time(r.get("obs_time")) or _parse_time(r.get("valid_time"))
            if obs_t is None: continue
            if since and obs_t < since: n_out_of_window += 1; continue
            if until and obs_t >= until: n_out_of_window += 1; continue
            xr = vt_spread.get((fld, r.get("valid_time")))
            if xr is None:
                n_no_spread += 1; continue
            x = _extract_features(r, xr, lead)
            if x is None:
                n_no_terminal += 1; continue
            fc_h = float(_get_hrrr(r, fld))
            fc_n = float(_get_nbm(r))
            obs = r.get("observed")
            if obs is None: continue
            try: obs = float(obs)
            except (TypeError, ValueError): continue
            beta, mu, sd = coefs[key]
            w = _predict_omega(x, beta, mu, sd)
            blend = w * fc_h + (1 - w) * fc_n
            served = r.get("forecast")
            served_err = None
            if served is not None:
                try: served_err = float(served) - obs
                except (TypeError, ValueError): pass
            out[key].append({
                "obs_time": obs_t,
                "omega": w,
                "blend_err": blend - obs,
                "hrrr_err": fc_h - obs,
                "nbm_err": fc_n - obs,
                "served_err": served_err,
            })
            n_scored += 1

    if verbose:
        print(f"  scanned {n_scanned:,} pair rows · scored {n_scored:,}")
        if n_no_regime: print(f"  skipped {n_no_regime:,} rows: no regime_synoptic in state_fc")
        if n_no_terminal: print(f"  skipped {n_no_terminal:,} rows: missing HRRR/NBM terminal")
        if n_no_spread: print(f"  skipped {n_no_spread:,} rows: no cross-run spread pair")
        if n_out_of_window: print(f"  skipped {n_out_of_window:,} rows: outside window")
    return out


def _mae(errs):
    errs = [e for e in errs if e is not None]
    if not errs: return None
    return sum(abs(e) for e in errs) / len(errs)


def _pct_lift(base, alt):
    if base is None or alt is None or base <= 0: return None
    return 100.0 * (base - alt) / base


def _score_rows(rows):
    """Whole-window stats plus halves-stable A/B split."""
    if not rows:
        return {"n": 0}
    rows = sorted(rows, key=lambda r: r["obs_time"])
    mid = len(rows) // 2
    halves = [rows[:mid], rows[mid:]] if mid >= 5 else [None, None]

    def _stats(rs):
        if not rs: return None
        blend = _mae([r["blend_err"] for r in rs])
        hrrr = _mae([r["hrrr_err"] for r in rs])
        nbm = _mae([r["nbm_err"] for r in rs])
        served = _mae([r["served_err"] for r in rs])
        best = min([m for m in (hrrr, nbm) if m is not None], default=None)
        omegas = [r["omega"] for r in rs]
        return {
            "n": len(rs),
            "blend_mae": blend, "hrrr_mae": hrrr, "nbm_mae": nbm,
            "served_mae": served, "best_single_mae": best,
            "lift_vs_served_pct": _pct_lift(served, blend),
            "lift_vs_best_pct": _pct_lift(best, blend),
            "lift_vs_hrrr_pct": _pct_lift(hrrr, blend),
            "lift_vs_nbm_pct": _pct_lift(nbm, blend),
            "omega_mean": sum(omegas) / len(omegas) if omegas else None,
        }

    out = {"n": len(rows), "pooled": _stats(rows)}
    out["half_A"] = _stats(halves[0])
    out["half_B"] = _stats(halves[1])
    if out["half_A"] and out["half_B"]:
        a, b = out["half_A"]["lift_vs_best_pct"], out["half_B"]["lift_vs_best_pct"]
        if a is not None and b is not None:
            out["halves_stable"] = (a > 0) == (b > 0)
        else:
            out["halves_stable"] = None
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage1", help="Score a Stage 1 output file instead of the curated table")
    p.add_argument("--since", help="Only include obs_time >= YYYY-MM-DD")
    p.add_argument("--until", help="Only include obs_time < YYYY-MM-DD")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    if args.stage1:
        cells = _load_cells_from_stage1(args.stage1)
        src = args.stage1
    else:
        cells = _load_cells_from_curated(CURATED_PATH)
        src = str(CURATED_PATH)
    if not cells:
        print(f"no cells with coefficients in {src}"); return
    print(f"Loaded {len(cells)} cells from {src}")

    since = datetime.strptime(args.since, "%Y-%m-%d") if args.since else None
    until = datetime.strptime(args.until, "%Y-%m-%d") if args.until else None

    scored = _scan(cells, since, until, args.verbose)

    hdr = (f"{'field':<5}{'regime':<14}{'band':<8}"
           f"{'n':>6}{'ω̄':>7}  "
           f"{'served':>8}{'blend':>8}"
           f"{'lift_v_served':>14}{'lift_v_best':>12}  "
           f"{'lift_A':>8}{'lift_B':>8}  halves")
    print("\n" + "=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))

    rows_out = []
    n_stable = n_pos = n_neg = n_thin = 0
    for f, r, b, *_ in cells:
        key = (f, r, b)
        s = _score_rows(scored.get(key, []))
        if s["n"] < MIN_N_CELL_REPORT:
            n_thin += 1
            print(f"{f:<5}{r:<14}{b:<8}{s['n']:>6}"
                  f"{'—':>7}  {'—':>8}{'—':>8}{'—':>14}{'—':>12}  {'—':>8}{'—':>8}  THIN")
            rows_out.append({"field": f, "regime": r, "band": b, "n": s["n"], "verdict": "THIN"})
            continue
        pooled = s["pooled"]
        lift_v_served = pooled["lift_vs_served_pct"]
        lift_v_best = pooled["lift_vs_best_pct"]
        a = s["half_A"]["lift_vs_best_pct"] if s["half_A"] else None
        b_ = s["half_B"]["lift_vs_best_pct"] if s["half_B"] else None
        hs = s.get("halves_stable")
        if lift_v_best is None:
            vd = "THIN"
        elif hs and lift_v_best > 0 and lift_v_served and lift_v_served > 0:
            vd = "STABLE"
            n_stable += 1
        elif lift_v_best > 0:
            vd = "POS-UNSTABLE"
            n_pos += 1
        else:
            vd = "NEG"
            n_neg += 1
        print(f"{f:<5}{r:<14}{b:<8}{s['n']:>6}"
              f"{(pooled['omega_mean'] or 0):>7.2f}  "
              f"{(pooled['served_mae'] or 0):>8.2f}"
              f"{(pooled['blend_mae'] or 0):>8.2f}"
              f"{(lift_v_served if lift_v_served is not None else 0):>+13.2f}%"
              f"{(lift_v_best if lift_v_best is not None else 0):>+11.2f}%  "
              f"{(a if a is not None else 0):>+7.2f}%"
              f"{(b_ if b_ is not None else 0):>+7.2f}%  "
              f"{'✓' if hs else ('✗' if hs is False else '?')}  {vd}")
        rows_out.append({
            "field": f, "regime": r, "band": b, "n": s["n"], "verdict": vd,
            "omega_mean_pooled": pooled["omega_mean"],
            "pooled": pooled, "half_A": s["half_A"], "half_B": s["half_B"],
            "halves_stable": hs,
        })
    print("=" * len(hdr))
    summary = (f"Retro score: {n_stable} STABLE / {n_pos} POS-UNSTABLE / "
               f"{n_neg} NEG / {n_thin} THIN (of {len(cells)} cells)")
    print(summary)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": src,
        "window_since": args.since,
        "window_until": args.until,
        "min_n_cell_report": MIN_N_CELL_REPORT,
        "cells": rows_out,
    }
    with open(OUT_JSON, "w") as fh: json.dump(payload, fh, indent=2, default=str)
    with open(OUT_TXT, "w") as fh:
        fh.write(summary + "\n")
        fh.write(f"Source: {src}\n")
        fh.write(f"Window: since={args.since} until={args.until}\n")
    print(f"\nwrote {OUT_JSON}")
    print(f"wrote {OUT_TXT}")


if __name__ == "__main__":
    main()

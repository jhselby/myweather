"""Shadow-verify — per curated cell, is the blender's shadow forecast beating
what the selector actually served? This is the flip gate for v0.7.0 and,
post-flip, the kill sentry.

Reads:
  - pair log (forecast_error_log_backstamped.jsonl on GCS via _cache)
    for rows carrying blend_shadow / blend_omega_shadow
  - the curated blender table (weather_collector/data/l1_blender_curated.json)
    for the SHIP-target cells + training ω̄ per cell for drift detection

Per curated cell, over rolling 7d and 30d windows:
  n_fires             — rows where blender actually stamped
  blend_MAE           — MAE of forecast_blend against observed
  hrrr_MAE / nbm_MAE  — single-source baselines
  served_MAE          — MAE of what the selector actually shipped (pair["forecast"])
  lift_vs_served_pct  — 100 · (served_MAE − blend_MAE) / served_MAE
  ω_mean_live / std   — live blend-weight distribution
  ω_drift             — |ω_mean_live − ω_mean_train|

Verdict per cell:
  SHIP-READY  — 7d n_fires ≥ MIN_N, blend beats served ≥ MIN_LIFT_PCT,
                ω drift ≤ OMEGA_DRIFT_TOL, no crashes
  HOLD        — insufficient fires, or lift positive but under threshold
  KILL        — 7d lift ≤ NEG_KILL_PCT (blend hurts materially)
  THIN        — 0 fires (regime hasn't matched any curated cell)

Rollup line for the executive summary:
  l1_blender_shadow_verify — Verdict: N ship-ready / M hold / K kill / T thin

Run:
    python3 analysis/l1_blender_shadow_verify.py
Emits:
    analysis/output/l1_blender_shadow_verify.txt
    analysis/output/l1_blender_shadow_verify.json
"""
import json, os, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CURATED_PATH = REPO / "weather_collector" / "data" / "l1_blender_curated.json"
PAIR_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"
OUT_TXT = HERE / "output" / "l1_blender_shadow_verify.txt"
OUT_JSON = HERE / "output" / "l1_blender_shadow_verify.json"

BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]

# Verdict thresholds
MIN_N_FIRES_7D = 50
MIN_LIFT_PCT = 3.0
NEG_KILL_PCT = -3.0
OMEGA_DRIFT_TOL = 0.20   # slightly looser than Stage 1's 0.15 — live sample noisier


def _band_for(lead_h):
    for name, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return name
    return None


def load_curated():
    with open(CURATED_PATH) as fh:
        data = json.load(fh)
    cells = {}
    for c in data.get("cells", []):
        key = (c["field"], c["regime"], c["band"])
        cells[key] = {
            "omega_mean_train": c.get("omega_mean_train"),
            "test_lift_A": c.get("test_lift_vs_best_A"),
            "test_lift_B": c.get("test_lift_vs_best_B"),
        }
    return cells


def parse_time(ts):
    """obs_time like '2026-09-23T14:00:00Z' or '2026-09-23T14:00' → naive UTC dt."""
    if not ts: return None
    ts = ts.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try: return datetime.strptime(ts[:19], fmt)
        except ValueError: continue
    return None


def scan_pair_log(curated_keys):
    """Yield rows with blend_shadow, keyed to curated cells."""
    path = cached_path(PAIR_URL)
    with open(path) as fh:
        for line in fh:
            try: r = json.loads(line)
            except Exception: continue
            blend_fc = r.get("blend_shadow")
            if blend_fc is None: continue
            fld = r.get("field")
            lh = r.get("lead_h")
            if fld is None or lh is None: continue
            band = _band_for(int(lh))
            if band is None: continue
            regime = (r.get("state_fc") or {}).get("regime_synoptic")
            key = (fld, regime, band)
            if key not in curated_keys: continue
            yield key, r


def mae(errs):
    if not errs: return None
    return sum(abs(e) for e in errs) / len(errs)


def score_window(rows):
    """Given rows in a window for one cell, return per-window stats."""
    if not rows:
        return {"n": 0}
    served_errs = [r["error"] for r in rows if r.get("error") is not None]
    hrrr_errs = []
    nbm_errs = []
    blend_errs = []
    omegas = []
    for r in rows:
        obs = r.get("observed")
        if obs is None: continue
        try: obs = float(obs)
        except (TypeError, ValueError): continue
        # HRRR terminal: try l6, l5, l4 fallback
        for k in ("forecast_l6", "forecast_l5", "forecast_l4"):
            v = r.get(k)
            if v is not None:
                hrrr_errs.append(float(v) - obs); break
        # NBM terminal: l3_nbm, l2_nbm, raw_nbm
        for k in ("forecast_l3_nbm", "forecast_l2_nbm", "forecast_raw_nbm"):
            v = r.get(k)
            if v is not None:
                nbm_errs.append(float(v) - obs); break
        bv = r.get("forecast_blend") or r.get("blend_shadow")
        if bv is not None:
            blend_errs.append(float(bv) - obs)
        om = r.get("blend_omega_shadow")
        if om is not None:
            omegas.append(float(om))
    served_mae = mae(served_errs)
    blend_mae = mae(blend_errs)
    hrrr_mae = mae(hrrr_errs)
    nbm_mae = mae(nbm_errs)
    lift_vs_served = None
    if served_mae and served_mae > 0 and blend_mae is not None:
        lift_vs_served = 100 * (served_mae - blend_mae) / served_mae
    return {
        "n": len(rows),
        "served_mae": served_mae,
        "blend_mae": blend_mae,
        "hrrr_mae": hrrr_mae,
        "nbm_mae": nbm_mae,
        "lift_vs_served_pct": lift_vs_served,
        "omega_mean": (sum(omegas)/len(omegas)) if omegas else None,
        "omega_std": (
            (sum((x - sum(omegas)/len(omegas))**2 for x in omegas)/len(omegas))**0.5
            if len(omegas) > 1 else None
        ),
    }


def verdict_for(cell_stats7, cell_stats30, train_omega):
    n7 = cell_stats7.get("n", 0)
    lift7 = cell_stats7.get("lift_vs_served_pct")
    om_live = cell_stats7.get("omega_mean")
    if n7 == 0:
        return "THIN"
    if lift7 is not None and lift7 <= NEG_KILL_PCT and n7 >= MIN_N_FIRES_7D:
        return "KILL"
    if n7 < MIN_N_FIRES_7D:
        return "HOLD"
    if lift7 is None or lift7 < MIN_LIFT_PCT:
        return "HOLD"
    if train_omega is not None and om_live is not None:
        if abs(om_live - train_omega) > OMEGA_DRIFT_TOL:
            return "HOLD"
    return "SHIP-READY"


def main():
    curated = load_curated()
    if not curated:
        print("no curated cells — nothing to verify")
        return
    print(f"Loaded {len(curated)} curated cells.")

    # Bucket pair-log rows by cell + window (7d, 30d)
    now = datetime.utcnow()
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)
    by_cell_7d = defaultdict(list)
    by_cell_30d = defaultdict(list)

    n_scanned = 0
    for key, row in scan_pair_log(set(curated.keys())):
        n_scanned += 1
        obs_t = parse_time(row.get("obs_time")) or parse_time(row.get("valid_time"))
        if obs_t is None: continue
        if obs_t >= cutoff_30d:
            by_cell_30d[key].append(row)
            if obs_t >= cutoff_7d:
                by_cell_7d[key].append(row)

    print(f"Scanned {n_scanned:,} blend-shadow-stamped rows total; "
          f"{sum(len(v) for v in by_cell_7d.values())} in last 7d, "
          f"{sum(len(v) for v in by_cell_30d.values())} in last 30d.")

    out_rows = []
    header = (f"{'field':<5}{'regime':<14}{'band':<8}"
              f"{'n7':>5}{'n30':>6}  "
              f"{'served':>8}{'blend':>8}{'lift%':>7}  "
              f"{'ω_live':>7}{'ω_tr':>6}{'Δω':>7}  verdict")
    print("\n" + "=" * len(header))
    print(header)
    print("-" * len(header))

    tally = {"SHIP-READY": 0, "HOLD": 0, "KILL": 0, "THIN": 0}
    for key in sorted(curated.keys()):
        f_, r_, b_ = key
        s7 = score_window(by_cell_7d.get(key, []))
        s30 = score_window(by_cell_30d.get(key, []))
        train_om = curated[key].get("omega_mean_train")
        v = verdict_for(s7, s30, train_om)
        tally[v] += 1
        om_live = s7.get("omega_mean")
        d_om = (abs(om_live - train_om) if (om_live is not None and train_om is not None) else None)
        print(f"{f_:<5}{r_:<14}{b_:<8}"
              f"{s7.get('n',0):>5}{s30.get('n',0):>6}  "
              f"{(s7.get('served_mae') or 0):>8.3f}"
              f"{(s7.get('blend_mae') or 0):>8.3f}"
              f"{(s7.get('lift_vs_served_pct') or 0):>+7.2f}  "
              f"{(om_live if om_live is not None else 0):>7.2f}"
              f"{(train_om if train_om is not None else 0):>6.2f}"
              f"{(d_om if d_om is not None else 0):>+7.2f}  "
              f"{v}")
        out_rows.append({
            "field": f_, "regime": r_, "band": b_,
            "verdict": v,
            "n_7d": s7.get("n"), "n_30d": s30.get("n"),
            "served_mae_7d": s7.get("served_mae"),
            "blend_mae_7d": s7.get("blend_mae"),
            "hrrr_mae_7d": s7.get("hrrr_mae"),
            "nbm_mae_7d": s7.get("nbm_mae"),
            "lift_vs_served_pct_7d": s7.get("lift_vs_served_pct"),
            "omega_mean_live_7d": om_live,
            "omega_mean_train": train_om,
            "omega_drift_7d": d_om,
            "n_30d_fires": s30.get("n"),
            "lift_vs_served_pct_30d": s30.get("lift_vs_served_pct"),
        })

    print("=" * len(header))
    summary = (f"Verdict: {tally['SHIP-READY']} SHIP-READY / "
               f"{tally['HOLD']} HOLD / {tally['KILL']} KILL / {tally['THIN']} THIN "
               f"(of {len(curated)} curated cells)")
    print(summary)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as fh:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "min_n_fires_7d": MIN_N_FIRES_7D,
            "min_lift_pct": MIN_LIFT_PCT,
            "neg_kill_pct": NEG_KILL_PCT,
            "omega_drift_tol": OMEGA_DRIFT_TOL,
            "tally": tally,
            "cells": out_rows,
        }, fh, indent=2)
    with open(OUT_TXT, "w") as fh:
        fh.write(summary + "\n")
        fh.write(f"Cells: {len(curated)} curated\n")
        fh.write(f"Scanned: {n_scanned} blend-shadow rows total\n")
    print(f"\nwrote {OUT_JSON}")
    print(f"wrote {OUT_TXT}")


if __name__ == "__main__":
    main()

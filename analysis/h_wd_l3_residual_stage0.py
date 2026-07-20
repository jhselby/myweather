"""Stage 0 — wd L3 residual per (regime × lead_band).

Circular analogue of [[h_daily_residual_persistence]]-style residual analysis,
narrowed to the L3 cell shape (regime_synoptic × lead_band).

Question: does a per-cell circular-mean residual (obs − L2_wd), applied on top
of L2 held-out, reduce wd MAE by ≥ 1% in any cell?

Baseline: forecast_l2 (per [[measure-against-live-stack-baseline]]).
Cells:    (regime_synoptic × lead_band) — same shape as [[project_wd_l3_l4_circular]].
Signal:   circular mean of angular residual in the cell over training window.
Apply:    corrected_fc = (fc_l2 + mean_residual) mod 360, held-out.
MAE:      mean |circular_diff(corrected, obs)|.

Gates:
  MIN_N_CELL = 30            — need at least this many training pairs per cell
  MIN_TEST_PER_CELL = 20     — held-out sample per cell
  STAGE0_HIT_PCT = 1.0       — ≥ 1% MAE improvement on any cell

Because wd L2 shipped 07-20 v0.6.368/368a, `forecast_l2` for wd only exists in
post-ship pairs. Until roughly 07-27 (7 days of pairs) most cells will report
INSUFFICIENT DATA. That's the point: the script is landed so the verdict is one
command away once the pair log deepens.

Run:
    python3 analysis/h_wd_l3_residual_stage0.py

Output:
    analysis/output/h_wd_l3_residual_stage0.txt
    analysis/output/h_wd_l3_residual_stage0.json
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_wd_l3_residual_stage0.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_wd_l3_residual_stage0.json")

MIN_N_CELL = 30
MIN_TEST_PER_CELL = 20
STAGE0_HIT_PCT = 1.0
HELD_OUT_DAYS = 7

LEAD_BANDS = [
    ("0-5",   1,  5),
    ("6-11",  6, 11),
    ("12-23", 12, 23),
    ("24-47", 24, 47),
]


def lead_band(lead):
    for name, lo, hi in LEAD_BANDS:
        if lo <= lead <= hi:
            return name
    return None


def signed_circ_diff(a, b):
    """Signed angular diff a − b in [-180, 180]."""
    return ((float(a) - float(b) + 180.0) % 360.0) - 180.0


def abs_circ_diff(a, b):
    d = abs(float(a) - float(b)) % 360.0
    return d if d <= 180.0 else 360.0 - d


def circular_mean_deg(residuals_deg):
    """Circular mean of a list of angular residuals (degrees).
    Returns mean in [-180, 180] via atan2 of unit-vector means."""
    if not residuals_deg:
        return 0.0
    sx = sum(math.sin(math.radians(r)) for r in residuals_deg) / len(residuals_deg)
    cx = sum(math.cos(math.radians(r)) for r in residuals_deg) / len(residuals_deg)
    if sx == 0.0 and cx == 0.0:
        return 0.0
    return math.degrees(math.atan2(sx, cx))


def compute():
    """Stream pair log, keep wd pairs with forecast_l2. Split into train/test
    on obs_time; per (regime × lead_band), fit circular-mean residual on train,
    score on test."""
    rows = []  # (obs_time, regime, band, fc_l2, obs)
    n_scanned = n_wd = n_kept = 0
    max_obs_time = ""
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            n_scanned += 1
            if r.get("field") != "wd":
                continue
            n_wd += 1
            fc_l2 = r.get("forecast_l2")
            obs = r.get("observed")
            lead = r.get("lead_h")
            state_fc = r.get("state_fc") or {}
            if fc_l2 is None or obs is None or lead is None:
                continue
            band = lead_band(lead)
            if band is None:
                continue
            regime = state_fc.get("regime_synoptic") or "unknown"
            obs_time = r.get("obs_time") or ""
            rows.append((obs_time, regime, band, float(fc_l2), float(obs)))
            if obs_time > max_obs_time:
                max_obs_time = obs_time
            n_kept += 1

    if not rows:
        return {}, {}, {}, n_scanned, n_wd, n_kept, None, None

    # Test window: last HELD_OUT_DAYS of obs_time, train = everything prior.
    if len(max_obs_time) < 10:
        return {}, {}, {}, n_scanned, n_wd, n_kept, None, None
    max_date = datetime.strptime(max_obs_time[:10], "%Y-%m-%d").date()
    from datetime import timedelta
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    train = defaultdict(list)  # (regime, band) -> list of signed residuals
    test = defaultdict(list)   # (regime, band) -> list of (fc_l2, obs)
    for obs_time, regime, band, fc_l2, obs in rows:
        obs_date = obs_time[:10]
        if obs_date < test_start:
            res = signed_circ_diff(obs, fc_l2)
            train[(regime, band)].append(res)
        else:
            test[(regime, band)].append((fc_l2, obs))

    # Fit + score per cell
    cells = {}
    for cell, residuals in train.items():
        if len(residuals) < MIN_N_CELL:
            cells[cell] = {"status": "THIN_TRAIN", "n_train": len(residuals)}
            continue
        mu = circular_mean_deg(residuals)
        test_rows = test.get(cell, [])
        if len(test_rows) < MIN_TEST_PER_CELL:
            cells[cell] = {"status": "THIN_TEST", "n_train": len(residuals),
                           "mean_residual_deg": round(mu, 2),
                           "n_test": len(test_rows)}
            continue
        mae_l2 = sum(abs_circ_diff(fc, ob) for fc, ob in test_rows) / len(test_rows)
        corrected = [((fc + mu) % 360.0, ob) for fc, ob in test_rows]
        mae_corr = sum(abs_circ_diff(fc, ob) for fc, ob in corrected) / len(corrected)
        pct = (mae_l2 - mae_corr) / mae_l2 * 100.0 if mae_l2 > 0 else 0.0
        cells[cell] = {
            "status": "SCORED",
            "n_train": len(residuals),
            "n_test": len(test_rows),
            "mean_residual_deg": round(mu, 2),
            "mae_l2": round(mae_l2, 2),
            "mae_corr": round(mae_corr, 2),
            "mae_improve_pct": round(pct, 2),
        }

    # Cells present only in test (no training data)
    for cell in test.keys():
        if cell not in cells:
            cells[cell] = {"status": "TRAIN_MISSING", "n_test": len(test.get(cell, []))}

    return cells, dict(train), dict(test), n_scanned, n_wd, n_kept, test_start, max_obs_time


def emit(cells, n_scanned, n_wd, n_kept, test_start, max_obs_time):
    lines = []
    lines.append("=" * 96)
    lines.append("STAGE 0 — wd L3 residual per (regime × lead_band)   [circular]")
    lines.append("=" * 96)
    lines.append(f"Scanned {n_scanned:,} rows; {n_wd:,} were wd; {n_kept:,} had forecast_l2 + obs + lead.")
    lines.append(f"Baseline: forecast_l2 (wd L2 shipped 07-20 v0.6.368/368a).")
    if test_start:
        lines.append(f"Train: obs_date <  {test_start}    Test: obs_date >= {test_start} (max {max_obs_time[:10]}).")
    lines.append(f"Gates: MIN_N_CELL={MIN_N_CELL} (train), MIN_TEST_PER_CELL={MIN_TEST_PER_CELL}, "
                 f"STAGE0_HIT ≥ +{STAGE0_HIT_PCT:.1f}% MAE.")
    lines.append("")
    if n_kept == 0:
        lines.append("Verdict: INSUFFICIENT DATA — no wd pairs carry forecast_l2 yet.")
        lines.append("Re-run after wd L2 has been shipping for ≥ 7 days (~07-27).")
        return "\n".join(lines)

    scored = {c: v for c, v in cells.items() if v.get("status") == "SCORED"}
    thin_train = sum(1 for v in cells.values() if v.get("status") == "THIN_TRAIN")
    thin_test = sum(1 for v in cells.values() if v.get("status") == "THIN_TEST")

    lines.append(f"Cells: {len(scored)} SCORED, {thin_train} THIN_TRAIN, {thin_test} THIN_TEST, "
                 f"{len(cells) - len(scored) - thin_train - thin_test} other.")
    lines.append("")
    if not scored:
        lines.append("Verdict: INSUFFICIENT DATA — no cell had ≥ {} train AND ≥ {} test pairs."
                     .format(MIN_N_CELL, MIN_TEST_PER_CELL))
        lines.append("Re-run once the post-L2 pair log deepens.")
        return "\n".join(lines)

    lines.append(f"{'regime':<18}{'band':>8}{'n_train':>10}{'n_test':>8}"
                 f"{'μ_res°':>10}{'MAE_L2':>10}{'MAE_corr':>12}{'Δ MAE %':>10}")
    lines.append("-" * 86)
    hits = 0
    for (regime, band), d in sorted(scored.items(), key=lambda x: -x[1]["mae_improve_pct"]):
        mark = " ★" if d["mae_improve_pct"] >= STAGE0_HIT_PCT else ""
        if d["mae_improve_pct"] >= STAGE0_HIT_PCT:
            hits += 1
        lines.append(f"{regime:<18}{band:>8}{d['n_train']:>10}{d['n_test']:>8}"
                     f"{d['mean_residual_deg']:>+10.1f}{d['mae_l2']:>10.1f}"
                     f"{d['mae_corr']:>12.1f}{d['mae_improve_pct']:>+10.2f}{mark}")
    lines.append("")
    if hits:
        lines.append(f"Verdict: STAGE 0 HIT — {hits} cell(s) show ≥ {STAGE0_HIT_PCT:.1f}% MAE improvement.")
        lines.append("Warrants circular-primitive build + Stage 1 wd L3 per [[project_wd_l3_l4_circular]].")
    else:
        lines.append(f"Verdict: NO STAGE 0 HIT — no cell crosses +{STAGE0_HIT_PCT:.1f}% MAE improvement.")
        lines.append("wd L3 signal absent above L2's circular blend; do not proceed to Stage 1.")
    return "\n".join(lines)


def main():
    cells, _train, _test, n_scanned, n_wd, n_kept, test_start, max_obs_time = compute()
    text = emit(cells, n_scanned, n_wd, n_kept, test_start, max_obs_time)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "forecast_error_log.jsonl",
        "min_n_cell": MIN_N_CELL,
        "min_test_per_cell": MIN_TEST_PER_CELL,
        "stage0_hit_pct": STAGE0_HIT_PCT,
        "held_out_days": HELD_OUT_DAYS,
        "n_scanned": n_scanned,
        "n_wd_rows": n_wd,
        "n_kept": n_kept,
        "test_start": test_start,
        "max_obs_time": max_obs_time,
        "cells": {f"{r}|{b}": v for (r, b), v in cells.items()},
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())

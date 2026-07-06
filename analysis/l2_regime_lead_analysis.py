"""
Cross-cut for the L2 lead-decay ship candidate — sr τ=24h.

Why this script exists:
  l2_lead_decay_fit.py flipped sr to IMPLEMENT (+2.9% MAE vs flat, no per-band
  loss). Aggregate-only + per-band gate isn't sufficient before shipping —
  sr is heavily regime-conditional (that's why L5 exists). A decay that wins
  on aggregate can still tank a specific regime (e.g. helps nw_flow long
  leads but hurts sea_breeze), and the fix in that case is skip-table
  architecture, not "don't ship."

Method:
  Stream pair log, sr only. Per row read forecast_l1, forecast_l2, observed,
  lead_h, state_obs.regime_synoptic. Compute per (regime × lead_band):
    |L2-flat|  = |err_l1 + applied_bias|
    |L2-decay| = |err_l1 + exp(-lead/τ) × applied_bias|   with τ=24h

Verdicts per cell (n≥200 floor):
    ★ L2 LOSES   Δ ≤ -2%   (decay makes MAE worse)
    flat         -2% < Δ < +2%
    WIN          Δ ≥ +2%

What to do with the output:
  - All WIN/flat: clean ship — wire sr τ=24h into l2_decay.json.
  - LOSS concentrated in a specific (regime, lead_band): skip-table candidate
    (skip the decay in that cell, ship everywhere else).
  - LOSS across all regimes at same lead_band: refit τ or ship narrower.
  - LOSS across all cells: aggregate win was noise — do not ship.
"""
import json
import math
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "l2_regime_lead_analysis.txt")

FIELD = "sr"
TAU_H = 24.0
LEAD_BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N_PER_CELL = 200
WIN_THRESHOLD_PCT = 2.0
LOSS_THRESHOLD_PCT = -2.0


def lead_band(lead_h):
    for label, lo, hi in LEAD_BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def verdict_for(delta_pct, n):
    if n < MIN_N_PER_CELL:
        return "thin"
    if delta_pct <= LOSS_THRESHOLD_PCT:
        return "★ L2 LOSES"
    if delta_pct >= WIN_THRESHOLD_PCT:
        return "WIN"
    return "flat"


def main():
    print("=" * 86)
    print(f"L2 REGIME × LEAD-BAND ANALYSIS — {FIELD} decay τ={TAU_H:g}h vs flat")
    print("=" * 86)

    print("\n[1/2] Streaming pair log...")
    # (band, regime) -> [n, sum|flat|, sum|decay|]
    by_regime = defaultdict(lambda: [0, 0.0, 0.0])

    n_total = n_field = n_kept = n_no_regime = 0
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            n_total += 1
            if r.get("field") != FIELD:
                continue
            n_field += 1
            lead_h = r.get("lead_h")
            f_l1 = r.get("forecast_l1")
            f_l2 = r.get("forecast_l2")
            obs  = r.get("observed")
            if lead_h is None or f_l1 is None or f_l2 is None or obs is None:
                continue
            band = lead_band(lead_h)
            if band is None:
                continue

            err_l1 = float(f_l1) - float(obs)
            applied_bias = float(f_l2) - float(f_l1)
            decay = math.exp(-lead_h / TAU_H)
            e_flat  = abs(err_l1 + applied_bias)
            e_decay = abs(err_l1 + decay * applied_bias)

            so = r.get("state_obs") or {}
            regime = so.get("regime_synoptic")
            if not regime:
                n_no_regime += 1
                continue

            cell = by_regime[(band, regime)]
            cell[0] += 1
            cell[1] += e_flat
            cell[2] += e_decay
            n_kept += 1

    print(f"  total pair rows:     {n_total:,}")
    print(f"  {FIELD} rows:              {n_field:,}")
    print(f"  kept (with regime):  {n_kept:,}")
    print(f"  skipped (no regime): {n_no_regime:,}")

    lines = []

    def emit(s):
        print(s)
        lines.append(s)

    emit("\n" + "=" * 86)
    emit(f"[A] L2 decay effect by SYNOPTIC REGIME × LEAD BAND (state_obs.regime_synoptic)")
    emit(f"    decay: exp(-lead/{TAU_H:g}h) × applied_bias   vs   flat: applied_bias")
    emit("=" * 86)

    all_regimes = sorted({k[1] for k in by_regime.keys()})

    header = f"  {'regime':<14} {'lead':<8} {'n':>8} {'|flat|':>9} {'|decay|':>9} {'Δ%':>7}  verdict"
    emit(header)
    emit("  " + "-" * 80)

    tally = {"WIN": 0, "flat": 0, "★ L2 LOSES": 0, "thin": 0}
    loss_cells = []
    for regime in all_regimes:
        for band_label, _, _ in LEAD_BANDS:
            cell = by_regime.get((band_label, regime))
            if not cell:
                continue
            n, s_flat, s_decay = cell
            if n == 0:
                continue
            m_flat = s_flat / n
            m_decay = s_decay / n
            d_pct = (m_flat - m_decay) / m_flat * 100 if m_flat > 0 else 0.0
            v = verdict_for(d_pct, n)
            tally[v] = tally.get(v, 0) + 1
            if v == "★ L2 LOSES":
                loss_cells.append((regime, band_label, n, d_pct))
            emit(f"  {regime:<14} {band_label:<8} {n:>8,} "
                 f"{m_flat:>9.3f} {m_decay:>9.3f} {d_pct:>6.1f}%  {v}")
        emit("")

    emit(f"Summary: {tally.get('WIN', 0)} WIN / {tally.get('flat', 0)} flat / "
         f"{tally.get('★ L2 LOSES', 0)} L2 LOSES / {tally.get('thin', 0)} thin")

    emit("\n" + "=" * 86)
    emit("VERDICT")
    emit("=" * 86)
    if tally["★ L2 LOSES"] == 0:
        emit(f"  → CLEAN — {FIELD} τ={TAU_H:g}h wins or is flat in every judgeable "
             f"(regime × lead_band) cell. Safe to wire into l2_decay.json without a "
             f"skip table.")
    else:
        loss_str = "; ".join(f"{r}/{b} ({d:+.1f}%, n={n:,})"
                             for r, b, n, d in loss_cells)
        distinct_bands = {b for _, b, _, _ in loss_cells}
        distinct_regimes = {r for r, _, _, _ in loss_cells}
        if len(distinct_bands) == 1 and len(distinct_regimes) > 1:
            shape = ("per-(field, lead_band) skip — LOSS concentrated at "
                     f"lead_band {next(iter(distinct_bands))} across regimes")
        elif len(distinct_regimes) == 1:
            shape = ("per-(field, regime) skip — LOSS concentrated in regime "
                     f"{next(iter(distinct_regimes))}")
        else:
            shape = "per-(field, regime, lead_band) skip — LOSS scattered"
        emit(f"  → SKIP-TABLE CANDIDATE — {FIELD} τ={TAU_H:g}h loses in "
             f"{tally['★ L2 LOSES']} cell(s): {loss_str}")
        emit(f"    Shape: {shape}.")
        emit(f"    Ship sr τ={TAU_H:g}h in l2_decay.json with a skip table for the "
             f"losing cell(s); do NOT ship globally.")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

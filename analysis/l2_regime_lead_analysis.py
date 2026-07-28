"""
Cross-cut for the L2 lead-decay ship candidate — sr τ=120h.

⚠  BLOCKED by unit mismatch — see project_sr_unit_mismatch.
   sr has NO L2 wired in production. Pair-log forecast_l2 for sr is a bit-
   identical echo of forecast_l1 (verified 20k rows). The +4.5% "improvement"
   this script and l2_lead_decay_fit.py report is fitting the definitional
   gap between model direct_radiation (direct-beam only) and Tempest
   solar_wm2 (total shortwave), not a real hyperlocal station-consensus
   signal. Naive L2 wiring here would re-encode the unit gap into a new
   correction — exactly the trap Lsr's old regime bias fell into.
   Actual open work: Lsb (sr_sea_breeze_lsr_override.py) shortwave-refit
   chain. Do NOT ship sr L2 from this script's output until that resolves.

Why this script still runs:
  When Lsb / shortwave-refit lands and sr L2 becomes wireable against
  shortwave, this regime × lead_band cross-cut is the pre-ship gate. Keep
  running so the diagnostic is ready.

Method:
  Stream pair log, sr only. Per row read forecast_l1, forecast_l2, observed,
  lead_h, state_obs.regime_synoptic. Compute per (regime × lead_band):
    |L2-flat|  = |err_l1 + applied_bias|
    |L2-decay| = |err_l1 + exp(-lead/τ) × applied_bias|   with τ=120h
    (τ=120h from analysis/l2_lead_decay_fit.py, replaces earlier τ=24h
     recommendation. Re-cut 2026-07-28 confirmed CLEAN across all 32 cells
     at τ=120h — zero regressions, calm/24-47 +2.1%, frontal/24-47 +5.8%.)

Verdicts per cell (n≥200 floor):
    ★ L2 LOSES   Δ ≤ -2%   (decay makes MAE worse)
    flat         -2% < Δ < +2%
    WIN          Δ ≥ +2%

What to do with the output:
  - Until unit mismatch resolved: informational only, do not ship.
  - Post-resolution: All WIN/flat → clean ship. LOSS in one cell →
    skip-table candidate. LOSS across cells → aggregate win was noise.
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
TAU_H = 120.0  # from l2_lead_decay_fit.py — supersedes stale 24.0
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
             f"(regime × lead_band) cell. ⚠  DO NOT SHIP: blocked by unit mismatch "
             f"(see project_sr_unit_mismatch — sr forecast_l2 is echo of forecast_l1 "
             f"in production; +% is fitting direct-vs-shortwave gap, not station "
             f"consensus). Diagnostic-only until Lsb/shortwave-refit resolves.")
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

"""
Stage 0 — L3 efficacy stratified by (regime × lead_band) and (fc wind speed
× lead_band), per field.

Why this script exists (the puzzle that motivated it):
  h_regime_l3.py shows ws L3 wins under every synoptic regime. The per-lead
  Forecast Accuracy chart shows ws L3 makes things +20–31% WORSE at leads
  18–47h. Both can't be right unless the cross-cut is (regime × lead_band)
  rather than regime alone — long-lead failures in some regimes washed out
  by short-lead wins in the same regime.

  Originally proposed (2026-06-29) as wind_l3_regime_analysis.py (ws/wg
  only). Broadened to all L3-applied MAE fields since the framework is
  identical and the question generalizes (cm and ch may have the same
  hidden long-lead behavior).

Method:
  Stream pair log; filter to L3-applied fields (ws, wg, ch, cm — pp is
  Brier-evaluated and excluded). Per row, read state_obs.regime_synoptic
  (observed regime — what actually happened) and state_fc.wind_speed
  (forecast wind speed — the value the model offered). Bin lead_h into
  the same 4 bands the walk-forward validator uses. Compute |error_l2|
  vs |error_l3| per cell — the marginal L3 contribution.

  Two splits per field:
    A. Synoptic regime × lead_band   (regime from state_obs)
    B. Forecast wind speed × lead_band   (wind speed bins from state_fc)

Verdicts per cell (with n≥200 floor):
    ★ L3 LOSES   if Δ ≤ -3%   (L3 makes MAE worse by 3pp+)
    flat         if -3% < Δ < +3%
    WIN          if Δ ≥ +3%

What to do with the output:
  If a field shows L3 LOSES concentrated in a specific (regime, lead_band)
  cell while winning elsewhere, that's the case for a per-(field, regime,
  lead_band) whitelist in decay_apply.py rather than a flat drop. If L3
  LOSES across all regimes at the same lead_band, that's a per-(field,
  lead_band) whitelist case (lead-band-only refinement).

  If L3 LOSES across all cells, that's the case for the flat drop the
  current walk-forward gate is counting toward.
"""
import json
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "l3_regime_lead_analysis.txt")

FIELDS = ("ws", "wg", "ch", "cm")
LEAD_BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
# Forecast wind speed bins (mph). Tuned for the local distribution — most
# WU/airport readings live 0–15; >15 is the "windy / frontal / nor'easter"
# tail where errors typically blow up.
FC_WIND_BINS = [
    ("0-3 calm",   0,   3),
    ("3-8 light",  3,   8),
    ("8-15 mod",   8,  15),
    ("15-25 strong", 15, 25),
    ("25+ severe", 25, 999),
]
MIN_N_PER_CELL = 200
WIN_THRESHOLD_PCT = 3.0   # Δ ≥ +3% = WIN
LOSS_THRESHOLD_PCT = -3.0  # Δ ≤ -3% = LOSS


def lead_band(lead_h):
    for label, lo, hi in LEAD_BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def fc_wind_bin(ws_mph):
    if ws_mph is None:
        return None
    for label, lo, hi in FC_WIND_BINS:
        if lo <= ws_mph < hi:
            return label
    return None


def verdict_for(delta_pct, n):
    if n < MIN_N_PER_CELL:
        return "thin"
    if delta_pct <= LOSS_THRESHOLD_PCT:
        return "★ L3 LOSES"
    if delta_pct >= WIN_THRESHOLD_PCT:
        return "WIN"
    return "flat"


def main():
    print("=" * 86)
    print("L3 REGIME × LEAD-BAND ANALYSIS — marginal L3 vs L2, stratified")
    print("=" * 86)

    print("\n[1/3] Streaming pair log...")
    # (field, lead_band, regime) -> [n, sum|e2|, sum|e3|]
    by_regime = defaultdict(lambda: [0, 0.0, 0.0])
    # (field, lead_band, fc_wind_bin) -> [n, sum|e2|, sum|e3|]
    by_fc_ws = defaultdict(lambda: [0, 0.0, 0.0])

    n_total = n_kept = n_no_l3 = n_no_regime = 0
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            n_total += 1
            field = r.get("field")
            if field not in FIELDS:
                continue
            e2 = r.get("error_l2")
            e3 = r.get("error_l3")
            if e2 is None or e3 is None:
                n_no_l3 += 1
                continue
            lead_h = r.get("lead_h")
            band = lead_band(lead_h) if lead_h is not None else None
            if band is None:
                continue

            n_kept += 1
            a2, a3 = abs(float(e2)), abs(float(e3))

            so = r.get("state_obs") or {}
            regime = so.get("regime_synoptic")
            if regime:
                cell = by_regime[(field, band, regime)]
                cell[0] += 1
                cell[1] += a2
                cell[2] += a3
            else:
                n_no_regime += 1

            sf = r.get("state_fc") or {}
            fc_ws = sf.get("wind_speed")
            fc_bin = fc_wind_bin(float(fc_ws)) if fc_ws is not None else None
            if fc_bin:
                cell = by_fc_ws[(field, band, fc_bin)]
                cell[0] += 1
                cell[1] += a2
                cell[2] += a3

    print(f"  total pair rows: {n_total:,}")
    print(f"  L3-field rows with l2+l3 errors: {n_kept:,}")
    print(f"  skipped (no l2/l3): {n_no_l3:,}")
    print(f"  rows with no observed regime: {n_no_regime:,}")

    lines = []

    def emit(s):
        print(s)
        lines.append(s)

    def render(title, agg, axis_label, axis_order):
        emit("\n" + "=" * 86)
        emit(title)
        emit("=" * 86)
        header = f"  {'field':<5} {axis_label:<18} {'lead':<8} {'n':>8} {'|L2|':>9} {'|L3|':>9} {'Δ%':>7}  verdict"
        for field in FIELDS:
            emit(f"\n[{field}]")
            emit(header)
            emit("  " + "-" * 80)
            field_summary = {"WIN": 0, "flat": 0, "★ L3 LOSES": 0, "thin": 0}
            for band_label, _, _ in LEAD_BANDS:
                for axis_val in axis_order:
                    cell = agg.get((field, band_label, axis_val))
                    if not cell:
                        continue
                    n, s2, s3 = cell
                    if n == 0:
                        continue
                    m2 = s2 / n
                    m3 = s3 / n
                    d_pct = (m2 - m3) / m2 * 100 if m2 > 0 else 0.0
                    v = verdict_for(d_pct, n)
                    field_summary[v] = field_summary.get(v, 0) + 1
                    emit(f"  {field:<5} {axis_val:<18} {band_label:<8} {n:>8,} "
                         f"{m2:>9.3f} {m3:>9.3f} {d_pct:>6.1f}%  {v}")
            emit(f"  summary for {field}: "
                 f"{field_summary.get('WIN', 0)} WIN / "
                 f"{field_summary.get('flat', 0)} flat / "
                 f"{field_summary.get('★ L3 LOSES', 0)} L3 LOSES / "
                 f"{field_summary.get('thin', 0)} thin")

    # Collect observed regime order — alphabetical for stability, but with
    # 'unknown' / None pushed to the end.
    all_regimes = sorted({k[2] for k in by_regime.keys()})
    render("[A] L3 marginal effect by SYNOPTIC REGIME × LEAD BAND (state_obs.regime_synoptic)",
           by_regime, "regime", all_regimes)

    fc_bin_order = [label for label, _, _ in FC_WIND_BINS]
    render("[B] L3 marginal effect by FORECAST WIND SPEED × LEAD BAND (state_fc.wind_speed)",
           by_fc_ws, "fc_ws bin", fc_bin_order)

    emit("\n" + "=" * 86)
    emit("INTERPRETATION GUIDE")
    emit("=" * 86)
    emit("  - L3 LOSES concentrated in one cell → per-(field, regime, lead_band) whitelist")
    emit("    candidate. Save the wins, kill the losses.")
    emit("  - L3 LOSES across all regimes at the same lead_band → per-(field, lead_band)")
    emit("    whitelist (lead-band-only refinement).")
    emit("  - L3 LOSES across all cells → flat drop, which is what the walk-forward gate")
    emit("    is currently counting toward.")
    emit("  - L3 mostly WIN/flat → leave L3 on; the gate-counter loss signal is")
    emit("    coming from elsewhere (regime drift, recency, etc.)")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

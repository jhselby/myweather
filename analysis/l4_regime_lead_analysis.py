"""
Stage 0 — L4 efficacy stratified by (regime × lead_band) and (fc wind speed
× lead_band), per field.

Mirror of l3_regime_lead_analysis.py for L4. Built 2026-06-29 to pre-empt
the walk-forward L4 drop-cc gate (currently 5/7, 2 reads from clearing).
Same question the L3 analysis answered for ws: is L4 cc actually broken
across the board, or is there a hidden (regime, lead_band) cell where L4
cc wins that a flat drop would throw away?

Method:
  Stream pair log; filter to L4-applied MAE fields (ch, cc). Per row, read
  state_obs.regime_synoptic and state_fc.wind_speed. Bin lead_h into the
  walk-forward validator's 4 bands. Compute |error_l3| vs |error_l4| per
  cell — the marginal L4 contribution.

  Two splits per field:
    A. Synoptic regime × lead_band   (regime from state_obs)
    B. Forecast wind speed × lead_band   (wind speed bins from state_fc)

  L4 is by design a diurnal (hour-of-day) correction, so an obvious third
  split would be hour-of-day × regime. Skipped here for budget reasons;
  if A/B don't resolve the picture, hour-of-day is the next axis to add.

Verdicts per cell (with n≥200 floor):
    ★ L4 LOSES   if Δ ≤ -3%   (L4 makes MAE worse by 3pp+)
    flat         if -3% < Δ < +3%
    WIN          if Δ ≥ +3%

What to do with the output:
  If a field shows L4 LOSES concentrated in a specific (regime, lead_band)
  cell while winning elsewhere, that's the case for a per-(field, regime,
  lead_band) whitelist rather than a flat drop. If L4 LOSES across all
  cells, the flat drop the walk-forward gate is counting toward is right.
"""
import json
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "l4_regime_lead_analysis.txt")

# L4_FIELDS in production: {ch, cc, h} after the post-walkforward-bugfix re-run
# recommended h. dp added 2026-06-30 to investigate the chart-vs-validator
# discrepancy (chart shows dp L4 lowest by 0.3-1.3%; validator below 3% gate).
# Recent pair rows (2026-06-30+) carry error_l4 for all fields; older rows
# without it are skipped at the e3/e4-None check.
FIELDS = ("ch", "cc", "dp")
LEAD_BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
FC_WIND_BINS = [
    ("0-3 calm",     0,   3),
    ("3-8 light",    3,   8),
    ("8-15 mod",     8,  15),
    ("15-25 strong", 15, 25),
    ("25+ severe",   25, 999),
]
MIN_N_PER_CELL = 200
WIN_THRESHOLD_PCT = 3.0
LOSS_THRESHOLD_PCT = -3.0


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
        return "★ L4 LOSES"
    if delta_pct >= WIN_THRESHOLD_PCT:
        return "WIN"
    return "flat"


def main():
    print("=" * 86)
    print("L4 REGIME × LEAD-BAND ANALYSIS — marginal L4 vs L3, stratified")
    print("=" * 86)

    print("\n[1/3] Streaming pair log...")
    by_regime = defaultdict(lambda: [0, 0.0, 0.0])
    by_fc_ws = defaultdict(lambda: [0, 0.0, 0.0])

    n_total = n_kept = n_no_l4 = n_no_regime = 0
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
            e3 = r.get("error_l3")
            e4 = r.get("error_l4")
            if e3 is None or e4 is None:
                n_no_l4 += 1
                continue
            lead_h = r.get("lead_h")
            band = lead_band(lead_h) if lead_h is not None else None
            if band is None:
                continue

            n_kept += 1
            a3, a4 = abs(float(e3)), abs(float(e4))

            so = r.get("state_obs") or {}
            regime = so.get("regime_synoptic")
            if regime:
                cell = by_regime[(field, band, regime)]
                cell[0] += 1
                cell[1] += a3
                cell[2] += a4
            else:
                n_no_regime += 1

            sf = r.get("state_fc") or {}
            fc_ws = sf.get("wind_speed")
            fc_bin = fc_wind_bin(float(fc_ws)) if fc_ws is not None else None
            if fc_bin:
                cell = by_fc_ws[(field, band, fc_bin)]
                cell[0] += 1
                cell[1] += a3
                cell[2] += a4

    print(f"  total pair rows: {n_total:,}")
    print(f"  L4-field rows with l3+l4 errors: {n_kept:,}")
    print(f"  skipped (no l3/l4): {n_no_l4:,}")
    print(f"  rows with no observed regime: {n_no_regime:,}")

    lines = []

    def emit(s):
        print(s)
        lines.append(s)

    def render(title, agg, axis_label, axis_order):
        emit("\n" + "=" * 86)
        emit(title)
        emit("=" * 86)
        header = (f"  {'field':<5} {axis_label:<18} {'lead':<8} {'n':>8} "
                  f"{'|L3|':>9} {'|L4|':>9} {'Δ%':>7}  verdict")
        for field in FIELDS:
            emit(f"\n[{field}]")
            emit(header)
            emit("  " + "-" * 80)
            field_summary = {"WIN": 0, "flat": 0, "★ L4 LOSES": 0, "thin": 0}
            for band_label, _, _ in LEAD_BANDS:
                for axis_val in axis_order:
                    cell = agg.get((field, band_label, axis_val))
                    if not cell:
                        continue
                    n, s3, s4 = cell
                    if n == 0:
                        continue
                    m3 = s3 / n
                    m4 = s4 / n
                    d_pct = (m3 - m4) / m3 * 100 if m3 > 0 else 0.0
                    v = verdict_for(d_pct, n)
                    field_summary[v] = field_summary.get(v, 0) + 1
                    emit(f"  {field:<5} {axis_val:<18} {band_label:<8} {n:>8,} "
                         f"{m3:>9.3f} {m4:>9.3f} {d_pct:>6.1f}%  {v}")
            emit(f"  summary for {field}: "
                 f"{field_summary.get('WIN', 0)} WIN / "
                 f"{field_summary.get('flat', 0)} flat / "
                 f"{field_summary.get('★ L4 LOSES', 0)} L4 LOSES / "
                 f"{field_summary.get('thin', 0)} thin")

    all_regimes = sorted({k[2] for k in by_regime.keys()})
    render("[A] L4 marginal effect by SYNOPTIC REGIME × LEAD BAND (state_obs.regime_synoptic)",
           by_regime, "regime", all_regimes)

    fc_bin_order = [label for label, _, _ in FC_WIND_BINS]
    render("[B] L4 marginal effect by FORECAST WIND SPEED × LEAD BAND (state_fc.wind_speed)",
           by_fc_ws, "fc_ws bin", fc_bin_order)

    emit("\n" + "=" * 86)
    emit("INTERPRETATION GUIDE")
    emit("=" * 86)
    emit("  - L4 LOSES concentrated in one cell → per-(field, regime, lead_band) whitelist")
    emit("    candidate. Save the wins, kill the losses.")
    emit("  - L4 LOSES across all regimes at the same lead_band → per-(field, lead_band)")
    emit("    whitelist (lead-band-only refinement).")
    emit("  - L4 LOSES across all cells → flat drop, which is what the walk-forward gate")
    emit("    is currently counting toward (drop-cc at 5/7 as of 2026-06-29).")
    emit("  - L4 mostly WIN/flat → leave L4 on; the gate-counter loss signal is")
    emit("    coming from elsewhere (regime drift, recency, etc.)")
    emit("  - Hour-of-day × regime would be the natural third split (L4 IS diurnal);")
    emit("    add if A/B above don't resolve the picture cleanly.")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

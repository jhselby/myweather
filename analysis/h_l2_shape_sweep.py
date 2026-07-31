#!/usr/bin/env python3
"""Precise floor × end grid sweep for h's L2 soft_ramp shape.

Extends h_lead_l2_ktaper_sim.py's 4-canned-shape comparison to a full grid
sweep. For each (floor, end) pair, back-solves the L2 correction from the
pair log (bias_applied = forecast_l2 - forecast_l1 at each lead) and re-applies
with the new ramp shape.

Grid:
  floor ∈ {0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4}
  end   ∈ {6, 8, 10, 12, 15, 18, 21, 24}

For the top-N shapes, also runs halves-verify (chronological split by obs_time
median). Winner must beat raw AND halves-stable AND per-band-non-worse.

Design gate:
  1. Beats raw by ≥ MIN_VS_RAW_PCT pooled
  2. Both halves beat raw by ≥ MIN_VS_RAW_PCT/2
  3. No lead-band worse than raw by more than TOLERANCE_PCT

Run:
    python3 -m analysis.h_l2_shape_sweep
    python3 -m analysis.h_l2_shape_sweep --window-days 14
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

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = Path(__file__).resolve().parent / "output" / "h_l2_shape_sweep.txt"

FIELD = "h"
FLOORS = [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4]
ENDS = [6, 8, 10, 12, 15, 18, 21, 24]
LEAD_BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]
MIN_VS_RAW_PCT = 1.0        # winner must beat raw by ≥ this
TOLERANCE_PCT = 1.0         # allowed per-band regression below raw


def band_of(lead):
    for lab, lo, hi in LEAD_BANDS:
        if lo <= lead < hi:
            return lab
    return None


def _ramp(lead, floor, end):
    """Piecewise-linear: 1.0 at 0 → floor at `end` → held at floor."""
    return max(floor, 1.0 - (1.0 - floor) * lead / end)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=7)
    ap.add_argument("--cutoff", default=None)
    args = ap.parse_args()

    end_dt = datetime.fromisoformat(args.cutoff) if args.cutoff else datetime.utcnow()
    start_dt = end_dt - timedelta(days=args.window_days)
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M")
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M")

    # Load all matching rows into memory
    rows = []
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            ot = r.get("obs_time") or ""
            if not (start_iso <= ot < end_iso):
                continue
            lead = r.get("lead_h")
            l1 = r.get("forecast_l1")
            l2 = r.get("forecast_l2")
            obs = r.get("observed")
            if None in (lead, l1, l2, obs):
                continue
            rows.append((ot, int(lead), float(l1), float(l2), float(obs)))

    out = []
    def p(*a):
        line = " ".join(str(x) for x in a)
        print(line); out.append(line)

    p("=" * 100)
    p(f"h_l2_shape_sweep — precise floor × end grid for h L2")
    p("=" * 100)
    p(f"Window: {start_iso} → {end_iso}  ({args.window_days}d)")
    p(f"Rows: {len(rows):,}")
    p()

    if len(rows) < 500:
        p(f"INSUFFICIENT DATA — need ≥500 rows, got {len(rows)}")
        return 1

    # L1 raw MAE (pooled + per-band)
    l1_abs = 0.0; l1_n = 0
    l1_band = defaultdict(lambda: [0.0, 0])
    for (_, lead, l1, _, obs) in rows:
        l1_abs += abs(l1 - obs); l1_n += 1
        b = band_of(lead)
        l1_band[b][0] += abs(l1 - obs); l1_band[b][1] += 1
    raw_mae = l1_abs / l1_n
    raw_band_mae = {b: (s/n if n else None) for b, (s, n) in l1_band.items()}
    p(f"L1 raw pooled MAE = {raw_mae:.4f}")
    p(f"L1 raw per-band  = " + ", ".join(f"{b}={raw_band_mae[b]:.4f}" for b, _, _ in LEAD_BANDS))
    p()

    # Sweep grid
    grid = {}   # (floor, end) -> {pooled: mae, bands: {band: mae}}
    for floor in FLOORS:
        for end in ENDS:
            abs_sum = 0.0; n = 0
            band_agg = defaultdict(lambda: [0.0, 0])
            for (_, lead, l1, l2, obs) in rows:
                bias_applied = l2 - l1
                new_f = l1 + bias_applied * _ramp(lead, floor, end)
                err = abs(new_f - obs)
                abs_sum += err; n += 1
                b = band_of(lead)
                band_agg[b][0] += err; band_agg[b][1] += 1
            grid[(floor, end)] = {
                "pooled": abs_sum / n if n else None,
                "bands": {b: (s/nb if nb else None) for b, (s, nb) in band_agg.items()},
            }

    # ── Grid table ──
    p("=" * 100)
    p("POOLED MAE — GRID (floor rows × end cols) — CELL = MAE   [±% vs raw]")
    p("=" * 100)
    label = "floor / end"
    header = f"  {label:<12}" + "".join(f"{e:>13}" for e in ENDS)
    p(header)
    for floor in FLOORS:
        row = [f"  {floor:<12.2f}"]
        for end in ENDS:
            v = grid[(floor, end)]["pooled"]
            pct = 100 * (raw_mae - v) / raw_mae
            marker = "*" if pct >= MIN_VS_RAW_PCT else " "
            row.append(f"{v:>7.4f}[{pct:>+4.1f}]")
        p("".join(row))
    p()
    p("  * = beats raw by ≥ MIN_VS_RAW_PCT (%). Higher magnitude of + = better.")
    p()

    # ── Top-5 shapes by pooled improvement ──
    ranked = sorted(grid.items(), key=lambda kv: kv[1]["pooled"])
    p("=" * 100)
    p("TOP 5 SHAPES BY POOLED MAE")
    p("=" * 100)
    p(f"  {'rank':>4} {'floor':>6} {'end':>4} {'pooled':>8} {'vs raw':>8}   "
      + " ".join(f"{b:>10}" for b, _, _ in LEAD_BANDS))
    p(f"  {'-':>4} {'-':>6} {'-':>4} {raw_mae:>8.4f} {'—':>8}   "
      + " ".join(f"{raw_band_mae[b]:>10.4f}" if raw_band_mae[b] else f"{'—':>10}" for b, _, _ in LEAD_BANDS)
      + "   raw baseline")
    top_shapes = []
    for i, ((floor, end), d) in enumerate(ranked[:5]):
        pooled = d["pooled"]
        vs_raw = 100 * (raw_mae - pooled) / raw_mae
        band_cells = []
        for b, _, _ in LEAD_BANDS:
            bv = d["bands"][b]
            if bv is None or raw_band_mae[b] is None:
                band_cells.append(f"{'—':>10}")
                continue
            d_band = 100 * (raw_band_mae[b] - bv) / raw_band_mae[b]
            marker = "" if d_band >= -TOLERANCE_PCT else "!"
            band_cells.append(f"{d_band:>+8.2f}%{marker}")
        p(f"  {i+1:>4} {floor:>6.2f} {end:>4d} {pooled:>8.4f} {vs_raw:>+7.2f}%   "
          + " ".join(band_cells))
        top_shapes.append((floor, end, pooled, vs_raw, d["bands"]))
    p()
    p(f"  ! marker = band worse than raw by >{TOLERANCE_PCT:.1f}%.")
    p()

    # ── Halves-verify top-5 ──
    p("=" * 100)
    p("HALVES-STABILITY for top 5 (chronological split by obs_time median)")
    p("=" * 100)
    rows_sorted = sorted(rows, key=lambda r: r[0])
    mid = len(rows_sorted) // 2
    half_A = rows_sorted[:mid]
    half_B = rows_sorted[mid:]

    def _mae_half(half, floor=None, end=None):
        s = 0.0; n = 0
        for (_, lead, l1, l2, obs) in half:
            if floor is None:
                new_f = l1
            else:
                bias_applied = l2 - l1
                new_f = l1 + bias_applied * _ramp(lead, floor, end)
            s += abs(new_f - obs); n += 1
        return s / n if n else None

    raw_A = _mae_half(half_A); raw_B = _mae_half(half_B)
    p(f"  raw baseline: A={raw_A:.4f} (n={len(half_A):,})   B={raw_B:.4f} (n={len(half_B):,})")
    p()
    p(f"  {'floor':>6} {'end':>4} {'A_mae':>8} {'A_vs_raw':>10} {'B_mae':>8} {'B_vs_raw':>10}   verdict")
    winners = []
    for (floor, end, pooled, vs_raw, bands) in top_shapes:
        a = _mae_half(half_A, floor, end)
        b = _mae_half(half_B, floor, end)
        a_vs = 100 * (raw_A - a) / raw_A if raw_A else 0
        b_vs = 100 * (raw_B - b) / raw_B if raw_B else 0
        halves_ok = (a_vs >= MIN_VS_RAW_PCT / 2) and (b_vs >= MIN_VS_RAW_PCT / 2)
        # Check per-band-not-worse gate
        bands_ok = all(
            bands[bl] is None or raw_band_mae[bl] is None
            or (raw_band_mae[bl] - bands[bl]) / raw_band_mae[bl] * 100 >= -TOLERANCE_PCT
            for bl, _, _ in LEAD_BANDS
        )
        pooled_ok = vs_raw >= MIN_VS_RAW_PCT
        verdict = "SHIP" if (pooled_ok and halves_ok and bands_ok) else "HOLD"
        why = []
        if not pooled_ok: why.append(f"pooled {vs_raw:+.1f}% <{MIN_VS_RAW_PCT}%")
        if not halves_ok: why.append(f"halves {a_vs:+.1f}/{b_vs:+.1f}")
        if not bands_ok: why.append("band regression")
        why_str = (" (" + ", ".join(why) + ")") if why else ""
        p(f"  {floor:>6.2f} {end:>4d} {a:>8.4f} {a_vs:>+9.2f}% {b:>8.4f} {b_vs:>+9.2f}%   {verdict}{why_str}")
        if verdict == "SHIP":
            winners.append((floor, end, pooled, vs_raw))
    p()

    # ── Verdict ──
    p("=" * 100)
    if not winners:
        p("VERDICT: STAGE 0 HOLD — no shape passes pooled + halves + per-band gate.")
    else:
        # Pick lowest pooled MAE among winners
        winners.sort(key=lambda w: w[2])
        floor, end, pooled, vs_raw = winners[0]
        p(f"VERDICT: STAGE 0 PROMOTE — best halves-stable shape is floor={floor}, end={end}.")
        p(f"  Pooled MAE {pooled:.4f} vs raw {raw_mae:.4f} ({vs_raw:+.2f}%).")
        p(f"  Ship: H_SOFT_RAMP_FLOOR = {floor}, H_SOFT_RAMP_END = {end} "
          f"in weather_collector/processors/corrected_hourly.py")
    p("=" * 100)

    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(out) + "\n")
    print(f"\nwrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

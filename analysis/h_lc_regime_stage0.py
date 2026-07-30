#!/usr/bin/env python3
"""Stage 0 magnitude sweep: does Lc bias concentrate by (field × regime × bin)?

Motivation: pooled Lc broke on cl+cc on 2026-07-28→30. Raw cl MAE 7.29 →
Lc-corrected cl MAE 56.96 (8× worse) on 07-30 as mostly-clear weather
came in. Same story cc raw 7.21 → l6 44.23. cm/ch held. Hypothesis:
Lc's pooled (field, bin) shift table is regime-blind — when the regime
mix shifts, one regime's over-forecast pattern anchors the pooled shift
away from what other regimes need.

Test: extend the fit to (field, regime, bin) and see if the bias
magnitude concentrates cleanly in specific regimes vs. spreads
uniformly. If it concentrates, regime-conditional Lc is the right fix.
If it spreads, pooled was the right shape and today's damage is a
transient (wait for the fitter window to roll).

Stage 0 discipline: no code wiring, no curated table emission. Just a
magnitude read + halves sanity check. Written per
[[feedback_hypothesis_promotion_pipeline]] — Stage 0 answers "is the
signal even there?" before Stage 1 spends time on structure.

Verdict logic per cell:
  * n ≥ MIN_N (per-regime, per-bin)
  * |mean_bias| ≥ MAG_FLOOR_PP
  * pooled Δ MAE improve% ≥ MAE_IMPROVE_FLOOR_PCT
  * halves A and B both improve% > 0 (halves-stable)
Cells passing all four are ★-magnitude candidates for Stage 1.

Comparison: for each ★ cell, we also compute the pooled-Lc shift the
current production table would apply. Cells where regime-shift ≠
pooled-shift by a wide margin are the smoking-gun evidence that pooled
is masking regime-conditional structure.

Run:
    python3 -m analysis.h_lc_regime_stage0
    MYWEATHER_REFRESH=1 python3 -m analysis.h_lc_regime_stage0
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis._cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_PATH = Path(__file__).resolve().parent / "output" / "h_lc_regime_stage0.txt"
LIVE_LC_TABLE = Path(__file__).resolve().parent.parent / "weather_collector" / "data" / "lc_correction_table.json"

CLOUD_FIELDS = ["cc", "cl", "cm", "ch"]

BINS = [
    (0,   5,      "0-5"),
    (5,   20,     "5-20"),
    (20,  50,     "20-50"),
    (50,  80,     "50-80"),
    (80,  95,     "80-95"),
    (95,  100.01, "95-100"),
]

MIN_N = 200
MAG_FLOOR_PP = 5.0
MAE_IMPROVE_FLOOR_PCT = 2.0


def bin_of(v):
    for lo, hi, lab in BINS:
        if lo <= v < hi:
            return lab
    return None


def load_forecast_from_row(r):
    return (
        r.get("forecast_l4")
        or r.get("forecast_l3")
        or r.get("forecast_l2")
        or r.get("forecast_l1")
    )


def regime_of(r):
    sfc = r.get("state_fc") or {}
    return sfc.get("regime_synoptic")


def cell_stats(pair_list):
    n = len(pair_list)
    if n == 0:
        return None
    mean_bias = sum(fc - obs for fc, obs in pair_list) / n
    shift = -mean_bias
    mae_pre = sum(abs(fc - obs) for fc, obs in pair_list) / n
    def apply_shift(fc):
        return max(0.0, min(100.0, fc + shift))
    mae_post = sum(abs(apply_shift(fc) - obs) for fc, obs in pair_list) / n
    improve_pct = 100.0 * (mae_pre - mae_post) / mae_pre if mae_pre > 0 else 0.0
    return {
        "n": n,
        "mean_bias": mean_bias,
        "shift": shift,
        "mae_pre": mae_pre,
        "mae_post": mae_post,
        "improve_pct": improve_pct,
    }


def halves_split(pair_list):
    """Deterministic split — first half of the list vs second half. Pair
    log is chronological so this is calendar-halves."""
    m = len(pair_list) // 2
    return pair_list[:m], pair_list[m:]


def main():
    # (field, regime, bin) → [(fc, obs), ...]
    triple = defaultdict(list)
    # (field, bin) → [(fc, obs), ...]   pooled reference
    pooled = defaultdict(list)
    rows_read = 0
    rows_used = 0
    rows_no_regime = 0

    print(f"reading {URL}")
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            rows_read += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            field = r.get("field")
            if field not in CLOUD_FIELDS:
                continue
            fc = load_forecast_from_row(r)
            obs = r.get("observed")
            if fc is None or obs is None:
                continue
            b = bin_of(fc)
            if b is None:
                continue
            regime = regime_of(r)
            if regime is None:
                rows_no_regime += 1
                continue
            triple[(field, regime, b)].append((float(fc), float(obs)))
            pooled[(field, b)].append((float(fc), float(obs)))
            rows_used += 1

    print(f"  rows read:  {rows_read:,}")
    print(f"  rows used:  {rows_used:,}")
    print(f"  no-regime:  {rows_no_regime:,}")
    print(f"  (field, regime, bin) cells populated: {len(triple):,}")
    print()

    # Pooled per-cell stats (reference — this is what live Lc uses)
    pooled_stats = {}
    for k, pairs in pooled.items():
        pooled_stats[k] = cell_stats(pairs)

    # Live Lc table for shift comparison
    live_lc = {}
    try:
        with open(LIVE_LC_TABLE) as fh:
            data = json.load(fh)
        for f, bins in data.get("cells", {}).items():
            for b, cell in bins.items():
                live_lc[(f, b)] = {
                    "shift": cell.get("shift"),
                    "verdict": cell.get("verdict"),
                    "n": cell.get("n"),
                }
    except Exception as e:
        print(f"  ⚠ could not load live Lc table: {e}")
    print()

    # Compute per (field, regime, bin) cell + halves
    results = []
    for (field, regime, lab), pairs in triple.items():
        s = cell_stats(pairs)
        if s is None:
            continue
        a, b = halves_split(pairs)
        sa = cell_stats(a) if len(a) >= 50 else None
        sb = cell_stats(b) if len(b) >= 50 else None

        # Verdict (Stage 0)
        if s["n"] < MIN_N:
            v = "thin"
        elif abs(s["mean_bias"]) < MAG_FLOOR_PP:
            v = "SKIP-mag"
        elif s["improve_pct"] < MAE_IMPROVE_FLOOR_PCT:
            v = "SKIP-Δ"
        elif sa is None or sb is None:
            v = "thin-halves"
        elif sa["improve_pct"] < 0 or sb["improve_pct"] < 0:
            v = "HALVES-DIVERGE"
        elif s["improve_pct"] < 2 * MAE_IMPROVE_FLOOR_PCT:
            v = "MARGINAL"
        else:
            v = "SHIP★"

        # Compare against pooled-live shift
        pool = pooled_stats.get((field, lab))
        live = live_lc.get((field, lab), {})
        results.append({
            "field": field,
            "regime": regime,
            "bin": lab,
            "verdict": v,
            **{k: s[k] for k in s},
            "half_a_improve_pct": sa["improve_pct"] if sa else None,
            "half_b_improve_pct": sb["improve_pct"] if sb else None,
            "pooled_shift": pool["shift"] if pool else None,
            "pooled_improve_pct": pool["improve_pct"] if pool else None,
            "live_shift": live.get("shift"),
            "live_verdict": live.get("verdict"),
        })

    # ── Report ──
    out = []
    def p(*a):
        line = " ".join(str(x) for x in a)
        print(line)
        out.append(line)

    p("=" * 100)
    p("h_lc_regime_stage0 — Lc regime × bin magnitude sweep")
    p("=" * 100)
    p()
    p(f"MIN_N={MIN_N}  MAG_FLOOR_PP={MAG_FLOOR_PP}  MAE_IMPROVE_FLOOR_PCT={MAE_IMPROVE_FLOOR_PCT}")
    p()

    # Full table per field
    for field in CLOUD_FIELDS:
        rows = [r for r in results if r["field"] == field]
        if not rows:
            continue
        p(f"── {field} ──────────────────────────────────────────────────────────────────────────")
        p(f"{'regime':<12} {'bin':<8} {'n':>6} {'bias':>8} {'shift':>8} {'Δpool%':>7} {'ΔhA%':>7} {'ΔhB%':>7} "
          f"{'liveShift':>10} {'verdict':<16}")
        # Sort by regime, then bin order
        bin_order = {lab: i for i, (_, _, lab) in enumerate(BINS)}
        rows.sort(key=lambda r: (r["regime"], bin_order.get(r["bin"], 99)))
        for r in rows:
            liveshift = r["live_shift"]
            liveshift_s = f"{liveshift:+8.2f}" if liveshift is not None else "     n/a"
            hA = r["half_a_improve_pct"]
            hB = r["half_b_improve_pct"]
            hA_s = f"{hA:+7.1f}" if hA is not None else "    n/a"
            hB_s = f"{hB:+7.1f}" if hB is not None else "    n/a"
            p(f"{r['regime']:<12} {r['bin']:<8} {r['n']:>6,} {r['mean_bias']:>+8.2f} {r['shift']:>+8.2f} "
              f"{r['improve_pct']:>+7.1f} {hA_s} {hB_s} {liveshift_s}  {r['verdict']:<16}")
        p()

    # ── ★ verdict rollup ──
    p("=" * 100)
    p("SHIP★ verdict cells (n≥MIN_N, |bias|≥MAG_FLOOR, Δ≥2×floor, halves both positive):")
    p("=" * 100)
    ship = [r for r in results if r["verdict"] == "SHIP★"]
    if not ship:
        p("  (none)")
    else:
        # Rollup by (field, regime)
        by_fr = defaultdict(list)
        for r in ship:
            by_fr[(r["field"], r["regime"])].append(r)
        for (field, regime), cells in sorted(by_fr.items()):
            bins = sorted([c["bin"] for c in cells], key=lambda b: [x[2] for x in BINS].index(b))
            total_n = sum(c["n"] for c in cells)
            p(f"  {field:<4} {regime:<12}  {len(cells)} bin(s): {bins}  (n={total_n:,})")
    p()

    # ── Divergence from pooled ──
    p("=" * 100)
    p("Cells where regime-shift diverges materially from pooled-live shift (|Δ| ≥ 8 pp):")
    p("=" * 100)
    diverge = []
    for r in results:
        if r["verdict"] in ("thin", "thin-halves"):
            continue
        if r["live_shift"] is None:
            continue
        d = r["shift"] - r["live_shift"]
        if abs(d) >= 8.0:
            diverge.append((abs(d), d, r))
    diverge.sort(reverse=True)
    if not diverge:
        p("  (none — pooled-live is close to per-regime shifts)")
    else:
        p(f"{'field':<4} {'regime':<12} {'bin':<8} {'regshift':>9} {'liveshift':>10} {'Δshift':>7} "
          f"{'n':>6} {'verdict':<16}")
        for _, d, r in diverge[:40]:
            p(f"{r['field']:<4} {r['regime']:<12} {r['bin']:<8} {r['shift']:>+9.2f} "
              f"{r['live_shift']:>+10.2f} {d:>+7.2f} {r['n']:>6,} {r['verdict']:<16}")
    p()

    # ── Verdict line for digest pickup ──
    p("=" * 100)
    n_ship = len(ship)
    n_halves = sum(1 for r in results if r["verdict"] == "HALVES-DIVERGE")
    n_cells = len(results)
    fields_with_ship = sorted({r["field"] for r in ship})
    if n_ship == 0:
        verdict = "VERDICT: NULL — no (field × regime × bin) cell clears halves-stable Stage 0."
    elif len(fields_with_ship) >= 2:
        verdict = (f"VERDICT: SIGNAL — {n_ship} ★ cell(s) across {len(fields_with_ship)} field(s) "
                   f"{fields_with_ship}. Regime-conditional Lc is worth Stage 1 workup.")
    else:
        verdict = (f"VERDICT: PARTIAL — {n_ship} ★ cell(s) in only 1 field ({fields_with_ship[0]}). "
                   f"Consider single-field regime-conditional Lc instead of blanket refactor.")
    p(verdict)
    p(f"  cells judged: {n_cells}  halves-diverge: {n_halves}  ★: {n_ship}")
    p("=" * 100)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(out) + "\n")
    print(f"\nwrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Walk-forward validator: regime-conditional Lc vs pooled Lc on held-out data.

Shape matches [[project_walkforward_l3l4_validator]]: single train/test
obs_time split. Fits BOTH the regime-conditional table AND a pooled-Lc
table on the training window, applies each to the held-out test window,
and reports per-(field × regime × bin) MAE for regime-Lc / pooled-Lc / raw.
Fair comparison: both tables fit on the same train window.

Motivation: Joe pointed out the 7-day Stage 2 walk-forward gate is
process discipline — but we have ~30d of pair log already, so we can
answer the stronger question NOW: does regime-conditional Lc actually
beat pooled Lc on held-out days, day after day?

Verdict per (field × regime × bin) cell:
  * n_test ≥ MIN_N_TEST
  * regime-Lc test MAE beats pooled-Lc test MAE by ≥ CELL_WIN_PCT: SHIP
  * regime-Lc loses to pooled-Lc by ≥ CELL_LOSS_PCT: SKIP-regime
  * else flat (keep pooled)

Field-level rollup: sample-weighted net win of regime-Lc over pooled-Lc.
If field wins overall, regime-conditional Lc is worth wiring for that
field even if a few cells fall back to pooled.

Run:
    python3 -m analysis.walkforward_lc_regime
    python3 -m analysis.walkforward_lc_regime --cutoff-days 10 --min-train-days 20
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
OUT_TXT = Path(__file__).resolve().parent / "output" / "walkforward_lc_regime.txt"

CLOUD_FIELDS = ["cc", "cl", "cm", "ch"]

BINS = [
    (0,   5,      "0-5"),
    (5,   20,     "5-20"),
    (20,  50,     "20-50"),
    (50,  80,     "50-80"),
    (80,  95,     "80-95"),
    (95,  100.01, "95-100"),
]

# Fit rules (must match Stage 1 for fair comparison)
MIN_N_FIT = 200
MAG_FLOOR_PP = 5.0
MAE_IMPROVE_FLOOR_PCT = 2.0
HALVES_MIN_PCT = 2.0

# Verdict thresholds on the held-out test window
MIN_N_TEST = 30
CELL_WIN_PCT = 3.0    # % improvement over pooled required to SHIP regime cell
CELL_LOSS_PCT = 3.0   # % regression vs pooled → SKIP-regime (fall back to pooled)


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


def _cell_shift_and_verdict(pairs):
    n = len(pairs)
    if n < MIN_N_FIT:
        return None, "thin"
    mean_bias = sum(fc - obs for fc, obs in pairs) / n
    shift = -mean_bias
    mae_pre = sum(abs(fc - obs) for fc, obs in pairs) / n
    def apply(fc):
        return max(0.0, min(100.0, fc + shift))
    mae_post = sum(abs(apply(fc) - obs) for fc, obs in pairs) / n
    improve = 100.0 * (mae_pre - mae_post) / mae_pre if mae_pre > 0 else 0.0
    if abs(mean_bias) < MAG_FLOOR_PP:
        return shift, "SKIP-mag"
    if improve < MAE_IMPROVE_FLOOR_PCT:
        return shift, "SKIP-Δ"
    # Halves check (chronological already ensured by caller — pairs is a
    # simple list here so we do positional halves)
    m = n // 2
    a, b = pairs[:m], pairs[m:]
    def half_stats(hh):
        if len(hh) < 50:
            return None
        hmb = sum(fc - obs for fc, obs in hh) / len(hh)
        hshift = -hmb
        pre = sum(abs(fc - obs) for fc, obs in hh) / len(hh)
        post = sum(abs(max(0.0, min(100.0, fc + shift)) - obs) for fc, obs in hh) / len(hh)
        return 100.0 * (pre - post) / pre if pre > 0 else 0.0
    ha = half_stats(a)
    hb = half_stats(b)
    if ha is None or hb is None:
        return shift, "thin-halves"
    if ha < HALVES_MIN_PCT or hb < HALVES_MIN_PCT:
        return shift, "MARGIN" if (ha > 0 and hb > 0) else "HALVES-DIVERGE"
    return shift, "SHIP"


def fit_tables(train_rows):
    """Fit BOTH regime-conditional and pooled tables on train_rows.
    train_rows are (field, fc, obs, regime) tuples, already sorted by obs_time."""
    regime_pairs = defaultdict(list)   # (field, regime, bin) → [(fc, obs), ...]
    pooled_pairs = defaultdict(list)   # (field, bin) → [(fc, obs), ...]
    for field, fc, obs, regime in train_rows:
        b = bin_of(fc)
        if b is None:
            continue
        pooled_pairs[(field, b)].append((fc, obs))
        if regime:
            regime_pairs[(field, regime, b)].append((fc, obs))

    # Fit each cell
    regime_table = {}  # (field, regime, bin) → (shift or None, verdict)
    for k, pairs in regime_pairs.items():
        regime_table[k] = _cell_shift_and_verdict(pairs)
    pooled_table = {}
    for k, pairs in pooled_pairs.items():
        pooled_table[k] = _cell_shift_and_verdict(pairs)
    return regime_table, pooled_table


def shift_via_regime(regime_table, pooled_table, field, regime, bin_lab):
    """Apply-side lookup: regime-cell SHIP → its shift; else pooled SHIP → pooled shift; else 0."""
    rc = regime_table.get((field, regime, bin_lab))
    if rc and rc[1] == "SHIP":
        return rc[0]
    pc = pooled_table.get((field, bin_lab))
    if pc and pc[1] == "SHIP":
        return pc[0]
    return 0.0


def shift_via_pooled(pooled_table, field, bin_lab):
    pc = pooled_table.get((field, bin_lab))
    if pc and pc[1] == "SHIP":
        return pc[0]
    return 0.0


def evaluate(test_rows, regime_table, pooled_table):
    """For each test row, compute raw / pooled-Lc / regime-Lc absolute error.
    Aggregate per (field, regime, bin) and per field."""
    per_cell = defaultdict(lambda: {"n": 0, "raw": 0.0, "pool": 0.0, "reg": 0.0})
    per_field = defaultdict(lambda: {"n": 0, "raw": 0.0, "pool": 0.0, "reg": 0.0})

    for field, fc, obs, regime in test_rows:
        b = bin_of(fc)
        if b is None or regime is None:
            continue
        raw_err = abs(fc - obs)
        pool_shift = shift_via_pooled(pooled_table, field, b)
        reg_shift = shift_via_regime(regime_table, pooled_table, field, regime, b)
        pool_fc = max(0.0, min(100.0, fc + pool_shift))
        reg_fc = max(0.0, min(100.0, fc + reg_shift))
        pool_err = abs(pool_fc - obs)
        reg_err = abs(reg_fc - obs)

        cell = per_cell[(field, regime, b)]
        cell["n"] += 1
        cell["raw"] += raw_err
        cell["pool"] += pool_err
        cell["reg"] += reg_err
        fld = per_field[field]
        fld["n"] += 1
        fld["raw"] += raw_err
        fld["pool"] += pool_err
        fld["reg"] += reg_err

    return per_cell, per_field


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff-days", type=int, default=10,
                    help="Days at the end of the pair log to use as held-out test window (default: 10)")
    ap.add_argument("--min-train-days", type=int, default=15,
                    help="Minimum training-window days required before running (default: 15)")
    args = ap.parse_args()

    print(f"reading {URL}")
    rows = []  # (obs_time_iso, field, fc, obs, regime)
    n_read = 0
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            n_read += 1
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
            t = r.get("obs_time") or r.get("run_time")
            if not t:
                continue
            regime = regime_of(r)
            rows.append((t, field, float(fc), float(obs), regime))
    rows.sort(key=lambda x: x[0])
    print(f"  rows read: {n_read:,}  cloud rows used: {len(rows):,}")

    if not rows:
        print("no rows")
        return 1
    t_min = rows[0][0][:10]
    t_max = rows[-1][0][:10]
    print(f"  obs_time span: {t_min} → {t_max}")

    # Split by cutoff-days from t_max
    max_dt = datetime.strptime(t_max, "%Y-%m-%d")
    cutoff_dt = max_dt - timedelta(days=args.cutoff_days)
    cutoff_iso = cutoff_dt.strftime("%Y-%m-%d")

    train = [(f, fc, obs, r) for (t, f, fc, obs, r) in rows if t[:10] < cutoff_iso]
    test = [(f, fc, obs, r) for (t, f, fc, obs, r) in rows if t[:10] >= cutoff_iso]
    train_days = len({t[:10] for (t, _, _, _, _) in rows if t[:10] < cutoff_iso})
    test_days = len({t[:10] for (t, _, _, _, _) in rows if t[:10] >= cutoff_iso})
    print(f"  train: {len(train):,} rows over {train_days} days (< {cutoff_iso})")
    print(f"  test:  {len(test):,} rows over {test_days} days (≥ {cutoff_iso})")
    if train_days < args.min_train_days:
        print(f"  ⚠ train window {train_days}d < min-train-days {args.min_train_days}; abort")
        return 2
    print()

    print("fitting tables on train window …")
    regime_table, pooled_table = fit_tables(train)
    reg_ship = sum(1 for v in regime_table.values() if v[1] == "SHIP")
    pool_ship = sum(1 for v in pooled_table.values() if v[1] == "SHIP")
    print(f"  regime SHIP cells: {reg_ship}   pooled SHIP cells: {pool_ship}")
    print()

    print("evaluating on test window …")
    per_cell, per_field = evaluate(test, regime_table, pooled_table)
    print()

    # ── Report ──
    out = []
    def p(*a):
        line = " ".join(str(x) for x in a)
        print(line)
        out.append(line)

    p("=" * 100)
    p("walkforward_lc_regime — regime-conditional Lc vs pooled Lc, held-out MAE")
    p("=" * 100)
    p(f"train: {len(train):,} rows over {train_days} days (obs_time < {cutoff_iso})")
    p(f"test:  {len(test):,} rows over {test_days} days (obs_time ≥ {cutoff_iso})")
    p(f"regime SHIP cells fit on train: {reg_ship}   pooled SHIP cells: {pool_ship}")
    p()

    # ── Field-level rollup ──
    p("=" * 100)
    p("FIELD-LEVEL held-out MAE (n-weighted):")
    p("=" * 100)
    p(f"{'field':<6} {'n_test':>7} {'raw':>8} {'pool':>8} {'reg':>8} "
      f"{'pool_vs_raw%':>12} {'reg_vs_raw%':>12} {'reg_vs_pool%':>13}")
    for field in CLOUD_FIELDS:
        f = per_field.get(field)
        if not f or f["n"] == 0:
            continue
        raw = f["raw"] / f["n"]
        pool = f["pool"] / f["n"]
        reg = f["reg"] / f["n"]
        pool_vs_raw = 100.0 * (raw - pool) / raw if raw > 0 else 0.0
        reg_vs_raw = 100.0 * (raw - reg) / raw if raw > 0 else 0.0
        reg_vs_pool = 100.0 * (pool - reg) / pool if pool > 0 else 0.0
        p(f"{field:<6} {f['n']:>7,} {raw:>8.2f} {pool:>8.2f} {reg:>8.2f} "
          f"{pool_vs_raw:>+11.2f}% {reg_vs_raw:>+11.2f}% {reg_vs_pool:>+12.2f}%")
    p()

    # ── Per-cell verdicts ──
    p("=" * 100)
    p("PER-CELL verdicts (reg_vs_pool improvement on held-out test window):")
    p(f"  SHIP: reg beats pool by ≥ {CELL_WIN_PCT}%   SKIP-regime: reg loses ≥ {CELL_LOSS_PCT}%   else FLAT")
    p("=" * 100)
    ship = []
    skip = []
    flat = []
    thin = []
    for (field, regime, lab), c in per_cell.items():
        if c["n"] < MIN_N_TEST:
            thin.append((field, regime, lab, c))
            continue
        raw = c["raw"] / c["n"]
        pool = c["pool"] / c["n"]
        reg = c["reg"] / c["n"]
        d = 100.0 * (pool - reg) / pool if pool > 0 else 0.0
        entry = (field, regime, lab, c, raw, pool, reg, d)
        if d >= CELL_WIN_PCT:
            ship.append(entry)
        elif d <= -CELL_LOSS_PCT:
            skip.append(entry)
        else:
            flat.append(entry)

    p(f"  totals: SHIP={len(ship)}  SKIP-regime={len(skip)}  FLAT={len(flat)}  thin={len(thin)}")
    p()

    if ship:
        p("── SHIP cells (regime-conditional beats pooled on held-out) ─────────────────────")
        p(f"{'field':<4} {'regime':<12} {'bin':<8} {'n':>5} {'raw':>7} {'pool':>7} {'reg':>7} {'reg_vs_pool':>12}")
        for entry in sorted(ship, key=lambda e: -e[7])[:60]:
            f, r, b, c, raw, pool, reg, d = entry
            p(f"{f:<4} {r:<12} {b:<8} {c['n']:>5,} {raw:>7.2f} {pool:>7.2f} {reg:>7.2f} {d:>+11.2f}%")
        p()

    if skip:
        p("── SKIP-regime cells (regime-conditional LOSES to pooled on held-out) ─────────")
        p(f"{'field':<4} {'regime':<12} {'bin':<8} {'n':>5} {'raw':>7} {'pool':>7} {'reg':>7} {'reg_vs_pool':>12}")
        for entry in sorted(skip, key=lambda e: e[7])[:60]:
            f, r, b, c, raw, pool, reg, d = entry
            p(f"{f:<4} {r:<12} {b:<8} {c['n']:>5,} {raw:>7.2f} {pool:>7.2f} {reg:>7.2f} {d:>+11.2f}%")
        p()

    # ── Verdict line ──
    total_n = sum(f["n"] for f in per_field.values())
    total_pool = sum(f["pool"] for f in per_field.values())
    total_reg = sum(f["reg"] for f in per_field.values())
    total_raw = sum(f["raw"] for f in per_field.values())
    if total_n > 0:
        overall_reg_vs_pool = 100.0 * (total_pool - total_reg) / total_pool if total_pool > 0 else 0.0
        overall_reg_vs_raw = 100.0 * (total_raw - total_reg) / total_raw if total_raw > 0 else 0.0
    else:
        overall_reg_vs_pool = 0.0
        overall_reg_vs_raw = 0.0

    p("=" * 100)
    if overall_reg_vs_pool >= CELL_WIN_PCT:
        v = (f"VERDICT: PROMOTE — regime-Lc beats pooled-Lc by {overall_reg_vs_pool:+.2f}% "
             f"on held-out ({total_n:,} rows / {test_days}d). "
             f"vs-raw: {overall_reg_vs_raw:+.2f}%. "
             f"{len(ship)} SHIP cells / {len(skip)} SKIP-regime cells / {len(flat)} flat.")
    elif overall_reg_vs_pool <= -CELL_LOSS_PCT:
        v = (f"VERDICT: REJECT — regime-Lc LOSES to pooled by {overall_reg_vs_pool:+.2f}% "
             f"on held-out. Something's wrong with the fit.")
    else:
        v = (f"VERDICT: FLAT — regime-Lc and pooled-Lc within noise ({overall_reg_vs_pool:+.2f}%) "
             f"on held-out. Per-cell wins (SHIP={len(ship)}) may still justify wire for hot cells only.")
    p(v)
    p("=" * 100)

    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(out) + "\n")
    print(f"\nwrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

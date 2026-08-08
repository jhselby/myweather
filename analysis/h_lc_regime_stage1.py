#!/usr/bin/env python3
"""Stage 1 halves-strict fit for regime-conditional Lc.

Follows Stage 0 ([[project_hypothesis_promotion_pipeline]]). Stage 0
([[analysis/h_lc_regime_stage0.py]]) confirmed VERDICT: SIGNAL — 95 ★
cells across all 4 cloud fields. Stage 1 tightens the SHIP criterion
(halves each ≥ MAG_FLOOR, not just positive) and emits a candidate
curated table structured for Stage 3 apply-side wiring.

Schema of the emitted table:

    {
      "generated_at": ...,
      "source": "forecast_error_log.jsonl",
      "fit_rules": { ... },
      "cells": {
        "cc": {
          "sw_flow": {
            "0-5":   {n, mean_bias, shift, mae_pre, mae_post, improve_pct,
                     halves: {a, b}, verdict},
            ...
          },
          ...
        },
        "cl": { ... },
        "cm": { ... },
        "ch": { ... }
      },
      "pooled_fallback": {  # cells[field][bin] — same shape as live lc_correction_table.json
        "cc": {"0-5": {shift, verdict}, ...},
        ...
      }
    }

Apply-side (Stage 3, future commit) will:
    1. Look up cells[field][regime][bin] — if SHIP, apply that shift
    2. Else look up pooled_fallback[field][bin] — if SHIP, apply pooled
    3. Else no shift (leave raw / L4)

Verdict criterion (all four required for SHIP):
    n ≥ MIN_N
    |mean_bias| ≥ MAG_FLOOR_PP
    pooled improve_pct ≥ MAE_IMPROVE_FLOOR_PCT
    halves A improve ≥ HALVES_MIN_PCT AND halves B improve ≥ HALVES_MIN_PCT

Halves are chronological (first-half / second-half of chronologically
sorted pair-log rows for the cell). Recent-anomaly contamination is
caught by any cell where B improves noticeably worse than A.

Gate history: appends this run to `.cache_lc_regime_gate_history.json`
(30-day retention, 7-day flip gate). Same shape as `.cache_lc_gate_history.json`.

Run:
    python3 -m analysis.h_lc_regime_stage1
    MYWEATHER_REFRESH=1 python3 -m analysis.h_lc_regime_stage1
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis._cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TABLE = Path(__file__).resolve().parent / "output" / "lc_regime_curated_stage1.json"
OUT_TXT = Path(__file__).resolve().parent / "output" / "h_lc_regime_stage1.txt"
GATE_HISTORY_PATH = Path(__file__).resolve().parent.parent / ".cache_lc_regime_gate_history.json"
GATE_HISTORY_RETENTION_DAYS = 30
GATE_WINDOW_DAYS = 7

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
HALVES_MIN_PCT = 2.0    # stricter than Stage 0's "both positive"


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


def obs_time_of(r):
    # Deterministic chronological ordering for halves-split.
    return r.get("obs_time") or r.get("run_time") or ""


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


def halves_split(sorted_pairs):
    m = len(sorted_pairs) // 2
    return sorted_pairs[:m], sorted_pairs[m:]


def classify(s, sa, sb):
    if s is None or s["n"] < MIN_N:
        return "thin"
    if abs(s["mean_bias"]) < MAG_FLOOR_PP:
        return "SKIP-mag"
    if s["improve_pct"] < MAE_IMPROVE_FLOOR_PCT:
        return "SKIP-Δ"
    if sa is None or sb is None:
        return "thin-halves"
    if sa["improve_pct"] < 0 or sb["improve_pct"] < 0:
        return "HALVES-DIVERGE"
    if sa["improve_pct"] < HALVES_MIN_PCT or sb["improve_pct"] < HALVES_MIN_PCT:
        return "MARGIN"
    return "SHIP"


def cell_payload(s, sa, sb, verdict):
    def rnd(x, k=3):
        return round(x, k) if isinstance(x, (int, float)) else x
    return {
        "n": s["n"],
        "mean_bias": rnd(s["mean_bias"]),
        "shift": rnd(s["shift"]),
        "mae_pre": rnd(s["mae_pre"]),
        "mae_post": rnd(s["mae_post"]),
        "improve_pct": rnd(s["improve_pct"], 2),
        "halves": {
            "a_improve_pct": rnd(sa["improve_pct"], 2) if sa else None,
            "b_improve_pct": rnd(sb["improve_pct"], 2) if sb else None,
            "a_n": sa["n"] if sa else None,
            "b_n": sb["n"] if sb else None,
        },
        "verdict": verdict,
    }


def main():
    # (field, bin) → chronologically-sorted [(fc, obs), ...]   pooled
    # (field, regime, bin) → chronologically-sorted [(fc, obs), ...]
    triple_with_time = defaultdict(list)
    pooled_with_time = defaultdict(list)
    rows_read = 0
    rows_used = 0

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
            t = obs_time_of(r)
            pooled_with_time[(field, b)].append((t, float(fc), float(obs)))
            if regime:
                triple_with_time[(field, regime, b)].append((t, float(fc), float(obs)))
            rows_used += 1

    # Chronological sort in each cell for deterministic halves.
    for k in pooled_with_time:
        pooled_with_time[k].sort(key=lambda x: x[0])
    for k in triple_with_time:
        triple_with_time[k].sort(key=lambda x: x[0])

    print(f"  rows read:  {rows_read:,}")
    print(f"  rows used:  {rows_used:,}")
    print(f"  (field, regime, bin) cells populated: {len(triple_with_time):,}")
    print()

    # Regime-conditional cells
    cells = {f: {} for f in CLOUD_FIELDS}
    verdict_counts = defaultdict(int)
    regime_ship_set = set()
    for (field, regime, lab), timed in triple_with_time.items():
        pairs = [(fc, obs) for _, fc, obs in timed]
        s = cell_stats(pairs)
        a, b = halves_split(pairs)
        sa = cell_stats(a) if len(a) >= 50 else None
        sb = cell_stats(b) if len(b) >= 50 else None
        v = classify(s, sa, sb)
        verdict_counts[v] += 1
        cells[field].setdefault(regime, {})[lab] = cell_payload(s, sa, sb, v)
        if v == "SHIP":
            regime_ship_set.add((field, regime, lab))

    # Pooled fallback cells (same schema as live lc_correction_table.json)
    pooled_cells = {f: {} for f in CLOUD_FIELDS}
    pooled_ship_set = set()
    for (field, lab), timed in pooled_with_time.items():
        pairs = [(fc, obs) for _, fc, obs in timed]
        s = cell_stats(pairs)
        a, b = halves_split(pairs)
        sa = cell_stats(a) if len(a) >= 50 else None
        sb = cell_stats(b) if len(b) >= 50 else None
        v = classify(s, sa, sb)
        pooled_cells[field][lab] = cell_payload(s, sa, sb, v)
        if v == "SHIP":
            pooled_ship_set.add((field, lab))

    # ── Prereq: pooled-must-also-ship ─────────────────────────────────────
    # Diagnosed 2026-08-08: Stage 1 was emitting 70+ SHIP cells that
    # walkforward_lc_regime rejected on held-out (-3.60% vs pooled). Root
    # cause: regime cells with small n overfit noise in bins where pooled-Lc
    # correctly stayed silent (e.g. ch/pre_frontal/0-5: raw=pool=5.52,
    # regime made it 15.53 on held-out, -181% loss). If pooled-Lc for the
    # same (field, bin) didn't earn its own SHIP, regime-conditional
    # shouldn't override — it's fitting per-regime variance that doesn't
    # generalize. Demote SHIP → SKIP-nopool where prereq fails.
    demoted = 0
    for field in list(cells.keys()):
        for regime in list(cells[field].keys()):
            for lab in list(cells[field][regime].keys()):
                cell = cells[field][regime][lab]
                if cell["verdict"] == "SHIP" and (field, lab) not in pooled_ship_set:
                    cell["verdict"] = "SKIP-nopool"
                    regime_ship_set.discard((field, regime, lab))
                    verdict_counts["SHIP"] -= 1
                    verdict_counts["SKIP-nopool"] += 1
                    demoted += 1
    print(f"  pool-prereq demoted {demoted} regime SHIP → SKIP-nopool")
    print()

    # ── Emit curated table ──
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "forecast_error_log.jsonl",
        "fit_rules": {
            "min_n": MIN_N,
            "magnitude_floor_pp": MAG_FLOOR_PP,
            "mae_improve_floor_pct": MAE_IMPROVE_FLOOR_PCT,
            "halves_min_pct": HALVES_MIN_PCT,
            "bins": [lab for _, _, lab in BINS],
            "regime_key": "state_fc.regime_synoptic",
            "halves_split": "chronological by obs_time",
        },
        "notes": (
            "Stage 1 candidate table — regime-conditional Lc bias shifts. "
            "Apply-side (Stage 3) reads cells[field][regime][bin] first; "
            "falls back to pooled_fallback[field][bin] if regime cell is "
            "THIN / SKIP / MARGIN; else no shift. Halves criterion: BOTH "
            "halves must improve by ≥ HALVES_MIN_PCT (stricter than Stage 0)."
        ),
        "cells": cells,
        "pooled_fallback": pooled_cells,
    }
    OUT_TABLE.parent.mkdir(parents=True, exist_ok=True)
    OUT_TABLE.write_text(json.dumps(payload, indent=2))

    # ── Text report ──
    out = []
    def p(*a):
        line = " ".join(str(x) for x in a)
        print(line)
        out.append(line)

    p("=" * 100)
    p("h_lc_regime_stage1 — halves-strict regime-conditional Lc fit")
    p("=" * 100)
    p(f"MIN_N={MIN_N}  MAG_FLOOR_PP={MAG_FLOOR_PP}  MAE_IMPROVE_FLOOR_PCT={MAE_IMPROVE_FLOOR_PCT}  HALVES_MIN_PCT={HALVES_MIN_PCT}")
    p(f"Halves split: chronological by obs_time (recent-anomaly contamination shows up as B < A)")
    p()

    # Verdict rollup
    p("Verdict rollup (regime-conditional cells):")
    for k in sorted(verdict_counts):
        p(f"  {k:<16} {verdict_counts[k]:>4}")
    p()

    # SHIP set by field
    p("=" * 100)
    p(f"SHIP set — {len(regime_ship_set)} regime-conditional cells:")
    p("=" * 100)
    by_field = defaultdict(list)
    for (f, r, b) in regime_ship_set:
        by_field[f].append((r, b))
    bin_idx = {lab: i for i, (_, _, lab) in enumerate(BINS)}
    for field in CLOUD_FIELDS:
        rows = sorted(by_field.get(field, []), key=lambda x: (x[0], bin_idx.get(x[1], 99)))
        if not rows:
            p(f"  {field}: (none)")
            continue
        p(f"  {field}: {len(rows)} cell(s)")
        for regime, lab in rows:
            cell = cells[field][regime][lab]
            hA = cell["halves"]["a_improve_pct"]
            hB = cell["halves"]["b_improve_pct"]
            p(f"    {regime:<12} {lab:<8}  n={cell['n']:>6,}  shift={cell['shift']:+7.2f}  "
              f"Δ={cell['improve_pct']:+6.1f}%  hA={hA:+5.1f}%  hB={hB:+5.1f}%")
    p()

    # Pooled-fallback SHIP set
    p("=" * 100)
    p(f"Pooled fallback SHIP — {len(pooled_ship_set)} cells (used when regime cell not SHIP):")
    p("=" * 100)
    for field in CLOUD_FIELDS:
        rows = sorted([b for (f, b) in pooled_ship_set if f == field], key=lambda b: bin_idx.get(b, 99))
        if not rows:
            p(f"  {field}: (none)")
            continue
        pairs = [f"{b}:{pooled_cells[field][b]['shift']:+.1f}" for b in rows]
        p(f"  {field}: " + "  ".join(pairs))
    p()

    # Gate history + verdict line
    gate = _append_gate_history({
        "fitted_at": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "verdict": "FIT" if regime_ship_set else "HOLD",
        "ship_count": len(regime_ship_set),
        "ship_set": sorted([[f, r, b] for (f, r, b) in regime_ship_set]),
    })

    p("=" * 100)
    p("Rolling 7-day gate:")
    p(f"  window: {gate['history_window_days']} days · runs seen: {gate['entries_in_window']} · "
      f"distinct days: {gate['days_in_window']}")
    p(f"  fit_days: {gate['fit_days']} · hold_days: {gate['hold_days']} · "
      f"latest FIT streak: {gate['latest_streak_fit']}")
    p(f"  SHIP-set stability: {'STABLE' if gate['stable'] else 'CHURN'} "
      f"(cells changed: {len(gate['cells_changed'])})")
    if gate["cells_changed"]:
        for c in gate["cells_changed"][:10]:
            p(f"    changed: {c}")
    p(f"  gate_clear: {gate['gate_clear']}   (requires ≥{GATE_WINDOW_DAYS} distinct days, "
      "no HOLD days, no SHIP-set changes)")
    p()

    # Final verdict line the digest picks up
    if not regime_ship_set:
        v = "VERDICT: NULL — no SHIP cells cleared halves-strict Stage 1."
    else:
        fields = sorted({f for (f, _, _) in regime_ship_set})
        v = (f"VERDICT: STAGE 1 PROMOTE — {len(regime_ship_set)} SHIP cells across "
             f"{len(fields)} field(s) {fields}. Ready for Stage 2 walk-forward stability "
             f"(currently day 1/{GATE_WINDOW_DAYS}; SHIP-set stability {'STABLE' if gate['stable'] else 'CHURN'}).")
    p(v)
    p("=" * 100)

    OUT_TXT.write_text("\n".join(out) + "\n")
    print(f"\nwrote {OUT_TABLE}")
    print(f"wrote {OUT_TXT}")
    return 0


def _append_gate_history(this_entry):
    try:
        history = json.loads(GATE_HISTORY_PATH.read_text())
    except FileNotFoundError:
        history = {"entries": []}
    except Exception as e:
        print(f"  ⚠ gate history load failed: {e} — starting fresh")
        history = {"entries": []}

    entries = history.get("entries", [])
    entries.append(this_entry)

    now = datetime.now()
    cutoff_ret = (now - timedelta(days=GATE_HISTORY_RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")
    entries = [e for e in entries if e.get("fitted_at", "") >= cutoff_ret]
    GATE_HISTORY_PATH.write_text(json.dumps({"entries": entries}, indent=2))

    cutoff_win = (now - timedelta(days=GATE_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M")
    window = [e for e in entries if e.get("fitted_at", "") >= cutoff_win]

    by_day = {}
    for e in window:
        day = e.get("fitted_at", "")[:10]
        if day:
            by_day.setdefault(day, []).append(e)

    fit_days = sum(1 for _, xs in by_day.items() if all(x.get("verdict") == "FIT" for x in xs))
    hold_days = len(by_day) - fit_days

    streak = 0
    for e in reversed(window):
        if e.get("verdict") == "FIT":
            streak += 1
        else:
            break

    current_ship = {tuple(x) for x in (this_entry.get("ship_set") or [])}
    cells_changed = []
    for e in reversed(window[:-1]):
        prior = {tuple(x) for x in (e.get("ship_set") or [])}
        for k in current_ship ^ prior:
            was = "SHIP" if k in prior else "not-SHIP"
            now_v = "SHIP" if k in current_ship else "not-SHIP"
            cells_changed.append((k, was, now_v))
    seen = set()
    dedup = []
    for c in cells_changed:
        if c[0] in seen:
            continue
        seen.add(c[0])
        dedup.append(c)

    stable = len(dedup) == 0
    gate_clear = (len(by_day) >= GATE_WINDOW_DAYS and hold_days == 0
                  and stable and len(current_ship) > 0)

    return {
        "entries_in_window": len(window),
        "days_in_window": len(by_day),
        "fit_days": fit_days,
        "hold_days": hold_days,
        "latest_streak_fit": streak,
        "stable": stable,
        "cells_changed": dedup,
        "gate_clear": gate_clear,
        "history_window_days": GATE_WINDOW_DAYS,
    }


if __name__ == "__main__":
    sys.exit(main())

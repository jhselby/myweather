#!/usr/bin/env python3
"""Fit the Lc (cloud saturation-unbiasing) correction table.

Lc is a domain-scoped specialist that sits post-L4, pre-Lsr. For each
cloud field (cc, cl, cm, ch), it stratifies the post-L4 forecast by
value bin and learns a signed shift per (field, bin) that pulls the
forecast toward the observed mean.

Fit input:   pair-log rows where field ∈ CLOUD_FIELDS and forecast_l4
             (or the deepest available lx) is available.
Fit output:  weather_collector/data/lc_correction_table.json — the
             per-(field, bin) shift, sample size, and MAE before/after
             shift, so the collector can decide per-cell whether to apply
             (SHIP), skip (SKIP), or defer (MARGINAL / thin).

Ship rule (per cell):
  n ≥ MIN_N                         AND
  |mean_bias| ≥ MAG_FLOOR (percentage points) AND
  post-shift MAE < pre-shift MAE by at least MAE_IMPROVE_FLOOR (%)

Cells that don't ship are logged with reason so the debug page can render
the applicability map cleanly.

Run:
    python3 -m analysis.lc_fit
    MYWEATHER_REFRESH=1 python3 -m analysis.lc_fit  # force pair-log refresh
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
OUT_PATH = Path(__file__).resolve().parent.parent / "weather_collector" / "data" / "lc_correction_table.json"

# Rolling gate history — appended each run, retained 30 days, checked over
# the last 7 days by the divergence report. Mirrors the .cache_l5_gate_history.json
# pattern; kept as a repo-root dotfile so it is committed with the codebase and
# survives across analysis sessions. Machine-enforces the 7-day live-layer change
# gate that `feedback_dont_over_gate` codifies (gate governs flips, not exploration).
GATE_HISTORY_PATH = Path(__file__).resolve().parent.parent / ".cache_lc_gate_history.json"
GATE_HISTORY_RETENTION_DAYS = 30
GATE_WINDOW_DAYS = 7

CLOUD_FIELDS = ["cc", "cl", "cm", "ch"]

# Same bins as h_cloud_floor_ceiling.py so the debug-page prose stays
# comparable across the two artifacts.
BINS = [
    (0,   5,      "0-5"),
    (5,   20,     "5-20"),
    (20,  50,     "20-50"),
    (50,  80,     "50-80"),
    (80,  95,     "80-95"),
    (95,  100.01, "95-100"),
]

MIN_N = 200               # per-cell sample floor
MAG_FLOOR_PP = 5.0        # per-cell |mean_bias| ≥ 5.0 pp to ship
MAE_IMPROVE_FLOOR_PCT = 2.0  # post-shift MAE must beat pre-shift by ≥ 2 %


def bin_of(v):
    for lo, hi, lab in BINS:
        if lo <= v < hi:
            return lab
    return None


def load_forecast_from_row(r):
    """Deepest-available forecast state, matching the runtime order Lc
    will see: post-L4 if present, otherwise deepest L3/L2/L1."""
    return (
        r.get("forecast_l4")
        or r.get("forecast_l3")
        or r.get("forecast_l2")
        or r.get("forecast_l1")
    )


def main():
    # (field, bin_label) → list of (fc, obs) pairs
    pairs = defaultdict(list)
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
            pairs[(field, b)].append((float(fc), float(obs)))
            rows_used += 1

    print(f"  rows read:  {rows_read:,}")
    print(f"  rows used:  {rows_used:,}  ({len(pairs)} (field, bin) cells populated)")
    print()

    cells = {f: {} for f in CLOUD_FIELDS}
    verdicts = {f: {} for f in CLOUD_FIELDS}
    print(f"{'field':<6} {'bin':<8} {'n':>7} {'mean_bias':>10} {'shift':>8} {'mae_pre':>9} {'mae_post':>10} {'Δ%':>7} {'verdict':<12}")
    print("-" * 90)

    for field in CLOUD_FIELDS:
        for lo, hi, lab in BINS:
            key = (field, lab)
            pair_list = pairs.get(key, [])
            n = len(pair_list)
            if n == 0:
                continue
            mean_bias = sum(fc - obs for fc, obs in pair_list) / n
            shift = -mean_bias  # subtract bias → move fc toward obs
            mae_pre = sum(abs(fc - obs) for fc, obs in pair_list) / n
            # Clamp corrected forecast to [0, 100] — Lc output feeds a
            # cloud-percentage field, so any shift that pushes past the
            # bounds is capped at the bound.
            def apply_shift(fc):
                return max(0.0, min(100.0, fc + shift))
            mae_post = sum(abs(apply_shift(fc) - obs) for fc, obs in pair_list) / n
            improve_pct = 100.0 * (mae_pre - mae_post) / mae_pre if mae_pre > 0 else 0.0

            # Verdict
            if n < MIN_N:
                verdict = "thin"
            elif abs(mean_bias) < MAG_FLOOR_PP:
                verdict = "SKIP"
            elif improve_pct < MAE_IMPROVE_FLOOR_PCT:
                verdict = "SKIP"
            elif improve_pct < 2 * MAE_IMPROVE_FLOOR_PCT:
                verdict = "MARGINAL"
            else:
                verdict = "SHIP"

            cells[field][lab] = {
                "n": n,
                "mean_bias": round(mean_bias, 3),
                "shift": round(shift, 3),
                "mae_pre": round(mae_pre, 3),
                "mae_post": round(mae_post, 3),
                "improve_pct": round(improve_pct, 2),
                "verdict": verdict,
            }
            verdicts[field][lab] = verdict

            print(f"{field:<6} {lab:<8} {n:>7,} {mean_bias:>+10.2f} {shift:>+8.2f} {mae_pre:>9.2f} {mae_post:>10.2f} {improve_pct:>+7.1f} {verdict:<12}")
        print()

    # Summary
    total = sum(len(cells[f]) for f in CLOUD_FIELDS)
    ship = sum(1 for f in CLOUD_FIELDS for c in cells[f].values() if c["verdict"] == "SHIP")
    marginal = sum(1 for f in CLOUD_FIELDS for c in cells[f].values() if c["verdict"] == "MARGINAL")
    skip = sum(1 for f in CLOUD_FIELDS for c in cells[f].values() if c["verdict"] == "SKIP")
    thin = sum(1 for f in CLOUD_FIELDS for c in cells[f].values() if c["verdict"] == "thin")
    print(f"Totals: {ship} SHIP, {marginal} MARGINAL, {skip} SKIP, {thin} thin (of {total} cells)")
    print()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "forecast_error_log.jsonl",
        "fit_rules": {
            "min_n": MIN_N,
            "magnitude_floor_pp": MAG_FLOOR_PP,
            "mae_improve_floor_pct": MAE_IMPROVE_FLOOR_PCT,
            "bins": [lab for _, _, lab in BINS],
        },
        "notes": (
            "Fit input = deepest available forecast_lN (l4 if present, "
            "else l3/l2/l1) — matches the runtime order Lc will see. "
            "Shift is signed: subtract from the L4-corrected forecast to "
            "unbias. Corrected value is clamped to [0, 100]. Only cells "
            "with verdict=SHIP should be applied by the collector."
        ),
        "cells": cells,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"wrote {OUT_PATH}")
    print()

    # Append this run to gate history + compute rolling 7-day status.
    gate = _append_and_summarize_gate_history({
        "fitted_at": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "verdict": "FIT" if ship > 0 else "HOLD",
        "ship_count": ship,
        "marginal_count": marginal,
        "skip_count": skip,
        "thin_count": thin,
        "verdicts": verdicts,
    })
    _print_gate_summary(gate)

    # Verdict line the digest can pick up
    if ship == 0:
        print("Verdict: HOLD — no cells cleared the SHIP gate.")
        return 0
    print(f"Verdict: FIT — {ship} SHIP cell(s) ready to wire into Lc.")
    return 0


def _append_and_summarize_gate_history(this_entry):
    """Append this run to .cache_lc_gate_history.json, prune to 30-day
    retention, then compute a 7-day rolling gate summary.

    Returns a dict:
      entries_in_window: count of runs in last 7 days
      fit_days / hold_days: day-level rollup (day is FIT only if EVERY run
        that day was FIT — same strictness as L5's rule)
      gate_clear: True when ≥7 distinct days present, no HOLD days, no
        SHIP-cell-set change over the window
      latest_streak_fit: trailing FIT-run streak
      ship_cell_stability: {"stable": True|False, "current_ship_cells": [...],
        "cells_changed_in_window": [(field, bin, from, to)]}
    """
    try:
        history = json.loads(GATE_HISTORY_PATH.read_text())
    except FileNotFoundError:
        history = {"entries": []}
    except Exception as e:
        print(f"  ⚠ gate history load failed: {e} — starting fresh")
        history = {"entries": []}

    entries = history.get("entries", [])
    entries.append(this_entry)

    # Prune retention.
    now = datetime.now()
    cutoff_ret = (now - timedelta(days=GATE_HISTORY_RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")
    entries = [e for e in entries if e.get("fitted_at", "") >= cutoff_ret]
    GATE_HISTORY_PATH.write_text(json.dumps({"entries": entries}, indent=2))

    # 7-day rolling window.
    cutoff_win = (now - timedelta(days=GATE_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M")
    window = [e for e in entries if e.get("fitted_at", "") >= cutoff_win]

    by_day = {}
    for e in window:
        day = e.get("fitted_at", "")[:10]
        if day:
            by_day.setdefault(day, []).append(e)

    fit_days = 0
    hold_days = 0
    for day, day_entries in by_day.items():
        if all(x.get("verdict") == "FIT" for x in day_entries):
            fit_days += 1
        else:
            hold_days += 1

    # Trailing FIT-run streak — newest first.
    streak = 0
    for e in reversed(window):
        if e.get("verdict") == "FIT":
            streak += 1
        else:
            break

    # Per-cell stability: has the SHIP set changed within the window?
    current_ship = _ship_set(this_entry.get("verdicts") or {})
    cells_changed = []
    seen_ship = current_ship
    for e in reversed(window[:-1]):  # exclude the entry we just appended
        prior = _ship_set(e.get("verdicts") or {})
        for k in current_ship ^ prior:
            was = "SHIP" if k in prior else "not-SHIP"
            now_v = "SHIP" if k in current_ship else "not-SHIP"
            cells_changed.append((k[0], k[1], was, now_v))
        # Only count the first change we find per cell — walking backward the
        # oldest visible diff wins. Simpler: dedup afterward.
    seen = set()
    dedup = []
    for c in cells_changed:
        key = (c[0], c[1])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(c)
    cells_changed = dedup

    stable = len(cells_changed) == 0
    gate_clear = len(by_day) >= GATE_WINDOW_DAYS and hold_days == 0 and stable

    return {
        "entries_in_window": len(window),
        "days_in_window": len(by_day),
        "fit_days": fit_days,
        "hold_days": hold_days,
        "gate_clear": gate_clear,
        "latest_streak_fit": streak,
        "ship_cell_stability": {
            "stable": stable,
            "current_ship_cells": sorted(current_ship),
            "cells_changed_in_window": cells_changed,
        },
        "history_window_days": GATE_WINDOW_DAYS,
    }


def _ship_set(verdicts_by_field):
    """Return the set of (field, bin) tuples with verdict SHIP."""
    return {
        (field, lab)
        for field, bins in verdicts_by_field.items()
        for lab, v in bins.items()
        if v == "SHIP"
    }


def _print_gate_summary(gate):
    """One-block print of the rolling gate state — for a human eyeballing
    the digest output, and for the divergence report to grep."""
    print("Lc 7-day rolling gate:")
    print(f"  window: {gate['history_window_days']} days · runs seen: {gate['entries_in_window']} · "
          f"distinct days: {gate['days_in_window']}")
    print(f"  fit_days: {gate['fit_days']} · hold_days: {gate['hold_days']} · "
          f"latest FIT streak: {gate['latest_streak_fit']}")
    stab = gate["ship_cell_stability"]
    print(f"  SHIP-cell stability: {'STABLE' if stab['stable'] else 'CHANGED'} · "
          f"current SHIP set: {len(stab['current_ship_cells'])} cells")
    if stab["cells_changed_in_window"]:
        print("  cells whose SHIP verdict changed within window:")
        for f, b, was, now_v in stab["cells_changed_in_window"]:
            print(f"    {f} {b}: {was} → {now_v}")
    print(f"  gate_clear: {gate['gate_clear']}   (requires ≥{GATE_WINDOW_DAYS} distinct days, "
          "no HOLD days, no SHIP-set changes)")
    print()


if __name__ == "__main__":
    sys.exit(main())

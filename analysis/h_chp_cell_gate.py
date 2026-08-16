#!/usr/bin/env python3
"""Stage 0/1: dynamic per-cell gate for chp (ch persistence gate).

Design intent [[project_chp_cell_skip_to_dynamic_gate]]: retire the
hand-curated `_CELL_SKIP` frozenset in ch_persistence_gate.py by
building a self-healing per-cell gate that suppresses chp on cells where
recent chp-vs-L6 performance says persistence loses to Lc.

Sibling design to [[project_lc_regime_conditional]] (Lc gate v0.6.413)
and [[project_lsr_recent_bias_gate]] (Lsr gate v0.6.420), adapted for
chp's different shape: chp is a substitution (persistence replaces L6),
not a shift, so the gate decision is "chp beats L6 recently?" rather
than "recent bias direction still matches historical?".

Source of truth for daily per-cell chp-vs-L6 Δ:
  ch_persistence_gate_curated_vs_l6.json
  (regenerated daily by h_ch_persistence_blend_stage2_vs_l6.py — 10-day
  window with 5+5 halves)

Per-cell 7-day gate rule (conservative — favors not-suppressing):
  * "chp lost to L6 today" = delta_full_pct > CHP_LOSS_THRESHOLD_PCT
  * gate_apply = False only if every one of the last GATE_WINDOW_DAYS
    distinct days recorded a loss for that cell.
  * Any single day of THIN, WIN, or missing history → gate_apply = True.

Emits:
  weather_collector/data/chp_cell_gate.json (runtime, ENABLED=False today)
  .cache_chp_cell_gate_history.json (per-cell history, retention 30d)

Runtime consumer (Stage 3, not shipped by this script):
  ch_persistence_gate.py adds CHP_CELL_GATE_ENABLED flag + _load_gate() +
  gate check inside _cell_fires — when ENABLED and per_cell[regime][band]
  .gate_apply is False, treat cell as skipped (falls to L6).

Run:
    python3 -m analysis.h_chp_cell_gate
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = Path(__file__).resolve().parent.parent
VS_L6_JSON = REPO / "weather_collector" / "data" / "ch_persistence_gate_curated_vs_l6.json"
LIVE_CURATED = REPO / "weather_collector" / "data" / "ch_persistence_gate_curated.json"
RUNTIME_TABLE_PATH = REPO / "weather_collector" / "data" / "chp_cell_gate.json"
HISTORY_PATH = REPO / ".cache_chp_cell_gate_history.json"

# Match h_ch_persistence_blend_stage2_vs_l6.MAE_IMPROVE_FLOOR_PCT: cells
# where chp beats L6 by <= 3% are considered wins-or-parity for gate purposes.
# Anything WORSE than +3% means chp materially loses vs Lc on that cell.
CHP_LOSS_THRESHOLD_PCT = 3.0

GATE_WINDOW_DAYS = 7
GATE_HISTORY_RETENTION_DAYS = 30
MIN_N_CELL = 100  # match vs_l6 script's own threshold


def _load_json(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"  ⚠ load failed for {path.name}: {e}")
        return None


def _cell_status(cell):
    """Classify today's per-cell verdict for gate history.

    Returns one of:
      'lose'  — chp materially loses to L6 (delta_full_pct > threshold)
      'win'   — chp beats L6 or parity (delta_full_pct <= threshold)
      'thin'  — insufficient sample or verdict THIN / missing
    """
    if not cell:
        return "thin"
    if cell.get("verdict") == "THIN":
        return "thin"
    n = cell.get("n") or 0
    if n < MIN_N_CELL:
        return "thin"
    d = cell.get("delta_full_pct")
    if d is None:
        return "thin"
    return "lose" if d > CHP_LOSS_THRESHOLD_PCT else "win"


def main():
    vs_l6 = _load_json(VS_L6_JSON)
    if not vs_l6:
        print(f"missing {VS_L6_JSON} — run h_ch_persistence_blend_stage2_vs_l6.py first")
        return
    live = _load_json(LIVE_CURATED) or {"cells": {}}
    live_cells = live.get("cells", {})

    cells_today = vs_l6.get("cells", {})
    generated_at = vs_l6.get("generated_at") or datetime.now(timezone.utc).isoformat()
    day = generated_at[:10]

    # Score today's per-cell status.
    per_cell_today = {}  # (regime, band) -> {'status', 'delta', 'n'}
    for regime, bands in cells_today.items():
        for band, cell in bands.items():
            status = _cell_status(cell)
            per_cell_today[(regime, band)] = {
                "status": status,
                "delta_full_pct": cell.get("delta_full_pct"),
                "n": cell.get("n"),
                "is_live_ship_or_margin": cell.get("is_live_ship_or_margin", False),
            }

    # Append today's per-cell reads to history.
    hist = _load_json(HISTORY_PATH) or {"entries": []}
    entries = hist.get("entries", [])
    # Idempotent by day: replace today's entry if we already ran today.
    entries = [e for e in entries if e.get("date") != day]
    entries.append({
        "date": day,
        "generated_at": generated_at,
        "per_cell": {
            f"{r}|{b}": v for (r, b), v in per_cell_today.items()
        },
    })
    # Retention.
    cutoff_ret = (datetime.now() - timedelta(days=GATE_HISTORY_RETENTION_DAYS)).strftime("%Y-%m-%d")
    entries = [e for e in entries if e.get("date", "") >= cutoff_ret]
    entries.sort(key=lambda e: e.get("date", ""))
    HISTORY_PATH.write_text(json.dumps({"entries": entries}, indent=2))

    # Per-cell 7-day gate decision.
    cutoff_win = (datetime.now() - timedelta(days=GATE_WINDOW_DAYS)).strftime("%Y-%m-%d")
    window = [e for e in entries if e.get("date", "") >= cutoff_win]
    days_in_window = sorted({e["date"] for e in window})

    # Universe: any cell that appeared in ANY window day. Includes THIN cells
    # so we can report per-cell streak "N losing days out of M seen."
    all_keys = set()
    for e in window:
        all_keys |= set(e.get("per_cell", {}).keys())

    def _series(key):
        """Return list of statuses aligned to days_in_window (None if missing)."""
        out = []
        for d in days_in_window:
            entry = next((e for e in window if e["date"] == d), None)
            if not entry:
                out.append(None); continue
            v = entry.get("per_cell", {}).get(key)
            out.append(v.get("status") if v else None)
        return out

    per_cell_runtime = defaultdict(dict)
    per_cell_report = []
    n_gated_off = 0
    for key in sorted(all_keys):
        r, b = key.split("|", 1)
        series = _series(key)
        n_seen = sum(1 for s in series if s is not None)
        n_lose = sum(1 for s in series if s == "lose")
        n_win = sum(1 for s in series if s == "win")
        n_thin = sum(1 for s in series if s == "thin")

        # Conservative decision: gate off ONLY if the window is full AND
        # every seen day is 'lose'. Missing days, thin days, or a single
        # win day → keep chp firing.
        cleared = (n_seen >= GATE_WINDOW_DAYS
                   and n_seen == GATE_WINDOW_DAYS
                   and n_lose == n_seen
                   and n_thin == 0)
        gate_apply = not cleared

        # Today's snapshot for the reader.
        today_v = per_cell_today.get((r, b), {})
        delta_today = today_v.get("delta_full_pct")
        n_today = today_v.get("n")
        is_live = today_v.get("is_live_ship_or_margin", False)

        per_cell_runtime[r][b] = {
            "gate_apply": bool(gate_apply),
            "cleared_off": bool(cleared),
            "days_seen": n_seen,
            "days_lose": n_lose,
            "days_win": n_win,
            "days_thin": n_thin,
            "today_delta_full_pct": delta_today,
            "today_n": n_today,
            "today_status": today_v.get("status"),
        }
        if cleared:
            n_gated_off += 1
        per_cell_report.append({
            "regime": r, "band": b, "series": series,
            "n_lose": n_lose, "n_win": n_win, "n_thin": n_thin,
            "n_seen": n_seen, "cleared": cleared, "gate_apply": gate_apply,
            "today_delta": delta_today, "today_n": n_today, "is_live": is_live,
        })

    # Report.
    print(f"chp cell gate — {day}")
    print(f"vs_l6 source: {generated_at}")
    print(f"window: {GATE_WINDOW_DAYS}d ({days_in_window[0] if days_in_window else 'empty'} → "
          f"{days_in_window[-1] if days_in_window else 'empty'})")
    print(f"per-cell threshold: chp loses to L6 when delta_full_pct > {CHP_LOSS_THRESHOLD_PCT}%")
    print()
    header = f"{'regime':<12} {'band':<7} {'live?':<6} {'series':<{max(1, len(days_in_window))*2+1}} {'seen':>5} {'lose':>5} {'win':>4} {'thin':>5} {'today':>10}  gate_apply"
    print(header)
    print("-" * len(header))
    for row in sorted(per_cell_report, key=lambda x: (x["regime"], x["band"])):
        # Render series as a compact string: L=lose, W=win, T=thin, .=missing.
        series_map = {"lose": "L", "win": "W", "thin": "T"}
        series_str = "".join(series_map.get(s, ".") for s in row["series"])
        today_s = f"{row['today_delta']:+6.1f}%" if row["today_delta"] is not None else "   n/a"
        gate_s = "OFF (cleared)" if row["cleared"] else "on"
        live_s = "LIVE" if row["is_live"] else "    "
        print(f"{row['regime']:<12} {row['band']:<7} {live_s:<6} {series_str:<{max(1,len(days_in_window))*2+1}} "
              f"{row['n_seen']:>5} {row['n_lose']:>5} {row['n_win']:>4} {row['n_thin']:>5} {today_s:>10}  {gate_s}")

    # Overlap with _CELL_SKIP frozenset (belt-and-suspenders comparison).
    # Load the runtime skip set inline — cheaper than importing the module.
    live_skip_cells = set()
    try:
        from weather_collector.processors.ch_persistence_gate import _CELL_SKIP  # type: ignore
        live_skip_cells = set(_CELL_SKIP)
    except Exception as e:
        print(f"\n  ⚠ could not import _CELL_SKIP for overlap check: {e}")

    print()
    print("=" * 100)
    print("OVERLAP WITH _CELL_SKIP (static frozenset — this gate exists to retire it):")
    print("=" * 100)
    cleared_cells = {(r, b) for r, bands in per_cell_runtime.items() for b, v in bands.items() if v["cleared_off"]}
    static_only = live_skip_cells - cleared_cells
    dynamic_only = cleared_cells - live_skip_cells
    both = live_skip_cells & cleared_cells
    print(f"  in _CELL_SKIP AND cleared by gate: {len(both)}  {sorted(both) if both else ''}")
    print(f"  in _CELL_SKIP but gate says 'on' : {len(static_only)}  {sorted(static_only) if static_only else ''}")
    print(f"  NOT in _CELL_SKIP but gate 'off' : {len(dynamic_only)}  {sorted(dynamic_only) if dynamic_only else ''}")
    print()
    print("Interpretation:")
    print("  - `in _CELL_SKIP but gate says 'on'` = cells hand-typed as scar tissue that")
    print("    the dynamic gate does NOT (yet) see as losers. Two reasons: cell recovered")
    print("    since being hand-added, OR insufficient history (day 1/7).")
    print("  - `NOT in _CELL_SKIP but gate 'off'` = cells the gate would suppress that")
    print("    haven't been hand-typed — the whole point of the dynamic gate.")

    # Verdict.
    print()
    print("=" * 100)
    print("STAGE 0/1 VERDICT:")
    print("=" * 100)
    if not days_in_window:
        v = "NULL — no history yet (this is day 1 of the walker)."
    elif n_gated_off == 0:
        v = (f"HOLD — no cell has cleared the {GATE_WINDOW_DAYS}-day all-lose gate today. "
             f"Walker at day {len(days_in_window)}/{GATE_WINDOW_DAYS} distinct dates.")
    else:
        v = (f"STAGE 1 PROMOTE — {n_gated_off} cell(s) cleared the {GATE_WINDOW_DAYS}-day gate. "
             f"Ready for Stage 3 wire in ch_persistence_gate.py (ship OFF, then flip).")
    print(f"  {v}")

    # Emit runtime table.
    runtime = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "h_chp_cell_gate.py",
        "vs_l6_source_generated_at": generated_at,
        "gate_window_days": GATE_WINDOW_DAYS,
        "chp_loss_threshold_pct": CHP_LOSS_THRESHOLD_PCT,
        "min_n_cell": MIN_N_CELL,
        "n_cells_gated_off": n_gated_off,
        "cells_cleared_off": sorted([f"{r}/{b}" for (r, b) in cleared_cells]),
        "static_cell_skip_overlap": {
            "both": sorted([f"{r}/{b}" for (r, b) in both]),
            "static_only": sorted([f"{r}/{b}" for (r, b) in static_only]),
            "dynamic_only": sorted([f"{r}/{b}" for (r, b) in dynamic_only]),
        },
        "per_cell": {r: dict(bands) for r, bands in per_cell_runtime.items()},
        "notes": (
            "Stage 3 wire contract: when CHP_CELL_GATE_ENABLED=True in "
            "ch_persistence_gate.py, treat any cell where "
            "per_cell[regime][band].gate_apply == False as skipped (falls "
            "to L6). This is a superset of the hand-curated _CELL_SKIP: "
            "once the dynamic gate has cleared and its `both` overlap "
            "matches _CELL_SKIP (or exceeds it), _CELL_SKIP can retire."
        ),
    }
    RUNTIME_TABLE_PATH.write_text(json.dumps(runtime, indent=2))
    print(f"\nwrote {RUNTIME_TABLE_PATH}")
    print(f"wrote {HISTORY_PATH}")


if __name__ == "__main__":
    main()

"""Shared harness — residual-persistence Stage 2 → Stage 3 promotion walker.

Extracted 2026-08-31 v0.6.529 to close the architectural gap surfaced during
today's telemetry sweep: wg and dp Stage 3 processors shipped in July via
manual review of Stage 2 output over ~7 days. No automated per-cell verdict
history existed. This walker mirrors the pattern established by
[[h_chp_cell_gate]] and [[h_lc_recent_bias_gate]] — a `.cache_{field}_...
_history.json` accumulator that tracks per-cell verdict daily and gates the
Stage 3 write on N/7 consecutive SHIP-or-MARGIN days.

Source of truth (per field):
  weather_collector/data/{field}_residual_persistence_curated.json
  (regenerated daily by h_{field}_residual_persistence_stage2.py)

Per-cell 7-day gate rule (conservative — favors not-wiring):
  * "positive today" = verdict in ("SHIP", "MARGIN")
  * cleared_for_wire = last GATE_WINDOW_DAYS distinct days ALL positive,
    with a full window seen (no missing days, no THIN).
  * A single SKIP or THIN day inside the window → not cleared.
  * A flip (yesterday SHIP/MARGIN, today SKIP/THIN) is called out separately.

Emits (per field):
  weather_collector/data/{field}_residual_persistence_walker.json (runtime,
    cleared cells + full per-cell state — no runtime consumer today; provides
    the read-shape a future Stage 3 wire will use to know which cells to
    enable without hand-editing the processor.)
  .cache_{field}_residual_persistence_walker_history.json (per-cell history,
    retention GATE_HISTORY_RETENTION_DAYS days.)
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

GATE_WINDOW_DAYS = 7
GATE_HISTORY_RETENTION_DAYS = 30
POSITIVE_VERDICTS = frozenset({"SHIP", "MARGIN"})


def _curated_path(field):
    return REPO / "weather_collector" / "data" / f"{field}_residual_persistence_curated.json"


def _runtime_path(field):
    return REPO / "weather_collector" / "data" / f"{field}_residual_persistence_walker.json"


def _history_path(field):
    return REPO / f".cache_{field}_residual_persistence_walker_history.json"


def _load_json(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"  ⚠ load failed for {path.name}: {e}", file=sys.stderr)
        return None


def _cells_from_curated(curated):
    """Return dict[(regime, band)] -> {'verdict', 'n', 'delta_full_pct'}.

    The Stage 2 emitter writes cells under `cells` keyed by regime with
    per-band sub-dicts; the wg/dp/h Stage 2 schema is identical."""
    out = {}
    cells = curated.get("cells") or {}
    for regime, bands in cells.items():
        if not isinstance(bands, dict):
            continue
        for band, cell in bands.items():
            if not isinstance(cell, dict):
                continue
            out[(regime, band)] = {
                "verdict": cell.get("verdict"),
                "n": cell.get("n"),
                "delta_full_pct": cell.get("delta_full_pct"),
            }
    return out


def run_walker(field):
    """Run the walker for `field`. Returns 0 on success, 1 on data-empty."""
    curated_path = _curated_path(field)
    curated = _load_json(curated_path)
    if not curated:
        print(f"missing {curated_path} — run h_{field}_residual_persistence_stage2.py first",
              file=sys.stderr)
        return 1

    generated_at = curated.get("generated_at") or datetime.now(timezone.utc).isoformat()
    day = generated_at[:10]
    per_cell_today = _cells_from_curated(curated)

    # Append today's per-cell reads to history (idempotent by day).
    history_path = _history_path(field)
    hist = _load_json(history_path) or {"entries": []}
    entries = [e for e in hist.get("entries", []) if e.get("date") != day]
    entries.append({
        "date": day,
        "generated_at": generated_at,
        "per_cell": {
            f"{r}|{b}": v for (r, b), v in per_cell_today.items()
        },
    })
    cutoff_ret = (datetime.now() - timedelta(days=GATE_HISTORY_RETENTION_DAYS)).strftime("%Y-%m-%d")
    entries = [e for e in entries if e.get("date", "") >= cutoff_ret]
    entries.sort(key=lambda e: e.get("date", ""))
    history_path.write_text(json.dumps({"entries": entries}, indent=2))

    # Gate window.
    cutoff_win = (datetime.now() - timedelta(days=GATE_WINDOW_DAYS)).strftime("%Y-%m-%d")
    window = [e for e in entries if e.get("date", "") >= cutoff_win]
    days_in_window = sorted({e["date"] for e in window})

    all_keys = set()
    for e in window:
        all_keys |= set(e.get("per_cell", {}).keys())

    def _series(key):
        out = []
        for d in days_in_window:
            entry = next((e for e in window if e["date"] == d), None)
            if not entry:
                out.append(None); continue
            v = entry.get("per_cell", {}).get(key)
            out.append(v.get("verdict") if v else None)
        return out

    per_cell_runtime = defaultdict(dict)
    report_rows = []
    n_cleared = 0
    n_flipped = 0
    for key in sorted(all_keys):
        r, b = key.split("|", 1)
        series = _series(key)
        n_seen = sum(1 for s in series if s is not None)
        n_pos = sum(1 for s in series if s in POSITIVE_VERDICTS)
        n_ship = sum(1 for s in series if s == "SHIP")
        n_margin = sum(1 for s in series if s == "MARGIN")
        n_skip = sum(1 for s in series if s == "SKIP")
        n_thin = sum(1 for s in series if s == "THIN")

        cleared = (n_seen == GATE_WINDOW_DAYS and n_pos == GATE_WINDOW_DAYS)

        # Flip detection: any (SHIP/MARGIN → SKIP/THIN) transition inside window.
        flipped = False
        for i in range(1, len(series)):
            prev, cur = series[i - 1], series[i]
            if prev in POSITIVE_VERDICTS and cur in ("SKIP", "THIN"):
                flipped = True; break

        today_v = per_cell_today.get((r, b), {})
        per_cell_runtime[r][b] = {
            "cleared_for_wire": bool(cleared),
            "flipped_in_window": bool(flipped),
            "days_seen": n_seen,
            "days_positive": n_pos,
            "days_ship": n_ship,
            "days_margin": n_margin,
            "days_skip": n_skip,
            "days_thin": n_thin,
            "today_verdict": today_v.get("verdict"),
            "today_n": today_v.get("n"),
            "today_delta_full_pct": today_v.get("delta_full_pct"),
        }
        if cleared: n_cleared += 1
        if flipped: n_flipped += 1
        report_rows.append({
            "regime": r, "band": b, "series": series,
            "n_seen": n_seen, "n_pos": n_pos, "n_ship": n_ship, "n_margin": n_margin,
            "n_skip": n_skip, "n_thin": n_thin, "cleared": cleared, "flipped": flipped,
            "today": today_v.get("verdict"),
        })

    # Report.
    print(f"{field} residual-persistence walker — {day}")
    print(f"curated source: {generated_at}")
    print(f"window: {GATE_WINDOW_DAYS}d ({days_in_window[0] if days_in_window else 'empty'} → "
          f"{days_in_window[-1] if days_in_window else 'empty'}), {len(days_in_window)} distinct day(s)")
    print(f"clear rule: {GATE_WINDOW_DAYS}/{GATE_WINDOW_DAYS} consecutive days in {{SHIP, MARGIN}}")
    print()

    series_w = max(1, len(days_in_window)) * 2 + 1
    header = (f"{'regime':<12} {'band':<7} {'series':<{series_w}} "
              f"{'seen':>5} {'ship':>5} {'marg':>5} {'skip':>5} {'thin':>5} "
              f"{'today':>7}  status")
    print(header)
    print("-" * len(header))
    vmap = {"SHIP": "S", "MARGIN": "M", "SKIP": "K", "THIN": "T"}
    for row in sorted(report_rows, key=lambda x: (x["regime"], x["band"])):
        series_str = "".join(vmap.get(s, ".") for s in row["series"])
        today_s = row["today"] or "—"
        if row["cleared"]:
            status = "✓ CLEARED"
        elif row["flipped"]:
            status = "⚠ FLIPPED"
        elif row["n_pos"] >= GATE_WINDOW_DAYS - 1:
            status = f"→ {row['n_pos']}/{GATE_WINDOW_DAYS}"
        else:
            status = ""
        print(f"{row['regime']:<12} {row['band']:<7} {series_str:<{series_w}} "
              f"{row['n_seen']:>5} {row['n_ship']:>5} {row['n_margin']:>5} "
              f"{row['n_skip']:>5} {row['n_thin']:>5} {today_s:>7}  {status}")

    print()
    print("=" * 100)
    print("WALKER VERDICT:")
    print("=" * 100)
    if not days_in_window:
        v = "NULL — no history yet (this is day 1)."
    elif len(days_in_window) < GATE_WINDOW_DAYS:
        v = (f"BUILDING — walker at day {len(days_in_window)}/{GATE_WINDOW_DAYS} distinct dates. "
             f"{n_cleared} cell(s) already track SHIP/MARGIN daily; "
             f"{n_flipped} cell(s) have flipped inside the window.")
    elif n_cleared == 0:
        v = (f"HOLD — window full ({GATE_WINDOW_DAYS}/{GATE_WINDOW_DAYS}) but no cell "
             f"has {GATE_WINDOW_DAYS}/{GATE_WINDOW_DAYS} consecutive positive days. "
             f"{n_flipped} cell(s) flipped inside window.")
    else:
        v = (f"STAGE 3 READY — {n_cleared} cell(s) cleared the {GATE_WINDOW_DAYS}-day gate. "
             f"Ready to write {field}_residual_persistence.py Stage 3 processor "
             f"(ship ENABLED=False, then flip via a live-layer gate).")
    print(f"  {v}")

    cleared_cells = sorted([f"{r}/{b}" for r, bands in per_cell_runtime.items()
                            for b, v in bands.items() if v["cleared_for_wire"]])
    flipped_cells = sorted([f"{r}/{b}" for r, bands in per_cell_runtime.items()
                            for b, v in bands.items() if v["flipped_in_window"]])
    if cleared_cells:
        print(f"  Cleared: {cleared_cells}")
    if flipped_cells:
        print(f"  Flipped: {flipped_cells}")

    runtime = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": f"_residual_persistence_walker.run_walker(field={field!r})",
        "curated_source_generated_at": generated_at,
        "gate_window_days": GATE_WINDOW_DAYS,
        "positive_verdicts": sorted(POSITIVE_VERDICTS),
        "n_cells_cleared": n_cleared,
        "n_cells_flipped": n_flipped,
        "cells_cleared_for_wire": cleared_cells,
        "cells_flipped_in_window": flipped_cells,
        "days_in_window": days_in_window,
        "per_cell": {r: dict(bands) for r, bands in per_cell_runtime.items()},
        "notes": (
            f"Stage 3 wire contract: when {field}_residual_persistence.py "
            f"reads this table, treat any cell where "
            f"per_cell[regime][band].cleared_for_wire == True as ship-eligible "
            f"(fires L2 + prior-14d residual correction). Cells not cleared "
            f"pass through unchanged. A flipped_in_window == True cell should "
            f"NOT be wired even if it re-clears later without operator review."
        ),
    }
    _runtime_path(field).write_text(json.dumps(runtime, indent=2))
    print(f"\nwrote {_runtime_path(field)}", file=sys.stderr)
    print(f"wrote {_history_path(field)}", file=sys.stderr)
    return 0

"""L1 selector by-regime — 7-day cell stability walker.

Sibling to `l1_selector_fit_by_regime.py`. That script fits a per-
(field, regime, band) diagnostic each run and flags cells where NBM Prod
beats HRRR Prod but the pooled-band selector picked HRRR (halves-stable,
n >= 60, lift >= 3.0%). This walker adds the temporal-stability layer
per [[feedback_whitelist_promotion_gate]] — a cell only becomes wire-
eligible after appearing in the flagged set on 7 consecutive daily reads.

Reads (upstream in the digest):
  analysis/l1_selector_by_regime_report.json

Writes:
  weather_collector/data/l1_selector_by_regime_walker.json
    (runtime shape; no consumer yet — future ship extends l1_selector.py
    to read this table and route NBM for cleared cells.)
  .cache_l1_selector_by_regime_walker_history.json
    (per-cell daily history, retention 30 days.)

Semantics:
  * "positive today" = cell present in today's masked_cells list
  * cleared_for_wire = 7/7 distinct dates in window all positive
  * flipped_in_window = present on earlier day, absent on later day
    within the same window. Flipped cells do not clear even if they
    re-appear later without operator review.

Runtime:
    python3 -m analysis.l1_selector_fit_by_regime_walker
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPORT_PATH = Path(__file__).resolve().parent / "l1_selector_by_regime_report.json"
RUNTIME_PATH = REPO / "weather_collector" / "data" / "l1_selector_by_regime_walker.json"
HISTORY_PATH = REPO / ".cache_l1_selector_by_regime_walker_history.json"

GATE_WINDOW_DAYS = 7
GATE_HISTORY_RETENTION_DAYS = 30


def _load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"  ⚠ load failed for {path}: {e}", file=sys.stderr)
        return None


def _cell_key(cell):
    return f"{cell['field']}|{cell['regime']}|{cell['band']}"


def run():
    report = _load_json(REPORT_PATH)
    if not report:
        print(f"missing {REPORT_PATH} — run l1_selector_fit_by_regime.py first",
              file=sys.stderr)
        return 1

    fitted_at = report.get("fitted_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    day = fitted_at[:10]
    masked = report.get("masked_cells") or []

    # Today's positive set + per-cell payload (kept for reporting).
    today_by_key = {_cell_key(c): {
        "field": c["field"], "regime": c["regime"], "band": c["band"],
        "lift_pct": c.get("lift_pct"), "n": c.get("n"),
        "half1_lift_pct": c.get("half1_lift_pct"),
        "half2_lift_pct": c.get("half2_lift_pct"),
    } for c in masked}

    # Append today's positive set to history (idempotent by day).
    hist = _load_json(HISTORY_PATH) or {"entries": []}
    entries = [e for e in hist.get("entries", []) if e.get("date") != day]
    entries.append({
        "date": day,
        "fitted_at": fitted_at,
        "positive": sorted(today_by_key.keys()),
        "payload": today_by_key,
    })
    cutoff_ret = (datetime.now() - timedelta(days=GATE_HISTORY_RETENTION_DAYS)).strftime("%Y-%m-%d")
    entries = [e for e in entries if e.get("date", "") >= cutoff_ret]
    entries.sort(key=lambda e: e.get("date", ""))
    HISTORY_PATH.write_text(json.dumps({"entries": entries}, indent=2))

    # Gate window.
    cutoff_win = (datetime.now() - timedelta(days=GATE_WINDOW_DAYS)).strftime("%Y-%m-%d")
    window = [e for e in entries if e.get("date", "") >= cutoff_win]
    days_in_window = sorted({e["date"] for e in window})

    all_keys = set()
    for e in window:
        all_keys |= set(e.get("positive", []))

    def _series(key):
        out = []
        for d in days_in_window:
            entry = next((e for e in window if e["date"] == d), None)
            out.append(bool(entry and key in entry.get("positive", [])))
        return out

    per_cell_runtime = defaultdict(lambda: defaultdict(dict))  # field -> regime -> band
    report_rows = []
    n_cleared = 0
    n_flipped = 0
    for key in sorted(all_keys):
        field, regime, band = key.split("|", 2)
        series = _series(key)
        n_seen = len(series)
        n_pos = sum(1 for s in series if s)

        cleared = (n_seen == GATE_WINDOW_DAYS and n_pos == GATE_WINDOW_DAYS)

        # Flip: any (True → False) inside window.
        flipped = any(series[i - 1] and not series[i] for i in range(1, len(series)))

        today = today_by_key.get(key, {})
        per_cell_runtime[field][regime][band] = {
            "cleared_for_wire": bool(cleared),
            "flipped_in_window": bool(flipped),
            "days_seen": n_seen,
            "days_positive": n_pos,
            "today_present": key in today_by_key,
            "today_lift_pct": today.get("lift_pct"),
            "today_n": today.get("n"),
            "today_half1_lift_pct": today.get("half1_lift_pct"),
            "today_half2_lift_pct": today.get("half2_lift_pct"),
        }
        if cleared:
            n_cleared += 1
        if flipped:
            n_flipped += 1
        report_rows.append({
            "field": field, "regime": regime, "band": band,
            "series": series, "n_seen": n_seen, "n_pos": n_pos,
            "cleared": cleared, "flipped": flipped,
            "today_lift_pct": today.get("lift_pct"),
            "today_n": today.get("n"),
        })

    # Report.
    print(f"L1 selector by-regime walker — {day}")
    print(f"diagnostic source: {fitted_at}")
    print(f"window: {GATE_WINDOW_DAYS}d "
          f"({days_in_window[0] if days_in_window else 'empty'} → "
          f"{days_in_window[-1] if days_in_window else 'empty'}), "
          f"{len(days_in_window)} distinct day(s)")
    print(f"clear rule: {GATE_WINDOW_DAYS}/{GATE_WINDOW_DAYS} consecutive days present in masked_cells")
    print()

    series_w = max(1, len(days_in_window)) + 2
    header = (f"{'field':<5} {'regime':<12} {'band':<7} {'series':<{series_w}} "
              f"{'seen':>5} {'pos':>5} {'lift%':>8} {'n':>6}  status")
    print(header)
    print("-" * len(header))
    for row in sorted(report_rows, key=lambda x: (x["field"], x["regime"], x["band"])):
        series_str = "".join("P" if s else "." for s in row["series"])
        if row["cleared"]:
            status = "✓ CLEARED"
        elif row["flipped"]:
            status = "⚠ FLIPPED"
        elif row["n_pos"] >= GATE_WINDOW_DAYS - 1:
            status = f"→ {row['n_pos']}/{GATE_WINDOW_DAYS}"
        else:
            status = ""
        lift_s = f"{row['today_lift_pct']:+.1f}" if row["today_lift_pct"] is not None else "—"
        n_s = f"{row['today_n']:,}" if row["today_n"] is not None else "—"
        print(f"{row['field']:<5} {row['regime']:<12} {row['band']:<7} "
              f"{series_str:<{series_w}} {row['n_seen']:>5} {row['n_pos']:>5} "
              f"{lift_s:>8} {n_s:>6}  {status}")

    print()
    print("=" * 100)
    print("WALKER VERDICT:")
    print("=" * 100)
    if not days_in_window:
        v = "NULL — no history yet (this is day 1)."
    elif len(days_in_window) < GATE_WINDOW_DAYS:
        v = (f"BUILDING — walker at day {len(days_in_window)}/{GATE_WINDOW_DAYS} distinct dates. "
             f"{n_cleared} cell(s) already track positive daily; "
             f"{n_flipped} cell(s) have flipped inside the window.")
    elif n_cleared == 0:
        v = (f"HOLD — window full ({GATE_WINDOW_DAYS}/{GATE_WINDOW_DAYS}) but no cell "
             f"has {GATE_WINDOW_DAYS}/{GATE_WINDOW_DAYS} consecutive positive days. "
             f"{n_flipped} cell(s) flipped inside window.")
    else:
        v = (f"WIRE READY — {n_cleared} cell(s) cleared the {GATE_WINDOW_DAYS}-day gate. "
             f"Ready to extend l1_selector.py to route NBM for these (field, regime, band) cells.")
    print(f"  {v}")

    cleared_cells = sorted([f"{f}/{r}/{b}"
                            for f, regs in per_cell_runtime.items()
                            for r, bands in regs.items()
                            for b, v in bands.items() if v["cleared_for_wire"]])
    flipped_cells = sorted([f"{f}/{r}/{b}"
                            for f, regs in per_cell_runtime.items()
                            for r, bands in regs.items()
                            for b, v in bands.items() if v["flipped_in_window"]])
    if cleared_cells:
        print(f"  Cleared: {cleared_cells}")
    if flipped_cells:
        print(f"  Flipped: {flipped_cells}")

    runtime = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "analysis/l1_selector_fit_by_regime_walker.py",
        "diagnostic_source_fitted_at": fitted_at,
        "gate_window_days": GATE_WINDOW_DAYS,
        "n_cells_cleared": n_cleared,
        "n_cells_flipped": n_flipped,
        "cells_cleared_for_wire": cleared_cells,
        "cells_flipped_in_window": flipped_cells,
        "days_in_window": days_in_window,
        "per_cell": {f: {r: dict(bands) for r, bands in regs.items()}
                     for f, regs in per_cell_runtime.items()},
        "notes": (
            "Wire contract: when l1_selector.py is extended to read this table, "
            "for any cell where per_cell[field][regime][band].cleared_for_wire == True, "
            "route NBM Prod instead of the pooled-band pick. Cells not cleared, or "
            "flipped_in_window == True, must not be wired without operator review."
        ),
    }
    RUNTIME_PATH.write_text(json.dumps(runtime, indent=2))
    print(f"\nwrote {RUNTIME_PATH}", file=sys.stderr)
    print(f"wrote {HISTORY_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(run())

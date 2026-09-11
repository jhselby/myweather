"""L1 selector by-regime — cell stability walker (3-day gate + window-sum n floor).

Sibling to `l1_selector_fit_by_regime.py`. That script fits a per-
(field, regime, band) diagnostic each run and flags cells where NBM Prod
beats HRRR Prod but the pooled-band selector picked HRRR (halves-stable,
n >= 60, lift >= 3.0%). This walker adds the temporal-stability layer
per [[feedback_whitelist_promotion_gate]] — a cell only becomes wire-
eligible after appearing in the flagged set on GATE_WINDOW_DAYS
consecutive daily reads AND having sum(n_today) across the window
>= WINDOW_SUM_N_MIN. The window-sum floor distinguishes a genuine
multi-day signal from a stuck-pattern flag on the 30-day rolling window,
while tolerating regime-quiet days where a given (regime, band) sees
zero paired samples in the rolling 24h read.

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
  * cleared_for_wire = GATE_WINDOW_DAYS/GATE_WINDOW_DAYS distinct dates
    in window all positive AND sum(payload n_today) across window
    >= WINDOW_SUM_N_MIN
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

GATE_WINDOW_DAYS = 3
GATE_HISTORY_RETENTION_DAYS = 30
# Window-total paired-sample floor. A cell must have at least this many
# pair-log samples SUMMED across the gate window's per-day rolling-24h
# n_today values. Per-day min was tried first (v0.6.566) but zeroed on
# any regime-quiet day — nw_flow, ne_flow and calm regimes routinely see
# 0 rolling-24h samples for a given lead band when the wind's from
# another quadrant, sinking cells with 600-2000 total 30d paired samples.
# Window-sum preserves the "reject 3-row streaks" intent while tolerating
# regime coverage gaps. See [[feedback_pooled_n_time_thin.md]] class.
WINDOW_SUM_N_MIN = 60

# The upstream diagnostic uses a 30d window over the pair log. The L1 selector
# refit landed 2026-08-31 10:15 UTC, so the diagnostic's baseline is mostly
# pre-refit for ~30 days after. Signal during that window is likely a pre-refit
# baseline artifact (same class that superseded [[project_nws_dp_promote_08_31]]).
# The 09-07 calendar re-check judges whether cells survive with 7+ days of post-
# refit data inside the diagnostic's window. Accumulation before this date is
# suppressed to avoid a wire flip on spurious positives.
NOT_BEFORE_DATE = "2026-09-07"


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

    if day < NOT_BEFORE_DATE:
        print(f"L1 selector by-regime walker — {day}")
        print(f"diagnostic source: {fitted_at}")
        print(f"SUPPRESSED — accumulation not_before {NOT_BEFORE_DATE} "
              f"(diagnostic window contains pre-refit selector baseline; "
              f"see NOT_BEFORE_DATE docstring).")
        print(f"  today's diagnostic flagged {len(masked)} cell(s); "
              f"not persisting to history until {NOT_BEFORE_DATE}.")
        return 0

    # Today's positive set + per-cell payload (kept for reporting).
    today_by_key = {_cell_key(c): {
        "field": c["field"], "regime": c["regime"], "band": c["band"],
        "lift_pct": c.get("lift_pct"), "n": c.get("n"),
        "n_today": c.get("n_today"),
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

    # Gate window — most recent GATE_WINDOW_DAYS entries in history.
    # A clock-based cutoff would count both today's entry and today-N
    # when both are present, yielding N+1 days and never clearing the
    # n_seen==N check.
    entries_sorted = sorted(entries, key=lambda e: e.get("date", ""))
    window = entries_sorted[-GATE_WINDOW_DAYS:]
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

    def _daily_ns(key):
        # Per-day n_today for this cell across the window. Missing (None or
        # absent — e.g. history entries written before n_today was plumbed)
        # is treated as 0 so the daily-n floor fails safely.
        out = []
        for d in days_in_window:
            entry = next((e for e in window if e["date"] == d), None)
            payload = (entry or {}).get("payload", {}) if entry else {}
            n = (payload.get(key) or {}).get("n_today")
            out.append(int(n) if n is not None else 0)
        return out

    per_cell_runtime = defaultdict(lambda: defaultdict(dict))  # field -> regime -> band
    report_rows = []
    n_cleared = 0
    n_flipped = 0
    for key in sorted(all_keys):
        field, regime, band = key.split("|", 2)
        series = _series(key)
        daily_ns = _daily_ns(key)
        n_seen = len(series)
        n_pos = sum(1 for s in series if s)
        min_daily_n_in_window = min(daily_ns) if daily_ns else 0
        sum_daily_n_in_window = sum(daily_ns) if daily_ns else 0
        enough_daily_n = sum_daily_n_in_window >= WINDOW_SUM_N_MIN

        cleared = (n_seen == GATE_WINDOW_DAYS
                   and n_pos == GATE_WINDOW_DAYS
                   and enough_daily_n)

        # Flip: any (True → False) inside window.
        flipped = any(series[i - 1] and not series[i] for i in range(1, len(series)))

        today = today_by_key.get(key, {})
        per_cell_runtime[field][regime][band] = {
            "cleared_for_wire": bool(cleared),
            "flipped_in_window": bool(flipped),
            "days_seen": n_seen,
            "days_positive": n_pos,
            "min_daily_n_in_window": min_daily_n_in_window,
            "sum_daily_n_in_window": sum_daily_n_in_window,
            "window_sum_n_required": WINDOW_SUM_N_MIN,
            "today_present": key in today_by_key,
            "today_lift_pct": today.get("lift_pct"),
            "today_n": today.get("n"),
            "today_n_today": today.get("n_today"),
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
            "min_daily_n": min_daily_n_in_window,
            "sum_daily_n": sum_daily_n_in_window,
            "enough_daily_n": enough_daily_n,
            "cleared": cleared, "flipped": flipped,
            "today_lift_pct": today.get("lift_pct"),
            "today_n": today.get("n"),
            "today_n_today": today.get("n_today"),
        })

    # Report.
    print(f"L1 selector by-regime walker — {day}")
    print(f"diagnostic source: {fitted_at}")
    print(f"window: {GATE_WINDOW_DAYS}d "
          f"({days_in_window[0] if days_in_window else 'empty'} → "
          f"{days_in_window[-1] if days_in_window else 'empty'}), "
          f"{len(days_in_window)} distinct day(s)")
    print(f"clear rule: {GATE_WINDOW_DAYS}/{GATE_WINDOW_DAYS} consecutive positive days "
          f"AND sum(n_today) across window >= {WINDOW_SUM_N_MIN}")
    print()

    series_w = max(1, len(days_in_window)) + 2
    header = (f"{'field':<5} {'regime':<12} {'band':<7} {'series':<{series_w}} "
              f"{'seen':>5} {'pos':>5} {'sum_dn':>7} {'lift%':>8} {'n':>6}  status")
    print(header)
    print("-" * len(header))
    for row in sorted(report_rows, key=lambda x: (x["field"], x["regime"], x["band"])):
        series_str = "".join("P" if s else "." for s in row["series"])
        if row["cleared"]:
            status = "✓ CLEARED"
        elif row["flipped"]:
            status = "⚠ FLIPPED"
        elif row["n_pos"] >= GATE_WINDOW_DAYS and not row["enough_daily_n"]:
            status = f"blocked: sum_dn={row['sum_daily_n']}<{WINDOW_SUM_N_MIN}"
        elif row["n_pos"] >= GATE_WINDOW_DAYS - 1:
            status = f"→ {row['n_pos']}/{GATE_WINDOW_DAYS}"
        else:
            status = ""
        lift_s = f"{row['today_lift_pct']:+.1f}" if row["today_lift_pct"] is not None else "—"
        n_s = f"{row['today_n']:,}" if row["today_n"] is not None else "—"
        sum_dn_s = f"{row['sum_daily_n']}"
        print(f"{row['field']:<5} {row['regime']:<12} {row['band']:<7} "
              f"{series_str:<{series_w}} {row['n_seen']:>5} {row['n_pos']:>5} "
              f"{sum_dn_s:>7} {lift_s:>8} {n_s:>6}  {status}")

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
             f"cleared: needs {GATE_WINDOW_DAYS}/{GATE_WINDOW_DAYS} consecutive positive days "
             f"AND sum(n_today) across window >= {WINDOW_SUM_N_MIN}. "
             f"{n_flipped} cell(s) flipped inside window.")
    else:
        v = (f"WIRE READY — {n_cleared} cell(s) cleared the {GATE_WINDOW_DAYS}-day gate "
             f"(sum(n_today) across window >= {WINDOW_SUM_N_MIN}). "
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
        "window_sum_n_min": WINDOW_SUM_N_MIN,
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

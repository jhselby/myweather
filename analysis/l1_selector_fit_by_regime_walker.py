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
    masked_hrrr = report.get("masked_cells_hrrr") or []

    if day < NOT_BEFORE_DATE:
        print(f"L1 selector by-regime walker — {day}")
        print(f"diagnostic source: {fitted_at}")
        print(f"SUPPRESSED — accumulation not_before {NOT_BEFORE_DATE} "
              f"(diagnostic window contains pre-refit selector baseline; "
              f"see NOT_BEFORE_DATE docstring).")
        print(f"  today's diagnostic flagged NBM-wire {len(masked)} + "
              f"HRRR-wire {len(masked_hrrr)} cell(s); "
              f"not persisting to history until {NOT_BEFORE_DATE}.")
        return 0

    def _payload(c):
        return {
            "field": c["field"], "regime": c["regime"], "band": c["band"],
            "lift_pct": c.get("lift_pct"), "n": c.get("n"),
            "n_today": c.get("n_today"),
            "half1_lift_pct": c.get("half1_lift_pct"),
            "half2_lift_pct": c.get("half2_lift_pct"),
        }

    # Today's positive sets + per-cell payload (kept for reporting).
    # Two directions tracked independently under the same gate.
    today_by_key = {_cell_key(c): _payload(c) for c in masked}
    today_by_key_hrrr = {_cell_key(c): _payload(c) for c in masked_hrrr}

    # Append today's positive set to history (idempotent by day).
    hist = _load_json(HISTORY_PATH) or {"entries": []}
    entries = [e for e in hist.get("entries", []) if e.get("date") != day]
    entries.append({
        "date": day,
        "fitted_at": fitted_at,
        "positive": sorted(today_by_key.keys()),
        "payload": today_by_key,
        "positive_hrrr": sorted(today_by_key_hrrr.keys()),
        "payload_hrrr": today_by_key_hrrr,
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

    def _direction_evaluate(positive_key, payload_key, today_lookup):
        """Run gate evaluation for one direction. Returns
        (per_cell_runtime_updates, report_rows, n_cleared, n_flipped,
         cleared_cells, flipped_cells)."""
        all_keys = set()
        for e in window:
            all_keys |= set(e.get(positive_key, []))

        def _series(key):
            out = []
            for d in days_in_window:
                entry = next((e for e in window if e["date"] == d), None)
                out.append(bool(entry and key in entry.get(positive_key, [])))
            return out

        def _daily_ns(key):
            out = []
            for d in days_in_window:
                entry = next((e for e in window if e["date"] == d), None)
                payload = (entry or {}).get(payload_key, {}) if entry else {}
                n = (payload.get(key) or {}).get("n_today")
                out.append(int(n) if n is not None else 0)
            return out

        per_cell = {}   # key -> per-cell dict
        rows = []
        cleared_ct = 0
        flipped_ct = 0
        for key in sorted(all_keys):
            series = _series(key)
            daily_ns = _daily_ns(key)
            n_seen = len(series)
            n_pos = sum(1 for s in series if s)
            min_dn = min(daily_ns) if daily_ns else 0
            sum_dn = sum(daily_ns) if daily_ns else 0
            enough_dn = sum_dn >= WINDOW_SUM_N_MIN

            cleared = (n_seen == GATE_WINDOW_DAYS
                       and n_pos == GATE_WINDOW_DAYS
                       and enough_dn)
            flipped = any(series[i - 1] and not series[i] for i in range(1, len(series)))

            today = today_lookup.get(key, {})
            per_cell[key] = {
                "cleared": bool(cleared),
                "flipped": bool(flipped),
                "days_seen": n_seen,
                "days_positive": n_pos,
                "min_daily_n_in_window": min_dn,
                "sum_daily_n_in_window": sum_dn,
                "window_sum_n_required": WINDOW_SUM_N_MIN,
                "today_present": key in today_lookup,
                "today_lift_pct": today.get("lift_pct"),
                "today_n": today.get("n"),
                "today_n_today": today.get("n_today"),
                "today_half1_lift_pct": today.get("half1_lift_pct"),
                "today_half2_lift_pct": today.get("half2_lift_pct"),
            }
            if cleared: cleared_ct += 1
            if flipped: flipped_ct += 1
            rows.append({
                "field": key.split("|", 2)[0],
                "regime": key.split("|", 2)[1],
                "band": key.split("|", 2)[2],
                "series": series, "n_seen": n_seen, "n_pos": n_pos,
                "min_daily_n": min_dn,
                "sum_daily_n": sum_dn,
                "enough_daily_n": enough_dn,
                "cleared": cleared, "flipped": flipped,
                "today_lift_pct": today.get("lift_pct"),
                "today_n": today.get("n"),
                "today_n_today": today.get("n_today"),
            })
        return per_cell, rows, cleared_ct, flipped_ct

    # Direction 1: NBM-wire (pooled=HRRR, regime says NBM helps).
    per_cell_nbm, report_rows, n_cleared, n_flipped = _direction_evaluate(
        "positive", "payload", today_by_key)
    # Direction 2: HRRR-wire (pooled=NBM, regime says HRRR helps). Symmetric gate.
    per_cell_hrrr, report_rows_hrrr, n_cleared_hrrr, n_flipped_hrrr = _direction_evaluate(
        "positive_hrrr", "payload_hrrr", today_by_key_hrrr)

    # Fold per-cell dicts into runtime structure: field -> regime -> band -> {wire_dir: dict}.
    per_cell_runtime = defaultdict(lambda: defaultdict(dict))
    for key, v in per_cell_nbm.items():
        field, regime, band = key.split("|", 2)
        per_cell_runtime[field][regime].setdefault(band, {})
        per_cell_runtime[field][regime][band]["nbm"] = v
        # Back-compat: top-level cleared_for_wire/flipped_in_window keep NBM-direction
        # semantics so existing l1_selector.pick_source() consumers keep working
        # without modification. HRRR-direction lives under ["hrrr"] sub-key.
        per_cell_runtime[field][regime][band]["cleared_for_wire"] = v["cleared"]
        per_cell_runtime[field][regime][band]["flipped_in_window"] = v["flipped"]
        per_cell_runtime[field][regime][band]["days_seen"] = v["days_seen"]
        per_cell_runtime[field][regime][band]["days_positive"] = v["days_positive"]
        per_cell_runtime[field][regime][band]["min_daily_n_in_window"] = v["min_daily_n_in_window"]
        per_cell_runtime[field][regime][band]["sum_daily_n_in_window"] = v["sum_daily_n_in_window"]
        per_cell_runtime[field][regime][band]["window_sum_n_required"] = v["window_sum_n_required"]
        per_cell_runtime[field][regime][band]["today_present"] = v["today_present"]
        per_cell_runtime[field][regime][band]["today_lift_pct"] = v["today_lift_pct"]
        per_cell_runtime[field][regime][band]["today_n"] = v["today_n"]
        per_cell_runtime[field][regime][band]["today_n_today"] = v["today_n_today"]
        per_cell_runtime[field][regime][band]["today_half1_lift_pct"] = v["today_half1_lift_pct"]
        per_cell_runtime[field][regime][band]["today_half2_lift_pct"] = v["today_half2_lift_pct"]
    for key, v in per_cell_hrrr.items():
        field, regime, band = key.split("|", 2)
        per_cell_runtime[field][regime].setdefault(band, {})
        per_cell_runtime[field][regime][band]["hrrr"] = v
        # New keys for HRRR direction (no back-compat concern — no consumer yet).
        per_cell_runtime[field][regime][band]["cleared_for_wire_hrrr"] = v["cleared"]
        per_cell_runtime[field][regime][band]["flipped_in_window_hrrr"] = v["flipped"]

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

    def _print_direction(label, rows):
        print()
        print(f"--- {label} ---")
        header = (f"{'field':<5} {'regime':<12} {'band':<7} {'series':<{series_w}} "
                  f"{'seen':>5} {'pos':>5} {'sum_dn':>7} {'lift%':>8} {'n':>6}  status")
        print(header)
        print("-" * len(header))
        if not rows:
            print("(no candidates)")
            return
        for row in sorted(rows, key=lambda x: (x["field"], x["regime"], x["band"])):
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

    _print_direction("NBM-wire (pooled=HRRR, regime says NBM helps)", report_rows)
    _print_direction("HRRR-wire (pooled=NBM, regime says HRRR helps)", report_rows_hrrr)

    print()
    print("=" * 100)
    print("WALKER VERDICT:")
    print("=" * 100)
    if not days_in_window:
        v = "NULL — no history yet (this is day 1)."
    elif len(days_in_window) < GATE_WINDOW_DAYS:
        v = (f"BUILDING — walker at day {len(days_in_window)}/{GATE_WINDOW_DAYS} distinct dates. "
             f"NBM-wire {n_cleared} cleared / {n_flipped} flipped; "
             f"HRRR-wire {n_cleared_hrrr} cleared / {n_flipped_hrrr} flipped.")
    elif n_cleared == 0 and n_cleared_hrrr == 0:
        v = (f"HOLD — window full ({GATE_WINDOW_DAYS}/{GATE_WINDOW_DAYS}) but no cell "
             f"cleared either direction. NBM-wire {n_flipped} flipped; "
             f"HRRR-wire {n_flipped_hrrr} flipped.")
    else:
        v = (f"WIRE READY — {n_cleared} NBM-wire + {n_cleared_hrrr} HRRR-wire cell(s) "
             f"cleared the {GATE_WINDOW_DAYS}-day gate "
             f"(sum(n_today) across window >= {WINDOW_SUM_N_MIN}). "
             f"l1_selector routes cleared cells with precedence over pooled band pick.")
    print(f"  {v}")

    cleared_cells = sorted([f"{f}/{r}/{b}"
                            for f, regs in per_cell_runtime.items()
                            for r, bands in regs.items()
                            for b, v in bands.items() if v.get("cleared_for_wire")])
    flipped_cells = sorted([f"{f}/{r}/{b}"
                            for f, regs in per_cell_runtime.items()
                            for r, bands in regs.items()
                            for b, v in bands.items() if v.get("flipped_in_window")])
    cleared_cells_hrrr = sorted([f"{f}/{r}/{b}"
                                 for f, regs in per_cell_runtime.items()
                                 for r, bands in regs.items()
                                 for b, v in bands.items() if v.get("cleared_for_wire_hrrr")])
    flipped_cells_hrrr = sorted([f"{f}/{r}/{b}"
                                 for f, regs in per_cell_runtime.items()
                                 for r, bands in regs.items()
                                 for b, v in bands.items() if v.get("flipped_in_window_hrrr")])
    if cleared_cells:
        print(f"  NBM-wire cleared: {cleared_cells}")
    if flipped_cells:
        print(f"  NBM-wire flipped: {flipped_cells}")
    if cleared_cells_hrrr:
        print(f"  HRRR-wire cleared: {cleared_cells_hrrr}")
    if flipped_cells_hrrr:
        print(f"  HRRR-wire flipped: {flipped_cells_hrrr}")

    runtime = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "analysis/l1_selector_fit_by_regime_walker.py",
        "diagnostic_source_fitted_at": fitted_at,
        "gate_window_days": GATE_WINDOW_DAYS,
        "window_sum_n_min": WINDOW_SUM_N_MIN,
        "n_cells_cleared": n_cleared,
        "n_cells_flipped": n_flipped,
        "n_cells_cleared_hrrr": n_cleared_hrrr,
        "n_cells_flipped_hrrr": n_flipped_hrrr,
        "cells_cleared_for_wire": cleared_cells,
        "cells_flipped_in_window": flipped_cells,
        "cells_cleared_for_wire_hrrr": cleared_cells_hrrr,
        "cells_flipped_in_window_hrrr": flipped_cells_hrrr,
        "days_in_window": days_in_window,
        "per_cell": {f: {r: dict(bands) for r, bands in regs.items()}
                     for f, regs in per_cell_runtime.items()},
        "notes": (
            "Wire contract (two-directional): for any (field, regime, band) cell where "
            "per_cell[field][regime][band].cleared_for_wire == True (and flipped_in_window "
            "== False), route NBM Prod. Where cleared_for_wire_hrrr == True (and "
            "flipped_in_window_hrrr == False), route HRRR Prod. Both take precedence over "
            "the pooled-band pick. NBM-wire and HRRR-wire are mutually exclusive by "
            "construction (a cell can't have both halves >0 and both halves <0)."
        ),
    }
    RUNTIME_PATH.write_text(json.dumps(runtime, indent=2))
    print(f"\nwrote {RUNTIME_PATH}", file=sys.stderr)
    print(f"wrote {HISTORY_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(run())

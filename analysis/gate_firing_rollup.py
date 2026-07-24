#!/usr/bin/env python3
"""Gate-firing rollup — Phase (b) of the operator dormancy audit.

Reads gate_firing_log.jsonl from GCS (produced per-tick by Phase (a) —
weather_collector/processors/gate_firing_log.py) and aggregates a 7-day
rolling window into gate_firing_rollup.json. Answers the question:
"which operator × field × regime cells are actually firing right now?"

Phase (a) definition of "fired": correction actually mutated the array,
not "would have applied." That distinction is what makes this useful vs.
the applied-layer audit (which is static config coherence).

Output shape:
{
  "generated_at": "...",
  "window_days": 7,
  "window_start": "...", "window_end": "...",
  "tick_count": 1008,
  "by_operator_field_regime": {
    "L3": {
      "ws": {
        "sea_breeze": {"fires": 3400, "skips": 850, "ticks": 170, ...},
        "ne_flow":    {"fires": 0,    "skips": 5280, "ticks": 110, ...},
        ...
      }
    }
  },
  "dormancy_flags": {
    "operators_never_fired": [...],
    "operator_field_pairs_never_fired": [[operator, field], ...],
    "operator_field_regime_never_fired_with_nonzero_ticks": [
      [operator, field, regime, tick_count]
    ]
  }
}

Non-goals:
  - Publish to GCS. That's Phase (c) / consumer's problem.
  - Alert on dormancy. Downstream layer (digest) reads the output and
    decides what to flag.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path


LOG_URL = "https://data.wymancove.com/gate_firing_log.jsonl"
OUTPUT_JSON = os.path.join(os.path.dirname(__file__), "output",
                           "gate_firing_rollup.json")
WINDOW_DAYS = 7


def _load_rows():
    path = cached_path(LOG_URL)
    rows = []
    with open(path, "rb") as fh:
        for raw in fh:
            try:
                rows.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return rows


def _tick_window_bounds(rows, window_days):
    """Return (window_start, window_end) as minute-truncated ISO strings.
    Window ends at the latest tick in the log; starts window_days before it."""
    if not rows:
        return None, None
    end_tick = max(r.get("tick", "") for r in rows if r.get("tick"))
    if not end_tick:
        return None, None
    try:
        end_dt = datetime.fromisoformat(end_tick)
    except (TypeError, ValueError):
        return None, None
    start_dt = end_dt - timedelta(days=window_days)
    return start_dt.strftime("%Y-%m-%dT%H:%M"), end_dt.strftime("%Y-%m-%dT%H:%M")


def aggregate(rows, window_start, window_end):
    """Fold rows into per-(operator, field, regime) counts.

    Also tracks per-(operator, regime) tick counts so the fire_rate
    denominator is meaningful (a tick counts once toward a regime bucket
    whether or not a specific field fired within it)."""
    # (operator, field, regime) -> {fires, skips, ticks_in_this_slot}
    cell = defaultdict(lambda: {"fires": 0, "skips": 0, "ticks": 0})
    # (operator, regime) -> ticks — used as denominator when a field
    # never fired in that regime (so 0 fires / N ticks distinguishes
    # "operator ran N ticks in this regime and field never fired" from
    # "operator never ran in this regime at all").
    op_regime_ticks = defaultdict(int)
    # Ticks that actually landed in the window (dedup by tick timestamp).
    seen_ticks = set()

    for r in rows:
        tick = r.get("tick")
        if not tick or not (window_start <= tick <= window_end):
            continue
        operator = r.get("operator")
        regime = r.get("regime")
        by_field = r.get("by_field") or {}
        if not operator:
            continue
        seen_ticks.add(tick)
        op_regime_ticks[(operator, regime)] += 1
        for field, counts in by_field.items():
            fires = counts.get("fires", 0) or 0
            skips = counts.get("skips", 0) or 0
            c = cell[(operator, field, regime)]
            c["fires"] += fires
            c["skips"] += skips
            c["ticks"] += 1

    return cell, op_regime_ticks, len(seen_ticks)


def build_output(cell, op_regime_ticks, tick_count, window_start, window_end):
    # Nested output
    by_ofr = defaultdict(lambda: defaultdict(dict))
    all_operators = set()
    op_to_fields = defaultdict(set)
    for (operator, field, regime), c in cell.items():
        denom = op_regime_ticks.get((operator, regime), c["ticks"])
        fire_rate = round(c["fires"] / denom, 3) if denom else 0.0
        by_ofr[operator][field][regime or "None"] = {
            "fires": c["fires"],
            "skips": c["skips"],
            "ticks_in_regime": denom,
            "fire_rate_per_tick": fire_rate,
        }
        all_operators.add(operator)
        op_to_fields[operator].add(field)

    # Dormancy flags
    operators_never_fired = []
    op_field_never_fired = []
    op_field_regime_never_fired = []
    for operator in sorted(all_operators):
        op_total_fires = sum(
            r["fires"] for f in by_ofr[operator].values() for r in f.values()
        )
        if op_total_fires == 0:
            operators_never_fired.append(operator)
            continue
        for field in sorted(op_to_fields[operator]):
            field_total = sum(r["fires"] for r in by_ofr[operator][field].values())
            if field_total == 0:
                op_field_never_fired.append([operator, field])
                continue
            for regime, r in by_ofr[operator][field].items():
                if r["fires"] == 0 and r["ticks_in_regime"] >= 5:
                    op_field_regime_never_fired.append(
                        [operator, field, regime, r["ticks_in_regime"]]
                    )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window_days": WINDOW_DAYS,
        "window_start": window_start,
        "window_end": window_end,
        "tick_count": tick_count,
        "by_operator_field_regime": {op: dict(v) for op, v in by_ofr.items()},
        "dormancy_flags": {
            "operators_never_fired": operators_never_fired,
            "operator_field_pairs_never_fired": op_field_never_fired,
            "operator_field_regime_never_fired_with_nonzero_ticks":
                op_field_regime_never_fired,
        },
    }


def print_summary(out):
    print(f"gate-firing rollup — {out['window_start']} → {out['window_end']}")
    print(f"  tick_count: {out['tick_count']}   window_days: {out['window_days']}")
    print()
    for operator in sorted(out["by_operator_field_regime"]):
        print(f"[{operator}]")
        for field in sorted(out["by_operator_field_regime"][operator]):
            print(f"  {field}")
            for regime in sorted(out["by_operator_field_regime"][operator][field]):
                r = out["by_operator_field_regime"][operator][field][regime]
                marker = " ★" if r["fires"] == 0 and r["ticks_in_regime"] >= 5 else ""
                print(f"    {regime:<15} fires={r['fires']:>6}  "
                      f"skips={r['skips']:>6}  "
                      f"ticks={r['ticks_in_regime']:>4}  "
                      f"rate/tick={r['fire_rate_per_tick']:>5.2f}{marker}")

    print()
    flags = out["dormancy_flags"]
    # Expected-dormant allowlist. Anything listed here fires the "expected" bucket
    # instead of the ⚠ bucket. Keep the reason inline so it's obvious when to remove.
    EXPECTED_DORMANT_OPERATORS = {
        "Lt":  "retired 2026-07-13 (Fix B refit +0.29% held-out, below +1.0% gate)",
        "MLC": "marine-layer cc sandbox, ENABLED=False, waiting on trend to hold",
        "Lsb": "sr sea_breeze cc-gated Lsr override, shipped 2026-07-17 v0.6.354 ENABLED=False; halves re-run 07-24",
        "ch_persistence_gate":   "shipped 2026-07-12 v0.6.327 with ENABLED=False; 7-day gate, earliest flip 07-19",
        "cl_persistence_gate": "shipped 2026-07-24 v0.6.379 with ENABLED=False (successor to cl_persistence_short_lead — narrow 0-5h shape retired); 7-day gate, flip earliest 07-31",
    }
    EXPECTED_DORMANT_PAIRS = {
        ("C1h", "t"): "REDUND to both C1f and C1e per co-axis ortho gate (v0.6.321); designed never to fire",
    }
    # (operator, field, regime) triples that are designed skips — SKIP_TABLE
    # entries in decay_apply.py, Lsr regime skip list, C1h co-axis gate skips.
    # Keep the reason inline so it's obvious when to remove.
    EXPECTED_DORMANT_CELLS = {
        ("L3", "ws", "ne_flow"):       "SKIP_TABLE (decay_apply.py v0.6.279): ws L3 skipped in ne_flow all bands",
        ("Lsr", "sr", "ne_flow"):      "Lsr skip regime (solar_correction.py v0.6.280): sr Lsr off in ne_flow",
        ("Lsr", "sr", "calm"):         "Lsr skip regime (solar_correction.py v0.6.280): sr Lsr off in calm",
        ("C1h", "ch", "ne_flow"):      "co-axis ortho gate (confidence_layer.py v0.6.321): ch/ne_flow REDUND",
    }

    ops_unexpected = [op for op in flags["operators_never_fired"] if op not in EXPECTED_DORMANT_OPERATORS]
    ops_expected   = [op for op in flags["operators_never_fired"] if op in EXPECTED_DORMANT_OPERATORS]
    pairs_unexpected = [(o,f) for o,f in flags["operator_field_pairs_never_fired"] if (o,f) not in EXPECTED_DORMANT_PAIRS]
    pairs_expected   = [(o,f) for o,f in flags["operator_field_pairs_never_fired"] if (o,f) in EXPECTED_DORMANT_PAIRS]
    cells_flagged = flags["operator_field_regime_never_fired_with_nonzero_ticks"]
    cells_unexpected = [(o,f,r,nt) for o,f,r,nt in cells_flagged if (o,f,r) not in EXPECTED_DORMANT_CELLS]
    cells_expected   = [(o,f,r,nt) for o,f,r,nt in cells_flagged if (o,f,r) in EXPECTED_DORMANT_CELLS]

    print("DORMANCY FLAGS")
    if ops_unexpected or pairs_unexpected or cells_unexpected:
        print("  ⚠ UNEXPECTED (action needed):")
        if ops_unexpected:
            print(f"    Operators never fired: {ops_unexpected}")
        if pairs_unexpected:
            print(f"    Operator+field pairs never fired ({len(pairs_unexpected)}):")
            for op, f in pairs_unexpected:
                print(f"      {op}/{f}")
        if cells_unexpected:
            print(f"    Operator+field never fired in regime that DID run (≥5 ticks) — silent dormancy candidates:")
            for op, f, r, nt in cells_unexpected:
                print(f"      {op}/{f}/{r} — {nt} ticks in that regime, 0 fires")
    else:
        print("  ⚠ UNEXPECTED: none")

    if ops_expected or pairs_expected or cells_expected:
        print("  ✓ EXPECTED (waiting on gate / designed dormant):")
        for op in ops_expected:
            print(f"    {op} — {EXPECTED_DORMANT_OPERATORS[op]}")
        for op, f in pairs_expected:
            print(f"    {op}/{f} — {EXPECTED_DORMANT_PAIRS[(op, f)]}")
        for op, f, r, nt in cells_expected:
            print(f"    {op}/{f}/{r} — {EXPECTED_DORMANT_CELLS[(op, f, r)]}")

    if not any(flags.values()):
        print("  none — every declared operator × field × regime fired at least once")


def _upload_to_gcs(out):
    """Publish the rollup to GCS so the debug page can fetch it via
    https://data.wymancove.com/gate_firing_rollup.json. Runs from Joe's Mac
    in the digest; Cloud Function collector doesn't need write access here.
    Silent no-op on any failure — the local artifact still lands."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from weather_collector.gcs_io import upload_json
        upload_json(out, "gate_firing_rollup.json", "gate_firing_rollup.json")
        print("  ✓ Published to gs://myweather-data/gate_firing_rollup.json")
    except Exception as e:
        print(f"  ⚠ GCS upload skipped ({type(e).__name__}: {e}) — local file still written")


def main():
    rows = _load_rows()
    if not rows:
        print("no rows in gate_firing_log.jsonl yet")
        return
    window_start, window_end = _tick_window_bounds(rows, WINDOW_DAYS)
    if window_start is None:
        print("cannot determine window bounds — no valid ticks")
        return
    cell, op_regime_ticks, tick_count = aggregate(rows, window_start, window_end)
    out = build_output(cell, op_regime_ticks, tick_count, window_start, window_end)
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(out, f, indent=2)
    print_summary(out)
    print()
    print(f"Wrote {OUTPUT_JSON}")
    _upload_to_gcs(out)


if __name__ == "__main__":
    main()

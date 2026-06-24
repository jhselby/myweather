"""
C1 confidence-layer calibration — Stage 1 v2 (multi-axis).

Extends the original (transition-only) calibration to a 4-axis table:

  axis_1: transition_flag      ∈ {stable, transition}     (legacy axis)
  axis_2: cluster_spread_q     ∈ {Q1, Q2, Q3, Q4}         (new — promoted 2026-06-20)
  axis_3: pressure_tendency    ∈ {falling_fast, falling, flat, rising}  (new — promoted 2026-06-20)
  axis_4: c1f_precip_fc        ∈ {p0, p1}                 (new — promoted 2026-06-24, 23 ortho cells)

Per-cell MAE measured across the test window; cell sample size determines
SHIP/MARGINAL/SKIP classification at curate-time (Stage 2).

Output schema is BACKWARDS-COMPATIBLE with the original Stage 1 script —
each (field, band) entry still carries `stable_mae`, `transition_mae`,
`premium_pct`, etc. (computed by collapsing across the new axes). The
multi-axis breakdown lives under a new `by_axes` sub-key per (field, band):

  {
    "t": {
      "0-5h": {
        "stable_mae": ..., "transition_mae": ..., ...,    # legacy axis
        "by_axes": {
          "Q1::flat::stable":      {"mae": x, "n": n},
          "Q4::falling_fast::transition": {"mae": x, "n": n},
          ...
        }
      }
    }
  }

This way the existing `confidence_layer.py` continues to read the legacy
axis without modification; the multi-axis lookup unlocks later when
confidence_layer is updated to consult cluster-spread + pt live.

Data sources joined:
  - forecast_error_log.jsonl    pair log (transition flag + pt already on each row)
  - cluster_spread_log.json     per-tick scalar, joined by obs_time within ±10min

Run:
  python3 analysis/c1_confidence_calibration_v2.py
  MYWEATHER_REFRESH=1 python3 analysis/c1_confidence_calibration_v2.py
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path  # noqa: E402


PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
CLUSTER_SPREAD_URL = "https://data.wymancove.com/cluster_spread_log.json"

# Use temp-spread (spread_t) as the canonical cluster-spread axis. Humidity
# spread (spread_h) tracks it closely on a 2-day smoke; if calibration shows
# they're not interchangeable, swap to a 2D spread axis later.
SPREAD_FIELD = "spread_t"

BANDS = [
    ("0-5h",   0, 6),
    ("6-11h",  6, 12),
    ("12-23h", 12, 24),
    ("24-47h", 24, 48),
]

PT_BINS = [
    ("falling_fast", float("-inf"), -1.0),
    ("falling",      -1.0,         -0.3),
    ("flat",         -0.3,         0.3),
    ("rising",       0.3,          float("inf")),
]

# C1f axis (v3): binary precip_fc>0 flag from state_fc.precip_in.
# Promoted 2026-06-24 — h_precip_fc_orthogonality.py returned 23 ortho cells.
C1F_LABELS = ("p0", "p1")

TEST_DAYS = 14
MIN_N_LEGACY = 100      # legacy single-axis floor (matches v1)
MIN_N_MULTI = 30        # multi-axis floor — cells are 8-32× sparser (now 16-64×)
TICK_JOIN_TOLERANCE_MIN = 15   # cluster_spread tick matched if within this window

OUTPUT_JSON = os.path.join(os.path.dirname(__file__), "output", "c1_confidence_premium_v2.json")


def _band_for_lead(lead_h):
    if lead_h is None:
        return None
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def _pt_bin(pt):
    if pt is None:
        return None
    for label, lo, hi in PT_BINS:
        if lo <= pt < hi:
            return label
    return None


def _tick_key(iso_ts):
    """Normalize an iso-ish timestamp to a YYYY-MM-DDTHH:MM key."""
    if not iso_ts:
        return None
    return iso_ts[:16]


def _shift_tick_minutes(tick, delta_min):
    dt = datetime.strptime(tick, "%Y-%m-%dT%H:%M")
    return (dt + timedelta(minutes=delta_min)).strftime("%Y-%m-%dT%H:%M")


def _load_cluster_spread_index():
    """Return dict[tick_key] -> spread_value, plus the Q1/Q3 quartile cuts."""
    try:
        path = cached_path(CLUSTER_SPREAD_URL)
    except Exception as e:
        print(f"  ⚠ cluster_spread log fetch failed: {e}")
        return {}, None, None

    try:
        with open(path) as f:
            doc = json.load(f)
    except Exception as e:
        print(f"  ⚠ cluster_spread log parse failed: {e}")
        return {}, None, None

    entries = doc.get("entries") or []
    by_tick = {}
    values = []
    for e in entries:
        ts = e.get("ts")
        v = e.get(SPREAD_FIELD)
        if ts is None or v is None:
            continue
        k = _tick_key(ts)
        if k is None:
            continue
        by_tick[k] = v
        values.append(v)

    if len(values) < 8:
        print(f"  ℹ cluster_spread index: only {len(values)} entries — not enough "
              f"for quartiles. Multi-axis cells will be empty for this run.")
        return by_tick, None, None

    s = sorted(values)
    n = len(s)
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    print(f"  ✓ cluster_spread index: {len(by_tick):,} ticks. "
          f"Q1≤{q1:.3f}, Q3≥{q3:.3f}, span {s[0]:.3f}–{s[-1]:.3f}")
    return by_tick, q1, q3


def _lookup_spread(spread_idx, tick):
    """Find the spread value for the given tick, tolerating ±TICK_JOIN_TOLERANCE_MIN."""
    if tick in spread_idx:
        return spread_idx[tick]
    for delta in range(1, TICK_JOIN_TOLERANCE_MIN + 1):
        cand = _shift_tick_minutes(tick, delta)
        if cand in spread_idx:
            return spread_idx[cand]
        cand = _shift_tick_minutes(tick, -delta)
        if cand in spread_idx:
            return spread_idx[cand]
    return None


def _spread_quartile(v, q1, q3):
    if v is None or q1 is None or q3 is None:
        return None
    if v <= q1:
        return "Q1"
    if v >= q3:
        return "Q4"
    return "Q23"  # middle quartiles collapsed — we only care about extremes


def measure():
    print(f"C1 multi-axis calibration · {TEST_DAYS}-day window")
    print("=" * 80)
    print("[1/3] Loading cluster_spread index...")
    spread_idx, sq1, sq3 = _load_cluster_spread_index()
    # Stash the cuts on a side-channel so main() can write them to the JSON
    measure._sq1 = sq1
    measure._sq3 = sq3

    cutoff = (datetime.now(timezone.utc) - timedelta(days=TEST_DAYS)).strftime("%Y-%m-%dT%H:%M")

    # Legacy aggregator: (field, band, is_transition) -> [sum_abs_err, n]
    legacy_accs = defaultdict(lambda: [0.0, 0])
    # Multi-axis aggregator: (field, band, spread_q, pt_label, is_trans, c1f) -> [sum_abs_err, n]
    multi_accs = defaultdict(lambda: [0.0, 0])

    print("[2/3] Streaming pair log...")
    path = cached_path(PAIR_LOG_URL)
    pairs_seen = 0
    pairs_used_legacy = 0
    pairs_used_multi = 0
    pairs_skip_no_spread = 0

    with open(path) as f:
        for line in f:
            if not line:
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            ot = p.get("obs_time") or ""
            if ot < cutoff:
                continue
            pairs_seen += 1

            field = p.get("field")
            obs = p.get("observed")
            lead = p.get("lead_h")
            if field is None or obs is None or lead is None:
                continue
            band = _band_for_lead(lead)
            if band is None:
                continue

            sfc = p.get("state_fc") or {}
            sob = p.get("state_obs") or {}
            rfc = sfc.get("regime_synoptic")
            rob = sob.get("regime_synoptic")
            if not rfc or not rob:
                continue

            fc = (p.get("forecast_l4") or p.get("forecast_l3")
                  or p.get("forecast_l2") or p.get("forecast_l1")
                  or p.get("forecast"))
            if fc is None:
                continue

            abs_err = abs(fc - obs)
            is_trans = (rfc != rob)

            # Legacy accumulator
            legacy_accs[(field, band, is_trans)][0] += abs_err
            legacy_accs[(field, band, is_trans)][1] += 1
            pairs_used_legacy += 1

            # Multi-axis accumulator — needs both pt_bin AND spread_quartile.
            pt_label = _pt_bin(sfc.get("pressure_trend_hpa_3h"))
            tick = _tick_key(ot)
            spread_v = _lookup_spread(spread_idx, tick) if spread_idx else None
            spread_q = _spread_quartile(spread_v, sq1, sq3)

            if pt_label is None or spread_q is None:
                if spread_q is None:
                    pairs_skip_no_spread += 1
                continue

            # C1f axis (v3): state_fc.precip_in > 0 → "p1", else "p0".
            c1f = "p1" if (sfc.get("precip_in") or 0) > 0 else "p0"

            multi_accs[(field, band, spread_q, pt_label, is_trans, c1f)][0] += abs_err
            multi_accs[(field, band, spread_q, pt_label, is_trans, c1f)][1] += 1
            pairs_used_multi += 1

    print(f"  pairs scanned: {pairs_seen:,}")
    print(f"  legacy axis used: {pairs_used_legacy:,}")
    print(f"  multi-axis used:  {pairs_used_multi:,}  "
          f"(skipped {pairs_skip_no_spread:,} for no cluster_spread join)")

    print("[3/3] Building output table...")
    # Legacy view (Stage 2 v1 reads this exactly as before)
    legacy_cells = {}
    for (field, band, is_trans), (s_e, n) in legacy_accs.items():
        if n == 0:
            continue
        slot = "transition" if is_trans else "stable"
        legacy_cells.setdefault(field, {}).setdefault(band, {})[slot] = {
            "mae": s_e / n, "n": n,
        }

    out_cells = {}
    for field, bands in legacy_cells.items():
        out_cells[field] = {}
        for band, halves in bands.items():
            st = halves.get("stable")
            tr = halves.get("transition")
            if not st or not tr or st["n"] < MIN_N_LEGACY or tr["n"] < MIN_N_LEGACY:
                continue
            premium_abs = tr["mae"] - st["mae"]
            premium_pct = 100 * premium_abs / st["mae"] if st["mae"] else None
            out_cells[field][band] = {
                "stable_mae":     round(st["mae"], 4),
                "transition_mae": round(tr["mae"], 4),
                "premium_abs":    round(premium_abs, 4),
                "premium_pct":    round(premium_pct, 2) if premium_pct is not None else None,
                "n_stable":       st["n"],
                "n_transition":   tr["n"],
                "by_axes":        {},
            }

    # Attach the multi-axis sub-table.
    for (field, band, spread_q, pt_label, is_trans, c1f), (s_e, n) in multi_accs.items():
        if n < MIN_N_MULTI:
            continue
        slot = "transition" if is_trans else "stable"
        key = f"{spread_q}::{pt_label}::{slot}::{c1f}"
        # Only attach if the legacy entry exists for this (field, band) — keeps
        # the table consistent (legacy entry is the parent).
        legacy_entry = out_cells.get(field, {}).get(band)
        if legacy_entry is None:
            continue
        legacy_entry["by_axes"][key] = {
            "mae": round(s_e / n, 4),
            "n":   n,
        }

    # Count multi-axis cells that survived MIN_N_MULTI.
    multi_cell_count = sum(
        len(b["by_axes"]) for f in out_cells.values() for b in f.values()
    )
    print(f"  legacy (field, band) cells: {sum(len(b) for b in out_cells.values()):,}")
    print(f"  multi-axis cells wired:     {multi_cell_count:,} (n≥{MIN_N_MULTI})")

    return out_cells, pairs_seen, pairs_used_legacy, pairs_used_multi


def main():
    cells, seen, used_legacy, used_multi = measure()

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "test_days":    TEST_DAYS,
            "min_n_legacy": MIN_N_LEGACY,
            "min_n_multi":  MIN_N_MULTI,
            "axes": {
                "transition":    ["stable", "transition"],
                "spread_q":      ["Q1", "Q23", "Q4"],
                "pt":            [b[0] for b in PT_BINS],
                "c1f":           list(C1F_LABELS),
            },
            "spread_field":  SPREAD_FIELD,
            "join_tolerance_min": TICK_JOIN_TOLERANCE_MIN,
            "spread_cuts": {
                "q1": getattr(measure, "_sq1", None),
                "q3": getattr(measure, "_sq3", None),
            },
            "pt_bins": [
                {"label": lbl, "lo": (None if lo == float("-inf") else lo),
                 "hi": (None if hi == float("inf") else hi)}
                for lbl, lo, hi in PT_BINS
            ],
            "cells": cells,
        }, f, indent=2)
    print(f"\nWrote {OUTPUT_JSON}")
    print()
    print("Next: re-run c1_curate_confidence_table.py to produce the curated")
    print("table. The v1 curator reads stable_mae/transition_mae and ignores")
    print("the by_axes sub-table — safe to run today. A v2 curator that")
    print("emits per-axis SHIP/SKIP rows is the next piece.")


if __name__ == "__main__":
    main()

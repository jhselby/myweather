#!/usr/bin/env python3
"""Stage 0/1: recent-bias gate on the L5 sr bias table.

Mirror of h_lc_recent_bias_gate.py, adapted for L5 (solar_correction).
See [[project_lsr_recent_bias_gate]] for the design rationale.

The problem: L5's `_BIAS_BY_REGIME_HOUR` static table (regenerated daily by
l5_recompute_biases_hourly) trains on the last 14d. When the underlying
model's sr bias flips sign for a few days, L5 keeps applying corrections in
the OLD direction and amplifies the error. Exactly the failure mode Lc had
before v0.6.413.

Gate rule (per (regime, hour) cell):
  * historical bias present in current curated table (n ≥ MIN_N_CELL trained)
  * sign(recent_bias) == sign(historical_bias)
  * |recent_bias| >= GATE_RATIO * |historical_bias|
  → apply historical shift. Else pass through (no correction).

Sign convention (matches solar_correction.py:272-273):
  bias = mean(fc - obs); shift = -bias.
  Large negative bias → model under-forecasts → shift is large positive
  (correction ADDS to fc). Sign check keeps the shift only when today's
  data still agrees the model is under- (or over-) forecasting the same way.

Cell attribution:
  Uses state_fc.regime_synoptic (per-lead regime) rather than reconstructing
  issue-time regime. This matches the per-lead attribution frame the pair
  log is scored in. Runtime wiring can choose issue-time or per-lead apply
  independently; the gate decision cell survives either choice.

Skip regimes: ne_flow, calm (already skipped by solar_correction.py at
runtime — matches production skip so the analysis speaks to what actually
ships).

Run:
    python3 -m analysis.h_lsr_recent_bias_gate
    MYWEATHER_REFRESH=1 python3 -m analysis.h_lsr_recent_bias_gate
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
LIVE_TABLE_PATH = Path(__file__).resolve().parent.parent / "weather_collector" / "data" / "lsr_bias_table_curated.json"
GATE_HISTORY_PATH = Path(__file__).resolve().parent.parent / ".cache_lsr_recent_bias_gate_history.json"
RUNTIME_TABLE_PATH = Path(__file__).resolve().parent.parent / "weather_collector" / "data" / "lsr_recent_bias_gate.json"

GATE_HISTORY_RETENTION_DAYS = 30
GATE_WINDOW_DAYS = 7

# Matches solar_correction.py: skip regimes + sun-up threshold.
L5_SKIP_REGIMES = {"ne_flow", "calm"}
SUN_UP_THRESHOLD = 50.0

RECENT_DAYS = 3
HOLDOUT_DAYS = 3
GATE_RATIO = 0.5
TOLERANCE_PCT = 5.0
MIN_N_CELL = 30


def main():
    live_tbl = json.loads(LIVE_TABLE_PATH.read_text())
    bias_by_rh = live_tbl.get("bias_by_regime_hour") or {}
    # Cells to consider = anything present in the live table (i.e. had enough
    # training data to fit). Structure: {regime: {hour_str: bias_or_dict}}.
    live_cells = {}  # (regime, hour_int) -> hist_bias
    for regime, hours in bias_by_rh.items():
        if regime in L5_SKIP_REGIMES:
            continue
        for h_str, v in (hours or {}).items():
            try:
                h = int(h_str)
            except (TypeError, ValueError):
                continue
            bias = v.get("bias") if isinstance(v, dict) else v
            if bias is None:
                continue
            live_cells[(regime, h)] = float(bias)

    # Bucket sr rows by (obs_date, regime, hour_local).
    rows = defaultdict(list)
    print(f"reading {PAIR_LOG_URL}")
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != "sr":
                continue
            fc = r.get("forecast_l1")  # pre-L5 baseline; L5 adds Δ on top of L1
            obs = r.get("observed")
            ot = r.get("obs_time")
            if fc is None or obs is None or not ot:
                continue
            fc = float(fc)
            if fc < SUN_UP_THRESHOLD:
                continue  # night — L5 doesn't fire, don't score
            state_fc = r.get("state_fc") or {}
            regime = state_fc.get("regime_synoptic")
            if not regime or regime in L5_SKIP_REGIMES:
                continue
            try:
                # obs_time is naive ISO; hour is local per pipeline convention
                # (obs are stamped in America/New_York per state_stamp.py).
                hour = int(ot[11:13])
            except (ValueError, IndexError):
                continue
            day = ot[:10]
            rows[(day, regime, hour)].append((fc, float(obs)))

    all_days = sorted({k[0] for k in rows.keys()})
    if len(all_days) < RECENT_DAYS + HOLDOUT_DAYS:
        print(f"insufficient days: {len(all_days)} < {RECENT_DAYS + HOLDOUT_DAYS}")
        return
    holdout_days = all_days[-HOLDOUT_DAYS:]
    recent_days = all_days[-(HOLDOUT_DAYS + RECENT_DAYS):-HOLDOUT_DAYS]
    print(f"recent window ({RECENT_DAYS}d): {recent_days[0]} → {recent_days[-1]}")
    print(f"holdout ({HOLDOUT_DAYS}d):      {holdout_days[0]} → {holdout_days[-1]}")
    print()

    # Recent-window mean bias per (regime, hour).
    recent_bias = {}
    for (regime, hour) in live_cells.keys():
        pairs = []
        for d in recent_days:
            pairs.extend(rows.get((d, regime, hour), []))
        if len(pairs) < MIN_N_CELL:
            continue
        recent_bias[(regime, hour)] = sum(fc - obs for fc, obs in pairs) / len(pairs)

    def mae(pairs, shift):
        if not pairs:
            return None
        # Solar can go negative if over-corrected; clamp at 0 (matches physical bound).
        return sum(abs(max(0.0, fc + shift) - obs) for fc, obs in pairs) / len(pairs)

    print(f"{'regime':<11} {'hr':>3} {'n':>5} {'hist_bias':>10} {'recent':>8} "
          f"{'ratio':>6} {'sign':>5} {'gate?':>6}  "
          f"{'MAE_raw':>8} {'MAE_live':>9} {'MAE_gate':>9}  {'live%':>7} {'gate%':>7}")
    print("-" * 132)

    field_agg = {"sr": {"n": 0, "raw": 0.0, "live": 0.0, "gate": 0.0}}
    gated_off_cells = []  # list of "regime/hr"
    # Runtime schema: per_cell[regime][hour_str] = {...} (mirrors Lc's per_cell[field][bin]).
    per_cell_runtime = defaultdict(dict)

    # Iterate in a stable order for readable output.
    for (regime, hour) in sorted(live_cells.keys()):
        hist_bias = live_cells[(regime, hour)]
        hist_shift = -hist_bias
        recent = recent_bias.get((regime, hour))

        holdout = []
        for d in holdout_days:
            holdout.extend(rows.get((d, regime, hour), []))
        n = len(holdout)
        if n < MIN_N_CELL:
            continue

        m_raw = mae(holdout, 0.0)
        m_live = mae(holdout, hist_shift)

        if recent is None:
            gate_apply = True
            gate_reason = "thin"
            sign_ok = None
            mag_ok = None
        else:
            sign_ok = (recent > 0 and hist_bias > 0) or (recent < 0 and hist_bias < 0)
            mag_ok = abs(recent) >= GATE_RATIO * abs(hist_bias)
            gate_apply = sign_ok and mag_ok
            gate_reason = "on" if gate_apply else ("sign" if not sign_ok else "mag")
            if not gate_apply:
                gated_off_cells.append(f"{regime}/{hour}")
        m_gate = mae(holdout, hist_shift if gate_apply else 0.0)

        per_cell_runtime[regime][str(hour)] = {
            "gate_apply": bool(gate_apply),
            "gate_reason": gate_reason,
            "sign_ok": sign_ok,
            "mag_ok": mag_ok,
            "recent_bias": None if recent is None else round(float(recent), 4),
            "hist_bias": round(float(hist_bias), 4),
            "hist_shift": round(float(hist_shift), 4),
            "n_holdout": n,
        }

        live_pct = 100.0 * (m_raw - m_live) / m_raw if m_raw > 0 else 0.0
        gate_pct = 100.0 * (m_raw - m_gate) / m_raw if m_raw > 0 else 0.0

        recent_s = f"{recent:+.1f}" if recent is not None else "n/a"
        ratio_s = f"{abs(recent) / abs(hist_bias):.2f}" if recent is not None and hist_bias != 0 else "n/a"
        sign_s = ("+" if (recent or 0) >= 0 else "-") if recent is not None else "?"
        print(f"{regime:<11} {hour:>3} {n:>5} {hist_bias:>+10.1f} {recent_s:>8} "
              f"{ratio_s:>6} {sign_s:>5} {gate_reason:>6}  "
              f"{m_raw:>8.2f} {m_live:>9.2f} {m_gate:>9.2f}  {live_pct:>+6.1f}% {gate_pct:>+6.1f}%")

        field_agg["sr"]["n"] += n
        field_agg["sr"]["raw"] += m_raw * n
        field_agg["sr"]["live"] += m_live * n
        field_agg["sr"]["gate"] += m_gate * n

    print()
    print("=" * 132)
    print("POOLED (weighted by n across cells with historical bias + n≥MIN_N):")
    print("=" * 132)
    a = field_agg["sr"]
    verdicts = []
    if a["n"] == 0:
        print("  no cells with sufficient data")
    else:
        r = a["raw"] / a["n"]; l = a["live"] / a["n"]; g = a["gate"] / a["n"]
        live_pct = 100.0 * (r - l) / r if r > 0 else 0.0
        gate_pct = 100.0 * (r - g) / r if r > 0 else 0.0
        delta = gate_pct - live_pct
        goff = ",".join(gated_off_cells) or "-"
        print(f"sr    {a['n']:>7} MAE_raw={r:>7.2f} MAE_live={l:>7.2f} MAE_gate={g:>7.2f}  "
              f"live%={live_pct:+.1f}%  gate%={gate_pct:+.1f}%  gate−live={delta:+.2f}pp")
        print(f"      gated_off_cells ({len(gated_off_cells)}): {goff}")
        if gate_pct > 0 and (live_pct <= 0 or gate_pct >= live_pct - TOLERANCE_PCT):
            verdicts.append(f"sr: PROMOTE (gate {gate_pct:+.1f}% vs live {live_pct:+.1f}%)")
        else:
            verdicts.append(f"sr: HOLD (gate {gate_pct:+.1f}% vs live {live_pct:+.1f}%)")

    print()
    print("=" * 132)
    print("STAGE 0 VERDICT:")
    print("=" * 132)
    for v in verdicts:
        print(f"  {v}")

    # STAGE 1 — halves-strict.
    print()
    print("=" * 132)
    print("STAGE 1 — HALVES-STRICT (chronological split of the holdout window)")
    print("=" * 132)
    mid = len(holdout_days) // 2 or 1
    half_a = holdout_days[:mid]
    half_b = holdout_days[mid:]
    print(f"half A: {half_a[0]} → {half_a[-1]}    half B: {half_b[0]} → {half_b[-1]}")
    print()

    def score_half(days_subset):
        agg = {"n": 0, "raw": 0.0, "live": 0.0, "gate": 0.0}
        for (regime, hour), hist_bias in live_cells.items():
            hist_shift = -hist_bias
            recent = recent_bias.get((regime, hour))
            pairs = []
            for d in days_subset:
                pairs.extend(rows.get((d, regime, hour), []))
            n = len(pairs)
            if n < MIN_N_CELL:
                continue
            m_raw = mae(pairs, 0.0); m_live = mae(pairs, hist_shift)
            if recent is None:
                gate_apply = True
            else:
                sign_ok = (recent > 0 and hist_bias > 0) or (recent < 0 and hist_bias < 0)
                mag_ok = abs(recent) >= GATE_RATIO * abs(hist_bias)
                gate_apply = sign_ok and mag_ok
            m_gate = mae(pairs, hist_shift if gate_apply else 0.0)
            agg["n"] += n
            agg["raw"] += m_raw * n; agg["live"] += m_live * n; agg["gate"] += m_gate * n
        if agg["n"] == 0:
            return None
        r = agg["raw"] / agg["n"]; l = agg["live"] / agg["n"]; g = agg["gate"] / agg["n"]
        return {
            "n": agg["n"],
            "live_pct": 100.0 * (r - l) / r if r > 0 else 0.0,
            "gate_pct": 100.0 * (r - g) / r if r > 0 else 0.0,
            "gate_beats_raw": g <= r,
        }

    a_score = score_half(half_a)
    b_score = score_half(half_b)

    stage1 = []
    if not a_score or not b_score:
        print("sr    insufficient halves data")
    else:
        raw_safe = a_score["gate_beats_raw"] and b_score["gate_beats_raw"]
        beats_live_A = a_score["gate_pct"] >= a_score["live_pct"] - TOLERANCE_PCT
        beats_live_B = b_score["gate_pct"] >= b_score["live_pct"] - TOLERANCE_PCT
        if raw_safe and beats_live_A and beats_live_B and (a_score["gate_pct"] > 0 or b_score["gate_pct"] > 0):
            v = "STAGE 1 PROMOTE"
        elif raw_safe:
            v = "HOLD (safe but no gain)"
        else:
            v = "FAIL (loses to raw on a half)"
        stage1.append(("sr", v))
        print(f"sr    A n={a_score['n']:>5} live%={a_score['live_pct']:+.1f}% gate%={a_score['gate_pct']:+.1f}%    "
              f"B n={b_score['n']:>5} live%={b_score['live_pct']:+.1f}% gate%={b_score['gate_pct']:+.1f}%    {v}")

    print()
    print("=" * 132)
    print("STAGE 1 VERDICT:")
    print("=" * 132)
    for f, v in stage1:
        print(f"  {f}: {v}")

    promoted = sorted(f for f, v in stage1 if v == "STAGE 1 PROMOTE")
    gate = _append_gate_history({
        "fitted_at": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "verdict": "PROMOTE" if promoted else "HOLD",
        "promoted_fields": promoted,
    })

    print()
    print("=" * 132)
    print(f"Rolling {GATE_WINDOW_DAYS}-day gate:")
    print(f"  window: {gate['history_window_days']} days · runs seen: {gate['entries_in_window']} · "
          f"distinct days: {gate['days_in_window']}")
    print(f"  promote_days: {gate['promote_days']} · hold_days: {gate['hold_days']} · "
          f"latest PROMOTE streak: {gate['latest_streak']}")
    print(f"  promoted-field set stability: {'STABLE' if gate['stable'] else 'CHURN'} "
          f"(fields changed: {len(gate['fields_changed'])})")
    if gate["fields_changed"]:
        for c in gate["fields_changed"][:10]:
            print(f"    changed: {c}")
    print(f"  gate_clear (set-level): {gate['gate_clear']}   (requires ≥{GATE_WINDOW_DAYS} distinct days, "
          "no HOLD days, promoted set stable, ≥1 field)")
    if gate.get("per_field"):
        print(f"  per-field clearance:")
        for f in sorted(gate["per_field"].keys()):
            pf = gate["per_field"][f]
            mark = "✓ CLEARED" if pf["cleared"] else f"streak {pf['streak_days']}/{GATE_WINDOW_DAYS}"
            print(f"    {f}: {mark} · promoted {pf['days_promoted_in_window']} days in window")
        if gate.get("fields_cleared"):
            print(f"  → fields ready for per-field ship: {gate['fields_cleared']}")
    print()

    if not promoted:
        v = "VERDICT: NULL — sr did not clear Stage 1 halves-strict today."
    else:
        fields_cleared = gate.get("fields_cleared") or []
        clear_note = ""
        if fields_cleared:
            clear_note = f", PER-FIELD CLEARED: {fields_cleared} — ready for Stage 3 wire"
        elif gate['gate_clear']:
            clear_note = ", SET-LEVEL GATE CLEARED — ready for Stage 3 wire"
        v = (f"VERDICT: STAGE 1 PROMOTE — sr cleared halves-strict. "
             f"Rolling {GATE_WINDOW_DAYS}-day gate: day {gate['days_in_window']}/{GATE_WINDOW_DAYS}, "
             f"set {'STABLE' if gate['stable'] else 'CHURN'}{clear_note}.")
    print(v)
    print("=" * 132)

    runtime = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "h_lsr_recent_bias_gate.py",
        "recent_window_days": RECENT_DAYS,
        "holdout_window_days": HOLDOUT_DAYS,
        "gate_ratio": GATE_RATIO,
        "min_n_cell": MIN_N_CELL,
        "sun_up_threshold_wm2": SUN_UP_THRESHOLD,
        "l5_skip_regimes": sorted(L5_SKIP_REGIMES),
        "promoted_fields": promoted,
        "fields_cleared": gate.get("fields_cleared") or [],
        "set_level_gate_clear": bool(gate.get("gate_clear")),
        "per_cell": {r: dict(hours) for r, hours in per_cell_runtime.items()},
        "notes": (
            "Stage 3 wire contract: for field in fields_cleared AND "
            "per_cell[regime][hour].gate_apply == False, solar_correction.py must "
            "return 0.0 (no correction) instead of the historical shift. All other "
            "cells (regime in L5_SKIP_REGIMES, cell missing, or gate_apply True/None) "
            "keep existing solar_correction behavior."
        ),
    }
    RUNTIME_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_TABLE_PATH.write_text(json.dumps(runtime, indent=2))
    print(f"\nwrote {RUNTIME_TABLE_PATH}")


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

    promote_days = sum(1 for _, xs in by_day.items()
                       if all(x.get("verdict") == "PROMOTE" for x in xs))
    hold_days = len(by_day) - promote_days

    streak = 0
    for e in reversed(window):
        if e.get("verdict") == "PROMOTE":
            streak += 1
        else:
            break

    current_set = set(this_entry.get("promoted_fields") or [])
    fields_changed = []
    for e in reversed(window[:-1]):
        prior = set(e.get("promoted_fields") or [])
        for k in current_set ^ prior:
            was = "PROMOTE" if k in prior else "not-PROMOTE"
            now_v = "PROMOTE" if k in current_set else "not-PROMOTE"
            fields_changed.append((k, was, now_v))
    seen = set()
    dedup = []
    for c in fields_changed:
        if c[0] in seen:
            continue
        seen.add(c[0])
        dedup.append(c)

    stable = len(dedup) == 0
    gate_clear = (len(by_day) >= GATE_WINDOW_DAYS and hold_days == 0
                  and stable and len(current_set) > 0)

    all_fields_seen = set()
    for e in window:
        all_fields_seen |= set(e.get("promoted_fields") or [])
    by_day_field = {}
    for e in window:
        day = e.get("fitted_at", "")[:10]
        if not day:
            continue
        for f in all_fields_seen:
            is_p = f in (e.get("promoted_fields") or [])
            slot = by_day_field.setdefault(day, {})
            slot[f] = slot.get(f, False) or is_p
    sorted_days = sorted(by_day_field.keys())
    per_field = {}
    for f in all_fields_seen:
        f_streak = 0
        for day in reversed(sorted_days):
            if by_day_field[day].get(f):
                f_streak += 1
            else:
                break
        f_days_in = sum(1 for d in sorted_days if by_day_field[d].get(f))
        per_field[f] = {
            "streak_days": f_streak,
            "days_promoted_in_window": f_days_in,
            "cleared": f_streak >= GATE_WINDOW_DAYS,
        }
    fields_cleared = sorted(f for f, v in per_field.items() if v["cleared"])

    return {
        "entries_in_window": len(window),
        "days_in_window": len(by_day),
        "promote_days": promote_days,
        "hold_days": hold_days,
        "latest_streak": streak,
        "stable": stable,
        "fields_changed": dedup,
        "gate_clear": gate_clear,
        "per_field": per_field,
        "fields_cleared": fields_cleared,
        "history_window_days": GATE_WINDOW_DAYS,
    }


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Stage 1 halves-strict fit for regime-conditional cc blend formula.

Follows Stage 0 ([[analysis/h_cc_blend_formula.py]]), which today flags 5
STABLE regimes where a non-max overlap formula (random / max_random) beats
Ccd's live `max` derivation by ≥3%. Stage 1 tightens the SHIP criterion
(halves each ≥ HALVES_MIN_PCT, MIN_N floor per regime, respect Ccd's
SKIP_REGIMES) and emits a regime-granularity curated table structured for
Stage 3 apply-side wiring.

Fills the gap between:
  - Stage 0 h_cc_blend_formula.py (pooled per-regime signal)
  - Existing per-cell walker h_cc_combine_walker.py (regime x band x day
    unanimous 7-day gate — much stricter, currently HOLD 0/27 cells)

The per-cell walker keeps its role for surgical cell overrides; Stage 1
provides a coarser regime-granularity fallback that can wire when the
walker never clears.

Schema of emitted table:

    {
      "generated_at": ...,
      "source": "forecast_error_log.jsonl",
      "fit_rules": { ... },
      "notes": ...,
      "regimes": {
        "pre_frontal": {
          "formula": "random",
          "n": 5711,
          "pooled_improve_pct": 5.65,
          "halves_a_improve_pct": 4.32,
          "halves_b_improve_pct": 6.63,
          "mae_max": ...,
          "mae_best": ...,
          "verdict": "SHIP" | "MARGIN" | "SKIP-mag" | "SKIP-thin" | "SKIP-ccd"
        },
        ...
      }
    }

Verdict criterion (all four required for SHIP):
    n >= MIN_N
    pooled_improve_pct >= POOLED_MIN_PCT
    halves A improve_pct >= HALVES_MIN_PCT AND halves B improve_pct >= HALVES_MIN_PCT
    regime NOT in CCD_SKIP_REGIMES (else SKIP-ccd — Ccd doesn't derive
                                     these anyway, so no wire target)

Halves are chronological (first-half / second-half of chronologically
sorted joined-quad rows for the regime). Recent-anomaly contamination
shows as B improve much worse than A.

Gate history: appends this run to `.cache_h_cc_blend_formula_gate_history.json`
(30-day retention, 7-day flip gate). Same shape as lc_regime_stage1
gate history.

Run:
    python3 -m analysis.h_cc_blend_formula_stage1
    MYWEATHER_REFRESH=1 python3 -m analysis.h_cc_blend_formula_stage1
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
OUT_TABLE = Path(__file__).resolve().parent / "output" / "cc_blend_formula_curated_stage1.json"
OUT_TXT = Path(__file__).resolve().parent / "output" / "h_cc_blend_formula_stage1.txt"
GATE_HISTORY_PATH = Path(__file__).resolve().parent.parent / ".cache_h_cc_blend_formula_gate_history.json"
GATE_HISTORY_RETENTION_DAYS = 30
GATE_WINDOW_DAYS = 7

CLOUD_FIELDS = {"cc", "cl", "cm", "ch"}
FORMULAS = ("max", "random", "max_random")
MIN_OBS_DATE = "2026-07-01"  # matches Stage 0

MIN_N = 500                  # pooled n per regime
MIN_N_HALF = 200             # each half
POOLED_MIN_PCT = 3.0         # matches Stage 0 GAIN_THRESHOLD_PCT
HALVES_MIN_PCT = 2.0         # stricter than Stage 0's "both positive"

# Regimes Ccd (cc_from_derivation.py) skips entirely — no wire target.
# Kept in sync with cc_from_derivation.SKIP_REGIMES; if that set changes,
# update here. If Stage 1 flagged a regime that Ccd skips, we still emit
# the row but mark it SKIP-ccd so it can't reach the ship set.
CCD_SKIP_REGIMES = frozenset({"se_flow", "unknown"})


def _clip(v):
    return max(0.0, min(100.0, v))


def _derive_max(cl, cm, ch):
    return _clip(max(cl, cm, ch))


def _derive_random(cl, cm, ch):
    a = 1.0 - cl / 100.0
    b = 1.0 - cm / 100.0
    c = 1.0 - ch / 100.0
    return _clip(100.0 * (1.0 - a * b * c))


def _derive_max_random(cl, cm, ch):
    lm = max(cl, cm)
    a = 1.0 - lm / 100.0
    b = 1.0 - ch / 100.0
    return _clip(100.0 * (1.0 - a * b))


DERIVERS = {"max": _derive_max, "random": _derive_random, "max_random": _derive_max_random}


def _deepest_available(r):
    for k in ("forecast_l6", "forecast_l4", "forecast_l3", "forecast_l2", "forecast_l1"):
        v = r.get(k)
        if v is not None:
            return float(v)
    return None


def _regime_of(r):
    sfc = r.get("state_fc") or {}
    return sfc.get("regime_synoptic")


def _obs_time_of(r):
    return r.get("obs_time") or r.get("run_time") or ""


def _mae_for_rows(rows, formula):
    """rows: [(cl, cm, cc_obs, cm_c, ch_c), ...] — return MAE for a formula.
    (We store the derived quad in tuple form; formula picks how to combine.)"""
    if not rows:
        return None
    fn = DERIVERS[formula]
    total = 0.0
    for cl_c, cm_c, ch_c, cc_obs in rows:
        total += abs(fn(cl_c, cm_c, ch_c) - cc_obs)
    return total / len(rows)


def _pct(new, base):
    if base is None or base == 0:
        return None
    return 100.0 * (base - new) / base


def _classify(mae_max, mae_best, n, halves_a_pct, halves_b_pct, n_a, n_b, regime):
    if n < MIN_N:
        return "SKIP-thin"
    if mae_max is None or mae_best is None:
        return "SKIP-thin"
    pooled_pct = _pct(mae_best, mae_max)
    if pooled_pct is None or pooled_pct < POOLED_MIN_PCT:
        return "SKIP-mag"
    if n_a < MIN_N_HALF or n_b < MIN_N_HALF:
        return "SKIP-halves-thin"
    if halves_a_pct is None or halves_b_pct is None:
        return "SKIP-halves-thin"
    if halves_a_pct < HALVES_MIN_PCT or halves_b_pct < HALVES_MIN_PCT:
        return "MARGIN"
    if regime in CCD_SKIP_REGIMES:
        return "SKIP-ccd"
    return "SHIP"


def main():
    # Group pair-log rows into (run_time, lead_h) quads so we can join cc obs
    # with cl/cm/ch forecasts fired for the same issue-time/lead. Same
    # pattern as Stage 0 h_cc_blend_formula.py.
    groups = defaultdict(dict)
    rows_read = 0
    print(f"reading {URL}")
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            rows_read += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            f = r.get("field")
            if f not in CLOUD_FIELDS:
                continue
            obs_t = r.get("obs_time", "")
            if obs_t < MIN_OBS_DATE:
                continue
            key = (r.get("run_time"), r.get("lead_h"))
            if key[0] is None or key[1] is None:
                continue
            groups[key][f] = r
    print(f"  rows read: {rows_read:,}   unique (run_time, lead_h) quads: {len(groups):,}")

    # For each complete quad, derive the three formula outputs and stash
    # into per-regime chronological buckets for halves splitting.
    per_regime_timed = defaultdict(list)  # regime -> [(obs_time, cl, cm, ch, cc_obs), ...]
    complete = 0
    for (run_time, lead_h), fields in groups.items():
        if not (CLOUD_FIELDS <= set(fields.keys())):
            continue
        cc_row = fields["cc"]
        cc_obs = cc_row.get("observed")
        if cc_obs is None:
            continue
        cl_c = _deepest_available(fields["cl"])
        cm_c = _deepest_available(fields["cm"])
        ch_c = _deepest_available(fields["ch"])
        if None in (cl_c, cm_c, ch_c):
            continue
        regime = _regime_of(cc_row) or "unknown"
        t = _obs_time_of(cc_row)
        per_regime_timed[regime].append((t, cl_c, cm_c, ch_c, float(cc_obs)))
        complete += 1
    print(f"  complete quads with obs: {complete:,}")
    print(f"  regimes seen: {len(per_regime_timed)}")
    print()

    # Chronological sort so halves-split is time-based.
    for k in per_regime_timed:
        per_regime_timed[k].sort(key=lambda x: x[0])

    # ── Per-regime halves-strict fit ─────────────────────────────────────
    regimes_out = {}
    ship_set = set()
    verdict_counts = defaultdict(int)

    for regime, timed in per_regime_timed.items():
        # Strip time; keep (cl, cm, ch, cc_obs).
        rows = [(cl, cm, ch, obs) for _, cl, cm, ch, obs in timed]
        n = len(rows)

        mae = {f: _mae_for_rows(rows, f) for f in FORMULAS}
        mae_max = mae["max"]

        # Best non-max formula by pooled MAE.
        non_max = [f for f in FORMULAS if f != "max"]
        best_formula = min(non_max, key=lambda f: mae[f] if mae[f] is not None else float("inf"))
        mae_best = mae[best_formula]
        pooled_pct = _pct(mae_best, mae_max)

        # Halves.
        m = n // 2
        rows_a, rows_b = rows[:m], rows[m:]
        n_a, n_b = len(rows_a), len(rows_b)
        mae_a_max = _mae_for_rows(rows_a, "max")
        mae_a_best = _mae_for_rows(rows_a, best_formula)
        mae_b_max = _mae_for_rows(rows_b, "max")
        mae_b_best = _mae_for_rows(rows_b, best_formula)
        halves_a_pct = _pct(mae_a_best, mae_a_max)
        halves_b_pct = _pct(mae_b_best, mae_b_max)

        verdict = _classify(mae_max, mae_best, n,
                            halves_a_pct, halves_b_pct, n_a, n_b, regime)
        verdict_counts[verdict] += 1
        if verdict == "SHIP":
            ship_set.add((regime, best_formula))

        def rnd(x, k=3):
            return round(x, k) if isinstance(x, (int, float)) else x

        regimes_out[regime] = {
            "formula": best_formula,
            "n": n,
            "mae_max": rnd(mae_max),
            "mae_best": rnd(mae_best),
            "pooled_improve_pct": rnd(pooled_pct, 2) if pooled_pct is not None else None,
            "halves": {
                "a_n": n_a,
                "b_n": n_b,
                "a_improve_pct": rnd(halves_a_pct, 2) if halves_a_pct is not None else None,
                "b_improve_pct": rnd(halves_b_pct, 2) if halves_b_pct is not None else None,
            },
            "verdict": verdict,
        }

    # ── Emit curated table ──
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "forecast_error_log.jsonl",
        "fit_rules": {
            "min_obs_date": MIN_OBS_DATE,
            "min_n": MIN_N,
            "min_n_half": MIN_N_HALF,
            "pooled_min_pct": POOLED_MIN_PCT,
            "halves_min_pct": HALVES_MIN_PCT,
            "formulas": list(FORMULAS),
            "regime_key": "state_fc.regime_synoptic",
            "halves_split": "chronological by obs_time",
            "ccd_skip_regimes": sorted(CCD_SKIP_REGIMES),
        },
        "notes": (
            "Stage 1 candidate table — regime-conditional cc blend formula. "
            "Apply-side (Stage 3) reads regimes[regime].formula and passes "
            "it to cc_from_derivation._derive_with() for rows in that regime. "
            "SKIP-ccd rows are regimes where Ccd already falls back to Pirate "
            "cc (SKIP_REGIMES) and no wire target exists. Halves criterion: "
            "BOTH halves must improve by >= HALVES_MIN_PCT vs the live max "
            "formula (stricter than Stage 0's `both positive`)."
        ),
        "regimes": regimes_out,
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
    p("h_cc_blend_formula_stage1 — halves-strict regime-conditional cc blend formula")
    p("=" * 100)
    p(f"MIN_N={MIN_N}  MIN_N_HALF={MIN_N_HALF}  POOLED_MIN_PCT={POOLED_MIN_PCT}  "
      f"HALVES_MIN_PCT={HALVES_MIN_PCT}")
    p(f"CCD_SKIP_REGIMES={sorted(CCD_SKIP_REGIMES)} (mirrors cc_from_derivation.py)")
    p(f"Halves split: chronological by obs_time")
    p()

    # Verdict rollup
    p("Verdict rollup (per regime):")
    for k in sorted(verdict_counts):
        p(f"  {k:<18} {verdict_counts[k]:>4}")
    p()

    # Per-regime detail (all regimes, ordered by descending n)
    p("=" * 100)
    p("Per-regime detail (ordered by n):")
    p("=" * 100)
    p(f"{'regime':<14} {'n':>7} {'formula':>11} {'mae_max':>8} {'mae_best':>9} "
      f"{'pooled Δ%':>10} {'hA Δ%':>8} {'hB Δ%':>8}  verdict")
    for regime in sorted(regimes_out.keys(),
                         key=lambda r: -regimes_out[r]["n"]):
        row = regimes_out[regime]
        pp = row["pooled_improve_pct"]
        ha = row["halves"]["a_improve_pct"]
        hb = row["halves"]["b_improve_pct"]
        pp_s = f"{pp:+8.2f}%" if pp is not None else "     n/a"
        ha_s = f"{ha:+6.2f}%" if ha is not None else "   n/a"
        hb_s = f"{hb:+6.2f}%" if hb is not None else "   n/a"
        p(f"{regime:<14} {row['n']:>7,} {row['formula']:>11} "
          f"{row['mae_max']:>8.3f} {row['mae_best']:>9.3f} "
          f"{pp_s:>10} {ha_s:>8} {hb_s:>8}  {row['verdict']}")
    p()

    # SHIP set
    p("=" * 100)
    p(f"SHIP set — {len(ship_set)} regime(s):")
    p("=" * 100)
    if not ship_set:
        p("  (none)")
    else:
        for regime, formula in sorted(ship_set):
            row = regimes_out[regime]
            p(f"  {regime:<14} formula={formula:<11} n={row['n']:>6,}  "
              f"pooled={row['pooled_improve_pct']:+.2f}%  "
              f"hA={row['halves']['a_improve_pct']:+.2f}%  "
              f"hB={row['halves']['b_improve_pct']:+.2f}%")
    p()

    # Gate history + verdict line
    gate = _append_gate_history({
        "fitted_at": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "verdict": "FIT" if ship_set else "HOLD",
        "ship_count": len(ship_set),
        "ship_set": sorted([[r, f] for (r, f) in ship_set]),
    })

    p("=" * 100)
    p("Rolling 7-day gate:")
    p(f"  window: {gate['history_window_days']} days · runs seen: {gate['entries_in_window']} · "
      f"distinct days: {gate['days_in_window']}")
    p(f"  fit_days: {gate['fit_days']} · hold_days: {gate['hold_days']} · "
      f"latest FIT streak: {gate['latest_streak_fit']}")
    p(f"  SHIP-set stability: {'STABLE' if gate['stable'] else 'CHURN'} "
      f"(entries changed: {len(gate['cells_changed'])})")
    if gate["cells_changed"]:
        for c in gate["cells_changed"][:10]:
            p(f"    changed: {c}")
    p(f"  gate_clear: {gate['gate_clear']}   (requires >= {GATE_WINDOW_DAYS} distinct days, "
      "no HOLD days, no SHIP-set changes)")
    p()

    if not ship_set:
        v = "VERDICT: NULL — no regime cleared halves-strict Stage 1."
    else:
        regimes = sorted({r for (r, _) in ship_set})
        v = (f"VERDICT: STAGE 1 PROMOTE — {len(ship_set)} regime(s) {regimes} cleared "
             f"halves-strict. Rolling 7-day gate: day {gate['days_in_window']}/"
             f"{GATE_WINDOW_DAYS}, set {'STABLE' if gate['stable'] else 'CHURN'}.")
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

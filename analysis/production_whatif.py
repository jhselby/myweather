"""
What-if audit: preview Production-vs-raw under each proposed intervention
by replaying the 7-day pair log with alternate applied-layer choices.

Motivation (2026-07-01): the v0.6.269 per-row applied-layer stamping +
v0.6.275 retro backfill exposed that:
  - T Production is +9% worse than raw (L6 warming branch net-negative)
  - ws Production is +23% worse than raw (population level; regime skip
    table would fix by preserving L3 in wins and skipping in losses)
  - pr Production is +5% worse than raw (L2 additive at K=1 is noisy)

Rather than waiting 7 days after each deploy to see the effect converge
in real Production, we simulate the interventions against the existing
pair-log rows. Every row carries error_l1..error_l6 already — we just
choose a different `applied_layer` per row for the intervention set,
then aggregate.

Interventions modeled:
  A) L6 warming disable — for T rows, apply=l2 (T has no L3/L4/L5, so L2
     is the deepest that changes value; both L6 branches off = Production
     equals L2).
  B) L2 direct-selection drop for ws — for ws rows, applied=l1 for the L2
     contribution (skip the station-median direct selection). L3 still
     applies where it fires (this is L2-only drop, not L3 drop).
  C) L2 additive drop for pr — for pr rows, applied=l1 (skip additive bias).
  D) ws L3 skip table — for ws rows in state_obs.regime_synoptic ∈
     {ne_flow (all bands), sea_breeze (0-11h)}, use error_l2 instead of
     error_l3. Other regimes keep L3.
  E) All above combined — the "targeted fixes" package.

Output:
  Per-field baseline Production vs raw + delta under each intervention.
  Scorecard summary (Overall / Winning fields / Biggest gain / Biggest
  regression) under baseline and each intervention.

Run:
  python3 analysis/production_whatif.py
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
WINDOW_DAYS = 7

# Field short names → human labels for print.
FIELDS = ["t", "h", "ws", "wg", "dp", "cc", "pp", "pr", "sr", "pa", "cl", "cm", "ch"]
BRIER_FIELDS = {"pp"}  # excluded from MAE-based Production comparisons

# ws L3 skip cells: (regime, lead_band_lo, lead_band_hi)
# From 2026-06-30 l3_regime_lead_analysis on 694K ws rows.
WS_SKIP_CELLS = [
    ("ne_flow",   0,  6),
    ("ne_flow",   6, 12),
    ("ne_flow",  12, 24),
    ("ne_flow",  24, 48),
    ("sea_breeze", 0,  6),
    ("sea_breeze", 6, 12),
]

# L5 (sr) skip cells: from 2026-07-02 l5_solar_analysis output.
# ne_flow: +32.3% WORSE with L5 (n=1497), calm: +10.7% worse (n=347).
# Other regimes helpful (-5% to -20%). Skip L5 in these two, use L4.
SR_L5_SKIP_CELLS = [
    ("ne_flow",   0, 48),  # all bands
    ("calm",      0, 48),
]


def _applied_from_walk(row):
    """Deepest layer whose error differs from the previous captured layer.
    Same rule as decay_fit.py's retro walk."""
    applied = None
    prev_e = None
    for lyr in ("l1", "l2", "l3", "l4", "l5", "l6"):
        e = row.get(f"error_{lyr}")
        if e is None:
            continue
        if prev_e is None or abs(float(e) - prev_e) > 1e-6:
            applied = lyr
        prev_e = float(e)
    return applied


def _ws_l3_skip(row):
    """Return True if this ws row falls in a skip cell (skip L3, use L2)."""
    if row.get("field") != "ws":
        return False
    state_obs = row.get("state_obs") or {}
    regime = state_obs.get("regime_synoptic")
    if not regime:
        return False
    lead = row.get("lead_h")
    if lead is None:
        return False
    for r, lo, hi in WS_SKIP_CELLS:
        if regime == r and lo <= lead < hi:
            return True
    return False


def _sr_l5_skip(row):
    """Return True if this sr row falls in an L5 skip cell (skip L5, use L4)."""
    if row.get("field") != "sr":
        return False
    state_obs = row.get("state_obs") or {}
    regime = state_obs.get("regime_synoptic")
    if not regime:
        return False
    lead = row.get("lead_h")
    if lead is None:
        return False
    for r, lo, hi in SR_L5_SKIP_CELLS:
        if regime == r and lo <= lead < hi:
            return True
    return False


def _intervention_error(row, intervention):
    """Return |error| for this row under the given intervention, or None if
    the row can't contribute (no per-layer breakdown)."""
    field = row.get("field")
    if intervention == "baseline":
        applied = _applied_from_walk(row)
    elif intervention == "L6_warming_off":
        # T rows: force applied to the deepest non-L6 layer (= L2 for T).
        if field == "t":
            applied = "l2"
        else:
            applied = _applied_from_walk(row)
    elif intervention == "L2_ws_drop":
        # ws L2 direct-selection off, L3 kept where it applies. L3 corrections
        # are additive per-lead constants — the correction that would result
        # from an L1 input equals the correction from an L2 input. So the
        # counterfactual is:
        #   forecast_L3_from_L1 = forecast_L3 - (forecast_L2 - forecast_L1)
        #   error_counterfactual = error_L3 - (forecast_L2 - forecast_L1)
        # Reconstruction needed only when we drop an EARLIER layer while
        # keeping a LATER one; if L3 doesn't fire (error_l3 == error_l2),
        # the counterfactual is just error_l1.
        if field == "ws":
            f_l1 = row.get("forecast_l1")
            f_l2 = row.get("forecast_l2")
            e_l3 = row.get("error_l3")
            e_l2 = row.get("error_l2")
            if e_l3 is not None and e_l2 is not None and f_l1 is not None and f_l2 is not None:
                l3_fires = abs(float(e_l3) - float(e_l2)) > 1e-6
                if l3_fires:
                    cf_err = float(e_l3) - (float(f_l2) - float(f_l1))
                    return abs(cf_err)
            # L3 didn't fire (or missing data): counterfactual = raw L1.
            e_l1 = row.get("error_l1")
            return abs(float(e_l1)) if e_l1 is not None else None
        else:
            applied = _applied_from_walk(row)
    elif intervention == "L2_pr_drop":
        # pr L2 additive off: pr has no other layers applied → applied=l1.
        if field == "pr":
            applied = "l1"
        else:
            applied = _applied_from_walk(row)
    elif intervention == "ws_L3_skip":
        # For ws rows in skip cells, use L2 error instead of L3.
        if field == "ws" and _ws_l3_skip(row):
            applied = "l2"
        else:
            applied = _applied_from_walk(row)
    elif intervention == "sr_L5_skip":
        # For sr rows in L5 skip cells (ne_flow + calm), use L4 error instead
        # of L5. Note: sr has no L2/L3 (structurally l4 == l1 for sr since
        # there's no mesonet L2 for solar and L3 isn't in sr's applicability
        # set), so "skip L5 → use L4" effectively means "use raw L1" for sr.
        # error_l4 will equal error_l1 by construction — using error_l4 is
        # correct and future-proof (if sr ever gets L3 or L4 corrections).
        if field == "sr" and _sr_l5_skip(row):
            applied = "l4"
        else:
            applied = _applied_from_walk(row)
    elif intervention == "all_targeted":
        # Combine L6 off + pr L2 drop + ws L2 drop + ws L3 skip + sr L5 skip.
        if field == "t":
            applied = "l2"
        elif field == "pr":
            applied = "l1"
        elif field == "sr" and _sr_l5_skip(row):
            applied = "l4"
        elif field == "ws":
            # L2 drop + skip-cell L3 drop.
            if _ws_l3_skip(row):
                # Both L2 and L3 off → use L1.
                e_l1 = row.get("error_l1")
                return abs(float(e_l1)) if e_l1 is not None else None
            else:
                # Keep L3, drop L2 — same counterfactual as L2_ws_drop above.
                f_l1 = row.get("forecast_l1")
                f_l2 = row.get("forecast_l2")
                e_l3 = row.get("error_l3")
                e_l2 = row.get("error_l2")
                if e_l3 is not None and e_l2 is not None and f_l1 is not None and f_l2 is not None:
                    if abs(float(e_l3) - float(e_l2)) > 1e-6:
                        return abs(float(e_l3) - (float(f_l2) - float(f_l1)))
                e_l1 = row.get("error_l1")
                return abs(float(e_l1)) if e_l1 is not None else None
        else:
            applied = _applied_from_walk(row)
    else:
        return None
    if applied is None:
        return None
    e_prod = row.get(f"error_{applied}")
    if e_prod is None:
        return None
    return abs(float(e_prod))


def _raw_error(row):
    """|error_l1| = raw model MAE contribution."""
    e = row.get("error_l1")
    return abs(float(e)) if e is not None else None


def aggregate(rows, intervention):
    """Return {field: {"prod_mae": x, "raw_mae": y, "n": n}}."""
    prod_abs = defaultdict(float)
    raw_abs = defaultdict(float)
    n_by = defaultdict(int)
    for r in rows:
        f = r.get("field")
        if f is None:
            continue
        e_prod = _intervention_error(r, intervention)
        e_raw = _raw_error(r)
        if e_prod is None or e_raw is None:
            continue
        prod_abs[f] += e_prod
        raw_abs[f] += e_raw
        n_by[f] += 1
    out = {}
    for f, n in n_by.items():
        if n == 0:
            continue
        out[f] = {
            "prod_mae": prod_abs[f] / n,
            "raw_mae":  raw_abs[f] / n,
            "n":        n,
        }
    return out


def scorecard(agg):
    """Compute Overall / Winning / Biggest gain / Biggest regression from
    an aggregate dict, excluding Brier fields."""
    rows = []
    for f, v in agg.items():
        if f in BRIER_FIELDS:
            continue
        if v["raw_mae"] == 0:
            continue
        pct = (v["prod_mae"] - v["raw_mae"]) / v["raw_mae"] * 100
        rows.append({"field": f, "pct": pct, "n": v["n"]})
    if not rows:
        return None
    mean_pct = sum(r["pct"] for r in rows) / len(rows)
    winning = sum(1 for r in rows if r["pct"] < 0)
    best = min(rows, key=lambda r: r["pct"])
    worst = max(rows, key=lambda r: r["pct"])
    return {
        "mean_pct":  mean_pct,
        "winning":   winning,
        "total":     len(rows),
        "best":      best if best["pct"] < 0 else None,
        "worst":     worst if worst["pct"] > 0 else None,
    }


def _load_rows():
    print(f"Streaming pair log (last {WINDOW_DAYS} days)...")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M")
    path = cached_path(PAIR_LOG_URL)
    rows = []
    n_total = n_kept = 0
    with open(path) as f:
        for line in f:
            n_total += 1
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (r.get("obs_time") or "") < cutoff:
                continue
            # Need per-layer errors to be usable in any intervention.
            if "error_l1" not in r:
                continue
            rows.append(r)
            n_kept += 1
    print(f"  scanned {n_total:,}, kept {n_kept:,} rows with per-layer breakdown\n")
    return rows


def _print_field_table(baseline, interventions_agg):
    """Per-field baseline vs each intervention. Shows Production %-vs-raw."""
    fields_present = sorted(set(baseline.keys()) | set(
        f for agg in interventions_agg.values() for f in agg.keys()
    ))
    labels = list(interventions_agg.keys())
    hdr = f"  {'field':>5}  {'n':>7}  {'raw':>8}  {'baseline':>10}"
    for lbl in labels:
        hdr += f"  {lbl[:14]:>14}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for f in fields_present:
        b = baseline.get(f)
        if not b:
            continue
        raw = b["raw_mae"]
        b_pct = (b["prod_mae"] - raw) / raw * 100 if raw else 0
        line = f"  {f:>5}  {b['n']:>7,}  {raw:>8.3f}  {b_pct:+9.1f}%"
        for lbl in labels:
            agg = interventions_agg[lbl]
            v = agg.get(f)
            if v and v["raw_mae"]:
                pct = (v["prod_mae"] - v["raw_mae"]) / v["raw_mae"] * 100
                delta = pct - b_pct
                line += f"  {pct:+7.1f}% ({delta:+5.1f})"
            else:
                line += f"  {'—':>14}"
        print(line)
    print()


def _print_scorecard(label, sc):
    if sc is None:
        print(f"  {label}: no eligible rows"); return
    best = sc["best"]
    worst = sc["worst"]
    best_s = f"{best['field']} {best['pct']:+.1f}%" if best else "—"
    worst_s = f"{worst['field']} {worst['pct']:+.1f}%" if worst else "—"
    print(f"  {label:<22} Overall {sc['mean_pct']:+6.1f}%   "
          f"Winning {sc['winning']:>2}/{sc['total']}   "
          f"Biggest gain {best_s:<16}   "
          f"Biggest regression {worst_s}")


def main():
    rows = _load_rows()

    print("=" * 100)
    print("PRODUCTION WHAT-IF — 7-day pair-log replay under each proposed intervention")
    print("=" * 100)
    print()

    scenarios = [
        ("baseline",         "current Production (real per-row)"),
        ("L6_warming_off",   "T: disable L6 warming branch (T Production = L2)"),
        ("L2_ws_drop",       "ws: drop L2 direct-selection (keep L3 where it fires)"),
        ("L2_pr_drop",       "pr: drop L2 additive"),
        ("ws_L3_skip",       "ws: skip L3 in (ne_flow *, sea_breeze 0-11h); keep L2"),
        ("sr_L5_skip",       "sr: skip L5 in (ne_flow *, calm *); use L4"),
        ("all_targeted",     "combined: L6 off + ws L2 drop + pr L2 drop + ws L3 skip + sr L5 skip"),
    ]

    aggs = {}
    for key, desc in scenarios:
        aggs[key] = aggregate(rows, key)

    print("Per-field Production %-vs-raw (baseline + delta under each intervention):")
    print()
    _print_field_table(
        aggs["baseline"],
        {k: v for k, v in aggs.items() if k != "baseline"},
    )

    print("Scorecard summary per scenario:")
    print()
    for key, desc in scenarios:
        _print_scorecard(f"{key}", scorecard(aggs[key]))
    print()
    print("Legend:")
    print("  Baseline column = current Production stack (real per-row) vs raw HRRR/GFS.")
    print("  Intervention columns = replayed Production %-vs-raw, with (Δ vs baseline) in parens.")
    print("  Negative = better than raw; positive = worse. Brier-evaluated fields (pp) excluded.")


if __name__ == "__main__":
    main()

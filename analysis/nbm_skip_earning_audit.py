#!/usr/bin/env python3
"""NBM skip-table stale-cell audit — symmetric to `nbm_walkforward_validator.py`
per-band SKIP proposals, but running in the opposite direction: for each cell
currently in `skip_table_nbm_curated.json`, evaluate whether the skip still
earns on recent data. If the pooled correction would now help in that cell,
propose REMOVE.

The ADD side of skip-table curation has been running daily since v0.6.462
(2026-08-21). The REMOVE side has never run — cells added on evidence weeks
ago have never been re-tested against fresh data. This closes the loop.

Scope today: l3_nbm cells only (all 19 current cells live under l3_nbm). Design
extends cleanly to l4_nbm / l5_nbm / chp_nbm / wdp_nbm when those grow skip
entries.

Counterfactual for l3_nbm skip cells:
  applied_bias   = l3_nbm_curated.corrections[field][lead_h]  (mean bias)
  cf_l3_nbm_err  = error_l2_nbm − applied_bias
  MAE(cf) vs MAE(error_l2_nbm) → if MAE(cf) < MAE, correction would help now.

Sample gate mirrors the ADD side (SKIP_CELL_LOSS_PCT=3.0, n≥50), inverted:
  REMOVE proposal iff:
    - cell lift (input − cf_layer) / input ≥ REMOVE_LIFT_PCT (3.0%)
    - n_paired ≥ MIN_N (50)
    - both halves of the window agree on direction

Runs analysis-only, no runtime effect. Downstream: `build_executive_summary`
adds a "NBM stale-skip proposals" section grep'd from the JSON output; humans
review before shipping a `history: remove` action.

Runtime:
    python3 -m analysis.nbm_skip_earning_audit
    MYWEATHER_REFRESH=1 python3 -m analysis.nbm_skip_earning_audit
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import pair_log_paths

REPO = Path(__file__).resolve().parent.parent
SKIP_TABLE_PATH = REPO / "weather_collector" / "data" / "skip_table_nbm_curated.json"
L3_NBM_CURATED_PATH = REPO / "weather_collector" / "data" / "l3_nbm_curated.json"

OUT_TXT = REPO / "analysis" / "output" / "nbm_skip_earning_audit.txt"
OUT_JSON = REPO / "analysis" / "output" / "nbm_skip_earning_audit.json"

WINDOW_DAYS = 14
MIN_N = 50
REMOVE_LIFT_PCT = 3.0        # matches SKIP_CELL_LOSS_PCT on the ADD side
HALVES_MIN_LIFT = 0.0        # both halves must be positive-lift for REMOVE

# LAYER_INPUT mirrors nbm_regression_sentry — which layer feeds this one.
LAYER_INPUT = {
    "l3_nbm": "l2_nbm",
    "l4_nbm": "l3_nbm",
    "l5_nbm": "l3_nbm",       # sr skips l4
    "l6_nbm": "l3_nbm",       # t skips l4/l5
    "chp_nbm": "l4_nbm",
    "wdp_nbm": "l3_nbm",
}


def _lead_in_cell(lead_h, lo, hi):
    """Skip-table cell shape is [regime, lead_lo_inclusive, lead_hi_exclusive]."""
    return lo <= lead_h < hi


def _load_skip_cells():
    """Yield (layer, field, regime, lead_lo, lead_hi) for every current entry."""
    try:
        doc = json.loads(SKIP_TABLE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    cells_by_layer = doc.get("cells") or {}
    out = []
    for layer, by_field in cells_by_layer.items():
        if not isinstance(by_field, dict):
            continue
        for field, cell_list in by_field.items():
            if not isinstance(cell_list, list):
                continue
            for c in cell_list:
                if not isinstance(c, list) or len(c) < 3:
                    continue
                out.append((layer, field, c[0], int(c[1]), int(c[2])))
    return out


def _load_l3_bias_table():
    """Return {field: [bias_per_lead ...]} from the current runtime L3 fit."""
    try:
        doc = json.loads(L3_NBM_CURATED_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    corr = doc.get("corrections") or {}
    return {f: v for f, v in corr.items() if isinstance(v, list)}


def _band_label(lo, hi):
    """Match nbm_walkforward_validator's band naming."""
    if (lo, hi) == (0, 6):   return "0-5h"
    if (lo, hi) == (6, 12):  return "6-11h"
    if (lo, hi) == (12, 24): return "12-23h"
    if (lo, hi) == (24, 48): return "24-47h"
    return f"{lo}-{hi-1}h"


def _score_cell(rows, layer, field, bias_table):
    """For rows in this (layer, field, regime, lead-range) cell, compute
    input MAE + counterfactual layer MAE + row-level halves split.

    Returns dict with n, input_mae, cf_layer_mae, lift_pct, halves_first_lift,
    halves_second_lift. Only l3_nbm has a scalar-bias counterfactual; other
    layers return None (extension point)."""
    if not rows:
        return None
    if layer != "l3_nbm":
        # Extension: for chp_nbm / wdp_nbm the counterfactual is the persistence
        # rule output, not a scalar bias. Would need to reconstruct from the
        # curated persistence-gate tables. Deferred — no non-l3_nbm cells today.
        return None
    bias_arr = bias_table.get(field)
    if not bias_arr:
        return None
    # Split rows by obs_time median for halves check.
    rows_sorted = sorted(rows, key=lambda r: r[0])
    mid_idx = len(rows_sorted) // 2

    def _one(bucket):
        n = 0
        sum_in = 0.0
        sum_cf = 0.0
        for _obs_time, lead_h, err_in in bucket:
            b = bias_arr[lead_h] if 0 <= lead_h < len(bias_arr) else None
            if b is None:
                continue
            n += 1
            sum_in += abs(err_in)
            sum_cf += abs(err_in - b)
        if n == 0:
            return None
        mae_in = sum_in / n
        mae_cf = sum_cf / n
        lift = 100.0 * (mae_in - mae_cf) / mae_in if mae_in > 0 else 0.0
        return {"n": n, "input_mae": mae_in, "cf_layer_mae": mae_cf, "lift_pct": lift}

    full = _one(rows_sorted)
    if full is None:
        return None
    first = _one(rows_sorted[:mid_idx])
    second = _one(rows_sorted[mid_idx:])
    return {
        "n": full["n"],
        "input_mae": round(full["input_mae"], 4),
        "cf_layer_mae": round(full["cf_layer_mae"], 4),
        "lift_pct": round(full["lift_pct"], 2),
        "halves_first_lift": round(first["lift_pct"], 2) if first else None,
        "halves_second_lift": round(second["lift_pct"], 2) if second else None,
        "n_first": first["n"] if first else 0,
        "n_second": second["n"] if second else 0,
    }


def _load_rows_for_cells(cells, window_days):
    """One pass over the pair log — for each row, if any cell matches,
    accumulate into that cell's bucket. Returns {cell_key: [(obs_time, lead_h, err_in), ...]}
    where cell_key is (layer, field, regime, lead_lo, lead_hi)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    cutoff = now - timedelta(days=window_days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M")

    # Index cells by field for fast filtering.
    by_field = defaultdict(list)  # field → list of (cell_key, layer, regime, lo, hi)
    for cell in cells:
        layer, field, regime, lo, hi = cell
        by_field[field].append((cell, layer, regime, lo, hi))

    buckets = defaultdict(list)
    n_in = 0
    for path in pair_log_paths():
        try:
            fh = open(path)
        except FileNotFoundError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                n_in += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                field = row.get("field")
                if field not in by_field:
                    continue
                obs_time = row.get("obs_time", "")
                if obs_time < cutoff_str:
                    continue
                lead_h = row.get("lead_h")
                if lead_h is None:
                    continue
                regime = ((row.get("state_fc") or {}).get("regime_synoptic")) or None
                if not regime:
                    continue
                # Match each candidate cell in this field.
                for cell, layer, cell_regime, lo, hi in by_field[field]:
                    if regime != cell_regime:
                        continue
                    if not _lead_in_cell(lead_h, lo, hi):
                        continue
                    # Input error = error_{LAYER_INPUT[layer]}
                    input_key = LAYER_INPUT.get(layer)
                    err_in = row.get(f"error_{input_key}") if input_key else None
                    if err_in is None:
                        continue
                    buckets[cell].append((obs_time, lead_h, float(err_in)))
    return buckets, n_in


def _verdict(scored):
    """Return REMOVE / HOLD / THIN based on gate rules."""
    if scored is None:
        return "THIN"
    if scored["n"] < MIN_N:
        return "THIN"
    if scored["lift_pct"] < REMOVE_LIFT_PCT:
        return "HOLD"
    h1 = scored.get("halves_first_lift")
    h2 = scored.get("halves_second_lift")
    if h1 is None or h2 is None:
        return "HOLD"
    if h1 <= HALVES_MIN_LIFT or h2 <= HALVES_MIN_LIFT:
        return "HOLD_UNSTABLE"
    return "REMOVE"


def run():
    cells = _load_skip_cells()
    if not cells:
        print("nbm_skip_earning_audit: skip table empty; nothing to audit.")
        return

    bias_table = _load_l3_bias_table()
    buckets, n_in = _load_rows_for_cells(cells, WINDOW_DAYS)

    per_cell = []
    for cell in cells:
        layer, field, regime, lo, hi = cell
        rows = buckets.get(cell, [])
        scored = _score_cell(rows, layer, field, bias_table)
        verdict = _verdict(scored)
        per_cell.append({
            "layer": layer,
            "field": field,
            "regime": regime,
            "lead_lo": lo,
            "lead_hi": hi,
            "band": _band_label(lo, hi),
            "verdict": verdict,
            "score": scored,
        })

    remove_count = sum(1 for c in per_cell if c["verdict"] == "REMOVE")
    hold_count = sum(1 for c in per_cell if c["verdict"] in ("HOLD", "HOLD_UNSTABLE"))
    thin_count = sum(1 for c in per_cell if c["verdict"] == "THIN")

    # Text report.
    lines = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M UTC")
    lines.append(f"NBM skip-table stale-cell audit — {now}")
    lines.append(f"  window={WINDOW_DAYS}d, MIN_N={MIN_N}, REMOVE_LIFT_PCT={REMOVE_LIFT_PCT}%")
    lines.append(f"  scanned {n_in:,} pair-log rows across {len(cells)} skip cells")
    lines.append("")
    lines.append(f"{'layer':<9}{'field':<5}{'regime':<13}{'band':<8}"
                 f"{'n':>6}{'input_MAE':>11}{'cf_MAE':>10}{'lift%':>9}"
                 f"{'halves1':>10}{'halves2':>10}   verdict")
    for c in per_cell:
        s = c["score"]
        if s is None:
            lines.append(f"{c['layer']:<9}{c['field']:<5}{c['regime']:<13}{c['band']:<8}"
                         f"{'—':>6}{'—':>11}{'—':>10}{'—':>9}"
                         f"{'—':>10}{'—':>10}   {c['verdict']}")
            continue
        lines.append(
            f"{c['layer']:<9}{c['field']:<5}{c['regime']:<13}{c['band']:<8}"
            f"{s['n']:>6}{s['input_mae']:>11.3f}{s['cf_layer_mae']:>10.3f}"
            f"{s['lift_pct']:>+8.2f}%"
            f"{(s['halves_first_lift'] or 0):>+9.2f}%{(s['halves_second_lift'] or 0):>+9.2f}%"
            f"   {c['verdict']}"
        )
    lines.append("")
    lines.append(f"Verdict: {remove_count} REMOVE, {hold_count} HOLD, {thin_count} THIN "
                 f"(of {len(cells)} cells).")
    if remove_count > 0:
        lines.append("")
        lines.append("REMOVE candidates (skip cell no longer earns — pooled L3 correction "
                     "would now help in this cell):")
        for c in per_cell:
            if c["verdict"] != "REMOVE":
                continue
            s = c["score"]
            lines.append(f"  • {c['layer']} {c['field']} {c['regime']} {c['band']}: "
                         f"n={s['n']:,} lift={s['lift_pct']:+.2f}% "
                         f"(halves {s['halves_first_lift']:+.2f}% / {s['halves_second_lift']:+.2f}%)")
    else:
        lines.append("")
        lines.append("No REMOVE candidates in this window — every current skip cell still "
                     "either earns its skip (pooled correction still hurts) or is THIN.")

    text = "\n".join(lines) + "\n"
    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text(text)

    out_json = {
        "fitted_at": now,
        "window_days": WINDOW_DAYS,
        "min_n": MIN_N,
        "remove_lift_pct": REMOVE_LIFT_PCT,
        "summary": {
            "remove": remove_count,
            "hold": hold_count,
            "thin": thin_count,
            "total": len(cells),
        },
        "per_cell": per_cell,
    }
    OUT_JSON.write_text(json.dumps(out_json, indent=2))

    print(text)
    print(f"  wrote {OUT_TXT}")
    print(f"  wrote {OUT_JSON}")


if __name__ == "__main__":
    run()

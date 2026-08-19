#!/usr/bin/env python3
"""Scoreboard v2 publisher (Phase 4 selector era, 2026-08-19).

Post-Phase-4 the "vs raw" scoreboard is no longer the honest question.
HRRR and NBM run in parallel; the selector picks per (field, lead-band).
The interesting questions are:

  1. Does Wyman Cove Production add value on top of the best free public
     forecast — argmin(raw HRRR, raw NBM) — for each field?
  2. Which national source is stronger (HRRR vs NBM)?
  3. Where is Production winning / flat / regressing?
  4. How stable + confident are those wins?

Emits `scoreboard_v2.json` to GCS with two windows (7-day, 24-hour)
covering the 14 forecast fields. Per-field cell shape:

    {
      "hrrr_raw_mae":  ...,   # from error_l1
      "nbm_raw_mae":   ...,   # from error_raw_nbm; None if NBM doesn't emit
      "best_public":   "hrrr"|"nbm"|"na",  # argmin per cell, or "na"
      "best_public_mae": ...,
      "selector_pick": "hrrr"|"nbm"|"na",  # from l1_selector_table
      "prod_mae":      ...,   # from `error` (whatever Prod stamped)
      "lift_vs_best_public_pct": ...,  # (best_public - prod) / best_public × 100
      "lift_vs_hrrr_pct":      ...,    # legacy "vs raw" for continuity
      "halves_a_lift_pct": ...,        # first half of window
      "halves_b_lift_pct": ...,
      "n":             ...,
      "confidence":    "HIGH"|"MED"|"LOW"|"NA",
      "verdict":       "STRONG"|"GOOD"|"WATCH"|"REGRESS"|"NA",
    }

Rollup block collapses to Section 1 numbers:
    prod_mae_mean_pct_vs_best_public
    winning_fields  (green/amber/red counts vs best-public)
    national_source_score (HRRR wins / NBM wins / insufficient)
    fields_adding_value (positive lift / flat / negative)
    health (confidence bucket counts)

Exclusions from arithmetic-mean rollup (same as v1 scoreboard):
    pp — Brier-scored, unit-different
    pa/pr — no MAE stack
    cc/dp — derived, would double-count components

Runtime:
    python3 -m analysis.scoreboard_v2
    MYWEATHER_REFRESH=1 python3 -m analysis.scoreboard_v2
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path
from analysis._output import out as _out

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
SELECTOR_TABLE_PATH = (
    Path(__file__).resolve().parent.parent
    / "weather_collector" / "data" / "l1_selector_table_curated.json"
)
OUT_JSON = _out("scoreboard_v2.json")

FIELDS = ["t", "dp", "h", "ws", "wg", "wd", "cc", "cl", "cm", "ch", "sr", "pr", "pp", "pa"]

# Fields the selector CAN choose NBM for (have full l3_nbm cascade wired).
# For fields NOT in this set, best_public collapses to HRRR-only — comparing
# Prod to a source the selector can't pick would punish us for scope, not
# correction quality. NBM raw is still shown in the display and folded into
# `opportunity_gap_pct` so the "we should extend cascade" signal isn't hidden.
SELECTOR_SCOPE = {"t", "ws", "wg", "wd", "h", "ch", "sr", "dp", "cc"}

# Fields excluded from top-level arithmetic-mean value-add rollup.
#   pp: Brier-scored, unit-different.
#   pa/pr: no meaningful MAE (pa native in inches per hour; pr in hPa; too different).
#   cc/dp: derived (cc = f(cl,cm,ch); dp = Magnus(t,h)); double-counts components.
ROLLUP_EXCLUDE = {"pp", "pa", "pr", "cc", "dp"}

BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]

WINDOWS = [("7d", 7), ("24h", 1)]

# Thresholds per Q3/Q4 agreed with Joe.
CONF_HIGH_LIFT = 10.0
CONF_HIGH_N = 200
CONF_MED_LIFT = 3.0
CONF_MED_N = 50

VERDICT_STRONG_LIFT = 10.0
VERDICT_GOOD_LIFT = 3.0
VERDICT_REGRESS_LIFT = -3.0
HALVES_STABLE_TOLERANCE = 5.0  # pp diff between halves = "stable" if both signs agree


def _load_selector_table():
    try:
        with open(SELECTOR_TABLE_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    # {field: {band: "hrrr"|"nbm"}}
    table = data.get("table") or {}
    parsed = {}
    for field, cells in table.items():
        parsed[field] = {band: (cell.get("source") or "hrrr")
                         for band, cell in (cells or {}).items()}
    return parsed


def _confidence(lift_pct, n, halves_agree):
    if lift_pct is None or n is None:
        return "NA"
    if abs(lift_pct) >= CONF_HIGH_LIFT and n >= CONF_HIGH_N and halves_agree:
        return "HIGH"
    if abs(lift_pct) >= CONF_MED_LIFT and n >= CONF_MED_N:
        return "MED"
    return "LOW"


def _verdict(lift_pct, halves_agree):
    if lift_pct is None:
        return "NA"
    if lift_pct >= VERDICT_STRONG_LIFT and halves_agree:
        return "STRONG"
    if lift_pct >= VERDICT_GOOD_LIFT:
        return "GOOD"
    if lift_pct <= VERDICT_REGRESS_LIFT:
        return "REGRESS"
    return "WATCH"


def _halves_agree(a, b):
    """Halves agree if both sides show the same sign of lift (both positive
    or both negative). NaN when either half is missing."""
    if a is None or b is None:
        return False
    return (a >= 0 and b >= 0) or (a <= 0 and b <= 0)


def _select_lift(field, band_picks, hrrr_mae, nbm_mae):
    """Return (source, source_mae) picked by the selector, or ("na", None)
    if unavailable. Falls back to hrrr when selector doesn't cover this
    field or when one side has no data."""
    picks = band_picks.get(field) or {}
    if hrrr_mae is None:
        return ("nbm", nbm_mae) if nbm_mae is not None else ("na", None)
    if nbm_mae is None:
        return ("hrrr", hrrr_mae)
    # majority-vote across bands where selector has an entry — since v2 is
    # aggregating per-field, we want one label per field per window.
    nbm_count = sum(1 for v in picks.values() if v == "nbm")
    hrrr_count = sum(1 for v in picks.values() if v == "hrrr")
    src = "nbm" if nbm_count > hrrr_count else "hrrr"
    return (src, nbm_mae if src == "nbm" else hrrr_mae)


def _band_for(lead_h):
    """0-5 / 6-11 / 12-23 / 24-47 — matches selector table + scoreboard bands."""
    if lead_h is None:
        return None
    if lead_h < 6:  return "0-5"
    if lead_h < 12: return "6-11"
    if lead_h < 24: return "12-23"
    if lead_h < 48: return "24-47"
    return None


def _accumulate(pair_log_path, window_start, halves_midpoint):
    """Walk pair log, accumulate per-field AND per-(field, band) abs-errors for
    HRRR raw, NBM raw, Prod. Split into halves at midpoint for stability check.
    Returns (per_field_acc, per_cell_acc) where per_cell_acc[(field, band)]
    carries the same keys but scoped to one lead band."""
    def _new_bucket():
        return {
            "hrrr":         [0.0, 0],  # [sum_abs, n]
            "nbm":          [0.0, 0],
            "prod":         [0.0, 0],
            "halves_a_hrrr": [0.0, 0],
            "halves_a_prod": [0.0, 0],
            "halves_b_hrrr": [0.0, 0],
            "halves_b_prod": [0.0, 0],
        }
    acc = {f: _new_bucket() for f in FIELDS}
    band_acc = defaultdict(_new_bucket)  # key: (field, band)

    with open(pair_log_path) as fin:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            field = row.get("field")
            if field not in acc:
                continue
            obs_time = row.get("obs_time", "")
            if obs_time < window_start:
                continue
            e_l1 = row.get("error_l1")
            # Prod residual is the DEEPEST-applied-layer error, not the top-
            # level `error` column (which is L2 residual by the "top-level =
            # {field}_l2" legacy convention in forecast_snapshot). The pair
            # log stamps `applied_layer` per row for exactly this purpose;
            # the corresponding `error_{applied}` is the honest Prod residual.
            # Fall back to top-level `error` when `applied_layer` is missing
            # (older pair-log rows pre-v0.6.269).
            applied = row.get("applied_layer")
            e_prod = row.get(f"error_{applied}") if applied else None
            if e_prod is None:
                e_prod = row.get("error")
            e_nbm = row.get("error_raw_nbm")
            b = acc[field]
            band = _band_for(row.get("lead_h"))
            cell = band_acc[(field, band)] if band else None
            in_half_b = (obs_time >= halves_midpoint)
            if e_l1 is not None:
                v = abs(float(e_l1))
                b["hrrr"][0] += v; b["hrrr"][1] += 1
                bucket = b["halves_b_hrrr"] if in_half_b else b["halves_a_hrrr"]
                bucket[0] += v; bucket[1] += 1
                if cell:
                    cell["hrrr"][0] += v; cell["hrrr"][1] += 1
                    bk = cell["halves_b_hrrr"] if in_half_b else cell["halves_a_hrrr"]
                    bk[0] += v; bk[1] += 1
            if e_nbm is not None:
                v = abs(float(e_nbm))
                b["nbm"][0] += v; b["nbm"][1] += 1
                if cell:
                    cell["nbm"][0] += v; cell["nbm"][1] += 1
            if e_prod is not None:
                v = abs(float(e_prod))
                b["prod"][0] += v; b["prod"][1] += 1
                bucket = b["halves_b_prod"] if in_half_b else b["halves_a_prod"]
                bucket[0] += v; bucket[1] += 1
                if cell:
                    cell["prod"][0] += v; cell["prod"][1] += 1
                    bk = cell["halves_b_prod"] if in_half_b else cell["halves_a_prod"]
                    bk[0] += v; bk[1] += 1
    return acc, band_acc


def _mean(sum_n):
    s, n = sum_n
    return (s / n) if n > 0 else None


def _compute_field_cell(field, window_acc, band_picks):
    hrrr_mae = _mean(window_acc["hrrr"])
    nbm_mae = _mean(window_acc["nbm"])
    prod_mae = _mean(window_acc["prod"])
    n = window_acc["prod"][1]

    in_scope = field in SELECTOR_SCOPE
    if in_scope and hrrr_mae is not None and nbm_mae is not None:
        if hrrr_mae <= nbm_mae:
            best_public, best_mae = "hrrr", hrrr_mae
        else:
            best_public, best_mae = "nbm", nbm_mae
    elif hrrr_mae is not None:
        # Out-of-scope OR NBM missing: HRRR is the only comparable baseline.
        best_public, best_mae = "hrrr", hrrr_mae
    elif nbm_mae is not None:
        best_public, best_mae = "nbm", nbm_mae
    else:
        best_public, best_mae = "na", None

    lift_vs_best = None
    if prod_mae is not None and best_mae is not None and best_mae > 0:
        lift_vs_best = 100.0 * (best_mae - prod_mae) / best_mae
    lift_vs_hrrr = None
    if prod_mae is not None and hrrr_mae is not None and hrrr_mae > 0:
        lift_vs_hrrr = 100.0 * (hrrr_mae - prod_mae) / hrrr_mae
    # Opportunity gap = NBM raw beats HRRR raw by X% on this field. Positive
    # value = "expanding selector to include NBM would gain this much". Only
    # meaningful when NBM raw exists AND the field is out of selector scope
    # (in-scope fields already benefit from selector picking NBM directly).
    opportunity_gap_pct = None
    if not in_scope and hrrr_mae is not None and nbm_mae is not None and hrrr_mae > 0:
        opportunity_gap_pct = 100.0 * (hrrr_mae - nbm_mae) / hrrr_mae

    # Halves lift vs HRRR raw within each half.
    def _half_lift(prefix):
        h_mae = _mean(window_acc[f"halves_{prefix}_hrrr"])
        p_mae = _mean(window_acc[f"halves_{prefix}_prod"])
        if p_mae is None or h_mae is None or h_mae == 0:
            return None
        return 100.0 * (h_mae - p_mae) / h_mae
    halves_a = _half_lift("a")
    halves_b = _half_lift("b")
    agree = _halves_agree(halves_a, halves_b)

    selector_pick, _ = _select_lift(field, band_picks, hrrr_mae, nbm_mae)

    return {
        "hrrr_raw_mae": (round(hrrr_mae, 3) if hrrr_mae is not None else None),
        "nbm_raw_mae":  (round(nbm_mae, 3) if nbm_mae is not None else None),
        "best_public":  best_public,
        "best_public_mae": (round(best_mae, 3) if best_mae is not None else None),
        "selector_pick": selector_pick,
        "prod_mae":     (round(prod_mae, 3) if prod_mae is not None else None),
        "lift_vs_best_public_pct": (round(lift_vs_best, 2) if lift_vs_best is not None else None),
        "lift_vs_hrrr_pct":        (round(lift_vs_hrrr, 2) if lift_vs_hrrr is not None else None),
        "opportunity_gap_pct":     (round(opportunity_gap_pct, 2) if opportunity_gap_pct is not None else None),
        "in_selector_scope":       in_scope,
        "halves_a_lift_pct": (round(halves_a, 2) if halves_a is not None else None),
        "halves_b_lift_pct": (round(halves_b, 2) if halves_b is not None else None),
        "halves_agree": agree,
        "n": n,
        "confidence": _confidence(lift_vs_best, n, agree),
        "verdict":    _verdict(lift_vs_best, agree),
    }


def _rollup(per_field, per_field_band, window_label):
    """Section 1-4 summary numbers from per-field + per-cell data.

    Now surfaces: touched-field vs full-field mean (rollup exclusions),
    selector-confidence % of cells, halves-agreement % of cells, verdict
    counts, and the largest (field, band) gain/regression cells.
    """
    all_lifts = []             # ALL fields (including derived/pp/pa/pr) — "all fields"
    touched_lifts = []         # excludes ROLLUP_EXCLUDE — "touched fields"
    winning = {"green": [], "amber": [], "red": []}
    source_score = {"hrrr": [], "nbm": [], "na": []}
    correction_value = {"positive": [], "flat": [], "negative": []}
    verdict_counts = {"STRONG": 0, "GOOD": 0, "WATCH": 0, "REGRESS": 0, "NA": 0}
    health = {"HIGH": 0, "MED": 0, "LOW": 0, "NA": 0}
    halves_agree_count = 0
    halves_disagree_count = 0
    for field, cell in per_field.items():
        health[cell["confidence"]] = health.get(cell["confidence"], 0) + 1
        verdict_counts[cell["verdict"]] = verdict_counts.get(cell["verdict"], 0) + 1
        if cell.get("halves_agree") is True: halves_agree_count += 1
        elif cell.get("halves_a_lift_pct") is not None and cell.get("halves_b_lift_pct") is not None:
            halves_disagree_count += 1
        lift = cell["lift_vs_best_public_pct"]
        if lift is not None:
            all_lifts.append(lift)
        # Rollup exclusions match legacy scorecard behavior.
        if field in ROLLUP_EXCLUDE:
            continue
        if lift is None:
            continue
        touched_lifts.append(lift)
        if   lift >= VERDICT_GOOD_LIFT:    winning["green"].append(field)
        elif lift <= VERDICT_REGRESS_LIFT: winning["red"].append(field)
        else:                              winning["amber"].append(field)
        # Correction value = did prod beat SELECTED source (not best public).
        # Positive: prod < selected; flat: within ±2%; negative: prod > selected.
        sel = cell["selector_pick"]
        if sel == "hrrr":
            src_mae = cell["hrrr_raw_mae"]
        elif sel == "nbm":
            src_mae = cell["nbm_raw_mae"]
        else:
            src_mae = None
        if src_mae is not None and cell["prod_mae"] is not None and src_mae > 0:
            delta = 100.0 * (src_mae - cell["prod_mae"]) / src_mae
            if   delta >= 2.0:   correction_value["positive"].append(field)
            elif delta <= -2.0:  correction_value["negative"].append(field)
            else:                correction_value["flat"].append(field)
        # National source score — which national raw is stronger on this field.
        hrrr_mae = cell["hrrr_raw_mae"]
        nbm_mae = cell["nbm_raw_mae"]
        if hrrr_mae is not None and nbm_mae is not None:
            source_score["nbm" if nbm_mae < hrrr_mae else "hrrr"].append(field)
        else:
            source_score["na"].append(field)

    def _mean_med(lst):
        if not lst: return (None, None)
        m = sum(lst) / len(lst)
        s = sorted(lst); mid = len(s) // 2
        med = s[mid] if len(s) % 2 else (s[mid-1] + s[mid]) / 2
        return (m, med)
    full_mean, full_med = _mean_med(all_lifts)
    touched_mean, touched_med = _mean_med(touched_lifts)

    # Four-answer framing: normalize each field's MAE as % of HRRR MAE
    # (unit-free), then average. Gives the direct answers to "how good is
    # HRRR vs NBM vs best-chosen vs Prod on average?". Only computed on
    # touched fields (same exclusion set) so units + interpretability stay
    # consistent with the touched-field lift row.
    nbm_ratios = []
    best_ratios = []
    prod_ratios = []
    for field, cell in per_field.items():
        if field in ROLLUP_EXCLUDE:
            continue
        h = cell.get("hrrr_raw_mae")
        n = cell.get("nbm_raw_mae")
        b = cell.get("best_public_mae")
        p = cell.get("prod_mae")
        if h is None or h <= 0:
            continue
        if n is not None:
            nbm_ratios.append(100.0 * n / h)
        if b is not None:
            best_ratios.append(100.0 * b / h)
        if p is not None:
            prod_ratios.append(100.0 * p / h)
    def _mean_or_none(lst):
        return (sum(lst) / len(lst)) if lst else None
    hrrr_baseline_pct = 100.0 if prod_ratios else None
    nbm_mean_pct = _mean_or_none(nbm_ratios)
    best_mean_pct = _mean_or_none(best_ratios)
    prod_mean_pct = _mean_or_none(prod_ratios)
    pipeline_value_add_pp = None
    if best_mean_pct is not None and prod_mean_pct is not None:
        pipeline_value_add_pp = best_mean_pct - prod_mean_pct

    # Per-cell drill-down: largest gain + regression across (field, band).
    largest_gain = None
    largest_regress = None
    n_hi_cells = 0
    n_total_cells = 0
    for field, band, lift_pct, n_cell, conf_cell, halves_ok in per_field_band:
        if lift_pct is None or n_cell < CONF_MED_N:
            continue
        n_total_cells += 1
        if conf_cell == "HIGH":
            n_hi_cells += 1
        if largest_gain is None or lift_pct > largest_gain["lift_pct"]:
            largest_gain = {"field": field, "band": band, "lift_pct": round(lift_pct, 2), "n": n_cell}
        if largest_regress is None or lift_pct < largest_regress["lift_pct"]:
            largest_regress = {"field": field, "band": band, "lift_pct": round(lift_pct, 2), "n": n_cell}

    total_halves = halves_agree_count + halves_disagree_count
    halves_agree_pct = (100.0 * halves_agree_count / total_halves) if total_halves else None
    selector_hi_pct = (100.0 * n_hi_cells / n_total_cells) if n_total_cells else None

    return {
        "window": window_label,
        "n_fields_touched": len(touched_lifts),
        "n_fields_all":     len(all_lifts),
        "value_add_mean_pct":         (round(touched_mean, 2) if touched_mean is not None else None),
        "value_add_median_pct":       (round(touched_med, 2) if touched_med is not None else None),
        "value_add_mean_all_fields":  (round(full_mean, 2) if full_mean is not None else None),
        "value_add_median_all_fields": (round(full_med, 2) if full_med is not None else None),
        "excluded_fields": sorted(list(ROLLUP_EXCLUDE)),
        # Four-answer framing: mean of per-field MAE normalized to HRRR
        # baseline (=100). Unit-free, comparable across fields.
        "mae_pct_of_hrrr": {
            "hrrr":               (round(hrrr_baseline_pct, 1) if hrrr_baseline_pct is not None else None),
            "nbm":                (round(nbm_mean_pct, 1) if nbm_mean_pct is not None else None),
            "best_chosen":        (round(best_mean_pct, 1) if best_mean_pct is not None else None),
            "prod":               (round(prod_mean_pct, 1) if prod_mean_pct is not None else None),
            "pipeline_value_add_pp": (round(pipeline_value_add_pp, 2) if pipeline_value_add_pp is not None else None),
            "n_fields": len(prod_ratios),
            "n_fields_with_nbm": len(nbm_ratios),
        },
        "winning_fields": {
            "green": winning["green"], "amber": winning["amber"], "red": winning["red"],
            "green_count": len(winning["green"]),
            "amber_count": len(winning["amber"]),
            "red_count":   len(winning["red"]),
        },
        "national_source_score": {
            "hrrr_wins_fields": source_score["hrrr"],
            "nbm_wins_fields":  source_score["nbm"],
            "insufficient":     source_score["na"],
            "hrrr_wins_count":  len(source_score["hrrr"]),
            "nbm_wins_count":   len(source_score["nbm"]),
            "insufficient_count": len(source_score["na"]),
        },
        "local_correction_value": {
            "positive_fields": correction_value["positive"],
            "flat_fields":     correction_value["flat"],
            "negative_fields": correction_value["negative"],
            "positive_count":  len(correction_value["positive"]),
            "flat_count":      len(correction_value["flat"]),
            "negative_count":  len(correction_value["negative"]),
        },
        "health": health,
        "verdict_counts": verdict_counts,
        "cell_drilldown": {
            "n_cells_scored": n_total_cells,
            "selector_high_conf_pct_of_cells": (round(selector_hi_pct, 1) if selector_hi_pct is not None else None),
            "halves_agree_pct_of_fields": (round(halves_agree_pct, 1) if halves_agree_pct is not None else None),
            "largest_gain": largest_gain,
            "largest_regression": largest_regress,
        },
    }


def main():
    band_picks = _load_selector_table()
    path = cached_path(PAIR_LOG_URL)
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

    windows_output = {}
    for label, days in WINDOWS:
        window_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
        halves_midpoint = (now - timedelta(days=days / 2)).strftime("%Y-%m-%dT%H:%M")
        acc, band_acc = _accumulate(path, window_start, halves_midpoint)
        per_field = {f: _compute_field_cell(f, acc[f], band_picks) for f in FIELDS}
        # Per-cell drilldown: compute lift + confidence per (field, band) so
        # the rollup can surface largest gain / regression and % of cells at
        # HIGH confidence. Use the same scope rule as field-level for
        # best_public (in-scope → argmin, else HRRR-only).
        per_field_band = []
        per_field_band_dict = {}
        for (field, band), b in band_acc.items():
            if b["prod"][1] == 0:
                continue
            hrrr = _mean(b["hrrr"]); nbm = _mean(b["nbm"]); prod = _mean(b["prod"])
            in_scope = field in SELECTOR_SCOPE
            if in_scope and hrrr is not None and nbm is not None:
                best = min(hrrr, nbm)
            elif hrrr is not None:
                best = hrrr
            elif nbm is not None:
                best = nbm
            else:
                best = None
            lift = None
            if prod is not None and best is not None and best > 0:
                lift = 100.0 * (best - prod) / best
            # Halves agree at cell level.
            def _hl(prefix):
                h = _mean(b[f"halves_{prefix}_hrrr"]); p = _mean(b[f"halves_{prefix}_prod"])
                return None if (p is None or h is None or h == 0) else 100.0 * (h - p) / h
            ha, hb = _hl("a"), _hl("b")
            agree = _halves_agree(ha, hb)
            n_cell = b["prod"][1]
            conf = _confidence(lift, n_cell, agree)
            per_field_band.append((field, band, lift, n_cell, conf, agree))
            per_field_band_dict.setdefault(field, {})[band] = {
                "hrrr_raw_mae": round(hrrr, 3) if hrrr is not None else None,
                "nbm_raw_mae":  round(nbm, 3) if nbm is not None else None,
                "prod_mae":     round(prod, 3) if prod is not None else None,
                "best_public_mae": round(best, 3) if best is not None else None,
                "lift_vs_best_public_pct": round(lift, 2) if lift is not None else None,
                "n": n_cell,
                "confidence": conf,
                "halves_agree": agree,
            }
        rollup = _rollup(per_field, per_field_band, label)
        windows_output[label] = {
            "per_field": per_field,
            "per_field_band": per_field_band_dict,
            "rollup": rollup,
        }

    payload = {
        "generated_at": now.isoformat() + "Z",
        "source": "forecast_error_log.jsonl",
        "windows": windows_output,
        "thresholds": {
            "confidence": {"high_lift_pct": CONF_HIGH_LIFT, "high_n": CONF_HIGH_N,
                           "med_lift_pct": CONF_MED_LIFT, "med_n": CONF_MED_N},
            "verdict":    {"strong_lift_pct": VERDICT_STRONG_LIFT,
                           "good_lift_pct":   VERDICT_GOOD_LIFT,
                           "regress_lift_pct": VERDICT_REGRESS_LIFT},
            "rollup_excluded_fields": sorted(list(ROLLUP_EXCLUDE)),
        },
        "notes": "Post-Phase-4 scoreboard. lift_vs_best_public_pct = (best_public_mae − prod_mae) / best_public_mae × 100. best_public = argmin(hrrr_raw, nbm_raw) per field. selector_pick = majority vote across bands from l1_selector_table_curated.json. halves_a/b = first/second half of window vs HRRR raw; halves_agree = same sign both halves. cc/dp/pp/pa/pr excluded from rollup arithmetic mean; still shown in per_field detail.",
    }

    with open(OUT_JSON, "w") as fout:
        json.dump(payload, fout, indent=2)
    print(f"wrote {OUT_JSON} ({os.path.getsize(OUT_JSON) / 1024:.1f} KB)")

    try:
        from weather_collector.gcs_io import upload_json  # noqa: E402
        upload_json(payload, "scoreboard_v2.json", "scoreboard_v2.json")
        print("  ✓ Published to gs://myweather-data/scoreboard_v2.json")
    except Exception as e:
        print(f"  ⚠ GCS upload skipped ({type(e).__name__}: {e}) — local file still written")

    # Summary print for terminal readers.
    for label, _ in WINDOWS:
        r = windows_output[label]["rollup"]
        print(f"\n=== {label} rollup ===")
        print(f"  value-add mean:   {r['value_add_mean_pct']}%  (n_fields={r['n_fields_touched']})")
        print(f"  winning: green={r['winning_fields']['green_count']} "
              f"amber={r['winning_fields']['amber_count']} "
              f"red={r['winning_fields']['red_count']}")
        print(f"  national: HRRR wins {r['national_source_score']['hrrr_wins_count']} · "
              f"NBM wins {r['national_source_score']['nbm_wins_count']} · "
              f"insufficient {r['national_source_score']['insufficient_count']}")
        print(f"  correction value: positive {r['local_correction_value']['positive_count']} · "
              f"flat {r['local_correction_value']['flat_count']} · "
              f"negative {r['local_correction_value']['negative_count']}")
        print(f"  health: HIGH={r['health']['HIGH']} MED={r['health']['MED']} "
              f"LOW={r['health']['LOW']} NA={r['health']['NA']}")


if __name__ == "__main__":
    main()

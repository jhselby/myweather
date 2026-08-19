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


def _accumulate(pair_log_path, window_start, halves_midpoint):
    """Walk pair log, accumulate per-field abs-errors for HRRR raw, NBM raw,
    Prod. Split into halves at midpoint for stability check. Returns
    {field: {"hrrr": [Σ, n], "nbm": [Σ, n], "prod": [Σ, n], "halves_a_hrrr": [...], ...}}."""
    acc = {f: {
        "hrrr":         [0.0, 0],  # [sum_abs, n]
        "nbm":          [0.0, 0],
        "prod":         [0.0, 0],
        "halves_a_hrrr": [0.0, 0],
        "halves_a_prod": [0.0, 0],
        "halves_b_hrrr": [0.0, 0],
        "halves_b_prod": [0.0, 0],
    } for f in FIELDS}

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
            e_prod = row.get("error")  # top-level Prod residual
            e_nbm = row.get("error_raw_nbm")
            b = acc[field]
            in_half_b = (obs_time >= halves_midpoint)
            if e_l1 is not None:
                b["hrrr"][0] += abs(float(e_l1))
                b["hrrr"][1] += 1
                bucket = b["halves_b_hrrr"] if in_half_b else b["halves_a_hrrr"]
                bucket[0] += abs(float(e_l1))
                bucket[1] += 1
            if e_nbm is not None:
                b["nbm"][0] += abs(float(e_nbm))
                b["nbm"][1] += 1
            if e_prod is not None:
                b["prod"][0] += abs(float(e_prod))
                b["prod"][1] += 1
                bucket = b["halves_b_prod"] if in_half_b else b["halves_a_prod"]
                bucket[0] += abs(float(e_prod))
                bucket[1] += 1
    return acc


def _mean(sum_n):
    s, n = sum_n
    return (s / n) if n > 0 else None


def _compute_field_cell(field, window_acc, band_picks):
    hrrr_mae = _mean(window_acc["hrrr"])
    nbm_mae = _mean(window_acc["nbm"])
    prod_mae = _mean(window_acc["prod"])
    n = window_acc["prod"][1]

    if hrrr_mae is not None and nbm_mae is not None:
        if hrrr_mae <= nbm_mae:
            best_public, best_mae = "hrrr", hrrr_mae
        else:
            best_public, best_mae = "nbm", nbm_mae
    elif hrrr_mae is not None:
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
        "halves_a_lift_pct": (round(halves_a, 2) if halves_a is not None else None),
        "halves_b_lift_pct": (round(halves_b, 2) if halves_b is not None else None),
        "halves_agree": agree,
        "n": n,
        "confidence": _confidence(lift_vs_best, n, agree),
        "verdict":    _verdict(lift_vs_best, agree),
    }


def _rollup(per_field, window_label):
    """Section 1-4 summary numbers from per-field cells."""
    prod_mae_pcts = []      # for arithmetic-mean value-add
    winning = {"green": [], "amber": [], "red": []}
    source_score = {"hrrr": [], "nbm": [], "na": []}
    correction_value = {"positive": [], "flat": [], "negative": []}
    health = {"HIGH": 0, "MED": 0, "LOW": 0, "NA": 0}
    for field, cell in per_field.items():
        health[cell["confidence"]] = health.get(cell["confidence"], 0) + 1
        # Rollup exclusions match legacy scorecard behavior.
        if field in ROLLUP_EXCLUDE:
            continue
        lift = cell["lift_vs_best_public_pct"]
        if lift is None:
            continue
        prod_mae_pcts.append(lift)
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
    value_add_mean = (sum(prod_mae_pcts) / len(prod_mae_pcts)) if prod_mae_pcts else None
    value_add_median = None
    if prod_mae_pcts:
        s = sorted(prod_mae_pcts)
        m = len(s) // 2
        value_add_median = s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2
    return {
        "window": window_label,
        "n_fields_in_mean": len(prod_mae_pcts),
        "value_add_mean_pct": (round(value_add_mean, 2) if value_add_mean is not None else None),
        "value_add_median_pct": (round(value_add_median, 2) if value_add_median is not None else None),
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
    }


def main():
    band_picks = _load_selector_table()
    path = cached_path(PAIR_LOG_URL)
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

    windows_output = {}
    for label, days in WINDOWS:
        window_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
        halves_midpoint = (now - timedelta(days=days / 2)).strftime("%Y-%m-%dT%H:%M")
        acc = _accumulate(path, window_start, halves_midpoint)
        per_field = {f: _compute_field_cell(f, acc[f], band_picks) for f in FIELDS}
        rollup = _rollup(per_field, label)
        windows_output[label] = {"per_field": per_field, "rollup": rollup}

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
        print(f"  value-add mean:   {r['value_add_mean_pct']}%  (n_fields={r['n_fields_in_mean']})")
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

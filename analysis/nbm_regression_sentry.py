#!/usr/bin/env python3
"""NBM per-layer regression sentry (F1, 2026-08-21).

Companion to `anomaly_detector.py` for the NBM cascade. Where anomaly_detector
watches the top-level Production forecast per field, this watches each NBM
layer's own residual so a degrading `l4_nbm`/`l5_nbm`/`chp_nbm` etc. surfaces
before it hurts the user-visible Prod (which may still look OK because the
selector table hasn't refit).

For each (field, layer) with an `error_{layer}` pair-log column:
  fresh window     = last 3 days
  sustained window = 4-10 days ago (7d span immediately prior to fresh)

Verdict per cell:
  HOT   MAE rose by >= 15% AND both windows have >= MIN_N pairs
  WATCH MAE rose by >= 8%
  CLEAN otherwise
  THIN  either window has < MIN_N

Digest exec-summary can grep the JSON to surface HOT rows.

Run:
    python3 analysis/nbm_regression_sentry.py

Output:
    analysis/output/nbm_regression_sentry.txt
    analysis/output/nbm_regression_sentry.json
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import pair_log_paths  # noqa: E402

OUT_TXT = os.path.join(SCRIPT_DIR, "output", "nbm_regression_sentry.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "nbm_regression_sentry.json")

# Per-layer field scope — matches the runtime whitelists in
# weather_collector/processors/{l3,l4,l5,l6}_nbm.py plus specialists.
LAYERS = [
    ("l3_nbm", ("t", "ws", "wg", "h", "ch", "sr", "dp", "cc", "wd")),
    ("l4_nbm", ("cc", "ch")),
    ("l5_nbm", ("sr",)),
    ("l6_nbm", ("t",)),
    ("chp_nbm", ("ch",)),
    ("wdp_nbm", ("wd",)),
]

# Layer's immediate input in the NBM cascade. Verdict compares the layer's
# MARGINAL help (input_mae - layer_mae) fresh vs sustained, so raw-weather
# drift (which inflates both input and layer MAE together) does not surface
# as a spurious layer regression.
LAYER_INPUT = {
    "l2_nbm": "raw_nbm",
    "l3_nbm": "l2_nbm",
    "l4_nbm": "l3_nbm",
    "l5_nbm": "l4_nbm",
    "l6_nbm": "l5_nbm",
    "chp_nbm": "l4_nbm",   # ch persistence gate rides on top of l4_nbm
    "wdp_nbm": "l3_nbm",   # wd persistence gate rides on top of l3_nbm
}

FRESH_DAYS = 3
SUSTAINED_DAYS = 7   # window immediately prior to fresh (day 4 → day 10 ago)
MIN_N_PER_WINDOW = 200

# Verdict thresholds apply to layer marginal degradation, not absolute MAE.
# HOT   = marginal helping dropped by >= 15 percentage points OR flipped
#         from helping to hurting.
# WATCH = marginal helping dropped by >= 8 pp.
HOT_PCT = 15.0
WATCH_PCT = 8.0


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def compute():
    # First pass: newest obs_time defines the anchor.
    max_ts = None
    for path in pair_log_paths():
        with open(path, "rb") as fh:
            for raw in fh:
                try:
                    r = json.loads(raw)
                except Exception:
                    continue
                ts = parse_ts(r.get("obs_time"))
                if ts is None:
                    continue
                if max_ts is None or ts > max_ts:
                    max_ts = ts
    if max_ts is None:
        return None, None

    fresh_start = max_ts - timedelta(days=FRESH_DAYS)
    sustained_end = fresh_start
    sustained_start = sustained_end - timedelta(days=SUSTAINED_DAYS)

    # acc[(field, layer)][bucket] = list of (|err_layer|, |err_input|) pairs
    # (input value is None when that row lacks the input's error column).
    # Prime with every (field, layer) in the runtime scope so cells that
    # have zero rows in either window still surface as THIN in the report.
    acc = defaultdict(lambda: {"fresh": [], "sustained": []})
    layer_names = [ln for ln, _ in LAYERS]
    field_scope = {ln: set(fs) for ln, fs in LAYERS}
    for lyr, fields in LAYERS:
        for f in fields:
            _ = acc[(f, lyr)]

    for path in pair_log_paths():
        with open(path, "rb") as fh:
            for raw in fh:
                try:
                    r = json.loads(raw)
                except Exception:
                    continue
                field = r.get("field")
                if field is None:
                    continue
                ts = parse_ts(r.get("obs_time"))
                if ts is None:
                    continue
                in_fresh = fresh_start <= ts <= max_ts
                in_sust = sustained_start <= ts < sustained_end
                if not (in_fresh or in_sust):
                    continue
                for lyr in layer_names:
                    if field not in field_scope[lyr]:
                        continue
                    err = r.get(f"error_{lyr}")
                    if err is None:
                        continue
                    input_key = LAYER_INPUT.get(lyr)
                    err_in = r.get(f"error_{input_key}") if input_key else None
                    err_in_abs = abs(float(err_in)) if err_in is not None else None
                    bucket = "fresh" if in_fresh else "sustained"
                    acc[(field, lyr)][bucket].append((abs(float(err)), err_in_abs))
    return acc, (sustained_start, sustained_end, fresh_start, max_ts)


def _window_stats(pairs):
    """Return (n_all, mae_layer, n_paired, mae_layer_paired, mae_input_paired).

    n_all is the count of rows where the layer's own error is present.
    The `_paired` values are computed only on rows where BOTH the layer's
    error and its input's error are present — so the marginal comparison
    (input_mae - layer_mae) is on the same row set.
    """
    n_all = len(pairs)
    if n_all == 0:
        return 0, 0.0, 0, 0.0, 0.0
    sum_layer = sum(p[0] for p in pairs)
    mae_layer = sum_layer / n_all
    paired = [p for p in pairs if p[1] is not None]
    n_paired = len(paired)
    if n_paired == 0:
        return n_all, mae_layer, 0, 0.0, 0.0
    mae_layer_paired = sum(p[0] for p in paired) / n_paired
    mae_input_paired = sum(p[1] for p in paired) / n_paired
    return n_all, mae_layer, n_paired, mae_layer_paired, mae_input_paired


def evaluate(acc):
    out = {}
    for (field, lyr), buckets in acc.items():
        n_f = len(buckets["fresh"])
        n_s = len(buckets["sustained"])
        cell = {"field": field, "layer": lyr, "n_fresh": n_f, "n_sustained": n_s}
        if n_f < MIN_N_PER_WINDOW or n_s < MIN_N_PER_WINDOW:
            cell["verdict"] = "THIN"
            out[f"{field}.{lyr}"] = cell
            continue
        _, mae_f, np_f, mae_lf, mae_if = _window_stats(buckets["fresh"])
        _, mae_s, np_s, mae_ls, mae_is = _window_stats(buckets["sustained"])
        cell["mae_fresh"] = round(mae_f, 3)
        cell["mae_sustained"] = round(mae_s, 3)
        cell["mae_pct_change"] = round(
            (mae_f - mae_s) / mae_s * 100 if mae_s > 0 else 0.0, 1
        )
        cell["input_layer"] = LAYER_INPUT.get(lyr)
        # If either window lacks paired input data, we cannot compute a
        # marginal — fall back to absolute-MAE verdict with a note.
        if np_f < MIN_N_PER_WINDOW or np_s < MIN_N_PER_WINDOW or mae_is <= 0 or mae_if <= 0:
            cell["marginal_available"] = False
            pct = cell["mae_pct_change"]
            if pct >= HOT_PCT:
                cell["verdict"] = "HOT"
            elif pct >= WATCH_PCT:
                cell["verdict"] = "WATCH"
            else:
                cell["verdict"] = "CLEAN"
            out[f"{field}.{lyr}"] = cell
            continue
        # Layer help as a pct of the input's MAE (positive = layer improves,
        # negative = layer degrades the input).
        help_s_pct = (mae_is - mae_ls) / mae_is * 100
        help_f_pct = (mae_if - mae_lf) / mae_if * 100
        degradation_pp = help_s_pct - help_f_pct  # positive = layer helping less now
        cell["marginal_available"] = True
        cell["n_paired_fresh"] = np_f
        cell["n_paired_sustained"] = np_s
        cell["input_mae_sustained"] = round(mae_is, 3)
        cell["input_mae_fresh"] = round(mae_if, 3)
        cell["layer_help_pct_sustained"] = round(help_s_pct, 2)
        cell["layer_help_pct_fresh"] = round(help_f_pct, 2)
        cell["marginal_degradation_pp"] = round(degradation_pp, 2)
        # HOT also fires when the layer flipped from net-helping to net-hurting
        # even below the +15pp bar.
        flipped_to_hurt = help_s_pct > 0 and help_f_pct < 0
        if degradation_pp >= HOT_PCT or flipped_to_hurt:
            cell["verdict"] = "HOT"
        elif degradation_pp >= WATCH_PCT:
            cell["verdict"] = "WATCH"
        else:
            cell["verdict"] = "CLEAN"
        out[f"{field}.{lyr}"] = cell
    return out


def emit(cells, windows):
    sustained_start, sustained_end, fresh_start, max_ts = windows
    lines = []
    lines.append("=" * 88)
    lines.append("NBM REGRESSION SENTRY — per-layer MAE watch (fresh 3d vs sustained 7d)")
    lines.append("=" * 88)
    lines.append(f"Sustained: {sustained_start.date().isoformat()} → {sustained_end.date().isoformat()}  ({SUSTAINED_DAYS}d)")
    lines.append(f"Fresh:     {fresh_start.date().isoformat()} → {max_ts.date().isoformat()}  ({FRESH_DAYS}d)")
    lines.append("")
    lines.append(f"HOT   layer marginal help dropped by ≥ +{HOT_PCT:.0f}pp (or flipped help→hurt)")
    lines.append(f"WATCH marginal help dropped by ≥ +{WATCH_PCT:.0f}pp · CLEAN otherwise · THIN n<{MIN_N_PER_WINDOW}")
    lines.append("Marginal filters out raw-weather drift; falls back to absolute ΔMAE when input pair missing.")
    lines.append("")

    hdr = (
        f"{'field':<6}{'layer':<10}{'verdict':<10}{'n_sust':>9}{'n_fresh':>9}"
        f"{'MAE_sust':>10}{'MAE_fresh':>11}{'ΔMAE%':>9}"
        f"{'help_s%':>10}{'help_f%':>10}{'Δhelp_pp':>10}"
    )
    lines.append(hdr)
    lines.append("-" * len(hdr))
    # Sort HOT first, then WATCH, then rest — most alarming at top.
    order = {"HOT": 0, "WATCH": 1, "CLEAN": 2, "THIN": 3}
    def sortkey(c):
        return (order.get(c.get("verdict", "THIN"), 4),
                -(c.get("marginal_degradation_pp") or c.get("mae_pct_change") or 0.0),
                c["layer"], c["field"])
    for c in sorted(cells.values(), key=sortkey):
        v = c.get("verdict", "?")
        mark = "★" if v == "HOT" else ("⚠" if v == "WATCH" else " ")
        if v == "THIN":
            lines.append(f"{c['field']:<6}{c['layer']:<10}{v:<10}{c['n_sustained']:>9,}{c['n_fresh']:>9,}")
            continue
        marg = c.get("marginal_available", False)
        help_s = f"{c['layer_help_pct_sustained']:>+10.2f}" if marg else f"{'  n/a':>10}"
        help_f = f"{c['layer_help_pct_fresh']:>+10.2f}" if marg else f"{'  n/a':>10}"
        dhelp = f"{c['marginal_degradation_pp']:>+10.2f}" if marg else f"{'  n/a':>10}"
        lines.append(
            f"{c['field']:<6}{c['layer']:<10}{v+' '+mark:<10}"
            f"{c['n_sustained']:>9,}{c['n_fresh']:>9,}"
            f"{c['mae_sustained']:>10.2f}{c['mae_fresh']:>11.2f}{c['mae_pct_change']:>+9.1f}"
            f"{help_s}{help_f}{dhelp}"
        )
    lines.append("")
    lines.append("help_s%/help_f% = (input_MAE - layer_MAE) / input_MAE per window (paired rows).")
    lines.append("Δhelp_pp = help_sustained − help_fresh (positive = layer degraded).")
    lines.append("")

    n_hot = sum(1 for c in cells.values() if c.get("verdict") == "HOT")
    n_watch = sum(1 for c in cells.values() if c.get("verdict") == "WATCH")
    n_clean = sum(1 for c in cells.values() if c.get("verdict") == "CLEAN")
    n_thin = sum(1 for c in cells.values() if c.get("verdict") == "THIN")
    if n_hot:
        hot = sorted(f"{c['field']}.{c['layer']}" for c in cells.values() if c.get("verdict") == "HOT")
        lines.append(f"Verdict: {n_hot} HOT, {n_watch} WATCH, {n_clean} CLEAN, {n_thin} THIN — hot: {', '.join(hot)}.")
    elif n_watch:
        watch = sorted(f"{c['field']}.{c['layer']}" for c in cells.values() if c.get("verdict") == "WATCH")
        lines.append(f"Verdict: {n_hot} HOT, {n_watch} WATCH, {n_clean} CLEAN, {n_thin} THIN — watch: {', '.join(watch)}.")
    else:
        lines.append(f"Verdict: CLEAN — {n_clean} NBM cells nominal ({n_thin} THIN).")
    return "\n".join(lines)


def main():
    acc, windows = compute()
    if acc is None:
        print("No pair-log rows found; aborting.", file=sys.stderr)
        return 1
    cells = evaluate(acc)
    text = emit(cells, windows)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    sustained_start, sustained_end, fresh_start, max_ts = windows
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "windows": {
            "sustained_start": sustained_start.isoformat(),
            "sustained_end": sustained_end.isoformat(),
            "fresh_start": fresh_start.isoformat(),
            "fresh_end": max_ts.isoformat(),
        },
        "thresholds": {
            "hot_pct": HOT_PCT,
            "watch_pct": WATCH_PCT,
            "min_n_per_window": MIN_N_PER_WINDOW,
        },
        "cells": cells,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    print(f"wrote {OUT_JSON}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

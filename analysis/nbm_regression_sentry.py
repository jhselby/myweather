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

FRESH_DAYS = 3
SUSTAINED_DAYS = 7   # window immediately prior to fresh (day 4 → day 10 ago)
MIN_N_PER_WINDOW = 200

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

    # acc[(field, layer)] = {"fresh": [|err|...], "sustained": [|err|...]}
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
                    bucket = "fresh" if in_fresh else "sustained"
                    acc[(field, lyr)][bucket].append(abs(float(err)))
    return acc, (sustained_start, sustained_end, fresh_start, max_ts)


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
        mae_f = sum(buckets["fresh"]) / n_f
        mae_s = sum(buckets["sustained"]) / n_s
        pct = (mae_f - mae_s) / mae_s * 100 if mae_s > 0 else 0.0
        cell["mae_fresh"] = round(mae_f, 3)
        cell["mae_sustained"] = round(mae_s, 3)
        cell["mae_pct_change"] = round(pct, 1)
        if pct >= HOT_PCT:
            cell["verdict"] = "HOT"
        elif pct >= WATCH_PCT:
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
    lines.append(f"HOT   ΔMAE ≥ +{HOT_PCT:.0f}% · WATCH ≥ +{WATCH_PCT:.0f}% · CLEAN otherwise · THIN n<{MIN_N_PER_WINDOW}")
    lines.append("")

    hdr = f"{'field':<6}{'layer':<10}{'verdict':<10}{'n_sust':>9}{'n_fresh':>9}{'MAE_sust':>10}{'MAE_fresh':>11}{'ΔMAE%':>9}"
    lines.append(hdr)
    lines.append("-" * len(hdr))
    # Sort HOT first, then WATCH, then rest — most alarming at top.
    order = {"HOT": 0, "WATCH": 1, "CLEAN": 2, "THIN": 3}
    def sortkey(c):
        return (order.get(c.get("verdict", "THIN"), 4),
                -(c.get("mae_pct_change") or 0.0),
                c["layer"], c["field"])
    for c in sorted(cells.values(), key=sortkey):
        v = c.get("verdict", "?")
        mark = "★" if v == "HOT" else ("⚠" if v == "WATCH" else " ")
        if v == "THIN":
            lines.append(f"{c['field']:<6}{c['layer']:<10}{v:<10}{c['n_sustained']:>9,}{c['n_fresh']:>9,}")
            continue
        lines.append(
            f"{c['field']:<6}{c['layer']:<10}{v+' '+mark:<10}"
            f"{c['n_sustained']:>9,}{c['n_fresh']:>9,}"
            f"{c['mae_sustained']:>10.2f}{c['mae_fresh']:>11.2f}{c['mae_pct_change']:>+9.1f}"
        )
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

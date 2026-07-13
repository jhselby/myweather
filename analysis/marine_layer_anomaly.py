"""
Marine-layer stratum bias-collapse detector.

The global anomaly_detector.py operates on all pair rows per field. That misses
strata that live inside ~3% of a field's pairs — like the NE-flow-morning cc
over-forecast bias that MLC sandbox is watching. Global cc bias can hold flat
while the MLC in-bin signal completely evaporates.

That's exactly what happened 2026-07-07: in_bin_signed_bias collapsed from
+37 (peak 06-30) to +10.82 (07-07) to +4.47 (07-13). Global cc bias never
budged. Had MLC.ENABLED=True been flipped mid-July per the original TODO
target, cc would now be under-corrected by ~+30 pp inside the gate.

This script reads marine_layer_watch.json (per-tick fit output already
published to GCS) and flags a collapse when the trailing 7-day mean of
in_bin_signed_bias drops materially below the prior 21-day mean. Same
2-window pattern as anomaly_detector.py, applied to the stratum's own
time series instead of a re-scan of the pair log.

Verdict:
  COLLAPSE  |Δmean| ≥ 15 units AND recent mean < 15 (signal effectively gone)
  DECAY     |Δmean| ≥ 10 units AND recent mean < baseline mean
  STABLE    otherwise

Run:
    python3 analysis/marine_layer_anomaly.py

Output:
    analysis/output/marine_layer_anomaly.txt
    analysis/output/marine_layer_anomaly.json
"""
import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

WATCH_URL = "https://data.wymancove.com/marine_layer_watch.json"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "marine_layer_anomaly.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "marine_layer_anomaly.json")

RECENT_DAYS = 7
BASELINE_DAYS = 21
COLLAPSE_DELTA = 15.0
COLLAPSE_ABS_FLOOR = 15.0
DECAY_DELTA = 10.0
MIN_ENTRIES_PER_WINDOW = 5


def parse_fitted_at(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def load_entries():
    with open(cached_path(WATCH_URL), "rb") as fh:
        payload = json.load(fh)
    out = []
    for e in payload.get("entries", []):
        ts = parse_fitted_at(e.get("fitted_at"))
        if ts is None:
            continue
        try:
            in_bias = float(e["in_bin_signed_bias"])
            out_bias = float(e["out_bin_signed_bias"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append({
            "fitted_at": ts,
            "in_bin_signed_bias": in_bias,
            "in_bin_n": e.get("in_bin_n"),
            "in_bin_mae": e.get("in_bin_mae"),
            "out_bin_signed_bias": out_bias,
        })
    out.sort(key=lambda r: r["fitted_at"])
    return out


def window_mean(entries, start, end, key):
    vals = [e[key] for e in entries if start <= e["fitted_at"] < end]
    if len(vals) < MIN_ENTRIES_PER_WINDOW:
        return None, len(vals)
    return statistics.mean(vals), len(vals)


def classify(recent_mean, baseline_mean):
    if recent_mean is None or baseline_mean is None:
        return "THIN"
    delta = recent_mean - baseline_mean
    if abs(delta) >= COLLAPSE_DELTA and recent_mean < COLLAPSE_ABS_FLOOR:
        return "COLLAPSE"
    if abs(delta) >= DECAY_DELTA and recent_mean < baseline_mean:
        return "DECAY"
    return "STABLE"


def main():
    entries = load_entries()
    if not entries:
        print("no entries in marine_layer_watch.json", file=sys.stderr)
        return 1
    max_ts = entries[-1]["fitted_at"]
    recent_start = max_ts - timedelta(days=RECENT_DAYS)
    baseline_start = recent_start - timedelta(days=BASELINE_DAYS)
    recent_end = max_ts + timedelta(minutes=1)

    in_recent, n_r = window_mean(entries, recent_start, recent_end, "in_bin_signed_bias")
    in_base, n_b = window_mean(entries, baseline_start, recent_start, "in_bin_signed_bias")
    out_recent, _ = window_mean(entries, recent_start, recent_end, "out_bin_signed_bias")
    out_base, _ = window_mean(entries, baseline_start, recent_start, "out_bin_signed_bias")
    verdict = classify(in_recent, in_base)

    lines = []
    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 88)
    emit("MARINE-LAYER STRATUM ANOMALY — MLC in-bin bias collapse detector")
    emit("=" * 88)
    emit(f"Latest fit: {max_ts.isoformat()}   entries loaded: {len(entries):,}")
    emit(f"Baseline window: {baseline_start.date().isoformat()} → {recent_start.date().isoformat()}  ({BASELINE_DAYS}d, n={n_b})")
    emit(f"Recent window:   {recent_start.date().isoformat()} → {max_ts.date().isoformat()}  ({RECENT_DAYS}d, n={n_r})")
    emit("")
    emit("In-bin signed bias (NE-flow-morning cc over-forecast — the MLC target signal):")
    if in_base is not None and in_recent is not None:
        d = in_recent - in_base
        emit(f"  baseline mean = {in_base:+.2f}   recent mean = {in_recent:+.2f}   Δ = {d:+.2f}")
    else:
        emit("  insufficient entries in one window")
    emit("")
    emit("Out-of-bin signed bias (rest of cc pairs — control):")
    if out_base is not None and out_recent is not None:
        emit(f"  baseline mean = {out_base:+.2f}   recent mean = {out_recent:+.2f}   Δ = {out_recent - out_base:+.2f}")
    emit("")

    mark = {"COLLAPSE": "★", "DECAY": "⚠", "STABLE": " ", "THIN": " "}.get(verdict, "?")
    emit(f"Verdict: {verdict} {mark}")
    if verdict == "COLLAPSE":
        emit("  → Recent in-bin bias is effectively gone. Flipping MLC.ENABLED=True now would over-correct cc.")
        emit("  → Investigate: (a) same HRRR anomaly window as cm (07-04 → present)? (b) seasonal shift?")
    elif verdict == "DECAY":
        emit("  → Signal is fading but not gone. Hold MLC.ENABLED=False; extend trend watch.")
    elif verdict == "STABLE":
        emit("  → In-bin signal holding. TODO's mid-July flip criterion still viable pending trend check.")

    text = "\n".join(lines)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "windows": {
            "baseline_start": baseline_start.isoformat(),
            "baseline_end": recent_start.isoformat(),
            "recent_start": recent_start.isoformat(),
            "recent_end": max_ts.isoformat(),
        },
        "thresholds": {
            "collapse_delta": COLLAPSE_DELTA,
            "collapse_abs_floor": COLLAPSE_ABS_FLOOR,
            "decay_delta": DECAY_DELTA,
            "min_entries_per_window": MIN_ENTRIES_PER_WINDOW,
        },
        "in_bin_bias_baseline_mean": in_base,
        "in_bin_bias_recent_mean": in_recent,
        "out_bin_bias_baseline_mean": out_base,
        "out_bin_bias_recent_mean": out_recent,
        "entries_baseline": n_b,
        "entries_recent": n_r,
        "verdict": verdict,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    print(f"wrote {OUT_JSON}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

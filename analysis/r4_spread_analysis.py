#!/usr/bin/env python3
"""
R4 hypothesis: does HRRR vs GFS spread predict forecast error?

For each (run, valid, field), we have:
  - HRRR L1 from forecast_error_log.jsonl (forecast_l1)
  - GFS L1 from gfs_l1_log.json (snapshots[].hours[])
  - Observed value from forecast_error_log.jsonl (observed)
  - Spread = |HRRR - GFS|
  - Actual error = |HRRR - observed|

Question: does spread correlate with error per-field, per-lead-band?

Verdict rule (from project_r4_r5_hypotheses memory):
  - Ship as a confidence signal if median Spearman ρ > 0.25
    for ≥ 3 fields, consistent across lead bands (1-6h, 6-24h, 24-47h).
  - Close the hypothesis otherwise.

Run:
    python3 analysis/r4_spread_analysis.py
    python3 analysis/r4_spread_analysis.py --local-file /tmp/forecast_error_log.jsonl

Output: analysis/output/r4_spread_summary.txt
"""
import argparse
import gzip
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
GFS_LOG_URL   = "https://data.wymancove.com/gfs_l1_log.json"
OUT_PATH      = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "output", "r4_spread_summary.txt")

FIELDS = ["t", "h", "ws", "wg", "pp", "cc"]  # GFS log captures these
BANDS  = [("1-6h", 1, 6), ("6-24h", 6, 24), ("24-47h", 24, 48)]
SHIP_THRESHOLD = 0.25  # median Spearman ρ to ship as confidence signal
MIN_FIELDS_AGREE = 3   # # of fields that need to clear the threshold


def _fetch_gfs_snapshots():
    """Load the full GFS L1 log into a {(run, valid, field): value} index."""
    req = urllib.request.Request(GFS_LOG_URL, headers={"User-Agent": "myweather-r4/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read()
    # Stored gzipped on GCS; Cloudflare may or may not decompress on the way.
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = json.loads(gzip.decompress(raw))
    snapshots = data.get("snapshots", [])
    sys.stderr.write(f"  Loaded {len(snapshots)} GFS snapshots\n")
    idx = {}
    for snap in snapshots:
        run = snap.get("run")
        if not run:
            continue
        for h in snap.get("hours", []):
            v = h.get("v")
            if not v:
                continue
            for f in FIELDS:
                if h.get(f) is not None:
                    idx[(run, v, f)] = h[f]
    sys.stderr.write(f"  GFS index: {len(idx):,} (run, valid, field) tuples\n")
    return idx


def _stream_pair_log(local_file=None):
    """Yield decoded pair rows from the live or local pair log."""
    if local_file:
        sys.stderr.write(f"  Reading pair log from {local_file}\n")
        with open(local_file) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        return
    req = urllib.request.Request(ERROR_LOG_URL, headers={"User-Agent": "myweather-r4/1.0"})
    sys.stderr.write(f"  Streaming pair log via Cloudflare (~7-10 min)...\n")
    with urllib.request.urlopen(req, timeout=1800) as resp:
        for raw in resp:
            if not raw or not raw.strip():
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                continue


def _band_for(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def _spearman(xs, ys):
    """Spearman rank correlation, ties broken by average. Returns ρ in [-1, 1]
    or None if n < 5."""
    n = len(xs)
    if n < 5:
        return None
    def _rank(arr):
        sorted_idx = sorted(range(n), key=lambda i: arr[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and arr[sorted_idx[j + 1]] == arr[sorted_idx[i]]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                ranks[sorted_idx[k]] = avg_rank
            i = j + 1
        return ranks
    rx = _rank(xs)
    ry = _rank(ys)
    mean_x = sum(rx) / n
    mean_y = sum(ry) / n
    num = sum((rx[i] - mean_x) * (ry[i] - mean_y) for i in range(n))
    dxx = sum((rx[i] - mean_x) ** 2 for i in range(n))
    dyy = sum((ry[i] - mean_y) ** 2 for i in range(n))
    denom = (dxx * dyy) ** 0.5
    return num / denom if denom > 0 else None


def run_analysis(local_file=None):
    gfs_idx = _fetch_gfs_snapshots()
    # Collect (spread, error) pairs per (field, band)
    samples = defaultdict(lambda: {"spread": [], "error": []})
    n_pair_rows = 0
    n_joined = 0
    for r in _stream_pair_log(local_file=local_file):
        n_pair_rows += 1
        field = r.get("field")
        if field not in FIELDS:
            continue
        lead_h = r.get("lead_h")
        if lead_h is None:
            continue
        band = _band_for(lead_h)
        if band is None:
            continue
        run = r.get("run_time")
        v = r.get("valid_time")
        if not run or not v:
            continue
        hrrr = r.get("forecast_l1")
        obs = r.get("observed")
        if hrrr is None or obs is None:
            continue
        gfs = gfs_idx.get((run, v, field))
        if gfs is None:
            continue
        spread = abs(hrrr - gfs)
        error = abs(hrrr - obs)
        samples[(field, band)]["spread"].append(spread)
        samples[(field, band)]["error"].append(error)
        n_joined += 1
    sys.stderr.write(f"  Streamed {n_pair_rows:,} pair rows, joined {n_joined:,} against GFS\n")

    # Per (field, band): Spearman ρ
    results = {}
    for (field, band), s in samples.items():
        rho = _spearman(s["spread"], s["error"])
        results[(field, band)] = {"n": len(s["spread"]), "rho": rho}

    # Per-field aggregate: median ρ across bands (only including non-null)
    field_medians = {}
    for f in FIELDS:
        rhos = []
        for b, _, _ in BANDS:
            r = results.get((f, b))
            if r and r["rho"] is not None:
                rhos.append(r["rho"])
        if rhos:
            field_medians[f] = sorted(rhos)[len(rhos) // 2]
        else:
            field_medians[f] = None

    # Verdict
    fields_above_threshold = sum(
        1 for f in FIELDS
        if field_medians.get(f) is not None and field_medians[f] > SHIP_THRESHOLD
    )
    ship = fields_above_threshold >= MIN_FIELDS_AGREE

    return {
        "results": results,
        "field_medians": field_medians,
        "fields_above_threshold": fields_above_threshold,
        "ship": ship,
        "n_pair_rows": n_pair_rows,
        "n_joined": n_joined,
    }


def write_summary(result, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = []
    lines.append(f"R4 hypothesis — HRRR vs GFS spread vs forecast error")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append(f"Ship threshold: median Spearman ρ > {SHIP_THRESHOLD} on ≥ {MIN_FIELDS_AGREE} fields")
    lines.append(f"Joined {result['n_joined']:,} (pair, GFS) tuples from {result['n_pair_rows']:,} pair rows")
    lines.append("")
    lines.append(f"{'field':<6}  {'1-6h ρ':>10}  {'n':>6}  {'6-24h ρ':>10}  {'n':>6}  {'24-47h ρ':>10}  {'n':>6}  {'median':>9}")
    lines.append("  " + "-" * 92)
    for f in FIELDS:
        row = [f]
        for b, _, _ in BANDS:
            r = result["results"].get((f, b))
            if r and r["rho"] is not None:
                row.append(f"{r['rho']:>10.3f}")
                row.append(f"{r['n']:>6}")
            else:
                row.append(f"{'--':>10}")
                row.append(f"{r['n'] if r else 0:>6}")
        med = result["field_medians"].get(f)
        row.append(f"{med:>9.3f}" if med is not None else f"{'--':>9}")
        lines.append("  " + "  ".join(row[:1]).ljust(6) + "  " + "  ".join(row[1:]))
    lines.append("")
    lines.append(f"Fields with median ρ > {SHIP_THRESHOLD}: {result['fields_above_threshold']} / {len(FIELDS)}")
    if result["ship"]:
        lines.append(f"VERDICT: SHIP — R4 spread is a usable confidence signal.")
        lines.append(f"  Hook into briefing prompt + widen displayed intervals when spread is high.")
    else:
        lines.append(f"VERDICT: CLOSE — R4 spread doesn't correlate strongly with error.")
        lines.append(f"  Below threshold on too many fields; spread isn't a reliable proxy.")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--local-file", default=None,
                   help="read pair log from local file instead of streaming")
    args = p.parse_args()
    result = run_analysis(local_file=args.local_file)
    out_path = write_summary(result, OUT_PATH)
    sys.stderr.write(f"\nWrote {out_path}\n")
    with open(out_path) as f:
        sys.stdout.write(f.read())
    return 0 if result["ship"] else 1


if __name__ == "__main__":
    sys.exit(main())

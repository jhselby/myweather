"""
Backtest sweep — evaluate many L3/L4 configs against the pair log in a
single stream of the file. Streams once, scores per (pair, config) at
each row, emits a comparison matrix.

10× faster than running `evaluate_config` per candidate when you have
multiple configs to test (vs running the streamer N times).
"""
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone


ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"


def _stream_pairlog(test_days, local_file=None):
    """Stream pairs in the last `test_days` window.

    If `local_file` is provided, read from that file (much faster, no
    network roundtrip). Otherwise fetch via urllib from Cloudflare CDN
    (takes ~7-10 min on the current 4 GB file, will shrink ~6× as the
    v0.6.77 dedup ages in over 30 days).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=test_days)).strftime("%Y-%m-%dT%H:%M")
    n_total = 0
    n_in_window = 0

    if local_file:
        sys.stderr.write(f"  Reading from local file {local_file} (cutoff={cutoff})...\n")
        with open(local_file) as f:
            for raw in f:
                if not raw or not raw.strip():
                    continue
                n_total += 1
                try:
                    r = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if (r.get("obs_time") or "") < cutoff:
                    continue
                n_in_window += 1
                yield r
        sys.stderr.write(f"  Read {n_total:,} rows, {n_in_window:,} in window\n")
        return

    sys.stderr.write(f"  Streaming pair log via Cloudflare (cutoff={cutoff}, ~7-10 min)...\n")
    req = urllib.request.Request(
        ERROR_LOG_URL,
        headers={"User-Agent": "myweather-backtest-sweep/1.0"},
    )
    with urllib.request.urlopen(req, timeout=1800) as resp:
        for raw in resp:
            if not raw or not raw.strip():
                continue
            n_total += 1
            try:
                r = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if (r.get("obs_time") or "") < cutoff:
                continue
            n_in_window += 1
            yield r
    sys.stderr.write(f"  Streamed {n_total:,} rows, {n_in_window:,} in window\n")


def _pick_forecast(pair, config):
    field = pair.get("field")
    l3 = config.get("L3_FIELDS", set())
    l4 = config.get("L4_FIELDS", set())
    if field in l4 and pair.get("forecast_l4") is not None:
        return pair["forecast_l4"]
    if field in l3 and pair.get("forecast_l3") is not None:
        return pair["forecast_l3"]
    if pair.get("forecast_l2") is not None:
        return pair["forecast_l2"]
    if pair.get("forecast_l1") is not None:
        return pair["forecast_l1"]
    return pair.get("forecast")


LEAD_BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]


def _band_for(lead_h):
    for label, lo, hi in LEAD_BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def sweep(configs, test_days=2, local_file=None, by_band=False):
    """Evaluate a dict of named configs in one stream of the pair log.

    configs: {name: {"L3_FIELDS": set, "L4_FIELDS": set}}

    Returns: {
      "test_days": float,
      "total_pairs": int,
      "results": {
        name: {field: {"n": int, "mae": float}},
        ...
      }
    }
    """
    stats = {name: defaultdict(lambda: [0, 0.0]) for name in configs}
    band_stats = {name: defaultdict(lambda: [0, 0.0]) for name in configs} if by_band else None
    total = 0
    for pair in _stream_pairlog(test_days, local_file=local_file):
        field = pair.get("field")
        obs = pair.get("observed")
        if field is None or obs is None:
            continue
        total += 1
        lead_h = pair.get("lead_h")
        band = _band_for(lead_h) if (by_band and lead_h is not None) else None
        for name, cfg in configs.items():
            fc = _pick_forecast(pair, cfg)
            if fc is None:
                continue
            ae = abs(fc - obs)
            s = stats[name][field]
            s[0] += 1
            s[1] += ae
            if band is not None:
                bs = band_stats[name][(field, band)]
                bs[0] += 1
                bs[1] += ae

    results = {}
    for name in configs:
        per_field = {}
        for field, (n, sum_abs) in stats[name].items():
            per_field[field] = {"n": n, "mae": round(sum_abs / n, 4) if n else None}
        results[name] = per_field
    out = {"test_days": test_days, "total_pairs": total, "results": results}

    if by_band:
        by_band_results = {}
        for name in configs:
            by_band_results[name] = {}
            for (field, band), (n, sum_abs) in band_stats[name].items():
                by_band_results[name].setdefault(field, {})[band] = {
                    "n": n,
                    "mae": round(sum_abs / n, 4) if n else None,
                }
        out["by_band"] = by_band_results
    return out


def print_matrix(sweep_result, sort_by="production"):
    """Pretty-print a comparison matrix across configs."""
    results = sweep_result["results"]
    names = list(results)
    all_fields = sorted({f for r in results.values() for f in r})

    # Header
    header = f"  {'field':<6} {'n':>7}"
    for name in names:
        header += f" {name[:14]:>14}"
    print(header)
    print(f"  {'-'*6} {'-'*7}" + "".join(f" {'-'*14}" for _ in names))

    for f in all_fields:
        n_any = max((results[name].get(f, {}).get("n") or 0) for name in names)
        row = f"  {f:<6} {n_any:>7}"
        for name in names:
            mae = results[name].get(f, {}).get("mae")
            row += f" {mae:>14.4f}" if mae is not None else f" {'--':>14}"
        print(row)

    print()
    print(f"Window: last {sweep_result['test_days']:.1f} days · total {sweep_result['total_pairs']:,} pairs")


def main():
    """CLI: run a sweep across the canonical named configs."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from backtest.run import NAMED_CONFIGS

    import argparse
    p = argparse.ArgumentParser(description="Multi-config backtest sweep")
    p.add_argument("--days", type=float, default=2.0)
    p.add_argument("--configs", default="production,walkforward_15jun,walkforward_08jun,stable_core,l2_only",
                   help="comma-separated config names")
    p.add_argument("--json", action="store_true")
    p.add_argument("--write-gcs", action="store_true",
                   help="upload result JSON to gs://myweather-data/backtest_sweep_results.json for the debug page")
    p.add_argument("--local-file", default=None,
                   help="read from local jsonl file instead of streaming via Cloudflare (much faster)")
    p.add_argument("--by-band", action="store_true",
                   help="also compute per-lead-band MAE (0-5h, 6-11h, 12-23h, 24-47h)")
    args = p.parse_args()

    config_names = [c.strip() for c in args.configs.split(",") if c.strip()]
    selected = {name: NAMED_CONFIGS[name] for name in config_names if name in NAMED_CONFIGS}
    if not selected:
        raise SystemExit(f"no valid configs. Available: {list(NAMED_CONFIGS)}")

    print(f"Running sweep across {len(selected)} configs: {list(selected)}")
    print(f"Window: last {args.days} days. Streaming pair log (may take 2-5 min)...")
    print()

    result = sweep(selected, test_days=args.days, local_file=args.local_file, by_band=args.by_band)

    if args.json:
        print(json.dumps(result, indent=2, default=list))
    else:
        print_matrix(result)

    if args.write_gcs:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from weather_collector.gcs_io import upload_json
        # Include config definitions so the UI can show what each named
        # config actually contains (otherwise the user has to look up the code).
        result["config_defs"] = {
            name: {"L3_FIELDS": sorted(cfg["L3_FIELDS"]), "L4_FIELDS": sorted(cfg["L4_FIELDS"])}
            for name, cfg in selected.items()
        }
        result["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        upload_json(result, "backtest_sweep_results.json", "backtest_sweep_results.json")
        print()
        print("Uploaded to gs://myweather-data/backtest_sweep_results.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())

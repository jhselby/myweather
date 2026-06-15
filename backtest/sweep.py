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


def _download_test_window(test_days, cache_path="/tmp/myweather_pairlog_window.jsonl"):
    """Download the pair-log rows in the last `test_days` window to a local
    cache file. One network stream, then all subsequent reads are local.

    Returns the cache path. Cache is reused if it's younger than 10 min
    (lets you re-run a sweep with different configs without re-downloading).
    """
    import os
    import subprocess
    if os.path.exists(cache_path):
        age_s = datetime.now().timestamp() - os.path.getmtime(cache_path)
        if age_s < 600:
            sys.stderr.write(f"  Using cached pair-log window ({age_s/60:.1f} min old)\n")
            return cache_path
    cutoff = (datetime.now(timezone.utc) - timedelta(days=test_days)).strftime("%Y-%m-%dT%H:%M")
    sys.stderr.write(f"  Downloading pair-log via gsutil (cutoff={cutoff})...\n")
    cmd = (
        f"gsutil cat gs://myweather-data/forecast_error_log.jsonl | "
        f"python3 -c \"import sys,json; cutoff='{cutoff}'; "
        f"[sys.stdout.write(l) for l in sys.stdin if l.strip() and (json.loads(l).get('obs_time') or '') >= cutoff]\""
    )
    with open(cache_path, "w") as out:
        result = subprocess.run(cmd, shell=True, stdout=out, stderr=subprocess.PIPE, timeout=600)
    if result.returncode != 0:
        sys.stderr.write(f"  Download failed: {result.stderr.decode()[:500]}\n")
        return None
    size_mb = os.path.getsize(cache_path) / 1024 / 1024
    sys.stderr.write(f"  Cached {size_mb:.1f} MB to {cache_path}\n")
    return cache_path


def _stream_cached(cache_path):
    """Yield decoded pair rows from the cache file."""
    with open(cache_path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


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


def sweep(configs, test_days=2):
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
    cache = _download_test_window(test_days)
    if cache is None:
        raise SystemExit("Failed to download pair-log window")
    stats = {name: defaultdict(lambda: [0, 0.0]) for name in configs}
    total = 0
    for pair in _stream_cached(cache):
        field = pair.get("field")
        obs = pair.get("observed")
        if field is None or obs is None:
            continue
        total += 1
        for name, cfg in configs.items():
            fc = _pick_forecast(pair, cfg)
            if fc is None:
                continue
            s = stats[name][field]
            s[0] += 1
            s[1] += abs(fc - obs)

    results = {}
    for name in configs:
        per_field = {}
        for field, (n, sum_abs) in stats[name].items():
            per_field[field] = {"n": n, "mae": round(sum_abs / n, 4) if n else None}
        results[name] = per_field
    return {"test_days": test_days, "total_pairs": total, "results": results}


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
    args = p.parse_args()

    config_names = [c.strip() for c in args.configs.split(",") if c.strip()]
    selected = {name: NAMED_CONFIGS[name] for name in config_names if name in NAMED_CONFIGS}
    if not selected:
        raise SystemExit(f"no valid configs. Available: {list(NAMED_CONFIGS)}")

    print(f"Running sweep across {len(selected)} configs: {list(selected)}")
    print(f"Window: last {args.days} days. Streaming pair log (may take 2-5 min)...")
    print()

    result = sweep(selected, test_days=args.days)

    if args.json:
        print(json.dumps(result, indent=2, default=list))
    else:
        print_matrix(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())

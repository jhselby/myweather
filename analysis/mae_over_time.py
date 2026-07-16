"""MAE / RMSE / bias over time — per obs day per field per layer.

Aggregates forecast_error_log.jsonl by obs date × field × layer (Raw vs
Prod). Emits daily-scale time series suitable for a "how is Production
trending over time" chart on the debug page.

Publishes to gs://myweather-data/mae_over_time.json for the frontend.

The pair log currently retains ~30 days of history. Chart shows Raw and
Prod side by side; the gap between them = how much work the correction
stack is doing. Trend flattening or gap shrinking is the drift signal
this chart surfaces earlier than the 2-window anomaly detector.

Run:
    python3 analysis/mae_over_time.py

Output:
    analysis/output/mae_over_time.json
    (published to GCS bucket if google auth available)
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "mae_over_time.json")

FIELDS = ["t", "dp", "h", "ws", "wg", "cc", "cl", "cm", "ch", "sr", "pr", "pp", "pa"]
MIN_N_PER_DAY = 200  # skip (field, day) cells with too few pairs — avoids noise spikes on thin days


LAYER_KEYS = [("raw", "error_l1"), ("l2", "error_l2"), ("l3", "error_l3"), ("prod", "error_l4")]


def main():
    path = cached_path(ERROR_LOG_URL)
    # (day, field) → {layer: [errs]}
    buckets = defaultdict(lambda: {ln: [] for ln, _ in LAYER_KEYS})
    n_total = 0
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            n_total += 1
            fld = r.get("field")
            if fld not in FIELDS:
                continue
            ot = r.get("obs_time")
            if not ot:
                continue
            day = ot[:10]
            skip = False
            per_layer = {}
            for ln, key in LAYER_KEYS:
                e = r.get(key)
                if e is None:
                    skip = True
                    break
                per_layer[ln] = e
            if skip:
                continue
            for ln, e in per_layer.items():
                buckets[(day, fld)][ln].append(e)

    days = sorted({d for d, _ in buckets})
    fields_present = sorted({f for _, f in buckets})

    # series[field][layer][day] = {n, mae, rmse, bias, brier}
    # brier = mean(err²) — same math as RMSE² but Brier is the conventional
    # name for probabilistic forecasts (pp). Emitted for every field; the
    # frontend surfaces it as a metric option and it's meaningful for pp
    # in particular (0-1 probability vs 0/1 observation).
    series = defaultdict(lambda: defaultdict(dict))
    for (day, fld), errs in buckets.items():
        for layer_name in errs:
            xs = errs[layer_name]
            n = len(xs)
            if n < MIN_N_PER_DAY:
                continue
            mae = sum(abs(x) for x in xs) / n
            sqerr_mean = sum(x * x for x in xs) / n
            rmse = math.sqrt(sqerr_mean)
            bias = sum(xs) / n
            series[fld][layer_name][day] = {
                "n": n,
                "mae": round(mae, 4),
                "rmse": round(rmse, 4),
                "bias": round(bias, 4),
                "brier": round(sqerr_mean, 4),
            }

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "forecast_error_log.jsonl",
        "min_n_per_day": MIN_N_PER_DAY,
        "days": days,
        "fields": fields_present,
        "series": {fld: dict(layers) for fld, layers in series.items()},
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"wrote {OUT_JSON}   ({n_total:,} pair rows, {len(days)} days, {len(fields_present)} fields)")

    # Publish to GCS (same pattern as h_persistence_skill.py)
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from weather_collector.gcs_io import upload_json  # noqa: E402
        upload_json(payload, "mae_over_time.json", "mae_over_time.json")
        print("  ✓ Published to gs://myweather-data/mae_over_time.json")
    except Exception as e:
        print(f"  ⚠ GCS upload skipped ({type(e).__name__}: {e}) — local file still written")


if __name__ == "__main__":
    main()

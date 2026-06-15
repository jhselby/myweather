"""
Pair-log-based backtest replay.

Given an L3/L4 enable config (subsets of currently-fitted fields), compute
per-field MAE on held-out pair-log data. Uses the per-layer forecast values
(`forecast_l1` ... `forecast_l4`) that the joiner stamps on each pair.

What this CAN test (Phase 3 MVP):
  - "Drop field X from L3_FIELDS"  → use forecast_l2 for X
  - "Drop field Y from L4_FIELDS"  → use forecast_l3 for Y
  - "Disable both layers entirely" → use forecast_l1 for everything

What this CANNOT test (deferred to Phase 4+):
  - Add fields to L3/L4 that aren't currently fitted (no coefficients exist
    to apply — would require re-running the Fitter on alternative whitelists)
  - Change τ values, Kalman gains, L2 station weights — these are baked into
    the production-stamped forecast_l1/l2 values
  - Change coefficient regularization / shrinkage

The output mirrors `analysis/walkforward_l3l4_validator.py` (per-field MAE
table) but supports arbitrary L3/L4 subsets rather than just the 3 fixed
enable-state combinations.
"""
import json
import os
import urllib.request
from collections import defaultdict


ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"


def _stream_pairs(test_days=2):
    """Stream pairs from the live forecast_error_log.jsonl. Filters to the
    last `test_days` of obs_time as the held-out test window."""
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=test_days)).strftime("%Y-%m-%dT%H:%M")

    req = urllib.request.Request(
        ERROR_LOG_URL,
        headers={
            "User-Agent": "myweather-backtest/1.0",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as f:
        for line in f:
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (r.get("obs_time") or "") >= cutoff:
                yield r


def _pick_forecast(pair, config):
    """Pick the appropriate forecast layer for this pair based on config.

    Resolution order (last-enabled-layer wins):
      - if field in config["L4_FIELDS"] and pair has forecast_l4 → l4
      - elif field in config["L3_FIELDS"] and pair has forecast_l3 → l3
      - elif pair has forecast_l2 → l2  (the natural baseline)
      - elif pair has forecast_l1 → l1
      - else: fall back to the top-level "forecast" field

    Returns (forecast_value, layer_label) or (None, None) if no usable value.
    """
    field = pair.get("field")
    l3 = config.get("L3_FIELDS", set())
    l4 = config.get("L4_FIELDS", set())
    if field in l4 and pair.get("forecast_l4") is not None:
        return pair["forecast_l4"], "l4"
    if field in l3 and pair.get("forecast_l3") is not None:
        return pair["forecast_l3"], "l3"
    if pair.get("forecast_l2") is not None:
        return pair["forecast_l2"], "l2"
    if pair.get("forecast_l1") is not None:
        return pair["forecast_l1"], "l1"
    if pair.get("forecast") is not None:
        return pair["forecast"], "raw"
    return None, None


def evaluate_config(config, test_days=2):
    """Compute per-field MAE for `config` on the last `test_days` of pair log.

    Returns:
      {
        "config": {...as-passed...},
        "per_field": {field: {"n": int, "mae": float, "layer_dist": {l1:n, l2:n, l3:n, l4:n}}},
        "test_days": float,
        "total_pairs": int,
      }
    """
    per_field = defaultdict(lambda: {"n": 0, "sum_abs_err": 0.0, "layer_dist": defaultdict(int)})
    total = 0
    for pair in _stream_pairs(test_days=test_days):
        field = pair.get("field")
        obs = pair.get("observed")
        if field is None or obs is None:
            continue
        fc, layer = _pick_forecast(pair, config)
        if fc is None:
            continue
        per_field[field]["n"] += 1
        per_field[field]["sum_abs_err"] += abs(fc - obs)
        per_field[field]["layer_dist"][layer] += 1
        total += 1

    result_per_field = {}
    for field, stats in per_field.items():
        result_per_field[field] = {
            "n":   stats["n"],
            "mae": round(stats["sum_abs_err"] / stats["n"], 4) if stats["n"] else None,
            "layer_dist": dict(stats["layer_dist"]),
        }
    return {
        "config": {"L3_FIELDS": sorted(config.get("L3_FIELDS", [])),
                   "L4_FIELDS": sorted(config.get("L4_FIELDS", []))},
        "per_field": result_per_field,
        "test_days": test_days,
        "total_pairs": total,
    }


def compare_configs(baseline, candidate, test_days=2):
    """A/B two configs against the same held-out pair-log window. Returns
    per-field MAE for each + delta + verdict (which config wins per field)."""
    a = evaluate_config(baseline, test_days=test_days)
    b = evaluate_config(candidate, test_days=test_days)

    rows = []
    all_fields = sorted(set(a["per_field"]) | set(b["per_field"]))
    for f in all_fields:
        a_mae = a["per_field"].get(f, {}).get("mae")
        b_mae = b["per_field"].get(f, {}).get("mae")
        n     = a["per_field"].get(f, {}).get("n") or b["per_field"].get(f, {}).get("n") or 0
        if a_mae is None or b_mae is None:
            verdict = "missing"
            delta = None
            pct = None
        else:
            delta = round(b_mae - a_mae, 4)
            pct = round(100 * delta / a_mae, 2) if a_mae else None
            if abs(pct) < 1.0:
                verdict = "tie (~)"
            elif delta < 0:
                verdict = "candidate wins"
            else:
                verdict = "baseline wins"
        rows.append({
            "field": f, "n": n,
            "baseline_mae": a_mae, "candidate_mae": b_mae,
            "delta": delta, "pct": pct, "verdict": verdict,
        })
    return {
        "baseline": a,
        "candidate": b,
        "comparison": rows,
    }

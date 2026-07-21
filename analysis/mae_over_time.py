"""MAE / RMSE / bias / Brier over time — per obs day per field per layer.

Aggregates forecast_error_log.jsonl by obs date × field × layer (Raw / L2 /
L3 / Prod). Emits a per-day time series for the "Accuracy over time" chart
on the debug page.

**Persistent history model.** The pair log is capped at ~30 days by
`decay_fit.py::RETENTION_DAYS`, so a re-aggregate-from-scratch view maxes
out at that window. This script instead maintains an accumulating history:

  1. Fetch the prior `mae_over_time.json` from GCS.
  2. Recompute per-day rollup from the (30-day) pair log.
  3. Merge: overwrite the last MERGE_REFRESH_DAYS days (still-live cells
     may add pairs), preserve older days that are already recorded (their
     underlying pair-log rows may have been pruned since).
  4. Write and republish.

Storage math: each (day × field × layer) cell = ~90 bytes JSON. 13 fields
× 4 layers = 52 cells/day → ~5 KB/day → ~1.8 MB/year. Trivial at years
of scale; noted here per the "always be mindful of data volume" rule.

Run:
    python3 analysis/mae_over_time.py

Output:
    analysis/output/mae_over_time.json  (local mirror of the GCS file)
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, date, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
HISTORY_URL = "https://data.wymancove.com/mae_over_time.json"
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "mae_over_time.json")

FIELDS = ["t", "dp", "h", "ws", "wg", "wd", "cc", "cl", "cm", "ch", "sr", "pr", "pp", "pa"]
MIN_N_PER_DAY = 200  # skip (field, day) cells with too few pairs — avoids noise spikes

# Fields with no L2/L3/L4 correction stack — pair-log rows only carry the top-level
# `error` key, not error_l1/l2/l3/l4. Route them through the permissive path with a
# single "raw" layer sourced from `error` (which IS L1 for these fields). Currently
# just wd (circular; the pair log emits circular-angular error directly). Add
# wd_persistence_gate output as a "chp"-style specialist layer once that gate wires.
L1_ONLY_FIELDS = {"wd"}

# Overwrite the last N days on every run — recent days may still be
# accumulating pairs, so re-aggregation gets fresher numbers. Days older
# than this window are locked-in from prior runs because the raw pair log
# may have already been pruned past its 30-day retention.
MERGE_REFRESH_DAYS = 3

# Strict layers: every pair must have all four to contribute. Preserves
# the comparability guarantee of the raw/l2/l3/prod comparison — same
# sample under each layer.
STRICT_LAYER_KEYS = [("raw", "error_l1"), ("l2", "error_l2"), ("l3", "error_l3"), ("prod", "error_l4")]

# Permissive specialist layers: contribute independently when present, skip
# silently when absent (Lsr only on sr; Lc on cc/cl/cm/ch; Lt on t, dormant).
# Their MAE is over a different sample than the strict layers — that's the
# honest reading for specialist attribution and lets the frontend filter
# the legend to layers with actual data for the selected field. (v0.6.360.)
PERMISSIVE_LAYER_KEYS = [("l5", "error_l5"), ("l6", "error_l6"),
                         # v0.6.361: post-Lc specialists — chp (ch_persistence_gate,
                         # ch only) and clp (cl_persistence_short_lead, cl only).
                         # Chart legend shows them as their own lines once a few
                         # days of data have accumulated.
                         ("chp", "error_chp"), ("clp", "error_clp")]

LAYER_KEYS = STRICT_LAYER_KEYS + PERMISSIVE_LAYER_KEYS


def load_prior_history():
    """Fetch the prior mae_over_time.json from GCS. Returns empty scaffolding
    on any error (first run, GCS unavailable, malformed payload)."""
    empty = {
        "generated_at": None,
        "source": "forecast_error_log.jsonl (with accumulating per-day history)",
        "min_n_per_day": MIN_N_PER_DAY,
        "days": [],
        "fields": [],
        "series": {},
    }
    try:
        path = cached_path(HISTORY_URL)
    except Exception as e:
        print(f"  (no prior history: {type(e).__name__}: {e}) — starting fresh")
        return empty
    try:
        with open(path) as f:
            prior = json.load(f)
        return prior
    except Exception as e:
        print(f"  ⚠ prior history unreadable ({type(e).__name__}: {e}) — starting fresh")
        return empty


def compute_fresh_rollup():
    """Compute per-day per-field per-layer aggregates from the current pair log."""
    path = cached_path(ERROR_LOG_URL)
    buckets = defaultdict(lambda: {ln: [] for ln, _ in LAYER_KEYS})
    # prod_real: real per-row Production aggregate, keyed on applied_layer stamp
    # (parallel to decay_fit.py:712-729 for per-band tables). Independent of the
    # STRICT layer completeness gate — contributes whenever applied_layer +
    # error_{applied} are both present. Pre-v0.6.269 rows without stamps are
    # skipped; those age out of the 30-day pair log by 07-31. (v0.6.371.)
    prod_real_buckets = defaultdict(list)
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

            applied = r.get("applied_layer")
            if applied:
                e_applied = r.get(f"error_{applied}")
                if e_applied is not None:
                    prod_real_buckets[(day, fld)].append(float(e_applied))

            per_layer = {}
            if fld in L1_ONLY_FIELDS:
                # Fields without an L3/L4 correction stack. `error` in the pair log
                # IS the raw-vs-obs metric (circular for wd). Route to "raw".
                # v0.6.371b: also emit L2 for wd (wind_blend circular unit-vector
                # blend, shipped 07-20 v0.6.368a). error_l2 populates on wd pairs
                # via v0.6.367; STRICT completeness gate would demand error_l3/l4
                # (which wd doesn't have yet) so wd stays in L1_ONLY but reads its
                # own L2 inline. Post-wdp 07-27, add error_wdp here too per the
                # wdp_ship_patches.md Site 7 (option (a)).
                e = r.get("error")
                if e is None:
                    continue
                per_layer["raw"] = e
                e_l2 = r.get("error_l2")
                if e_l2 is not None:
                    per_layer["l2"] = e_l2
            else:
                skip = False
                for ln, key in STRICT_LAYER_KEYS:
                    e = r.get(key)
                    if e is None:
                        skip = True
                        break
                    per_layer[ln] = e
                if skip:
                    continue
                for ln, key in PERMISSIVE_LAYER_KEYS:
                    e = r.get(key)
                    if e is not None:
                        per_layer[ln] = e
            for ln, e in per_layer.items():
                buckets[(day, fld)][ln].append(e)

    fresh = defaultdict(lambda: defaultdict(dict))  # fresh[field][layer][day] = cell
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
            fresh[fld][layer_name][day] = {
                "n": n,
                "mae": round(mae, 4),
                "rmse": round(rmse, 4),
                "bias": round(bias, 4),
                "brier": round(sqerr_mean, 4),
            }

    for (day, fld), xs in prod_real_buckets.items():
        n = len(xs)
        if n < MIN_N_PER_DAY:
            continue
        mae = sum(abs(x) for x in xs) / n
        sqerr_mean = sum(x * x for x in xs) / n
        rmse = math.sqrt(sqerr_mean)
        bias = sum(xs) / n
        fresh[fld]["prod_real"][day] = {
            "n": n,
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "bias": round(bias, 4),
            "brier": round(sqerr_mean, 4),
        }
    return fresh, n_total


def merge(prior_series, fresh_series, refresh_cutoff_day):
    """Merge fresh rollup into prior series.

    For each (field × layer × day) cell:
      - Day >= refresh_cutoff_day → prefer fresh (recent days still accumulating)
      - Day <  refresh_cutoff_day → prefer prior if present, else use fresh (backfill)

    Cutoff is inclusive: days on or after cutoff get overwritten.

    Returns merged series dict + counts (kept_prior, overwritten, added_new).
    """
    merged = {}
    kept_prior = overwritten = added_new = 0
    all_fields = set(prior_series) | set(fresh_series)
    for fld in all_fields:
        merged[fld] = {}
        prior_layers = prior_series.get(fld, {})
        fresh_layers = fresh_series.get(fld, {})
        all_layers = set(prior_layers) | set(fresh_layers)
        for layer in all_layers:
            merged[fld][layer] = {}
            prior_days = prior_layers.get(layer, {})
            fresh_days = fresh_layers.get(layer, {})
            all_days = set(prior_days) | set(fresh_days)
            for day in all_days:
                p = prior_days.get(day)
                f = fresh_days.get(day)
                if day >= refresh_cutoff_day:
                    # Recent — prefer fresh if we have it
                    if f is not None:
                        merged[fld][layer][day] = f
                        if p is not None:
                            overwritten += 1
                        else:
                            added_new += 1
                    elif p is not None:
                        # Recent day dropped out of fresh (edge case: MIN_N floor
                        # cut it off today). Keep prior rather than deleting.
                        merged[fld][layer][day] = p
                        kept_prior += 1
                else:
                    # Older — prior is locked in; only backfill if missing
                    if p is not None:
                        merged[fld][layer][day] = p
                        kept_prior += 1
                    elif f is not None:
                        merged[fld][layer][day] = f
                        added_new += 1
    return merged, kept_prior, overwritten, added_new


def main():
    print("[1/3] Loading prior mae_over_time history from GCS...")
    prior = load_prior_history()
    prior_series = prior.get("series", {}) or {}
    prior_days_count = len(prior.get("days") or [])
    print(f"  prior history: {prior_days_count} days")

    print("[2/3] Recomputing per-day rollup from pair log...")
    fresh_series, n_pair_rows = compute_fresh_rollup()
    fresh_days = sorted({d for f in fresh_series.values()
                         for lyr in f.values() for d in lyr})
    print(f"  fresh rollup: {n_pair_rows:,} pair rows → {len(fresh_days)} days")

    print("[3/3] Merging (overwrite last {} days, preserve older)...".format(MERGE_REFRESH_DAYS))
    today = date.today()
    cutoff = (today - timedelta(days=MERGE_REFRESH_DAYS - 1)).isoformat()  # inclusive
    merged, kept, over, added = merge(prior_series, fresh_series, cutoff)
    all_days = sorted({d for f in merged.values()
                       for lyr in f.values() for d in lyr})
    all_fields = sorted(f for f in merged if merged[f])

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "forecast_error_log.jsonl (with accumulating per-day history since first run)",
        "min_n_per_day": MIN_N_PER_DAY,
        "merge_refresh_days": MERGE_REFRESH_DAYS,
        "days": all_days,
        "fields": all_fields,
        "series": {fld: {lyr: dict(days) for lyr, days in layers.items()}
                   for fld, layers in merged.items()},
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    size_kb = os.path.getsize(OUT_JSON) / 1024
    print(f"  merge: {kept} kept from prior, {over} overwritten, {added} new")
    print(f"  wrote {OUT_JSON}   ({len(all_days)} days total, {len(all_fields)} fields, {size_kb:.1f} KB)")
    if all_days:
        print(f"  range: {all_days[0]} → {all_days[-1]}   (retention-independent — grows as new days accumulate)")

    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from weather_collector.gcs_io import upload_json  # noqa: E402
        upload_json(payload, "mae_over_time.json", "mae_over_time.json")
        print("  ✓ Published to gs://myweather-data/mae_over_time.json")
    except Exception as e:
        print(f"  ⚠ GCS upload skipped ({type(e).__name__}: {e}) — local file still written")


if __name__ == "__main__":
    main()

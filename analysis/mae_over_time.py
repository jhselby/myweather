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

# Fields routed through the permissive path (skip the strict L1/L2/L3/L4 completeness
# gate). wd lives here because its stack shape doesn't match the cloud/temp/wind fields
# (no L3 or L4 corrections; circular math). Post-v0.6.368 the pair log now carries
# error_l1 for wd from the raw_wind_direction stash (wind_blend.py:440-441) — prefer
# that when present. Fallback to top-level `error` for pre-v0.6.368 rows; those age
# out with the 30-day pair-log window.
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
                         # ch only) and clp (cl_persistence_gate, cl only —
                         # v0.6.379 successor to cl_persistence_short_lead).
                         # v0.6.382: wdp (wd_persistence_gate, wd only).
                         # Chart legend shows each as its own line once a few
                         # days of data have accumulated.
                         ("chp", "error_chp"), ("clp", "error_clp"),
                         ("wdp", "error_wdp")]

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
    """Compute per-day per-field per-layer aggregates from the current pair log.
    Also emits a rolling last-24h aggregate per (field, layer) — always contains
    a full diurnal cycle, unlike the calendar-day "today" bucket which is a partial
    at any tick before end-of-day. Used by the debug page's per-field snapshot
    "last 24h" column."""
    path = cached_path(ERROR_LOG_URL)
    buckets = defaultdict(lambda: {ln: [] for ln, _ in LAYER_KEYS})
    # prod_real: real per-row Production aggregate, keyed on applied_layer stamp
    # (parallel to decay_fit.py:712-729 for per-band tables). Independent of the
    # STRICT layer completeness gate — contributes whenever applied_layer +
    # error_{applied} are both present. Pre-v0.6.269 rows without stamps are
    # skipped; those age out of the 30-day pair log by 07-31. (v0.6.371.)
    prod_real_buckets = defaultdict(list)
    # Rolling last-24h buckets. Same shape as `buckets` and `prod_real_buckets`
    # but keyed by field only (no day). Populated for any row with obs_time
    # >= now - 24h.
    last_24h_buckets = defaultdict(lambda: {ln: [] for ln, _ in LAYER_KEYS})
    last_24h_prod_real = defaultdict(list)
    # Per-band 24h buckets — for the debug page's per-cell "worst cell (band)"
    # tile so its rolling-24h read is honest at the same granularity as its
    # 7d read. Bands mirror LAYER_SHAPE_BANDS / regression sentry conventions.
    LAST_24H_BANDS = (("0-5", 0, 5), ("6-11", 6, 11), ("12-23", 12, 23), ("24-47", 24, 47))
    last_24h_band_buckets = defaultdict(lambda: defaultdict(lambda: {ln: [] for ln, _ in LAYER_KEYS}))
    last_24h_band_prod_real = defaultdict(lambda: defaultdict(list))
    def _band_for(lead):
        if lead is None: return None
        for lbl, lo, hi in LAST_24H_BANDS:
            if lo <= lead <= hi: return lbl
        return None
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")
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

            in_last_24h = ot >= cutoff_24h
            band = _band_for(r.get("lead_h")) if in_last_24h else None

            applied = r.get("applied_layer")
            if applied:
                e_applied = r.get(f"error_{applied}")
                if e_applied is not None:
                    prod_real_buckets[(day, fld)].append(float(e_applied))
                    if in_last_24h:
                        last_24h_prod_real[fld].append(float(e_applied))
                        if band is not None:
                            last_24h_band_prod_real[fld][band].append(float(e_applied))

            per_layer = {}
            if fld in L1_ONLY_FIELDS:
                # Permissive fields without a strict L1..L4 stack. Prefer explicit
                # error_l1 (post-v0.6.368 wd rows have it from raw_wind_direction);
                # fall back to top-level `error` for pre-v0.6.368 rows that only
                # carried a single error metric. NOTE: for wd, top-level `error` is
                # actually L2-view (fc = wd_l2 per forecast_snapshot._round_for), so
                # falling back to it as "raw" mislabels post-v0.6.368 rows — the
                # explicit error_l1 path corrects this. Applied-layer stamping isn't
                # used for L1_ONLY_FIELDS (wd has no applied_layer key), so prod_real
                # is derived inline by picking the deepest available specialist.
                raw = r.get("error_l1")
                if raw is None:
                    raw = r.get("error")
                if raw is None:
                    continue
                per_layer["raw"] = raw
                e_l2 = r.get("error_l2")
                if e_l2 is not None:
                    per_layer["l2"] = e_l2
                e_wdp = r.get("error_wdp")
                if e_wdp is not None:
                    per_layer["wdp"] = e_wdp
                # prod_real for L1_ONLY_FIELDS = deepest specialist present.
                # Enables the standard "prod_real vs raw" trend reads without
                # needing an applied_layer stamp (which wd doesn't have).
                prod = e_wdp if e_wdp is not None else e_l2
                if prod is not None:
                    prod_real_buckets[(day, fld)].append(float(prod))
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
                if in_last_24h:
                    last_24h_buckets[fld][ln].append(e)
                    if band is not None:
                        last_24h_band_buckets[fld][band][ln].append(e)

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

    # Rolling last-24h aggregate. MIN_N floor uses 1/7 of MIN_N_PER_DAY since
    # the window is 24h vs 7-day-hourly. Keeps thin windows out but doesn't
    # over-gate a genuinely quiet field.
    last_24h = defaultdict(dict)
    min_n_24h = max(30, MIN_N_PER_DAY // 5)
    for fld, layers in last_24h_buckets.items():
        for ln, xs in layers.items():
            n = len(xs)
            if n < min_n_24h:
                continue
            mae = sum(abs(x) for x in xs) / n
            sqerr_mean = sum(x * x for x in xs) / n
            rmse = math.sqrt(sqerr_mean)
            bias = sum(xs) / n
            last_24h[fld][ln] = {
                "n": n,
                "mae": round(mae, 4),
                "rmse": round(rmse, 4),
                "bias": round(bias, 4),
                "brier": round(sqerr_mean, 4),
            }
    for fld, xs in last_24h_prod_real.items():
        n = len(xs)
        if n < min_n_24h:
            continue
        mae = sum(abs(x) for x in xs) / n
        sqerr_mean = sum(x * x for x in xs) / n
        rmse = math.sqrt(sqerr_mean)
        bias = sum(xs) / n
        last_24h[fld]["prod_real"] = {
            "n": n,
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "bias": round(bias, 4),
            "brier": round(sqerr_mean, 4),
        }

    # Band-level 24h aggregate. Smaller MIN_N floor (each band is ~1/4 of the
    # window's data, and we're bucketing across leads not fields, so use a
    # lower floor to keep bands visible).
    last_24h_bands = defaultdict(lambda: defaultdict(dict))
    min_n_24h_band = max(10, MIN_N_PER_DAY // 20)
    for fld, bands in last_24h_band_buckets.items():
        for bnd, layers in bands.items():
            for ln, xs in layers.items():
                n = len(xs)
                if n < min_n_24h_band:
                    continue
                mae = sum(abs(x) for x in xs) / n
                sqerr_mean = sum(x * x for x in xs) / n
                rmse = math.sqrt(sqerr_mean)
                bias = sum(xs) / n
                last_24h_bands[fld][bnd][ln] = {
                    "n": n,
                    "mae": round(mae, 4),
                    "rmse": round(rmse, 4),
                    "bias": round(bias, 4),
                    "brier": round(sqerr_mean, 4),
                }
    for fld, bands in last_24h_band_prod_real.items():
        for bnd, xs in bands.items():
            n = len(xs)
            if n < min_n_24h_band:
                continue
            mae = sum(abs(x) for x in xs) / n
            sqerr_mean = sum(x * x for x in xs) / n
            rmse = math.sqrt(sqerr_mean)
            bias = sum(xs) / n
            last_24h_bands[fld].setdefault(bnd, {})["prod_real"] = {
                "n": n,
                "mae": round(mae, 4),
                "rmse": round(rmse, 4),
                "bias": round(bias, 4),
                "brier": round(sqerr_mean, 4),
            }

    # Coerce nested defaultdicts to dicts for JSON serialization.
    last_24h_bands = {f: {b: dict(lyrs) for b, lyrs in bands.items()}
                      for f, bands in last_24h_bands.items()}
    return fresh, n_total, dict(last_24h), last_24h_bands, cutoff_24h


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
    fresh_series, n_pair_rows, last_24h, last_24h_bands, cutoff_24h = compute_fresh_rollup()
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

    # last_7d: n-weighted rollup across the trailing 7 calendar days from the
    # per-day merged series. Single canonical 7d cut used across the debug
    # page (top per-field snapshot, scoreboard, narrative). Cell shape mirrors
    # last_24h so consumers can swap. n-weighted aggregation keeps thin days
    # from dominating; MAE is recovered from per-day (mae, n) as
    # sum(mae_d * n_d) / sum(n_d); RMSE from brier (sqerr_mean); bias from
    # per-day biases the same way.
    last_7d_window_days = 7
    last_7d_days = all_days[-last_7d_window_days:] if all_days else []
    last_7d = {}
    for fld, layers in merged.items():
        fld_out = {}
        for layer_name, days_map in layers.items():
            total_n = 0
            weighted_mae = 0.0
            weighted_rmse_sq = 0.0
            weighted_bias = 0.0
            for d in last_7d_days:
                cell = days_map.get(d)
                if not cell:
                    continue
                nd = cell.get("n", 0)
                if nd <= 0:
                    continue
                total_n += nd
                weighted_mae += cell.get("mae", 0.0) * nd
                # brier is the mean squared error per day; sum(brier*n) = SSE
                weighted_rmse_sq += cell.get("brier", 0.0) * nd
                weighted_bias += cell.get("bias", 0.0) * nd
            if total_n <= 0:
                continue
            mae = weighted_mae / total_n
            sqerr_mean = weighted_rmse_sq / total_n
            fld_out[layer_name] = {
                "n": total_n,
                "mae": round(mae, 4),
                "rmse": round(math.sqrt(sqerr_mean), 4),
                "bias": round(weighted_bias / total_n, 4),
                "brier": round(sqerr_mean, 4),
            }
        if fld_out:
            last_7d[fld] = fld_out

    # raw_difficulty_index: was this week harder or easier than the trailing
    # 90-day reference (excluding the 7d itself so the comparison isn't
    # contaminated by the numerator)? Reported as a per-field ratio
    # raw_mae_7d / raw_mae_ref (>1.0 = harder, <1.0 = easier) plus an
    # unweighted mean across fields. Cheap correction-independent audit
    # signal for the debug page: when a weekly aggregate moves, the reader
    # can tell at a glance whether the raw baseline moved with it. Only
    # uses raw-layer MAEs per field so units don't mix (each field is
    # normalized by its own reference).
    ref_window_days = 90
    ref_days = all_days[-(last_7d_window_days + ref_window_days):-last_7d_window_days] if len(all_days) > last_7d_window_days else []
    def _weighted_raw_mae(days_list, layers_map):
        raw_days = layers_map.get("raw") or layers_map.get("l1") or {}
        total_n = 0
        weighted = 0.0
        for d in days_list:
            cell = raw_days.get(d)
            if not cell:
                continue
            nd = cell.get("n", 0)
            if nd <= 0:
                continue
            total_n += nd
            weighted += cell.get("mae", 0.0) * nd
        return (weighted / total_n) if total_n > 0 else None, total_n
    per_field_ratios = {}
    for fld, layers_map in merged.items():
        mae_7d, n_7d = _weighted_raw_mae(last_7d_days, layers_map)
        mae_ref, n_ref = _weighted_raw_mae(ref_days, layers_map)
        if mae_7d is None or mae_ref is None or mae_ref <= 0:
            continue
        per_field_ratios[fld] = {
            "raw_mae_7d": round(mae_7d, 4),
            "raw_mae_ref": round(mae_ref, 4),
            "ratio": round(mae_7d / mae_ref, 4),
            "n_7d": n_7d,
            "n_ref": n_ref,
        }
    if per_field_ratios:
        ratios = [v["ratio"] for v in per_field_ratios.values()]
        mean_ratio = sum(ratios) / len(ratios)
        raw_difficulty_index = {
            "ref_window_days": ref_window_days,
            "ref_days": ref_days[:1] + ref_days[-1:] if ref_days else [],
            "per_field": per_field_ratios,
            "mean_ratio": round(mean_ratio, 4),
            "n_fields": len(ratios),
            "note": "ratio > 1.0 = raw MAE this week is harder than the trailing 90d reference (this week excluded from the reference); ratio < 1.0 = easier. Per-field normalization prevents unit mixing.",
        }
    else:
        raw_difficulty_index = None

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "forecast_error_log.jsonl (with accumulating per-day history since first run)",
        "min_n_per_day": MIN_N_PER_DAY,
        "merge_refresh_days": MERGE_REFRESH_DAYS,
        "days": all_days,
        "fields": all_fields,
        "series": {fld: {lyr: dict(days) for lyr, days in layers.items()}
                   for fld, layers in merged.items()},
        "last_24h": last_24h,
        "last_24h_bands": last_24h_bands,
        "last_24h_window_start_utc": cutoff_24h,
        "last_7d": last_7d,
        "last_7d_days": last_7d_days,
        "raw_difficulty_index": raw_difficulty_index,
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

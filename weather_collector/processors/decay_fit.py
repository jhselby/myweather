"""
Fitter (Piece 3 of the decay model): once-a-day pass over
forecast_error_log.jsonl that does two things:

1. For each (field, lead_h) bin, compute the recency-weighted mean signed
   error and the number of pairs that fed it. Write the result to
   decay_corrections.json. Piece 4 (Apply) will subtract these from the
   forecast at each lead.
2. Rewrite forecast_error_log.jsonl pruned to RETENTION_DAYS. The Joiner
   appends via GCS compose; this rewrite resets the component count back
   to 1 (the compose ceiling is 5,300 components, hit around day 36 at
   144 ticks/day).

Each pair contributes weight `w = exp(-age_days / TAU_DAYS)` to its bin —
recent pairs dominate, old pairs fade. The bin mean is `Σ(error × w) / Σw`.
n_samples in the output reports unweighted pair counts (for display);
weighted sums drive the actual corrections. See TAU_DAYS comment below.

Streaming I/O via blob.open — memory is bounded by the bin accumulators
(6 fields × 48 leads), independent of file size. At steady state the
input is ~1.3 GB.

Wired to run once per day from collector.main() gated on the 03:X7 tick.
Error sign convention (from the Joiner): error = forecast - observed, so
the correction is weighted_mean(error) and corrected_forecast = forecast - correction.
"""
import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta

import pytz

from ..gcs_io import BUCKET, get_client, load_json, upload_json
from ..utils import redact_secrets


ERROR_LOG_PATH = "forecast_error_log.jsonl"
CORRECTIONS_PATH = "decay_corrections.json"
HISTORY_PATH = "decay_corrections_history.json"
HISTORY_RETENTION_DAYS = 30
TEMP_PATH = "forecast_error_log_flatten.tmp.jsonl"
TZ = pytz.timezone("America/New_York")
RETENTION_DAYS = 30
LEAD_BINS = 48  # lead_h 0..47

# Recency weighting: each pair contributes exp(-age_days / TAU_DAYS) to its bin.
# τ=14 days → half-weight at ~10 days, ~12% weight at 30 days. Lets the fit
# track seasonal transitions (spring→summer, fall onset, etc.) and recover
# faster from upstream data-quality changes (e.g. the May 31 humidity fix in
# obs_log.py). Pre-v0.6.1 used uniform weighting. To revert: set TAU_DAYS to
# something much larger than RETENTION_DAYS (e.g. 10000) — weights collapse
# to ~1.0 and behavior matches uniform.
TAU_DAYS = 14

FIELDS = ("t", "ws", "wg", "h", "dp", "pp")


def fit_decay_corrections():
    """Daily Fitter entry point."""
    client = get_client()
    bucket = client.bucket(BUCKET)
    main_blob = bucket.blob(ERROR_LOG_PATH)

    if not main_blob.exists():
        logging.info("  ℹ  Fitter: no forecast_error_log.jsonl yet, skipping")
        return

    # obs_time in rows is local-naive ISO minute ("%Y-%m-%dT%H:%M"), so a
    # lexicographic compare against a same-format cutoff is exact.
    cutoff = (datetime.now(TZ).replace(tzinfo=None) - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")

    # Weighted accumulators: bin mean = Σ(error × w) / Σw, where w = exp(-age/τ).
    # raw_counts tracks unweighted pair counts for display (n_samples in output).
    now_naive = datetime.now(TZ).replace(tzinfo=None)
    sums = defaultdict(float)
    weights = defaultdict(float)
    raw_counts = defaultdict(int)
    n_in = 0
    n_kept = 0

    temp_blob = bucket.blob(TEMP_PATH)
    with main_blob.open("r") as fin, temp_blob.open("w") as fout:
        for raw in fin:
            line = raw.strip()
            if not line:
                continue
            n_in += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            obs_time = row.get("obs_time", "")
            if obs_time < cutoff:
                continue
            n_kept += 1
            fout.write(line + "\n")
            field = row.get("field")
            lead_h = row.get("lead_h")
            error = row.get("error")
            if field is None or lead_h is None or error is None:
                continue
            if not (0 <= lead_h < LEAD_BINS):
                continue
            try:
                obs_dt = datetime.strptime(obs_time, "%Y-%m-%dT%H:%M")
            except ValueError:
                continue
            age_days = max(0.0, (now_naive - obs_dt).total_seconds() / 86400.0)
            w = math.exp(-age_days / TAU_DAYS)
            sums[(field, lead_h)] += float(error) * w
            weights[(field, lead_h)] += w
            raw_counts[(field, lead_h)] += 1

    corrections = {}
    n_samples = {}
    for f in FIELDS:
        c_arr = [None] * LEAD_BINS
        n_arr = [0] * LEAD_BINS
        for h in range(LEAD_BINS):
            w_sum = weights.get((f, h), 0.0)
            n_arr[h] = raw_counts.get((f, h), 0)
            if w_sum > 0:
                c_arr[h] = round(sums[(f, h)] / w_sum, 3)
        corrections[f] = c_arr
        n_samples[f] = n_arr

    output = {
        "fitted_at": now_naive.strftime("%Y-%m-%dT%H:%M"),
        "n_pairs": n_kept,
        "retention_days": RETENTION_DAYS,
        "weighting": {"method": "exponential_decay", "tau_days": TAU_DAYS},
        "corrections": corrections,
        "n_samples": n_samples,
    }
    upload_json(output, CORRECTIONS_PATH, "decay_corrections.json")

    # Append this fit to a rolling history file so the debug page can show
    # how curves evolve over time. 30-day window. Each entry is a full copy
    # of the fit (fitted_at, n_pairs, weighting, corrections, n_samples).
    # Storage cost is trivial (~7 KB/fit × 30 = ~210 KB).
    try:
        history = load_json(HISTORY_PATH, default={"history": []})
        hist_cutoff = (now_naive - timedelta(days=HISTORY_RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")
        kept = [h for h in history.get("history", [])
                if isinstance(h, dict) and h.get("fitted_at", "") >= hist_cutoff]
        kept.append(output)
        upload_json({"history": kept}, HISTORY_PATH, "decay_corrections_history.json")
        logging.info(f"  ✓ History: {len(kept)} fits in {HISTORY_RETENTION_DAYS}-day window")
    except Exception as e:
        logging.warning(f"  ⚠  History append failed: {redact_secrets(e)}")

    # Overwrite main with the pruned temp (resets compose component count to 1).
    try:
        bucket.copy_blob(temp_blob, bucket, ERROR_LOG_PATH)
        temp_blob.delete()
    except Exception as e:
        logging.error(f"  ✗ Fitter: rewrite of {ERROR_LOG_PATH} failed: {redact_secrets(e)}")
        try:
            if temp_blob.exists():
                temp_blob.delete()
        except Exception:
            pass
        raise

    pruned = n_in - n_kept
    logging.info(f"  ✓ Fitter: {n_in:,} pairs in, {n_kept:,} kept ({pruned:,} pruned >{RETENTION_DAYS}d)")

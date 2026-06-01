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
TIDE_PHASE_PATH = "tide_phase_corrections.json"
TIDE_PHASE_HISTORY_PATH = "tide_phase_corrections_history.json"
HISTORY_RETENTION_DAYS = 30
TEMP_PATH = "forecast_error_log_flatten.tmp.jsonl"
TZ = pytz.timezone("America/New_York")
RETENTION_DAYS = 30
LEAD_BINS = 48  # lead_h 0..47

# Tide-phase binning (Section 5 — research/diagnostic, not in Apply).
# 12 bins of ~1.03h each across the M2 cycle. Reference high tide at Salem
# station 8442645: 2026-06-01 12:23 EDT = 16:23 UTC. Used as M2 phase=0
# anchor — approximate vs NOAA harmonic predictions, but offset error just
# shifts all bins by a constant, which doesn't affect the over-time
# drift-detection test that motivates this feature.
TIDE_PHASE_BINS = 12
M2_PERIOD_HOURS = 12.4206
M2_REFERENCE_UTC = datetime(2026, 6, 1, 16, 23, 0)

# Time-series diagnostic (Section 6 — research). For each hour in the last
# TIMESERIES_DAYS, compute mean error per field at TIMESERIES_LEAD lead, and
# the approximate tide elevation at that hour. Lets the debug page render
# "error vs time + tide overlay" so the eye can check if they oscillate
# together. Lead 18h is where the tide signal is strongest in our data.
TIMESERIES_LEAD = 18
TIMESERIES_DAYS = 7
TIMESERIES_PATH = "time_series_diagnostic.json"
# Approximate M2 tidal amplitude at Salem (peak-to-mean) in feet. Real tide
# heights are a sum of many harmonics; this is a single-component
# approximation good enough for the visual oscillation check.
SALEM_M2_AMPLITUDE_FT = 4.0

# Recency weighting: each pair contributes exp(-age_days / TAU_DAYS) to its bin.
# τ=14 days → half-weight at ~10 days, ~12% weight at 30 days. Lets the fit
# track seasonal transitions (spring→summer, fall onset, etc.) and recover
# faster from upstream data-quality changes (e.g. the May 31 humidity fix in
# obs_log.py). Pre-v0.6.1 used uniform weighting. To revert: set TAU_DAYS to
# something much larger than RETENTION_DAYS (e.g. 10000) — weights collapse
# to ~1.0 and behavior matches uniform.
TAU_DAYS = 14

FIELDS = ("t", "ws", "wg", "h", "dp", "pp")


def _tide_phase_bin(obs_time_str):
    """Return tide-phase bin index for obs_time, or None if unparseable."""
    try:
        local_naive = datetime.strptime(obs_time_str, "%Y-%m-%dT%H:%M")
    except (ValueError, TypeError):
        return None
    local_aware = TZ.localize(local_naive)
    utc_naive = local_aware.astimezone(pytz.UTC).replace(tzinfo=None)
    hours_since_ref = (utc_naive - M2_REFERENCE_UTC).total_seconds() / 3600.0
    # Python `%` keeps sign positive when divisor is positive, so negative
    # ages (obs before reference) wrap correctly.
    phase_frac = (hours_since_ref % M2_PERIOD_HOURS) / M2_PERIOD_HOURS
    return min(int(phase_frac * TIDE_PHASE_BINS), TIDE_PHASE_BINS - 1)


def _tide_elevation_ft(obs_hour_str):
    """Approximate M2 tide elevation at obs_hour, in feet. M2 cosine model
    anchored to the reference high tide. Real tide is the sum of many
    harmonics; this is single-component, good enough for the oscillation
    visualization on the debug page."""
    try:
        local_naive = datetime.strptime(obs_hour_str, "%Y-%m-%dT%H:%M")
    except (ValueError, TypeError):
        return None
    local_aware = TZ.localize(local_naive)
    utc_naive = local_aware.astimezone(pytz.UTC).replace(tzinfo=None)
    hours_since_ref = (utc_naive - M2_REFERENCE_UTC).total_seconds() / 3600.0
    phase_frac = (hours_since_ref % M2_PERIOD_HOURS) / M2_PERIOD_HOURS
    return round(SALEM_M2_AMPLITUDE_FT * math.cos(2 * math.pi * phase_frac), 2)


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
    # Parallel accumulators binned by tide phase instead of lead_h — feeds the
    # tide-phase historical view (Section 5). Same recency weighting.
    tide_sums = defaultdict(float)
    tide_weights = defaultdict(float)
    tide_raw_counts = defaultdict(int)
    # Time-series accumulators for Section 6 — only pairs at TIMESERIES_LEAD
    # within the last TIMESERIES_DAYS, grouped per obs hour. Unweighted (raw
    # mean per hour) because we want to see the actual hour-by-hour signal,
    # not a smoothed weighted version.
    ts_cutoff = (now_naive - timedelta(days=TIMESERIES_DAYS)).strftime("%Y-%m-%dT%H:%M")
    ts_sums = defaultdict(float)   # key: (field, obs_hour_iso)
    ts_counts = defaultdict(int)
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
            tide_bin = _tide_phase_bin(obs_time)
            if tide_bin is not None:
                tide_sums[(field, tide_bin)] += float(error) * w
                tide_weights[(field, tide_bin)] += w
                tide_raw_counts[(field, tide_bin)] += 1
            # Time-series accumulation — only pairs at the chosen lead, recent
            # enough to be in the time-series window, grouped per obs hour.
            if lead_h == TIMESERIES_LEAD and obs_time >= ts_cutoff:
                obs_hour = obs_time[:13] + ":00"
                ts_sums[(field, obs_hour)] += float(error)
                ts_counts[(field, obs_hour)] += 1

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

    # Tide-phase output + rolling history. Same shape as the lead-h history,
    # but bins are tide phase (0..TIDE_PHASE_BINS-1) instead of lead_h.
    # Diagnostic-only — never enters Apply. Watching this evolve across days
    # tests whether forecast error tracks tide phase (stable curves → real
    # tide signal; drifting curves → diurnal masquerading as tide).
    tide_corrections = {}
    tide_n_samples = {}
    for f in FIELDS:
        c_arr = [None] * TIDE_PHASE_BINS
        n_arr = [0] * TIDE_PHASE_BINS
        for b in range(TIDE_PHASE_BINS):
            w_sum = tide_weights.get((f, b), 0.0)
            n_arr[b] = tide_raw_counts.get((f, b), 0)
            if w_sum > 0:
                c_arr[b] = round(tide_sums[(f, b)] / w_sum, 3)
        tide_corrections[f] = c_arr
        tide_n_samples[f] = n_arr
    tide_output = {
        "fitted_at": now_naive.strftime("%Y-%m-%dT%H:%M"),
        "n_pairs": n_kept,
        "retention_days": RETENTION_DAYS,
        "weighting": {"method": "exponential_decay", "tau_days": TAU_DAYS},
        "tide_phase_bins": TIDE_PHASE_BINS,
        "m2_period_hours": M2_PERIOD_HOURS,
        "corrections_by_tide_phase": tide_corrections,
        "n_samples_by_tide_phase": tide_n_samples,
    }
    upload_json(tide_output, TIDE_PHASE_PATH, "tide_phase_corrections.json")
    try:
        tide_history = load_json(TIDE_PHASE_HISTORY_PATH, default={"history": []})
        hist_cutoff = (now_naive - timedelta(days=HISTORY_RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")
        kept_tp = [h for h in tide_history.get("history", [])
                   if isinstance(h, dict) and h.get("fitted_at", "") >= hist_cutoff]
        kept_tp.append(tide_output)
        upload_json({"history": kept_tp}, TIDE_PHASE_HISTORY_PATH, "tide_phase_corrections_history.json")
        logging.info(f"  ✓ Tide-phase history: {len(kept_tp)} fits in {HISTORY_RETENTION_DAYS}-day window")
    except Exception as e:
        logging.warning(f"  ⚠  Tide-phase history append failed: {redact_secrets(e)}")

    # Time-series diagnostic (Section 6) — last TIMESERIES_DAYS of hour-by-hour
    # mean error per field at TIMESERIES_LEAD, plus an M2 tide-elevation curve
    # at each hour. Lets the debug page render error and tide elevation on a
    # shared time axis so the eye can check "do they oscillate together?"
    ts_hours = sorted({h for (_, h) in ts_sums.keys()})
    ts_errors = {f: [] for f in FIELDS}
    ts_counts_per_hour = {f: [] for f in FIELDS}
    for h in ts_hours:
        for f in FIELDS:
            c = ts_counts.get((f, h), 0)
            ts_counts_per_hour[f].append(c)
            if c > 0:
                ts_errors[f].append(round(ts_sums[(f, h)] / c, 3))
            else:
                ts_errors[f].append(None)
    ts_output = {
        "fitted_at": now_naive.strftime("%Y-%m-%dT%H:%M"),
        "lead_h": TIMESERIES_LEAD,
        "window_days": TIMESERIES_DAYS,
        "m2_period_hours": M2_PERIOD_HOURS,
        "salem_m2_amplitude_ft": SALEM_M2_AMPLITUDE_FT,
        "hours": ts_hours,
        "tide_elevation_ft": [_tide_elevation_ft(h) for h in ts_hours],
        "errors": ts_errors,
        "n_samples": ts_counts_per_hour,
    }
    try:
        upload_json(ts_output, TIMESERIES_PATH, "time_series_diagnostic.json")
        logging.info(f"  ✓ Time-series: {len(ts_hours)} hours at lead {TIMESERIES_LEAD}h over last {TIMESERIES_DAYS}d")
    except Exception as e:
        logging.warning(f"  ⚠  Time-series write failed: {redact_secrets(e)}")

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

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
import urllib.request
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

# v0.6.47: hypothesis-tracking gates. The L2 lead-decay fix (v0.6.44) +
# per-field L3/L4 whitelist (v0.6.45) closed the live-correction questions
# the Fitter was originally built to support. The hypothesis-only branches
# below are gated off to save GCP compute; the code stays for future revival.
# See `corrections_debug.html` → Research & Diagnostics → "Discarded
# hypotheses" for the final reports.
RUN_TIDE_TRACKING = False  # weak signal entangled with diurnal — final 2026-06-08
HISTORY_RETENTION_DAYS = 365  # ~annual cycle of fits; ~2.8 MB/year per history file
TEMP_PATH = "forecast_error_log_flatten.tmp.jsonl"
# Snapshot the live log to an immutable blob before reading. The Joiner appends
# to forecast_error_log.jsonl every 10 min via GCS compose; a multi-minute read
# of a multi-hundred-MB file racing with those appends caused stream-desync and
# 404-on-pinned-generation errors (June 5, 2026). Reading from a server-side
# copy sidesteps the race entirely. Cleaned up after the main rewrite swap.
SNAPSHOT_PATH = "forecast_error_log_fitter_snapshot.jsonl"
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

# Diurnal (hour-of-day) binning. 24 bins, one per local hour 0..23.
# Diurnal effects are typically the biggest unmodeled signal in coastal
# microclimate forecasting (sea breeze, diurnal mixing, daytime convection),
# bigger than tide effects in our data.
DIURNAL_BINS = 24
DIURNAL_PATH = "diurnal_corrections.json"
DIURNAL_HISTORY_PATH = "diurnal_corrections_history.json"

# L2 lead-decay τ fit (v0.6.44+). For each field, fit a single τ_hours such
# that bias_applied(lead) = current_bias × exp(-lead/τ) minimizes weighted
# squared residual vs the L1 error on recent pairs. Closed-form: each pair
# contributes (err_l1 + decay × bias)² × w. Expanding gives three accumulators
# per (field, lead): Σw·e², Σw·e·b, Σw·b² — independent of τ. Then we
# grid-search τ to find the minimum SSE. Same recency-weighted window as the
# rest of the fitter (TAU_DAYS=14).
#
# Fields fit: only those where L2 actually applies a bias to a forecast array.
# dp is derived from (t, h); cc/sr/pa/cl/cm/ch have ~zero L2 bias in practice
# (no Mesonet stations for those fields); wd is circular. ws/wg fit included
# as diagnostic — they currently use flat (τ=∞) in production and the audit
# confirmed that's correct, but tracking τ over time tells us if that flips.
L2_DECAY_PATH = "l2_decay.json"
L2_DECAY_HISTORY_PATH = "l2_decay_history.json"
L2_TAU_FIELDS = ("t", "h", "pr", "ws", "wg")
# Grid in hours. 1e9 ≈ ∞ → flat (current L2 behavior).
L2_TAU_GRID = (0.5, 1, 2, 3, 4, 6, 8, 12, 18, 24, 36, 60, 120, 240, 1e9)
# Minimum pairs for a τ fit to publish — otherwise leave field absent so the
# loader falls back to DEFAULT_L2_TAUS in corrected_hourly.py.
L2_TAU_MIN_PAIRS = 500

# Time-series diagnostic (Section 6 — research). For each hour in the last
# TIMESERIES_DAYS, compute mean error per (field, lead) at each lead in
# TIMESERIES_LEADS, plus the approximate tide elevation at that hour. Lets
# the debug page render "error vs time + tide overlay" with a lead-time
# selector. 6h steps gives 8 dropdown options — enough variety to explore
# whether the tide pattern is lead-specific without cluttering the UI.
TIMESERIES_LEADS = [0, 6, 12, 18, 24, 30, 36, 42]
TIMESERIES_LEADS_SET = set(TIMESERIES_LEADS)  # for O(1) membership in the tight pair-log loop
TIMESERIES_DAYS = 7
TIMESERIES_PATH = "time_series_diagnostic.json"
# Approximate M2 tidal amplitude at Salem (peak-to-mean) in feet. Used only as
# a FALLBACK when the NOAA tide-prediction fetch fails — real heights from
# NOAA come from station 8442645 via _fetch_noaa_tide_hourly() below.
SALEM_M2_AMPLITUDE_FT = 5.0
NOAA_TIDE_STATION = "8442645"
NOAA_TIDE_URL_TPL = (
    "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    "?product=predictions&application=myweather_fitter"
    "&begin_date={start}&end_date={end}"
    "&datum=MLLW&station={station}&time_zone=lst_ldt"
    "&units=english&interval=h&format=json"
)

# Recency weighting: each pair contributes exp(-age_days / TAU_DAYS) to its bin.
# τ=14 days → half-weight at ~10 days, ~12% weight at 30 days. Lets the fit
# track seasonal transitions (spring→summer, fall onset, etc.) and recover
# faster from upstream data-quality changes (e.g. the May 31 humidity fix in
# obs_log.py). Pre-v0.6.1 used uniform weighting. To revert: set TAU_DAYS to
# something much larger than RETENTION_DAYS (e.g. 10000) — weights collapse
# to ~1.0 and behavior matches uniform.
TAU_DAYS = 14

FIELDS = ("t", "ws", "wg", "h", "dp", "pp", "pr", "cc",
          "sr",  # solar radiation (W/m², daytime non-zero only)
          "pa",  # precipitation amount (in/hr, max-of-WU)
          "cl",  # cloud cover low (% — METAR layers <6500ft)
          "cm",  # cloud cover mid (% — METAR layers 6500-20000ft)
          "ch",  # cloud cover high (% — METAR layers >20000ft)
          "wd")  # wind direction (degrees, circular — fit via sin/cos components)


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


def _tide_elevation_ft_m2(obs_hour_str):
    """M2 cosine approximation of tide elevation, in feet. Used as a fallback
    when the NOAA fetch fails. Single-harmonic, so underestimates the spring
    tide range and ignores fortnightly variation — but the phase is right."""
    try:
        local_naive = datetime.strptime(obs_hour_str, "%Y-%m-%dT%H:%M")
    except (ValueError, TypeError):
        return None
    local_aware = TZ.localize(local_naive)
    utc_naive = local_aware.astimezone(pytz.UTC).replace(tzinfo=None)
    hours_since_ref = (utc_naive - M2_REFERENCE_UTC).total_seconds() / 3600.0
    phase_frac = (hours_since_ref % M2_PERIOD_HOURS) / M2_PERIOD_HOURS
    return round(SALEM_M2_AMPLITUDE_FT * math.cos(2 * math.pi * phase_frac), 2)


def _fetch_noaa_tide_hourly(start_date_yyyymmdd, end_date_yyyymmdd):
    """Fetch real hourly tide-elevation harmonic predictions from NOAA Tides
    & Currents for Salem station 8442645. Returns a dict mapping local-naive
    ISO hour strings ("YYYY-MM-DDTHH:00") to elevation in feet. Empty dict
    on failure — callers fall back to the M2 cosine approximation."""
    url = NOAA_TIDE_URL_TPL.format(
        start=start_date_yyyymmdd,
        end=end_date_yyyymmdd,
        station=NOAA_TIDE_STATION,
    )
    out = {}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "myweather-fitter/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        for p in data.get("predictions", []):
            t = p.get("t", "")  # "YYYY-MM-DD HH:MM" in local time (lst_ldt)
            v = p.get("v", "")
            try:
                iso = t.replace(" ", "T")
                out[iso] = float(v)
            except (ValueError, TypeError):
                continue
    except Exception as e:
        logging.warning(f"  ⚠  NOAA tide fetch failed: {redact_secrets(e)}")
    return out


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
    # Diurnal (hour-of-day) accumulators — feeds Layer 5 corrections + Section 7.
    diurnal_sums = defaultdict(float)
    diurnal_weights = defaultdict(float)
    diurnal_raw_counts = defaultdict(int)
    # Time-series accumulators for Section 6 — only pairs at TIMESERIES_LEAD
    # within the last TIMESERIES_DAYS, grouped per obs hour. Unweighted (raw
    # mean per hour) because we want to see the actual hour-by-hour signal,
    # not a smoothed weighted version.
    ts_cutoff = (now_naive - timedelta(days=TIMESERIES_DAYS)).strftime("%Y-%m-%dT%H:%M")
    ts_sums = defaultdict(float)   # key: (field, obs_hour_iso)
    ts_counts = defaultdict(int)
    # v0.6.27 wind-direction circular fit: accumulate sin/cos components per
    # lead bin (the standard solution for circular variables — the wraparound
    # at 0°/360° breaks the regular signed-error mean). Per pair we receive
    # error_sin = sin(forecast_rad) − sin(observed_rad) (and same for cos)
    # from the Joiner; per-lead means feed the Apply step which uses atan2 of
    # the component-corrected (sin, cos) pair to recover an angle.
    wd_sin_sums    = defaultdict(float)  # key: lead_h
    wd_cos_sums    = defaultdict(float)
    wd_sin_weights = defaultdict(float)
    wd_cos_weights = defaultdict(float)
    # v0.6.25c per-layer × per-lead accumulators. For each (field, lead, layer)
    # triplet aggregate |error| over the 7-day window. Lets the Forecast
    # Accuracy section render one chart per field with 4 lines (one per layer)
    # × 48 lead bins — showing where each correction layer adds value vs the
    # raw model. Lead 0 will show L2 ≈ 0 by construction (circular comparison
    # — same correction applied to both sides at the same moment); lead 1+
    # is meaningful (snapshot's forecast made hours ago vs fresh mesonet obs).
    # Only post-v0.6.25 pair rows have per-layer error fields; older pairs
    # silently feed only the legacy lead-time fit, not the per-layer table.
    per_layer_abs    = defaultdict(float)  # key: (field, lead_h, layer)
    per_layer_signed = defaultdict(float)
    per_layer_n      = defaultdict(int)
    # L2 τ-fit accumulators. Keyed by (field, lead_h). Filled only when both
    # error_l1 and error_l2 are present on the row so bias = err_l1 - err_l2
    # is well-defined.
    tau_e2 = defaultdict(float)  # Σ w · err_l1²
    tau_eb = defaultdict(float)  # Σ w · err_l1 · bias
    tau_b2 = defaultdict(float)  # Σ w · bias²
    tau_n  = defaultdict(int)    # raw pair count per (field, lead)
    n_in = 0
    n_kept = 0

    temp_blob = bucket.blob(TEMP_PATH)
    # Server-side copy to an immutable snapshot; the Joiner can keep appending
    # to main_blob during our read without affecting this handle.
    snapshot_blob = bucket.copy_blob(main_blob, bucket, SNAPSHOT_PATH)
    logging.info(f"  ℹ  Fitter: snapshotted {ERROR_LOG_PATH} -> {SNAPSHOT_PATH} ({snapshot_blob.size:,} bytes)")
    with snapshot_blob.open("r") as fin, temp_blob.open("w") as fout:
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
            # Wind direction circular fit: accumulate sin/cos errors separately.
            if field == "wd":
                e_sin = row.get("error_sin")
                e_cos = row.get("error_cos")
                if e_sin is not None and e_cos is not None:
                    wd_sin_sums[lead_h]    += float(e_sin) * w
                    wd_cos_sums[lead_h]    += float(e_cos) * w
                    wd_sin_weights[lead_h] += w
                    wd_cos_weights[lead_h] += w
            if RUN_TIDE_TRACKING:
                tide_bin = _tide_phase_bin(obs_time)
                if tide_bin is not None:
                    tide_sums[(field, tide_bin)] += float(error) * w
                    tide_weights[(field, tide_bin)] += w
                    tide_raw_counts[(field, tide_bin)] += 1
            # Diurnal binning: hour-of-day from the obs_time string (cheap to
            # parse — first 13 chars are "YYYY-MM-DDTHH").
            try:
                hod = int(obs_time[11:13])
            except (ValueError, IndexError):
                hod = None
            # Wind direction excluded from diurnal fit (v0.6.31): the diurnal
            # aggregator uses signed-mean-error which is meaningless for circular
            # variables — produces nonsensical ±139°-magnitude "corrections" by
            # averaging angular deltas that wrap. Same sin/cos special-case as
            # decay would solve this, but Layer 4 for wd is deferred (v0.6.27
            # scope: decay only). Skip entirely to keep diurnal_corrections.json
            # free of bogus wd entries.
            if hod is not None and 0 <= hod < DIURNAL_BINS and field != "wd":
                # Fit only on L3 residual (error after decay). Fitting on L2
                # error was structurally flawed: both decay (per-lead) and
                # diurnal (per-hour) were picking up the same hour-bias signal,
                # and mean-zero normalization didn't decouple them when lead
                # and hour-of-day were correlated. Skip pre-v0.6.25 pairs that
                # don't carry error_l3 entirely — the L3-bearing window will
                # fill in as new pairs accumulate.
                e_diurnal = row.get("error_l3")
                if e_diurnal is not None:
                    diurnal_sums[(field, hod)] += float(e_diurnal) * w
                    diurnal_weights[(field, hod)] += w
                    diurnal_raw_counts[(field, hod)] += 1
            # Time-series accumulation — pairs at any of the chosen leads,
            # recent enough to be in the time-series window, grouped per
            # (field, lead, obs_hour). Each lead gets its own series for
            # the Section 6 lead-time selector.
            if lead_h in TIMESERIES_LEADS_SET and obs_time >= ts_cutoff:
                obs_hour = obs_time[:13] + ":00"
                ts_sums[(field, lead_h, obs_hour)] += float(error)
                ts_counts[(field, lead_h, obs_hour)] += 1
            # Per-layer × per-lead accumulation for the Forecast Accuracy chart.
            # All lead bins, 7-day window. Only post-v0.6.25 pairs carry the
            # per-layer error fields; older pairs silently skip this loop and
            # only feed the legacy single-error aggregation above.
            if obs_time >= ts_cutoff:
                for lyr in ("l1", "l2", "l3", "l4"):
                    e = row.get(f"error_{lyr}")
                    if e is None:
                        continue
                    e = float(e)
                    key = (field, lead_h, lyr)
                    per_layer_abs[key]    += abs(e)
                    per_layer_signed[key] += e
                    per_layer_n[key]      += 1
            # L2 τ-fit: only fields we publish τ for, only post-v0.6.25 rows
            # carrying both error_l1 and error_l2 (so bias = err_l1 - err_l2
            # is well-defined). Recency weighting reuses the same `w` as the
            # legacy fit, so the windowing matches L3 and L4.
            if field in L2_TAU_FIELDS:
                e1 = row.get("error_l1")
                e2 = row.get("error_l2")
                if e1 is not None and e2 is not None:
                    e1f = float(e1)
                    bias = e1f - float(e2)
                    key = (field, lead_h)
                    tau_e2[key] += w * e1f * e1f
                    tau_eb[key] += w * e1f * bias
                    tau_b2[key] += w * bias * bias
                    tau_n[key]  += 1

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

    # Wind direction circular fit: emit per-lead sin/cos correction arrays.
    # Apply step uses them as: corrected_sin = sin(raw) − sin_corr; same for cos;
    # then atan2(corrected_sin, corrected_cos) recovers the corrected angle.
    wd_sin = [None] * LEAD_BINS
    wd_cos = [None] * LEAD_BINS
    for h in range(LEAD_BINS):
        ws_sum = wd_sin_weights.get(h, 0.0)
        wc_sum = wd_cos_weights.get(h, 0.0)
        if ws_sum > 0:
            wd_sin[h] = round(wd_sin_sums[h] / ws_sum, 5)
        if wc_sum > 0:
            wd_cos[h] = round(wd_cos_sums[h] / wc_sum, 5)
    corrections["wd_components"] = {"sin": wd_sin, "cos": wd_cos}

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

    # Tide-phase output + rolling history. Gated off in v0.6.47 — hypothesis
    # closed (weak, diurnal-entangled). Existing GCS files are left in place
    # so the R1/R2 charts (now under "Discarded hypotheses") still render the
    # frozen final state. Re-enable by flipping RUN_TIDE_TRACKING above.
    if RUN_TIDE_TRACKING:
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

    # Diurnal-hour output + rolling history. 24 bins, one per local hour.
    # Feeds Layer 4 (Apply step subtracts these from each forecast hour based
    # on that hour's local hour-of-day). Each per-hour value is the recency-
    # weighted mean L3 residual at that hour — i.e. what's still systematically
    # off after Layer 3 (decay) has been applied. No mean-zero normalization:
    # since we're fitting on the L3 residual, Layer 3's contribution is already
    # removed from the signal, and the raw per-hour mean is the correct
    # remaining adjustment.
    diurnal_corrections = {}
    diurnal_n_samples = {}
    for f in FIELDS:
        c_arr = [None] * DIURNAL_BINS
        n_arr = [0] * DIURNAL_BINS
        for b in range(DIURNAL_BINS):
            w_sum = diurnal_weights.get((f, b), 0.0)
            n_arr[b] = diurnal_raw_counts.get((f, b), 0)
            if w_sum > 0:
                c_arr[b] = round(diurnal_sums[(f, b)] / w_sum, 3)
        diurnal_corrections[f] = c_arr
        diurnal_n_samples[f] = n_arr
    diurnal_output = {
        "fitted_at": now_naive.strftime("%Y-%m-%dT%H:%M"),
        "n_pairs": n_kept,
        "retention_days": RETENTION_DAYS,
        "weighting": {"method": "exponential_decay", "tau_days": TAU_DAYS},
        "diurnal_bins": DIURNAL_BINS,
        "corrections_by_hour": diurnal_corrections,
        "n_samples_by_hour": diurnal_n_samples,
    }
    upload_json(diurnal_output, DIURNAL_PATH, "diurnal_corrections.json")
    try:
        diurnal_history = load_json(DIURNAL_HISTORY_PATH, default={"history": []})
        kept_d = [h for h in diurnal_history.get("history", [])
                  if isinstance(h, dict) and h.get("fitted_at", "") >= hist_cutoff]
        kept_d.append(diurnal_output)
        upload_json({"history": kept_d}, DIURNAL_HISTORY_PATH, "diurnal_corrections_history.json")
        logging.info(f"  ✓ Diurnal history: {len(kept_d)} fits in {HISTORY_RETENTION_DAYS}-day window")
    except Exception as e:
        logging.warning(f"  ⚠  Diurnal history append failed: {redact_secrets(e)}")

    # L2 lead-decay τ fit. For each field, find the τ in L2_TAU_GRID that
    # minimizes weighted SSE of (err_l1 + exp(-lead/τ) × bias)² across all
    # leads. SSE(τ) = Σ_l [e2[f,l] + 2·exp(-l/τ)·eb[f,l] + exp(-2l/τ)·b2[f,l]],
    # so the per-(f,l) accumulators we built in the pair-log loop are
    # sufficient. n_pairs threshold prevents publishing a noisy fit on a
    # too-thin field.
    tau_hours_out = {}
    tau_n_pairs_out = {}
    tau_sse_curve = {}  # for the history file — SSE at each grid point per field
    for f in L2_TAU_FIELDS:
        n_pairs = sum(tau_n.get((f, l), 0) for l in range(LEAD_BINS))
        tau_n_pairs_out[f] = n_pairs
        if n_pairs < L2_TAU_MIN_PAIRS:
            continue
        best_tau = None
        best_sse = float("inf")
        sse_at = {}
        for tau in L2_TAU_GRID:
            sse = 0.0
            for l in range(LEAD_BINS):
                if (f, l) not in tau_e2:
                    continue
                if tau >= 1e8:
                    d = 1.0
                    d2 = 1.0
                else:
                    d  = math.exp(-l / tau)
                    d2 = math.exp(-2.0 * l / tau)
                sse += tau_e2[(f, l)] + 2.0 * d * tau_eb[(f, l)] + d2 * tau_b2[(f, l)]
            sse_at[("inf" if tau >= 1e8 else f"{tau:g}")] = round(sse, 4)
            if sse < best_sse:
                best_sse = sse
                best_tau = tau
        if best_tau is not None:
            tau_hours_out[f] = "inf" if best_tau >= 1e8 else (
                int(best_tau) if best_tau == int(best_tau) else round(best_tau, 2))
            tau_sse_curve[f] = sse_at
    # Loader treats string "inf" as flat (τ ≥ 1e8 in corrected_hourly.py).
    # Numeric values are hours.
    l2_decay_output = {
        "fitted_at": now_naive.strftime("%Y-%m-%dT%H:%M"),
        "n_pairs_total": n_kept,
        "retention_days": RETENTION_DAYS,
        "weighting": {"method": "exponential_decay", "tau_days": TAU_DAYS},
        "tau_hours": tau_hours_out,
        "n_pairs_per_field": tau_n_pairs_out,
        "sse_at_grid": tau_sse_curve,
        "tau_grid_hours": [("inf" if t >= 1e8 else (int(t) if t == int(t) else t))
                           for t in L2_TAU_GRID],
        "min_pairs_threshold": L2_TAU_MIN_PAIRS,
    }
    upload_json(l2_decay_output, L2_DECAY_PATH, "l2_decay.json")
    logging.info(f"  ✓ L2 τ fit: " + ", ".join(
        f"{f}={tau_hours_out[f]}h" for f in L2_TAU_FIELDS if f in tau_hours_out
    ))
    try:
        l2_history = load_json(L2_DECAY_HISTORY_PATH, default={"history": []})
        kept_l2 = [h for h in l2_history.get("history", [])
                   if isinstance(h, dict) and h.get("fitted_at", "") >= hist_cutoff]
        kept_l2.append(l2_decay_output)
        upload_json({"history": kept_l2}, L2_DECAY_HISTORY_PATH, "l2_decay_history.json")
        logging.info(f"  ✓ L2 τ history: {len(kept_l2)} fits in {HISTORY_RETENTION_DAYS}-day window")
    except Exception as e:
        logging.warning(f"  ⚠  L2 τ history append failed: {redact_secrets(e)}")

    # Time-series diagnostic (Section 6) — last TIMESERIES_DAYS of hour-by-hour
    # mean error per (field, lead), plus an M2 tide-elevation curve at each
    # hour. Lets the debug page render error and tide elevation on a shared
    # time axis and switch which lead is shown via the Section 6 dropdown.
    # Time axis (`hours` + `tide_elevation_ft`) is shared across all leads.
    ts_hours = sorted({h for (_, _, h) in ts_sums.keys()})
    errors_by_lead = {str(lead): {f: [] for f in FIELDS} for lead in TIMESERIES_LEADS}
    samples_by_lead = {str(lead): {f: [] for f in FIELDS} for lead in TIMESERIES_LEADS}
    for h in ts_hours:
        for lead in TIMESERIES_LEADS:
            lead_str = str(lead)
            for f in FIELDS:
                c = ts_counts.get((f, lead, h), 0)
                samples_by_lead[lead_str][f].append(c)
                if c > 0:
                    errors_by_lead[lead_str][f].append(round(ts_sums[(f, lead, h)] / c, 3))
                else:
                    errors_by_lead[lead_str][f].append(None)
    # Fetch real NOAA tide harmonic predictions covering the time-series window
    # so the elevation overlay shows actual heights instead of an M2 cosine
    # approximation. Pad by ±1 day to cover any edge-of-window hours.
    if ts_hours:
        try:
            ts_start = datetime.strptime(ts_hours[0], "%Y-%m-%dT%H:%M") - timedelta(days=1)
            ts_end = datetime.strptime(ts_hours[-1], "%Y-%m-%dT%H:%M") + timedelta(days=1)
        except ValueError:
            ts_start, ts_end = now_naive - timedelta(days=TIMESERIES_DAYS + 1), now_naive + timedelta(days=1)
    else:
        ts_start, ts_end = now_naive - timedelta(days=TIMESERIES_DAYS + 1), now_naive + timedelta(days=1)
    # NOAA tide-elevation fetch + per-hour tide column for the time series.
    # Gated off in v0.6.47 (tide hypothesis closed). Without it, ts_hours
    # gets no tide_elevation_ft column; the R2 chart's tide overlay just
    # disappears, which is fine for a discarded hypothesis.
    if RUN_TIDE_TRACKING:
        noaa_tides = _fetch_noaa_tide_hourly(
            ts_start.strftime("%Y%m%d"), ts_end.strftime("%Y%m%d"),
        )
        tide_source = "noaa_harmonic" if noaa_tides else "m2_cosine_fallback"
        tide_elevation_ft = []
        for h in ts_hours:
            if h in noaa_tides:
                tide_elevation_ft.append(round(noaa_tides[h], 2))
            else:
                tide_elevation_ft.append(_tide_elevation_ft_m2(h))
    else:
        tide_source = "disabled"
        tide_elevation_ft = []

    # v0.6.25c: per-layer × per-lead MAE grids for the Forecast Accuracy chart.
    # For each (field, layer) emit a 48-bin array of MAE values (one per lead
    # hour 0..47). Missing-data leads come out as null. Frontend renders one
    # chart per field with 4 lines (raw, +mesonet, +decay, +final) × 48 leads.
    per_layer_mae_by_lead  = {}
    per_layer_bias_by_lead = {}
    per_layer_n_by_lead    = {}
    for f in FIELDS:
        per_layer_mae_by_lead[f]  = {}
        per_layer_bias_by_lead[f] = {}
        per_layer_n_by_lead[f]    = {}
        for lyr in ("l1", "l2", "l3", "l4"):
            mae_arr  = [None] * LEAD_BINS
            bias_arr = [None] * LEAD_BINS
            n_arr    = [0]    * LEAD_BINS
            for lead in range(LEAD_BINS):
                n = per_layer_n.get((f, lead, lyr), 0)
                n_arr[lead] = n
                if n > 0:
                    mae_arr[lead]  = round(per_layer_abs[(f, lead, lyr)] / n, 3)
                    bias_arr[lead] = round(per_layer_signed[(f, lead, lyr)] / n, 3)
            per_layer_mae_by_lead[f][lyr]  = mae_arr
            per_layer_bias_by_lead[f][lyr] = bias_arr
            per_layer_n_by_lead[f][lyr]    = n_arr

    ts_output = {
        "fitted_at": now_naive.strftime("%Y-%m-%dT%H:%M"),
        "leads_h": TIMESERIES_LEADS,
        "window_days": TIMESERIES_DAYS,
        "tide_source": tide_source,
        "tide_station": NOAA_TIDE_STATION,
        "hours": ts_hours,
        "tide_elevation_ft": tide_elevation_ft,
        "errors_by_lead": errors_by_lead,
        "n_samples_by_lead": samples_by_lead,
        "per_layer_mae_by_lead":  per_layer_mae_by_lead,
        "per_layer_bias_by_lead": per_layer_bias_by_lead,
        "per_layer_n_by_lead":    per_layer_n_by_lead,
    }
    try:
        upload_json(ts_output, TIMESERIES_PATH, "time_series_diagnostic.json")
        logging.info(f"  ✓ Time-series: {len(ts_hours)} hours × {len(TIMESERIES_LEADS)} leads over last {TIMESERIES_DAYS}d")
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
        try:
            if snapshot_blob.exists():
                snapshot_blob.delete()
        except Exception:
            pass
        raise

    try:
        snapshot_blob.delete()
    except Exception as e:
        logging.warning(f"  ⚠  Fitter: snapshot cleanup failed (non-fatal): {redact_secrets(e)}")

    pruned = n_in - n_kept
    logging.info(f"  ✓ Fitter: {n_in:,} pairs in, {n_kept:,} kept ({pruned:,} pruned >{RETENTION_DAYS}d)")

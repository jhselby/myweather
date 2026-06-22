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
from . import state_stratified


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
# Last N days of pairs held out as test set. Fit τ on the older "train" data,
# then score it on the recent "test" data the fitter never saw. Without this
# split the fit collapses to min τ in-sample (recent bias trivially fits recent
# obs); the held-out score is the only thing that says "this τ generalizes."
L2_HELDOUT_DAYS = 2.0
# Default τ values (mirror of DEFAULT_L2_TAUS in corrected_hourly.py). Used as
# the baseline to score "did the new fit beat the hardcoded defaults?" — the
# guardrail in the loader uses that delta to decide whether to adopt.
L2_DEFAULT_TAUS = {"t": 4.0, "h": 240.0, "pr": 12.0}
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

# Per-field τ overrides for fields where decay_tau_tuning.py shows ≥5% MAE
# improvement vs the global τ=14. Only fields that clear the 5% floor go
# here; marginal differences stay at the default. Re-validate weekly via
# analysis/decay_tau_tuning.py.
TAU_DAYS_BY_FIELD = {
    "pp": 28,  # +11.1% MAE held-out vs τ=14 (2026-06-21 read)
    "pa": 28,  # +9.4% MAE held-out vs τ=14 (2026-06-22 read)
}


def _tau_for_field(field):
    return TAU_DAYS_BY_FIELD.get(field, TAU_DAYS)

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


L5_GATE_HISTORY_PATH = "l5_gate_history.json"
L5_GATE_WINDOW_DAYS = 7
L5_GATE_HISTORY_RETENTION_DAYS = 30  # keep enough scrollback for debug page

MARINE_WATCH_PATH = "marine_layer_watch.json"
MARINE_WATCH_RETENTION_DAYS = 30


def _compute_marine_layer_watch(marine_acc, fitted_at):
    """Stage 2.5: append today's marine-layer NE+morn cc bias to
    marine_layer_watch.json, prune to retention, return the latest snapshot.

    Signed bias = (forecast - observed) mean error in the NE+morn stratum
    (wd 45-105°, hour 4-9 EDT). Positive = forecast over-calls clouds.
    Stage 1 baseline (2026-06-21): +28.1 mean / +25.0 median, n=3,119.
    Stage 3 promotion still gated on the Sun-morning weekly verdict.
    """
    in_n = marine_acc["n"]
    out_n = marine_acc["out_n"]
    if in_n < 10:
        return None  # too thin to log meaningfully
    in_w = marine_acc["weight"] or 1.0
    out_w = marine_acc["out_weight"] or 1.0
    in_bias = marine_acc["signed_sum"] / in_w
    in_abs  = marine_acc["abs_sum"] / in_w
    out_bias = (marine_acc["out_signed_sum"] / out_w) if out_n else None
    out_abs  = (marine_acc["out_abs_sum"] / out_w) if out_n else None
    entry = {
        "fitted_at": fitted_at,
        "in_bin_signed_bias": round(in_bias, 2),
        "in_bin_mae":         round(in_abs, 2),
        "in_bin_n":           in_n,
        "out_bin_signed_bias": round(out_bias, 2) if out_bias is not None else None,
        "out_bin_mae":        round(out_abs, 2) if out_abs is not None else None,
        "out_bin_n":          out_n,
    }
    log = load_json(MARINE_WATCH_PATH, default={"entries": []})
    entries = log.get("entries", [])
    entries.append(entry)
    cutoff = (datetime.now(TZ) - timedelta(days=MARINE_WATCH_RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")
    entries = [e for e in entries if e.get("fitted_at", "") >= cutoff]
    upload_json({"entries": entries}, MARINE_WATCH_PATH, MARINE_WATCH_PATH)
    return entry


def _compute_l5_gate_7d(this_cycle):
    """Append this cycle's L5 verdict to l5_gate_history.json and compute the
    trailing-7-day promotion-gate status.

    Day-level rollup: a day's verdict is SHIP only if every Fitter cycle that
    day was SHIP. Mirrors the strictness of analysis/simulate_windows.py's
    7-of-7 rule but applied to Fitter-cycle days instead of cutoff windows.

    Returns dict {ship_days, hold_days, insufficient_days, total_days,
                  gate_clear, latest_streak_ship, history_window_days}.
    """
    history = load_json(L5_GATE_HISTORY_PATH, default={"entries": []})
    entries = history.get("entries", [])
    entries.append(this_cycle)
    # Prune to retention window.
    cutoff = (datetime.now(TZ) - timedelta(days=L5_GATE_HISTORY_RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")
    entries = [e for e in entries if e.get("fitted_at", "") >= cutoff]
    upload_json({"entries": entries}, L5_GATE_HISTORY_PATH, L5_GATE_HISTORY_PATH)

    # Compute 7-day gate by day-rolling up entries.
    window_cutoff = (datetime.now(TZ) - timedelta(days=L5_GATE_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M")
    recent = [e for e in entries if e.get("fitted_at", "") >= window_cutoff]
    by_day = {}
    for e in recent:
        day = e.get("fitted_at", "")[:10]  # YYYY-MM-DD
        if not day:
            continue
        by_day.setdefault(day, []).append(e.get("verdict", ""))
    ship_days = hold_days = insufficient_days = 0
    for day, verdicts in by_day.items():
        if all(v == "SHIP" for v in verdicts):
            ship_days += 1
        elif any(v == "insufficient_data" for v in verdicts):
            insufficient_days += 1
        else:
            hold_days += 1
    total_days = len(by_day)
    gate_clear = total_days >= L5_GATE_WINDOW_DAYS and hold_days == 0 and insufficient_days == 0
    # Trailing SHIP streak — newest entries first.
    streak = 0
    for e in reversed(recent):
        if e.get("verdict") == "SHIP":
            streak += 1
        else:
            break
    return {
        "ship_days": ship_days,
        "hold_days": hold_days,
        "insufficient_days": insufficient_days,
        "total_days": total_days,
        "gate_clear": gate_clear,
        "latest_streak_ship": streak,
        "history_window_days": L5_GATE_WINDOW_DAYS,
    }


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
    # v0.6.48: state-stratified accuracy accumulators — equal-weight, fed
    # in-loop alongside the recency-weighted fits above. See module docstring
    # for the hypothesis under test.
    state_acc = state_stratified.init_accumulators()
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
    # L2 τ-fit accumulators (v0.6.105: switched from closed-form SSE to
    # per-pair MAE iteration). The earlier SSE approach picked τ=0.5h on every
    # held-out fit because squared-error penalty makes a handful of bias
    # overshoots dominate the optimization, even when the average absolute
    # error improved with a larger τ. Storing per-pair tuples means we can
    # compute MAE = Σ w·|err_l1 + d·bias| / Σ w directly for each candidate τ.
    # Train list feeds the search; test list scores the chosen τ on data the
    # search never saw. Pair counts are modest (~70k train, ~11k test per
    # field) so memory is trivial — ~few MB of tuples for the L2 block.
    # Tuple shape: (lead_h, err_l1, bias, w). Keyed by field.
    l2_train = defaultdict(list)
    l2_test  = defaultdict(list)

    # v0.6.124 R6 audit accumulators (replaces v0.6.110 R5 wiring; R5 retired
    # 2026-06-17). For each pair with both state_fc.regime_synoptic and
    # state_obs.regime_synoptic, classify as stable (regimes agree) or
    # transition (regimes disagree — model expected A, B happened). Tally
    # sum-of-abs-error per (field, lead_band, is_transition). Verdict counts
    # buckets where transition MAE is ≥10% worse than stable MAE with both
    # sides ≥200 pairs; SHIP if ≥10 buckets, HOLD otherwise.
    # See analysis/regime_transition_audit.py and analysis/simulate_windows.py.
    # v0.6.179: recency-weighted R6 audit (same fix as v0.6.178 L5). Each
    # pair contributes |error|·w with w=exp(-age_days / TAU_DAYS) so recent
    # transitions weigh more than 4-week-old ones. n stays unweighted for
    # display.
    r6_acc = defaultdict(lambda: {"sum_abs": 0.0, "weight": 0.0, "n": 0})
    # v0.6.182: marine-layer Stage 2.5 — daily passive watch. Accumulates
    # signed cc error in the NE+morn stratum (wd 45-105°, obs hour 4-9 EDT)
    # so the marine-layer hypothesis Stage 2 weekly read isn't the only
    # visibility on the bias. Stage 3 wiring still requires the weekly
    # verdict to stabilize (see [[project-todo]] weekly Sun re-reads).
    marine_acc = {"signed_sum": 0.0, "abs_sum": 0.0, "weight": 0.0, "n": 0,
                  "out_signed_sum": 0.0, "out_abs_sum": 0.0, "out_weight": 0.0, "out_n": 0}

    # v0.6.112 L5 solar audit accumulators. Same pattern as R5 but joins via
    # the pair's own state_fc/state_obs.regime_synoptic instead of an external
    # log — state metadata is on every post-v0.6.29 pair, so no extra fetch.
    # "Realistic" uses state_fc.regime_synoptic (the regime the model thought
    # we were in at forecast time — what production keys on at runtime, since
    # solar_correction.stamp uses derived.state.regime_synoptic which is the
    # current observed regime, equivalent to state_fc at the tick that fires).
    from .solar_correction import (
        compute_solar_correction as _l5_compute,
        SUN_UP_THRESHOLD as _L5_SUN_UP,
    )
    # v0.6.178: recency-weighted L5 audit. Each pair contributes
    # abs_error × exp(-age_days / TAU_DAYS) to baseline and l5; "weight"
    # accumulates Σw so the displayed MAE is Σ(w·|e|) / Σw (weighted mean).
    # "n" stays as unweighted count for display ("audit ran on N pairs").
    # Matches the recency weighting used by the rest of the Fitter; prior
    # versions averaged all 30 retention-days equally and ran ~2pp more
    # optimistic than the 7-day simulator on the same biases.
    l5_acc = defaultdict(lambda: {"baseline": 0.0, "l5": 0.0, "weight": 0.0, "n": 0})

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
            # State-stratified accumulators (equal-weight). Done before the
            # field-required filter below because state_stratified has its
            # own validity checks and tolerates rows the lead-h fit skips.
            state_stratified.accumulate(state_acc, row)
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
            w = math.exp(-age_days / _tau_for_field(field))
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
            # v0.6.112 L5 solar audit accumulator. Solar pairs with state_fc
            # regime, daytime (forecast_l1 ≥ SUN_UP_THRESHOLD), lead 1+.
            # Mirrors analysis/l5_solar_analysis.py's "realistic" view.
            if field == "sr" and lead_h >= 1:
                state_fc = row.get("state_fc") or {}
                regime_fc = state_fc.get("regime_synoptic")
                f_l1 = row.get("forecast_l1")
                e_l4_sr = row.get("error_l4")
                if regime_fc and f_l1 is not None and e_l4_sr is not None:
                    try:
                        f_l1f = float(f_l1)
                        e_l4f_sr = float(e_l4_sr)
                        if f_l1f >= _L5_SUN_UP:
                            try:
                                hour_local_l5 = int(obs_time[11:13])
                            except (ValueError, IndexError):
                                hour_local_l5 = None
                            l5_delta = _l5_compute(regime_fc, f_l1f, hour_local_l5)
                            if   lead_h < 6:  band_l5 = "0-5h"
                            elif lead_h < 12: band_l5 = "6-11h"
                            elif lead_h < 24: band_l5 = "12-23h"
                            else:             band_l5 = "24-47h"
                            for bk in [(regime_fc, band_l5), (regime_fc, "all"),
                                       ("any", band_l5), ("any", "all")]:
                                a = l5_acc[bk]
                                a["baseline"] += abs(e_l4f_sr) * w
                                a["l5"]       += abs(e_l4f_sr + l5_delta) * w
                                a["weight"]   += w
                                a["n"]        += 1
                    except (TypeError, ValueError):
                        pass

            # v0.6.124 R6 audit accumulator. Any pair where both state_fc
            # and state_obs carry regime_synoptic — classify stable vs
            # transition, bucket by (field, band, is_transition). Uses the
            # final-answer "error" column (whatever the highest applied layer
            # produced).
            sfc_r6 = row.get("state_fc") or {}
            sob_r6 = row.get("state_obs") or {}
            rfc_r6 = sfc_r6.get("regime_synoptic")
            rob_r6 = sob_r6.get("regime_synoptic")
            err_r6 = row.get("error")
            if rfc_r6 and rob_r6 and err_r6 is not None:
                if   lead_h < 6:  band_r6 = "0-5h"
                elif lead_h < 12: band_r6 = "6-11h"
                elif lead_h < 24: band_r6 = "12-23h"
                else:             band_r6 = "24-47h"
                is_trans = (rfc_r6 != rob_r6)
                try:
                    a = r6_acc[(field, band_r6, is_trans)]
                    a["sum_abs"] += abs(float(err_r6)) * w
                    a["weight"]  += w
                    a["n"]       += 1
                except (TypeError, ValueError):
                    pass
            # v0.6.182 marine-layer watch — stratify cc errors by (wd ∈ [45,105],
            # obs hour ∈ [4,9] EDT). Recency-weighted like everything else.
            if field == "cc":
                state_obs_ml = row.get("state_obs") or {}
                wd_ml = state_obs_ml.get("wind_dir")
                err_ml = row.get("error_l4") if row.get("error_l4") is not None else row.get("error")
                if wd_ml is not None and err_ml is not None:
                    try:
                        hour_ml = int(obs_time[11:13])
                    except (ValueError, IndexError):
                        hour_ml = None
                    if hour_ml is not None:
                        try:
                            err_mlf = float(err_ml)
                            in_bin = (45 <= wd_ml <= 105) and (4 <= hour_ml <= 9)
                            prefix = "" if in_bin else "out_"
                            marine_acc[prefix + "signed_sum"] += err_mlf * w
                            marine_acc[prefix + "abs_sum"]    += abs(err_mlf) * w
                            marine_acc[prefix + "weight"]     += w
                            marine_acc[prefix + "n"]          += 1
                        except (TypeError, ValueError):
                            pass
            # L2 τ-fit: only fields we publish τ for, only post-v0.6.25 rows
            # carrying both error_l1 and error_l2 (so bias = err_l1 - err_l2
            # is well-defined). Recency weighting reuses the same `w` as the
            # legacy fit, so the windowing matches L3 and L4.
            if field in L2_TAU_FIELDS:
                e1 = row.get("error_l1")
                e2 = row.get("error_l2")
                if e1 is not None and e2 is not None:
                    e1f = float(e1)
                    # bias is defined so that err_l1 + 1.0*bias == err_l2 — i.e.,
                    # at decay=1 the corrected residual equals the full-L2 error.
                    # Sign matters: had been inverted since v0.6.44 (e1-e2),
                    # which caused every fit to land at τ=0.5h regardless of
                    # whether the L2 correction actually helped.
                    bias = float(e2) - e1f
                    pair = (lead_h, e1f, bias, w)
                    if age_days < L2_HELDOUT_DAYS:
                        l2_test[field].append(pair)
                    else:
                        l2_train[field].append(pair)

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
        "weighting": {"method": "exponential_decay", "tau_days": TAU_DAYS, "tau_days_by_field": dict(TAU_DAYS_BY_FIELD)},
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
            "weighting": {"method": "exponential_decay", "tau_days": TAU_DAYS, "tau_days_by_field": dict(TAU_DAYS_BY_FIELD)},
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
        "weighting": {"method": "exponential_decay", "tau_days": TAU_DAYS, "tau_days_by_field": dict(TAU_DAYS_BY_FIELD)},
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

    # v0.6.48: state-stratified accuracy output. Equal-weight tables across
    # the kept window — per-field per-dimension MAE + ranked opportunities +
    # verdict line. Diagnostic-only (active hypothesis, not yet applied).
    try:
        ss_output = state_stratified.build_output(
            state_acc, now_naive.strftime("%Y-%m-%dT%H:%M")
        )
        upload_json(ss_output, "state_stratified_accuracy.json",
                    "state_stratified_accuracy.json")
        logging.info(f"  ✓ State-stratified accuracy: {ss_output['n_pairs_used']:,} pairs used "
                     f"({len(ss_output['ranked_opportunities'])} ranked opps)")
    except Exception as e:
        logging.warning(f"  ⚠  State-stratified accuracy failed: {redact_secrets(e)}")

    # L2 lead-decay τ fit with held-out MAE validation.
    #
    # Pick τ on TRAIN by MAE, score on TEST by MAE. Earlier closed-form SSE
    # version picked τ=0.5h on every fit because squared-error penalty made
    # outlier corrections dominate the optimization, even when the average
    # absolute error favored a larger τ. MAE matches what the loader's
    # guardrail actually cares about (forecast error users experience) and
    # matches the metric the hardcoded defaults were originally fit on.
    #
    # No closed form for MAE — iterate per-pair for each τ candidate. With
    # ~70k train and ~11k test pairs per field × 15 τ candidates × 5 fields,
    # this is still well under a second of compute.

    def _mae_at(tau, pairs):
        if not pairs:
            return None
        if tau >= 1e8:
            err_sum = sum(w * abs(e + b) for (_l, e, b, w) in pairs)
        else:
            err_sum = sum(w * abs(e + math.exp(-l / tau) * b) for (l, e, b, w) in pairs)
        w_sum = sum(w for (_l, _e, _b, w) in pairs)
        return err_sum / w_sum if w_sum > 0 else None

    tau_hours_out = {}
    tau_n_pairs_out_train = {}
    tau_n_pairs_out_test = {}
    tau_mae_curve = {}  # train MAE at each grid point (diagnostics)
    heldout_out = {}    # per-field test MAE at flat/default/fitted τ
    for f in L2_TAU_FIELDS:
        train_pairs = l2_train.get(f, [])
        test_pairs  = l2_test.get(f, [])
        n_train = len(train_pairs)
        n_test  = len(test_pairs)
        tau_n_pairs_out_train[f] = n_train
        tau_n_pairs_out_test[f]  = n_test
        if n_train < L2_TAU_MIN_PAIRS:
            continue
        # Pick τ on TRAIN by min MAE.
        best_tau = None
        best_mae = float("inf")
        mae_at = {}
        for tau in L2_TAU_GRID:
            m = _mae_at(tau, train_pairs)
            if m is None:
                continue
            mae_at[("inf" if tau >= 1e8 else f"{tau:g}")] = round(m, 6)
            if m < best_mae:
                best_mae = m
                best_tau = tau
        if best_tau is None:
            continue
        tau_hours_out[f] = "inf" if best_tau >= 1e8 else (
            int(best_tau) if best_tau == int(best_tau) else round(best_tau, 2))
        tau_mae_curve[f] = mae_at
        # Score on TEST at flat / default / fitted.
        if n_test >= max(100, L2_TAU_MIN_PAIRS // 5):
            mae_flat    = _mae_at(1e9, test_pairs)
            mae_default = _mae_at(L2_DEFAULT_TAUS.get(f, 1e9), test_pairs)
            mae_fitted  = _mae_at(best_tau, test_pairs)
            imp_vs_default = (100.0 * (mae_default - mae_fitted) / mae_default
                              if (mae_default and mae_default > 0) else 0.0)
            imp_vs_flat = (100.0 * (mae_flat - mae_fitted) / mae_flat
                           if (mae_flat and mae_flat > 0) else 0.0)
            heldout_out[f] = {
                "n_test": n_test,
                "mae_flat": round(mae_flat, 4) if mae_flat is not None else None,
                "mae_default": round(mae_default, 4) if mae_default is not None else None,
                "mae_fitted": round(mae_fitted, 4) if mae_fitted is not None else None,
                "improvement_vs_default_pct": round(imp_vs_default, 2),
                "improvement_vs_flat_pct": round(imp_vs_flat, 2),
            }

    l2_decay_output = {
        "fitted_at": now_naive.strftime("%Y-%m-%dT%H:%M"),
        "n_pairs_total": n_kept,
        "retention_days": RETENTION_DAYS,
        "heldout_days": L2_HELDOUT_DAYS,
        "weighting": {"method": "exponential_decay", "tau_days": TAU_DAYS, "tau_days_by_field": dict(TAU_DAYS_BY_FIELD)},
        "tau_hours": tau_hours_out,
        "heldout": heldout_out,
        "n_pairs_per_field": {
            "train": tau_n_pairs_out_train,
            "test": tau_n_pairs_out_test,
        },
        "mae_at_grid": tau_mae_curve,
        "tau_grid_hours": [("inf" if t >= 1e8 else (int(t) if t == int(t) else t))
                           for t in L2_TAU_GRID],
        "min_pairs_threshold": L2_TAU_MIN_PAIRS,
        "default_taus": dict(L2_DEFAULT_TAUS),
    }
    upload_json(l2_decay_output, L2_DECAY_PATH, "l2_decay.json")
    # Per-field log line: fitted τ + held-out improvement vs default. The
    # loader's guardrail decides whether each field is actually adopted; this
    # log is the human-readable record of what the fitter proposed.
    log_parts = []
    for f in L2_TAU_FIELDS:
        if f not in tau_hours_out:
            continue
        h = heldout_out.get(f, {})
        if h:
            log_parts.append(
                f"{f}={tau_hours_out[f]}h ({h['improvement_vs_default_pct']:+.1f}% "
                f"vs default, n_test={h['n_test']:,})"
            )
        else:
            log_parts.append(f"{f}={tau_hours_out[f]}h (no held-out score)")
    logging.info("  ✓ L2 τ fit: " + ", ".join(log_parts) if log_parts
                 else "  ⊘ L2 τ fit: no fields had enough train pairs")
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

    # v0.6.124 R6 audit verdict — compute from accumulators built during the
    # main pair-stream loop above. Same logic as analysis/regime_transition_audit.py.
    # Counts (field, band) buckets where transition MAE exceeds stable MAE
    # by ≥10% with both sides having ≥200 pairs; SHIP if ≥10 buckets, else HOLD.
    r6_audit_verdict = None
    try:
        R6_PENALTY_PCT = 10.0
        R6_MIN_PER_BUCKET = 200
        R6_MIN_FLAGGED = 10
        # Collect all (field, band) keys present in the accumulator.
        r6_fields = {k[0] for k in r6_acc.keys()}
        r6_bands_present = ["0-5h", "6-11h", "12-23h", "24-47h"]
        flagged = 0
        evaluated = 0
        worst = None  # (field, band, penalty_pct)
        for fld in r6_fields:
            for bnd in r6_bands_present:
                s = r6_acc.get((fld, bnd, False))
                t = r6_acc.get((fld, bnd, True))
                if not s or not t:
                    continue
                if s["n"] < R6_MIN_PER_BUCKET or t["n"] < R6_MIN_PER_BUCKET:
                    continue
                evaluated += 1
                mae_s = s["sum_abs"] / (s["weight"] or 1.0)
                mae_t = t["sum_abs"] / (t["weight"] or 1.0)
                if mae_s > 0:
                    pct = 100.0 * (mae_t - mae_s) / mae_s
                    if pct >= R6_PENALTY_PCT:
                        flagged += 1
                    if worst is None or pct > worst[2]:
                        worst = (fld, bnd, pct)
        total_pairs = sum(v["n"] for v in r6_acc.values())
        if evaluated > 0:
            verdict_r6 = "SHIP" if flagged >= R6_MIN_FLAGGED else "HOLD"
            r6_audit_verdict = {
                "verdict": verdict_r6,
                "enabled": False,  # R6 has no production layer yet
                "n_flagged_buckets": flagged,
                "n_evaluated_buckets": evaluated,
                "worst_field": worst[0] if worst else None,
                "worst_band": worst[1] if worst else None,
                "worst_penalty_pct": round(worst[2], 2) if worst else None,
                "n_pairs": total_pairs,
            }
            logging.info(f"  ✓ R6 audit: {verdict_r6} ({flagged}/{evaluated} buckets "
                         f"≥{R6_PENALTY_PCT:.0f}% transition penalty, n={total_pairs:,})")
        else:
            r6_audit_verdict = {
                "verdict": "insufficient_data",
                "enabled": False,
                "n_pairs": total_pairs,
            }
            logging.info(f"  ⊘ R6 audit: insufficient data (n={total_pairs}, no bucket met ≥{R6_MIN_PER_BUCKET}/side)")
    except Exception as e:
        logging.warning(f"  ⚠  R6 audit failed: {redact_secrets(e)}")

    # v0.6.112 L5 audit verdict — same pattern as R5 but for solar regime
    # correction. Thresholds match analysis/l5_solar_analysis.py.
    l5_audit_verdict = None
    try:
        from .solar_correction import ENABLED as L5_ENABLED
        overall_l5 = l5_acc.get(("any", "all"))
        if overall_l5 and overall_l5["n"] >= 500:
            n_l5 = overall_l5["n"]
            w_l5 = overall_l5["weight"] or 1.0
            mae_b_l5 = overall_l5["baseline"] / w_l5
            mae_a_l5 = overall_l5["l5"] / w_l5
            d_l5 = (100.0 * (mae_b_l5 - mae_a_l5) / mae_b_l5) if mae_b_l5 > 0 else 0.0
            # Count regimes with ≥3% individual improvement
            L5_REGIMES = ("frontal", "sw_flow", "pre_frontal", "sea_breeze",
                          "nw_flow", "calm", "se_flow", "ne_flow")
            regimes_winning = 0
            for r in L5_REGIMES:
                rb = l5_acc.get((r, "all"))
                if not rb or rb["n"] < 50:
                    continue
                rb_w = rb["weight"] or 1.0
                rb_b = rb["baseline"] / rb_w
                rb_a = rb["l5"] / rb_w
                if rb_b > 0 and (rb_b - rb_a) / rb_b >= 0.03:
                    regimes_winning += 1
            ship = (d_l5 >= 5.0) and (regimes_winning >= 5)
            verdict_l5 = "SHIP" if ship else "HOLD"
            l5_audit_verdict = {
                "verdict": verdict_l5,
                "enabled": bool(L5_ENABLED),
                "mae_baseline": round(mae_b_l5, 2),
                "mae_with_layer": round(mae_a_l5, 2),
                "improvement_pct": round(d_l5, 2),
                "n_pairs": n_l5,
                "regimes_winning": regimes_winning,
                "regimes_total": len(L5_REGIMES),
            }
            logging.info(f"  ✓ L5 audit: {verdict_l5} (baseline MAE {mae_b_l5:.1f} W/m², "
                         f"L5 {d_l5:+.2f}%, {regimes_winning}/{len(L5_REGIMES)} regimes winning, n={n_l5:,})")
            # v0.6.180: trailing-7-day promotion-gate status. Auto-aggregates
            # the Fitter's per-cycle L5 verdicts into a 7-day rolling read so
            # the debug page can show gate status without anyone running
            # analysis/simulate_windows.py. Persisted in l5_gate_history.json.
            try:
                _gate = _compute_l5_gate_7d({
                    "fitted_at": output["fitted_at"],
                    "verdict": verdict_l5,
                    "improvement_pct": round(d_l5, 2),
                    "regimes_winning": regimes_winning,
                })
                if _gate:
                    l5_audit_verdict["gate_7d"] = _gate
                    logging.info(f"  ✓ L5 gate 7d: {_gate.get('ship_days')}/{_gate.get('total_days')} SHIP days "
                                 f"({'CLEAR' if _gate.get('gate_clear') else 'FLICKER'})")
            except Exception as e:
                logging.warning(f"  ⚠  L5 gate_7d failed: {redact_secrets(e)}")
        else:
            n_l5 = (overall_l5 or {}).get("n", 0)
            l5_audit_verdict = {
                "verdict": "insufficient_data",
                "enabled": bool(L5_ENABLED),
                "n_pairs": n_l5,
            }
            logging.info(f"  ⊘ L5 audit: insufficient data (n={n_l5}, need ≥500)")
    except Exception as e:
        logging.warning(f"  ⚠  L5 audit failed: {redact_secrets(e)}")

    # v0.6.182 marine-layer Stage 2.5 watch — log NE+morn cc bias per cycle.
    marine_watch = None
    try:
        marine_watch = _compute_marine_layer_watch(marine_acc, output["fitted_at"])
        if marine_watch:
            logging.info(f"  ✓ Marine-layer watch: in-bin signed bias "
                         f"{marine_watch['in_bin_signed_bias']:+.1f}pp "
                         f"(n={marine_watch['in_bin_n']}), out-bin "
                         f"{marine_watch['out_bin_signed_bias']:+.1f}pp "
                         f"(n={marine_watch['out_bin_n']})")
    except Exception as e:
        logging.warning(f"  ⚠  Marine-layer watch failed: {redact_secrets(e)}")

    # Shadow whitelist tuner: log what the auto-tuner WOULD have recommended
    # this Fitter cycle. Doesn't change production. Accumulates over months
    # so we can later evaluate "how often does shadow agree with human choices?"
    # — the precondition for considering automation. v0.6.112: logs L5;
    # v0.6.124: logs R6 (R5 retired). Same shape, plugs in via conditional_audits.
    try:
        from .shadow_whitelist import log_shadow_recommendation
        from .decay_apply import L3_FIELDS, L4_FIELDS
        conditional_audits = {}
        if l5_audit_verdict:
            conditional_audits["l5"] = l5_audit_verdict
        if r6_audit_verdict:
            conditional_audits["r6"] = r6_audit_verdict
        if marine_watch:
            conditional_audits["marine_layer_watch"] = marine_watch
        log_shadow_recommendation(ts_output, L3_FIELDS, L4_FIELDS,
                                  conditional_audits=conditional_audits or None)
    except Exception as e:
        logging.warning(f"  ⚠  Shadow whitelist log failed: {redact_secrets(e)}")

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

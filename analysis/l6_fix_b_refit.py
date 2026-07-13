"""
L6 Fix B — refit the cove correction lookup against the L2-corrected baseline.

Step 2 of the TODO in project_l6_l2_double_counting_hypothesis. The current
_DELTA_BY_OCTANT and _HOUR_DELTA_SB_OFF tables in cove_correction.py were
fit from cove_gradient_log.json (waterfront_obs − inland_obs) — the raw
microclimate gap. Real per-row Production evidence (2026-07-01) showed
that adding that raw gradient on top of L2 double-counts, because L2's
Kalman blend already carries "waterfront bias" via station weighting.

This script fits residuals as (obs − forecast_L2), keyed the same way
the live lookup is keyed (sb_active_fc × octant, and sb_off × hour).
Bins with |mean| < threshold or n < threshold drop to 0 (L2 already
handled that regime). Held-out check evaluates the refit tables against
L2 alone on the newest 7 days.

Run:
    python3 analysis/l6_fix_b_refit.py

Output:
    analysis/output/l6_fix_b_refit.txt
    analysis/output/l6_fix_b_lookup.json
"""
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "l6_fix_b_refit.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "l6_fix_b_lookup.json")

OCTANTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
SB_OCTANTS = {"S", "SE", "SW"}
SB_HOUR_LO, SB_HOUR_HI = 13, 18

# Bin-ship thresholds (train window)
MIN_N_PER_BIN = 100
MIN_ABS_MEAN = 0.5   # °F
MAX_STD = 2.5        # °F

# Held-out ship rule
TEST_WINDOW_DAYS = 7
MIN_HELDOUT_IMPROVEMENT_PCT = 1.0


def octant(deg):
    if deg is None:
        return None
    return OCTANTS[int((deg + 22.5) % 360 / 45)]


def sb_active_fc(hour_local, wind_dir_deg):
    """Mirror cove_correction._sb_active_forecast — S-half wind, 13-18 EDT."""
    if hour_local is None or wind_dir_deg is None:
        return False
    if not (SB_HOUR_LO <= hour_local <= SB_HOUR_HI):
        return False
    return octant(wind_dir_deg) in SB_OCTANTS


def parse_iso_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def stats(vals):
    n = len(vals)
    if n == 0:
        return {"n": 0, "mean": None, "median": None, "std": None}
    m = sum(vals) / n
    return {
        "n": n,
        "mean": m,
        "median": statistics.median(vals),
        "std": statistics.stdev(vals) if n > 1 else 0.0,
    }


def load_pairs():
    """Stream cove t-pairs. Yields (obs_time, hour_local, wd_fc, forecast_l2, observed)."""
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != "t":
                continue
            f2 = r.get("forecast_l2")
            obs = r.get("observed")
            if f2 is None or obs is None:
                continue
            fc_state = r.get("state_fc") or {}
            wd_fc = fc_state.get("wind_dir")
            if wd_fc is None:
                continue
            vt = r.get("valid_time")
            if not vt or len(vt) < 13:
                continue
            try:
                hour_local = int(vt[11:13])
            except ValueError:
                continue
            obs_time = r.get("obs_time")
            yield (obs_time, hour_local, float(wd_fc),
                   float(f2), float(obs))


def bin_key(hour_local, wd_fc):
    """Return (branch, key) where branch is 'sb_on' or 'sb_off'."""
    oct_ = octant(wd_fc)
    if oct_ is None:
        return None
    if sb_active_fc(hour_local, wd_fc):
        return ("sb_on", oct_)
    return ("sb_off", hour_local)


def fit_tables(train_rows):
    """train_rows: list of (branch, key, residual). Returns (delta_by_octant, hour_delta_sb_off, per_bin_stats)."""
    buckets = defaultdict(list)
    for br, key, res in train_rows:
        buckets[(br, key)].append(res)

    delta_by_octant = {}   # {(sb_active_bool, oct): delta}
    hour_delta_sb_off = {} # {hour: delta}
    per_bin = {}

    for (br, key), vals in buckets.items():
        s = stats(vals)
        per_bin[(br, key)] = s
        ok = (s["n"] >= MIN_N_PER_BIN
              and s["mean"] is not None
              and abs(s["mean"]) >= MIN_ABS_MEAN
              and (s["std"] or 0) < MAX_STD)
        if not ok:
            continue
        delta = round(s["mean"], 2)
        if br == "sb_on":
            delta_by_octant[(True, key)] = delta
        else:
            hour_delta_sb_off[key] = delta
    return delta_by_octant, hour_delta_sb_off, per_bin


def lookup_delta(delta_by_octant, hour_delta_sb_off, hour_local, wd_fc):
    oct_ = octant(wd_fc)
    if oct_ is None:
        return 0.0
    if sb_active_fc(hour_local, wd_fc):
        return delta_by_octant.get((True, oct_), 0.0)
    return hour_delta_sb_off.get(hour_local, 0.0)


def evaluate_heldout(test_rows_full, delta_by_octant, hour_delta_sb_off):
    """test_rows_full: (hour_local, wd_fc, forecast_l2, observed)."""
    n = 0
    sum_err_l2 = 0.0
    sum_err_refit = 0.0
    n_delta_applied = 0
    for hour_local, wd_fc, f2, obs in test_rows_full:
        d = lookup_delta(delta_by_octant, hour_delta_sb_off, hour_local, wd_fc)
        err_l2 = abs(f2 - obs)
        err_refit = abs((f2 + d) - obs)
        sum_err_l2 += err_l2
        sum_err_refit += err_refit
        n += 1
        if d != 0.0:
            n_delta_applied += 1
    if n == 0:
        return None
    mae_l2 = sum_err_l2 / n
    mae_refit = sum_err_refit / n
    impr_pct = (mae_l2 - mae_refit) / mae_l2 * 100 if mae_l2 > 0 else 0.0
    return {
        "n_test": n,
        "n_delta_applied": n_delta_applied,
        "mae_l2": mae_l2,
        "mae_refit": mae_refit,
        "improvement_pct": impr_pct,
    }


def main():
    lines = []
    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 92)
    emit("L6 FIX B — REFIT COVE LOOKUP AGAINST L2 BASELINE")
    emit("=" * 92)
    emit(f"Residual = observed − forecast_l2 (positive = L2 under-forecast, needs positive Δ).")
    emit(f"Bin-ship rule: n ≥ {MIN_N_PER_BIN}, |mean| ≥ {MIN_ABS_MEAN}°F, std < {MAX_STD}°F.")
    emit(f"Held-out ship rule: ≥ {MIN_HELDOUT_IMPROVEMENT_PCT}% MAE improvement on last {TEST_WINDOW_DAYS} days.")
    emit("")

    # First pass: find max obs_time to fix the train/test split
    all_rows = []
    max_ts = None
    for obs_time, hour_local, wd_fc, f2, obs in load_pairs():
        dt = parse_iso_date(obs_time)
        if dt is None:
            continue
        if max_ts is None or dt > max_ts:
            max_ts = dt
        all_rows.append((dt, hour_local, wd_fc, f2, obs))

    if not all_rows:
        emit("No qualifying pair rows; aborting.")
        with open(OUT_TXT, "w") as f:
            f.write("\n".join(lines) + "\n")
        return 1

    split_ts = max_ts - timedelta(days=TEST_WINDOW_DAYS)
    emit(f"Latest pair: {max_ts.isoformat()}")
    emit(f"Train/test split at: {split_ts.isoformat()}")
    emit("")

    train_rows = []   # (branch, key, residual)
    test_rows_full = []  # (hour_local, wd_fc, f2, obs)
    for dt, hour_local, wd_fc, f2, obs in all_rows:
        residual = obs - f2
        bk = bin_key(hour_local, wd_fc)
        if bk is None:
            continue
        branch, key = bk
        if dt < split_ts:
            train_rows.append((branch, key, residual))
        else:
            test_rows_full.append((hour_local, wd_fc, f2, obs))

    emit(f"Train rows (fits): {len(train_rows):,}")
    emit(f"Test rows (held-out): {len(test_rows_full):,}")
    emit("")

    delta_by_octant, hour_delta_sb_off, per_bin = fit_tables(train_rows)

    # ---------- Per-bin dump ----------
    emit("-" * 92)
    emit("[A] sb_on × octant bins (S-half sea-breeze warming candidates)")
    emit("-" * 92)
    emit(f"{'octant':<8} {'n':>6} {'mean':>8} {'median':>8} {'std':>8}   {'ship?':<6}")
    for oct_ in OCTANTS:
        s = per_bin.get(("sb_on", oct_))
        if s is None or s["n"] == 0:
            continue
        ship = "★" if (True, oct_) in delta_by_octant else "-"
        emit(f"{oct_:<8} {s['n']:>6,} {s['mean']:>+8.2f} {s['median']:>+8.2f} {s['std']:>8.2f}   {ship:<6}")
    emit("")

    emit("-" * 92)
    emit("[B] sb_off × hour bins (diurnal residual against L2)")
    emit("-" * 92)
    emit(f"{'hour':<6} {'n':>6} {'mean':>8} {'median':>8} {'std':>8}   {'ship?':<6}")
    for h in range(24):
        s = per_bin.get(("sb_off", h))
        if s is None or s["n"] == 0:
            continue
        ship = "★" if h in hour_delta_sb_off else "-"
        emit(f"{h:02d}:00 {s['n']:>6,} {s['mean']:>+8.2f} {s['median']:>+8.2f} {s['std']:>8.2f}   {ship:<6}")
    emit("")

    # ---------- Held-out ----------
    ho = evaluate_heldout(test_rows_full, delta_by_octant, hour_delta_sb_off)
    emit("-" * 92)
    emit(f"[C] Held-out evaluation on last {TEST_WINDOW_DAYS} days")
    emit("-" * 92)
    if ho is None:
        emit("No test rows; verdict INDETERMINATE.")
        ship = False
    else:
        emit(f"n_test               = {ho['n_test']:,}")
        emit(f"n_delta_applied      = {ho['n_delta_applied']:,} "
             f"({100.0*ho['n_delta_applied']/ho['n_test']:.1f}% of test rows)")
        emit(f"MAE L2 alone         = {ho['mae_l2']:.3f}°F")
        emit(f"MAE L2 + refit table = {ho['mae_refit']:.3f}°F")
        emit(f"Improvement          = {ho['improvement_pct']:+.2f}%  "
             f"(ship threshold ≥ {MIN_HELDOUT_IMPROVEMENT_PCT}%)")
        ship = ho['improvement_pct'] >= MIN_HELDOUT_IMPROVEMENT_PCT
    emit("")

    # ---------- Verdict ----------
    emit("=" * 92)
    if ship:
        emit(f"VERDICT: SHIP — refit tables beat L2 alone by "
             f"{ho['improvement_pct']:.2f}% on held-out.")
        emit(f"Next: replace _DELTA_BY_OCTANT and _HOUR_DELTA_SB_OFF in "
             f"weather_collector/processors/cove_correction.py with fitted values,")
        emit(f"remove the unconditional `return 0.0` on the compute path, "
             f"flip ENABLED = True (Lt gate still applies).")
    else:
        emit("VERDICT: HOLD — refit tables did not beat L2 by threshold.")
        emit("Interpretation: L2's Kalman blend is doing enough that no per-regime")
        emit("residual survives the held-out test. Leave cove_correction disabled;")
        emit("the microclimate signal is already captured by station weighting.")
    emit("=" * 92)

    # ---------- Write outputs ----------
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as f:
        f.write("\n".join(lines) + "\n")

    lookup = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "verdict": "SHIP" if ship else "HOLD",
        "delta_by_octant": {
            f"{'True' if sb else 'False'}|{oct_}": v
            for (sb, oct_), v in delta_by_octant.items()
        },
        "hour_delta_sb_off": {str(h): v for h, v in hour_delta_sb_off.items()},
        "held_out": ho,
        "bin_ship_thresholds": {
            "min_n": MIN_N_PER_BIN,
            "min_abs_mean_f": MIN_ABS_MEAN,
            "max_std_f": MAX_STD,
        },
        "heldout_ship_threshold_pct": MIN_HELDOUT_IMPROVEMENT_PCT,
    }
    with open(OUT_JSON, "w") as f:
        json.dump(lookup, f, indent=2)

    sys.stderr.write(f"\nWrote {OUT_TXT}\n")
    sys.stderr.write(f"Wrote {OUT_JSON}\n")
    return 0 if ship else 1


if __name__ == "__main__":
    sys.exit(main())

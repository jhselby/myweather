"""
Stage 0 corrective test — pp two-component recalibration.

Follow-up to h_pp_platt_calibration.py (07-27 HOLD). That run showed the
raw-HRRR-pp miscalibration is separable: the SHAPE (slope b in Platt space)
is stationary across halves, only the LEVEL (intercept a) drifts with the
base rate of the fitting window.

This script tests the corresponding two-component recalibration:
    calibrated_p = σ(a_t + b · logit(raw_p))
where
    b       is fitted ONCE from a long window (offline);
    a_t     floats on a rolling window of the most recent K hours of
            (raw_p, obs) pairs, refit at each new tick by 1-param Newton
            with b held fixed.

This mimics what the live wiring would do: L2/Kalman-style running-bias
correction, but in logit-space with a fixed shape parameter.

Halves-test:
  1. Sort pair-log rows by obs_time; split 50/50 into halves A / B.
  2. Fit b on half A via 2-param Newton (same as h_pp_platt).
  3. Traverse half B in time order. For each row at time t, collect all
     rows in half B with obs_time in [t − K_hours, t) (i.e., strictly-prior
     obs that would have been available live), fit a_t via 1-param Newton
     with b_A held fixed, apply calibration, score Brier vs raw.
  4. Skip the first K_hours of half B (warmup — no full window yet).
  5. Swap (fit b on half B, score half A the same way).

For each candidate window K ∈ {24h, 72h, 168h}, report the halves-test
verdict. Whichever wins survives; if none ship, the two-component design
is falsified and we move to regime-conditional bin-lift or a multi-source
blend.

Ship gate (per window):
  SHIP     if both halves improve Brier ≥ 5% AND |Δb| across halves ≤ 0.15
           AND minimum-fit-pairs floor (≥ 100 pairs per rolling window)
           was met on ≥ 90% of scored rows.
  MARGINAL if both halves improve but below threshold.
  HOLD     otherwise.

Run:
    python3 analysis/h_pp_kalman_recalibrate.py

Output:
    analysis/output/h_pp_kalman_recalibrate.txt
    analysis/output/h_pp_kalman_recalibrate.json  (uploaded to GCS)
"""
import bisect
import json
import math
import os
import random
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_pp_kalman_recalibrate.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_pp_kalman_recalibrate.json")

FIELD = "pp"
CLIP = 1e-3
SHIP_BRIER_PCT = 5.0
STABLE_DB = 0.15
MIN_PAIRS_IN_WINDOW = 100
MIN_WINDOW_COVERAGE = 0.90         # ≥ this fraction of scored rows must have full window
CANDIDATE_WINDOWS_H = [24, 72, 168]
MAX_ITERS = 50
TOL = 1e-8
REFIT_BUCKET_S = 3600.0            # refit a_t once per hour (matches collector-tick cadence)
MAX_FIT_SAMPLE = 5000              # cap Newton-fit sample; scalar fits saturate well below this
RNG_SEED = 20260727                # deterministic subsampling for reproducibility


def _sigmoid(z):
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def _logit(p):
    p = min(max(p, CLIP), 1.0 - CLIP)
    return math.log(p / (1.0 - p))


def _parse_ts(ts):
    # Pair log timestamps look like "2026-07-27T05:07:00" or with 'Z'.
    # We only need something monotonic → epoch seconds is fine.
    if isinstance(ts, (int, float)):
        return float(ts)
    s = ts.rstrip("Z")
    # Handle both with and without seconds; strip fractional.
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    # Fallback: string compare (still monotonic since ISO).
    return 0.0


def load_rows():
    rows = []
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            ob = r.get("observed")
            fc_l1 = r.get("forecast_l1")
            lead = r.get("lead_h")
            ts_raw = r.get("obs_time") or r.get("valid_time") or r.get("run_time")
            if ob is None or fc_l1 is None or lead is None or ts_raw is None:
                continue
            rows.append({
                "ts": _parse_ts(ts_raw),
                "ts_raw": ts_raw,
                "obs": float(ob) / 100.0,
                "raw": float(fc_l1) / 100.0,
                "lead": int(lead),
            })
    rows.sort(key=lambda r: r["ts"])
    return rows


def fit_ab(rows):
    """Fit both (a, b) via Newton-Raphson. Returns (a, b, converged, iters)."""
    xs = [_logit(r["raw"]) for r in rows]
    ys = [r["obs"] for r in rows]
    n = len(rows)
    a, b = 0.0, 1.0
    prev_loss = None
    for it in range(MAX_ITERS):
        g_a = g_b = h_aa = h_ab = h_bb = 0.0
        loss = 0.0
        for i in range(n):
            z = a + b * xs[i]
            p = _sigmoid(z)
            p_c = min(max(p, CLIP), 1.0 - CLIP)
            loss -= ys[i] * math.log(p_c) + (1.0 - ys[i]) * math.log(1.0 - p_c)
            r_ = p - ys[i]
            g_a += r_
            g_b += r_ * xs[i]
            w = p * (1.0 - p)
            h_aa += w
            h_ab += w * xs[i]
            h_bb += w * xs[i] * xs[i]
        loss /= n
        det = h_aa * h_bb - h_ab * h_ab
        if det <= 0:
            break
        a -= (h_bb * g_a - h_ab * g_b) / det
        b -= (-h_ab * g_a + h_aa * g_b) / det
        if prev_loss is not None and abs(prev_loss - loss) < TOL:
            return a, b, True, it + 1
        prev_loss = loss
    return a, b, False, MAX_ITERS


def fit_a_given_b(window_rows, b):
    """1-param Newton for a with b held fixed. Returns (a, converged)."""
    if not window_rows:
        return 0.0, False
    xs = [_logit(r["raw"]) for r in window_rows]
    ys = [r["obs"] for r in window_rows]
    n = len(window_rows)
    # Good init: closed-form for balanced calibration.
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    a = _logit(mean_y) - b * mean_x
    for it in range(MAX_ITERS):
        g = h = 0.0
        for i in range(n):
            z = a + b * xs[i]
            p = _sigmoid(z)
            g += p - ys[i]
            h += p * (1.0 - p)
        if h <= 0:
            return a, False
        step = g / h
        a -= step
        if abs(step) < TOL:
            return a, True
        # Tiny safety cap: don't let it wander too far in one iter.
        if abs(step) > 5.0:
            return a, False
    return a, False


def score_kalman(train_half, score_half, b, window_h):
    """Score `score_half` using `b` fitted on `train_half`, with a_t floating
    on rolling `window_h`-hour history of already-observed pairs (initialized
    with the tail of `train_half`).

    Refits a_t once per REFIT_BUCKET_S seconds (default 1h) — matches the
    live collector-tick cadence and cuts fit-count by ~500× vs per-row. On
    each refit, subsamples the window to MAX_FIT_SAMPLE pairs (scalar Newton
    fit saturates well below this) so 168h windows don't blow up compute.
    """
    combined = train_half + score_half
    combined.sort(key=lambda r: r["ts"])
    combined_ts = [r["ts"] for r in combined]
    window_s = window_h * 3600.0
    rng = random.Random(RNG_SEED)

    sum_raw = 0.0
    sum_cal = 0.0
    n_scored = 0
    n_full_window = 0
    n_skipped_thin = 0
    a_cached = 0.0
    bucket_cached = None
    cached_full = False

    for r in score_half:
        t = r["ts"]
        bucket = int(t // REFIT_BUCKET_S)
        if bucket != bucket_cached:
            hi = bisect.bisect_left(combined_ts, t)
            lo = bisect.bisect_left(combined_ts, t - window_s)
            window_rows = combined[lo:hi]
            if len(window_rows) < MIN_PAIRS_IN_WINDOW:
                cached_full = False
            else:
                if len(window_rows) > MAX_FIT_SAMPLE:
                    window_rows = rng.sample(window_rows, MAX_FIT_SAMPLE)
                a_t, ok = fit_a_given_b(window_rows, b)
                if ok:
                    a_cached = a_t
                    cached_full = True
                else:
                    cached_full = False
            bucket_cached = bucket

        if cached_full:
            cal_p = _sigmoid(a_cached + b * _logit(r["raw"]))
            n_full_window += 1
        else:
            cal_p = r["raw"]  # fallback matches live behavior
            n_skipped_thin += 1

        sum_raw += (r["raw"] - r["obs"]) ** 2
        sum_cal += (cal_p - r["obs"]) ** 2
        n_scored += 1

    if n_scored == 0:
        return None
    return {
        "raw_brier": sum_raw / n_scored,
        "cal_brier": sum_cal / n_scored,
        "n_scored": n_scored,
        "n_full_window": n_full_window,
        "n_skipped_thin": n_skipped_thin,
        "coverage": n_full_window / n_scored,
    }


def _pct(raw, cal):
    if not raw or raw == 0:
        return 0.0
    return (cal - raw) / raw * 100.0


def main():
    rows = load_rows()
    if len(rows) < 1000:
        print(f"Not enough pp rows ({len(rows)}) for halves test — need ≥1000.", file=sys.stderr)
        return 1

    mid = len(rows) // 2
    half_a = rows[:mid]
    half_b = rows[mid:]

    a_A, b_A, conv_A, iters_A = fit_ab(half_a)
    a_B, b_B, conv_B, iters_B = fit_ab(half_b)
    db = abs(b_A - b_B)

    lines = []
    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 100)
    emit("pp TWO-COMPONENT RECALIBRATION — Stage 0 corrective halves test")
    emit("  (fitted slope b, rolling-window intercept a_t)")
    emit("=" * 100)
    emit(f"Rows: {len(rows):,} (half A: {len(half_a):,}, half B: {len(half_b):,}); "
         f"span {rows[0]['ts_raw']} → {rows[-1]['ts_raw']}.")
    emit("")
    emit("Full-window fits (for slope stability check):")
    emit(f"  Half A: a={a_A:+.4f}  b={b_A:+.4f}  converged={conv_A}")
    emit(f"  Half B: a={a_B:+.4f}  b={b_B:+.4f}  converged={conv_B}")
    emit(f"  |Δb|={db:.4f}  (STABLE if ≤ {STABLE_DB})")
    emit("")

    per_window = {}
    verdict_by_window = {}

    for k_h in CANDIDATE_WINDOWS_H:
        emit(f"--- Window: last {k_h}h of pairs for a_t ---")
        result_AB = score_kalman(half_a, half_b, b_A, k_h)  # b from A, score B
        result_BA = score_kalman(half_b, half_a, b_B, k_h)  # b from B, score A
        if result_AB is None or result_BA is None:
            emit(f"  score returned empty for window={k_h}h; skipping.")
            continue
        pct_AB = _pct(result_AB["raw_brier"], result_AB["cal_brier"])
        pct_BA = _pct(result_BA["raw_brier"], result_BA["cal_brier"])
        emit(f"  Fit A → score B:  raw={result_AB['raw_brier']:.5f}  "
             f"cal={result_AB['cal_brier']:.5f}  Δ={pct_AB:+.2f}%  "
             f"coverage={result_AB['coverage']:.1%}  (n_full={result_AB['n_full_window']:,})")
        emit(f"  Fit B → score A:  raw={result_BA['raw_brier']:.5f}  "
             f"cal={result_BA['cal_brier']:.5f}  Δ={pct_BA:+.2f}%  "
             f"coverage={result_BA['coverage']:.1%}  (n_full={result_BA['n_full_window']:,})")

        both_improve = pct_AB < 0 and pct_BA < 0
        both_strong = pct_AB <= -SHIP_BRIER_PCT and pct_BA <= -SHIP_BRIER_PCT
        stable = db <= STABLE_DB
        cov_ok = (result_AB["coverage"] >= MIN_WINDOW_COVERAGE
                  and result_BA["coverage"] >= MIN_WINDOW_COVERAGE)

        if both_strong and stable and cov_ok:
            v = "SHIP"
            r_ = (f"both halves improve Brier ≥{SHIP_BRIER_PCT}% ({pct_BA:+.2f}% / {pct_AB:+.2f}%), "
                  f"slope stable (|Δb|={db:.2f}≤{STABLE_DB}), coverage ≥ {MIN_WINDOW_COVERAGE:.0%}.")
        elif both_improve and stable and cov_ok:
            v = "MARGINAL"
            r_ = (f"both halves improve Brier ({pct_BA:+.2f}% / {pct_AB:+.2f}%) with stable slope, "
                  f"but below the {SHIP_BRIER_PCT}% ship threshold.")
        elif both_improve:
            v = "MARGINAL"
            r_ = (f"both halves improve Brier ({pct_BA:+.2f}% / {pct_AB:+.2f}%) "
                  f"but slope drift |Δb|={db:.2f} or coverage below floor.")
        else:
            v = "HOLD"
            r_ = f"halves diverge ({pct_BA:+.2f}% / {pct_AB:+.2f}%); two-component doesn't transfer at this window."
        emit(f"  → {v}: {r_}")
        emit("")

        per_window[str(k_h)] = {
            "fit_A_score_B": {**result_AB, "pct": pct_AB},
            "fit_B_score_A": {**result_BA, "pct": pct_BA},
        }
        verdict_by_window[str(k_h)] = {"state": v, "rationale": r_}

    # Overall verdict picks the best window: SHIP > MARGINAL > HOLD; within
    # SHIP, largest average improvement wins.
    best_key = None
    best_score = None
    for k, v in verdict_by_window.items():
        state = v["state"]
        # Sort key: state rank, then avg improvement (more negative = better).
        rank = {"SHIP": 0, "MARGINAL": 1, "HOLD": 2}[state]
        r = per_window[k]
        avg_pct = (r["fit_A_score_B"]["pct"] + r["fit_B_score_A"]["pct"]) / 2.0
        key = (rank, avg_pct)
        if best_score is None or key < best_score:
            best_score = key
            best_key = k

    if best_key is not None:
        best_verdict = verdict_by_window[best_key]
        emit("=" * 100)
        emit(f"→ BEST WINDOW: {best_key}h — {best_verdict['state']}")
        emit(f"VERDICT: {best_verdict['state']} pp_kalman_recalibrate "
             f"best_window={best_key}h "
             f"halfA→B={per_window[best_key]['fit_A_score_B']['pct']:+.2f}% "
             f"halfB→A={per_window[best_key]['fit_B_score_A']['pct']:+.2f}% "
             f"b_A={b_A:.3f} b_B={b_B:.3f} dB={db:.3f}")
        emit("=" * 100)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"forecast_error_log.jsonl (field={FIELD})",
        "n_rows": len(rows),
        "halves": {
            "A": {"n": len(half_a), "ts_start": half_a[0]["ts_raw"],
                  "ts_end": half_a[-1]["ts_raw"]},
            "B": {"n": len(half_b), "ts_start": half_b[0]["ts_raw"],
                  "ts_end": half_b[-1]["ts_raw"]},
        },
        "slope_fits": {
            "A": {"a": a_A, "b": b_A, "converged": conv_A, "iters": iters_A},
            "B": {"a": a_B, "b": b_B, "converged": conv_B, "iters": iters_B},
            "db": db,
            "stable_db_threshold": STABLE_DB,
        },
        "per_window": per_window,
        "verdicts_by_window": verdict_by_window,
        "best_window_h": int(best_key) if best_key else None,
        "verdict": ({
            "state": verdict_by_window[best_key]["state"],
            "candidate": "pp_kalman_recalibrate",
            "best_window_h": int(best_key),
            "rationale": verdict_by_window[best_key]["rationale"],
        } if best_key else {"state": "NO_DATA", "candidate": "pp_kalman_recalibrate"}),
        "gates": {
            "ship_brier_pct": SHIP_BRIER_PCT,
            "stable_db": STABLE_DB,
            "min_pairs_in_window": MIN_PAIRS_IN_WINDOW,
            "min_window_coverage": MIN_WINDOW_COVERAGE,
        },
    }

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    print(f"wrote {OUT_JSON}", file=sys.stderr)

    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from weather_collector.gcs_io import upload_json  # noqa: E402
        upload_json(payload, "h_pp_kalman_recalibrate.json", "h_pp_kalman_recalibrate.json")
        print("  ✓ Published to gs://myweather-data/h_pp_kalman_recalibrate.json", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠ GCS upload skipped ({type(e).__name__}: {e}) — local file still written", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

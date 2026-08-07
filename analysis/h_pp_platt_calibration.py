"""
Stage 0 corrective test — pp Platt (logistic) recalibration.

Follow-up to h_pp_bin_calibration.py after that came back HOLD on
07-27 (pooled bin-lift table doesn't transfer across halves because
the base rate is non-stationary within a 30-day retention window).

Platt scaling fits a 2-parameter monotone recalibration
    calibrated_p = σ(a + b · logit(raw_p))
where σ is the sigmoid. Because it has 2 params instead of a 10-bin
lookup, it's far less prone to the base-rate overfit that killed the
bin-lift attempt; it also forces monotonicity by construction (b > 0
recalibrates without changing rank order).

Method:
  1. Load pair-log pp rows sorted by obs_time.
  2. Split 50/50 into halves A / B.
  3. Fit (a, b) on half A via Newton-Raphson on binary log-loss.
  4. Apply (a, b) to half B raw fc; score Brier vs raw baseline.
  5. Swap (fit B, score A).

Promotion verdict:
  SHIP     if both halves improve Brier ≥ SHIP_BRIER_PCT (5%) AND both
           fits give b > 0 with |a_A − a_B| and |b_A − b_B| below the
           stability thresholds — cross-halves parameter agreement.
  MARGINAL if both halves improve but below threshold, or params drift.
  HOLD     otherwise.

Run:
    python3 analysis/h_pp_platt_calibration.py

Output:
    analysis/output/h_pp_platt_calibration.txt
    analysis/output/h_pp_platt_calibration.json (uploaded to GCS)
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402
from _output import out as _out  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = _out("h_pp_platt_calibration.txt")
OUT_JSON = _out("h_pp_platt_calibration.json")

FIELD = "pp"
CLIP = 1e-3                 # keep logit finite
SHIP_BRIER_PCT = 5.0        # both halves must beat raw by this % to SHIP
STABLE_DA = 0.5             # |a_A − a_B| ceiling for SHIP
STABLE_DB = 0.3             # |b_A − b_B| ceiling for SHIP
MAX_ITERS = 50
TOL = 1e-8


def _sigmoid(z):
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def _logit(p):
    p = min(max(p, CLIP), 1.0 - CLIP)
    return math.log(p / (1.0 - p))


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
            ts = r.get("obs_time") or r.get("valid_time") or r.get("run_time")
            if ob is None or fc_l1 is None or lead is None or ts is None:
                continue
            rows.append({
                "ts": ts,
                "obs": float(ob) / 100.0,
                "raw": float(fc_l1) / 100.0,
                "lead": int(lead),
            })
    rows.sort(key=lambda r: r["ts"])
    return rows


def fit_platt(rows):
    """Newton-Raphson on binary log-loss with features [1, logit(raw)].
    Returns (a, b, converged, iters, final_loss)."""
    xs = [_logit(r["raw"]) for r in rows]
    ys = [r["obs"] for r in rows]
    n = len(rows)
    a, b = 0.0, 1.0  # sensible start: identity in logit space
    prev_loss = None
    for it in range(MAX_ITERS):
        # Gradient + Hessian in one pass.
        g_a = 0.0
        g_b = 0.0
        h_aa = 0.0
        h_ab = 0.0
        h_bb = 0.0
        loss = 0.0
        for i in range(n):
            z = a + b * xs[i]
            p = _sigmoid(z)
            # binary cross-entropy
            # -[y log p + (1-y) log(1-p)]
            p_clip = min(max(p, CLIP), 1.0 - CLIP)
            loss -= ys[i] * math.log(p_clip) + (1.0 - ys[i]) * math.log(1.0 - p_clip)
            r = p - ys[i]
            g_a += r
            g_b += r * xs[i]
            w = p * (1.0 - p)
            h_aa += w
            h_ab += w * xs[i]
            h_bb += w * xs[i] * xs[i]
        loss /= n
        # Newton step: [a,b] -= H^-1 g. 2x2 inverse in closed form.
        det = h_aa * h_bb - h_ab * h_ab
        if det <= 0:
            break
        step_a = (h_bb * g_a - h_ab * g_b) / det
        step_b = (-h_ab * g_a + h_aa * g_b) / det
        a -= step_a
        b -= step_b
        if prev_loss is not None and abs(prev_loss - loss) < TOL:
            return a, b, True, it + 1, loss
        prev_loss = loss
    return a, b, False, MAX_ITERS, loss


def apply_and_score(rows, a, b):
    """Apply Platt to raw fc on each row; return (raw_brier, cal_brier, n)."""
    if not rows:
        return None, None, 0
    sum_raw = 0.0
    sum_cal = 0.0
    for r in rows:
        raw_p = r["raw"]
        cal_p = _sigmoid(a + b * _logit(raw_p))
        sum_raw += (raw_p - r["obs"]) ** 2
        sum_cal += (cal_p - r["obs"]) ** 2
    n = len(rows)
    return sum_raw / n, sum_cal / n, n


def _pct(raw, cal):
    if not raw or raw == 0:
        return 0.0
    return (cal - raw) / raw * 100.0


def _sample_curve(a, b, ps=(0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95)):
    """Return the recalibration curve at a handful of raw-probability points.
    Makes the fit's shape human-readable in the digest."""
    return [{"raw": p, "calibrated": round(_sigmoid(a + b * _logit(p)), 4)} for p in ps]


def main():
    rows = load_rows()
    if len(rows) < 1000:
        print(f"Not enough pp rows ({len(rows)}) for halves test — need ≥1000.", file=sys.stderr)
        return 1

    mid = len(rows) // 2
    half_a = rows[:mid]
    half_b = rows[mid:]

    a_A, b_A, conv_A, iters_A, loss_A = fit_platt(half_a)
    a_B, b_B, conv_B, iters_B, loss_B = fit_platt(half_b)

    raw_b, cal_b, n_b = apply_and_score(half_b, a_A, b_A)
    raw_a, cal_a, n_a = apply_and_score(half_a, a_B, b_B)

    pct_b = _pct(raw_b, cal_b)
    pct_a = _pct(raw_a, cal_a)

    lines = []
    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 100)
    emit("pp PLATT (LOGISTIC) RECALIBRATION — Stage 0 corrective halves test")
    emit("=" * 100)
    emit(f"Rows: {len(rows):,} (half A: {len(half_a):,}, half B: {len(half_b):,}); "
         f"span {rows[0]['ts']} → {rows[-1]['ts']}.")
    emit("")
    emit("Fit results (calibrated_p = σ(a + b · logit(raw_p))):")
    emit(f"  Half A: a={a_A:+.4f}  b={b_A:+.4f}  "
         f"converged={conv_A}  iters={iters_A}  log-loss={loss_A:.5f}")
    emit(f"  Half B: a={a_B:+.4f}  b={b_B:+.4f}  "
         f"converged={conv_B}  iters={iters_B}  log-loss={loss_B:.5f}")
    emit(f"  Parameter drift: |Δa|={abs(a_A - a_B):.4f}  |Δb|={abs(b_A - b_B):.4f}")
    emit("")
    emit("Recalibration curve (from half A fit — raw → calibrated):")
    curve = _sample_curve(a_A, b_A)
    emit("  " + " · ".join(f"{c['raw']:.2f}→{c['calibrated']:.3f}" for c in curve))
    emit("")
    emit("Held-out Brier deltas (fit on one half → score on the other):")
    emit(f"  Fit A → score B:  raw={raw_b:.5f}  calibrated={cal_b:.5f}  Δ={pct_b:+.2f}%  (n={n_b:,})")
    emit(f"  Fit B → score A:  raw={raw_a:.5f}  calibrated={cal_a:.5f}  Δ={pct_a:+.2f}%  (n={n_a:,})")
    emit("")

    both_improve = pct_a < 0 and pct_b < 0
    both_strong = pct_a <= -SHIP_BRIER_PCT and pct_b <= -SHIP_BRIER_PCT
    params_stable = (abs(a_A - a_B) <= STABLE_DA and abs(b_A - b_B) <= STABLE_DB
                     and b_A > 0 and b_B > 0)

    if both_strong and params_stable:
        verdict_state = "SHIP"
        rationale = (f"both halves improve Brier ≥{SHIP_BRIER_PCT}% "
                     f"({pct_a:+.2f}% / {pct_b:+.2f}%) AND fitted params agree "
                     f"(|Δa|={abs(a_A - a_B):.2f}≤{STABLE_DA}, "
                     f"|Δb|={abs(b_A - b_B):.2f}≤{STABLE_DB}, both b>0).")
    elif both_improve and params_stable:
        verdict_state = "MARGINAL"
        rationale = (f"both halves improve Brier ({pct_a:+.2f}% / {pct_b:+.2f}%) "
                     f"and params are stable, but below the {SHIP_BRIER_PCT}% ship threshold.")
    elif both_improve:
        verdict_state = "MARGINAL"
        rationale = (f"both halves improve Brier ({pct_a:+.2f}% / {pct_b:+.2f}%) "
                     f"but params drift (|Δa|={abs(a_A - a_B):.2f}, "
                     f"|Δb|={abs(b_A - b_B):.2f}) — recalibration shape not stationary.")
    else:
        verdict_state = "HOLD"
        rationale = (f"halves diverge ({pct_a:+.2f}% / {pct_b:+.2f}%); "
                     f"Platt recalibration does not transfer across halves.")

    emit("=" * 100)
    emit(f"→ {verdict_state}: {rationale}")
    emit(f"VERDICT: {verdict_state} pp_platt_calibration "
         f"halfA→B={pct_b:+.2f}% halfB→A={pct_a:+.2f}% "
         f"dA={abs(a_A - a_B):.2f} dB={abs(b_A - b_B):.2f}")
    emit("=" * 100)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"forecast_error_log.jsonl (field={FIELD})",
        "n_rows": len(rows),
        "halves": {
            "A": {"n": len(half_a), "ts_start": str(half_a[0]["ts"]),
                  "ts_end": str(half_a[-1]["ts"])},
            "B": {"n": len(half_b), "ts_start": str(half_b[0]["ts"]),
                  "ts_end": str(half_b[-1]["ts"])},
        },
        "fit_A": {"a": a_A, "b": b_A, "converged": conv_A,
                  "iters": iters_A, "log_loss": loss_A},
        "fit_B": {"a": a_B, "b": b_B, "converged": conv_B,
                  "iters": iters_B, "log_loss": loss_B},
        "param_drift": {"da": abs(a_A - a_B), "db": abs(b_A - b_B)},
        "recalibration_curve_from_A": curve,
        "brier": {
            "fit_A_score_B": {"raw": raw_b, "calibrated": cal_b, "pct": pct_b, "n": n_b},
            "fit_B_score_A": {"raw": raw_a, "calibrated": cal_a, "pct": pct_a, "n": n_a},
        },
        "gates": {
            "ship_brier_pct": SHIP_BRIER_PCT,
            "stable_da": STABLE_DA,
            "stable_db": STABLE_DB,
        },
        "verdict": {
            "state": verdict_state,
            "candidate": "pp_platt_calibration",
            "rationale": rationale,
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
        upload_json(payload, "h_pp_platt_calibration.json", "h_pp_platt_calibration.json")
        print("  ✓ Published to gs://myweather-data/h_pp_platt_calibration.json", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠ GCS upload skipped ({type(e).__name__}: {e}) — local file still written", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

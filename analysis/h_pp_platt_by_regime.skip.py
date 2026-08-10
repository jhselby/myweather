"""
Stage 0 corrective test — pp Platt recalibration, per synoptic regime.

Booked 2026-07-27 v0.6.382q evening after the source-blend HOLD closed
out the aggregate-recalibration attack surface. Rationale from
[[project_pp_recalibration_session]]:

    "If a future session revisits Reliability-attack candidates, use
    b=0.60 as a fixed prior... and focus the design on making the
    intercept robust to base-rate shifts. Regime-conditional fits (per
    state_fc) are the natural next attempt because within-regime base
    rate is more stable."

The pooled Platt fit (h_pp_platt_calibration.py) HOLD'd with |Δa|
drifting +0.11 vs −0.82 across halves while slope b stayed stable at
|Δb|=0.06 — miscalibration SHAPE is stationary but LEVEL drifts because
the base rate of positives is non-stationary at 30-day scale. This
script tests whether that non-stationarity is regime-driven: if fits
inside each state_fc.regime_synoptic bucket transfer cleanly across
halves, the pooled failure was aggregation over heterogeneous regimes,
not fundamental non-stationarity.

Method:
  1. Load pair-log pp rows; keep those with state_fc.regime_synoptic set.
  2. Bucket by regime.
  3. Within each regime with n ≥ MIN_REGIME_ROWS:
     - split 50/50 by ts into halves
     - fit Platt (a, b) on half A → score half B; swap
     - report per-regime verdict
  4. Aggregate weighted-by-n verdict across all regimes.

Ship conditions per-regime match the pooled script: both halves must
improve Brier ≥ SHIP_BRIER_PCT (5%) AND fitted params must be stable
within that regime (STABLE_DA/STABLE_DB).

Overall SHIP if the weighted-by-n Brier improvement clears ship_pct
AND at least MIN_SHIP_REGIMES regimes hit SHIP individually — that
gates against a single-regime dominating the aggregate.

Run:
    python3 analysis/h_pp_platt_by_regime.py

Output:
    analysis/output/h_pp_platt_by_regime.txt
    analysis/output/h_pp_platt_by_regime.json
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_pp_platt_by_regime.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_pp_platt_by_regime.json")

FIELD = "pp"
CLIP = 1e-3
SHIP_BRIER_PCT = 5.0
STABLE_DA = 0.5
STABLE_DB = 0.3
MIN_REGIME_ROWS = 400  # need enough for halves = 200 each
MIN_SHIP_REGIMES = 3    # aggregate SHIP requires this many per-regime SHIPs
MAX_ITERS = 50
TOL = 1e-8
# Ridge damping — small so it stays near-zero when data is informative,
# but rescues per-regime fits with thin positive counts (same trick as
# h_pp_source_blend.py's collinearity fix).
RIDGE = 1e-3


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
    n_skipped_no_regime = 0
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
            state_fc = r.get("state_fc") or {}
            regime = state_fc.get("regime_synoptic")
            if not regime:
                n_skipped_no_regime += 1
                continue
            rows.append({
                "ts": ts,
                "obs": float(ob) / 100.0,
                "raw": float(fc_l1) / 100.0,
                "lead": int(lead),
                "regime": regime,
            })
    rows.sort(key=lambda r: r["ts"])
    return rows, n_skipped_no_regime


def fit_platt(rows):
    """Newton-Raphson on binary log-loss, features [1, logit(raw)].
    Ridge-damped to survive thin positive-classes in narrow regimes.
    Returns (a, b, converged, iters, final_loss)."""
    xs = [_logit(r["raw"]) for r in rows]
    ys = [r["obs"] for r in rows]
    n = len(rows)
    a, b = 0.0, 1.0
    prev = None
    ridge = RIDGE * n
    for it in range(MAX_ITERS):
        g_a = 0.0
        g_b = 0.0
        h_aa = 0.0
        h_ab = 0.0
        h_bb = 0.0
        loss = 0.0
        for i in range(n):
            z = a + b * xs[i]
            p = _sigmoid(z)
            pc = min(max(p, CLIP), 1.0 - CLIP)
            loss -= ys[i] * math.log(pc) + (1 - ys[i]) * math.log(1 - pc)
            r = p - ys[i]
            g_a += r
            g_b += r * xs[i]
            w = p * (1 - p)
            h_aa += w
            h_ab += w * xs[i]
            h_bb += w * xs[i] * xs[i]
        loss /= n
        h_aa += ridge
        h_bb += ridge
        det = h_aa * h_bb - h_ab * h_ab
        if det <= 0:
            break
        step_a = (h_bb * g_a - h_ab * g_b) / det
        step_b = (-h_ab * g_a + h_aa * g_b) / det
        a -= step_a
        b -= step_b
        if prev is not None and abs(prev - loss) < TOL:
            return a, b, True, it + 1, loss
        prev = loss
    return a, b, False, MAX_ITERS, loss


def apply_and_score(rows, a, b):
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
    if raw is None or cal is None or raw == 0:
        return None
    return (cal - raw) / raw * 100.0


def evaluate_regime(regime, regime_rows):
    """Run halves-test inside one regime. Returns dict with per-regime verdict."""
    mid = len(regime_rows) // 2
    half_a = regime_rows[:mid]
    half_b = regime_rows[mid:]
    a_A, b_A, cA, iA, lA = fit_platt(half_a)
    a_B, b_B, cB, iB, lB = fit_platt(half_b)
    raw_b, cal_b, n_b = apply_and_score(half_b, a_A, b_A)
    raw_a, cal_a, n_a = apply_and_score(half_a, a_B, b_B)
    pct_a = _pct(raw_a, cal_a)
    pct_b = _pct(raw_b, cal_b)

    stable = (abs(a_A - a_B) <= STABLE_DA and abs(b_A - b_B) <= STABLE_DB
              and b_A > 0 and b_B > 0)
    both_improve = pct_a is not None and pct_b is not None and pct_a < 0 and pct_b < 0
    both_strong = pct_a is not None and pct_b is not None and pct_a <= -SHIP_BRIER_PCT and pct_b <= -SHIP_BRIER_PCT

    if both_strong and stable:
        verdict = "SHIP"
    elif both_improve and stable:
        verdict = "MARGINAL_STABLE"
    elif both_improve:
        verdict = "MARGINAL_DRIFT"
    else:
        verdict = "HOLD"

    return {
        "regime": regime,
        "n": len(regime_rows),
        "fit_A": {"a": a_A, "b": b_A, "converged": cA, "iters": iA, "log_loss": lA},
        "fit_B": {"a": a_B, "b": b_B, "converged": cB, "iters": iB, "log_loss": lB},
        "brier": {
            "fit_A_score_B": {"raw": raw_b, "calibrated": cal_b, "pct": pct_b, "n": n_b},
            "fit_B_score_A": {"raw": raw_a, "calibrated": cal_a, "pct": pct_a, "n": n_a},
        },
        "param_drift": {"da": abs(a_A - a_B), "db": abs(b_A - b_B)},
        "verdict": verdict,
    }


def main():
    rows, skipped_no_regime = load_rows()
    if len(rows) < 1000:
        print(f"Not enough pp rows with state_fc.regime_synoptic ({len(rows)}) — "
              f"need ≥1000. Skipped {skipped_no_regime:,} rows without regime.",
              file=sys.stderr)
        return 1

    by_regime = {}
    for r in rows:
        by_regime.setdefault(r["regime"], []).append(r)

    lines = []
    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 100)
    emit("pp PLATT RECALIBRATION — PER REGIME (Stage 0 corrective halves test)")
    emit("=" * 100)
    emit(f"Rows: {len(rows):,} with state_fc.regime_synoptic present; "
         f"{skipped_no_regime:,} pair-log pp rows skipped for missing regime. "
         f"Span {rows[0]['ts']} → {rows[-1]['ts']}. "
         f"Ship: per-regime both halves ≥ {SHIP_BRIER_PCT}% Brier lift + stable params.")
    emit("")

    per_regime = []
    for regime in sorted(by_regime):
        rr = by_regime[regime]
        if len(rr) < MIN_REGIME_ROWS:
            emit(f"  [SKIP] regime={regime:<12s} n={len(rr):>5d} — below {MIN_REGIME_ROWS} threshold.")
            per_regime.append({"regime": regime, "n": len(rr), "verdict": "SKIP_THIN"})
            continue
        result = evaluate_regime(regime, rr)
        per_regime.append(result)

    emit("")
    emit(f"  {'regime':<12s} {'n':>6s} {'a_A':>7s} {'b_A':>6s} {'a_B':>7s} {'b_B':>6s} "
         f"{'|Δa|':>5s} {'|Δb|':>5s} {'pctA→B':>7s} {'pctB→A':>7s}  verdict")
    emit(f"  {'-'*12} {'-'*6} {'-'*7} {'-'*6} {'-'*7} {'-'*6} {'-'*5} {'-'*5} {'-'*7} {'-'*7}  -------")
    for r in per_regime:
        if r["verdict"] == "SKIP_THIN":
            emit(f"  {r['regime']:<12s} {r['n']:>6d} {'—':>7s} {'—':>6s} {'—':>7s} {'—':>6s} "
                 f"{'—':>5s} {'—':>5s} {'—':>7s} {'—':>7s}  {r['verdict']}")
            continue
        pB = r["brier"]["fit_A_score_B"]["pct"]
        pA = r["brier"]["fit_B_score_A"]["pct"]
        emit(f"  {r['regime']:<12s} {r['n']:>6d} "
             f"{r['fit_A']['a']:>+7.3f} {r['fit_A']['b']:>+6.3f} "
             f"{r['fit_B']['a']:>+7.3f} {r['fit_B']['b']:>+6.3f} "
             f"{r['param_drift']['da']:>5.2f} {r['param_drift']['db']:>5.2f} "
             f"{pA:>+7.2f} {pB:>+7.2f}  {r['verdict']}")

    # Aggregate weighted-by-n Brier delta across regimes with real fits
    weighted_num_A = 0.0
    weighted_num_B = 0.0
    weighted_den = 0
    ship_count = 0
    marginal_stable_count = 0
    for r in per_regime:
        if r["verdict"] == "SKIP_THIN":
            continue
        pB = r["brier"]["fit_A_score_B"]["pct"]
        pA = r["brier"]["fit_B_score_A"]["pct"]
        if pA is None or pB is None:
            continue
        n = r["n"]
        weighted_num_A += n * pA
        weighted_num_B += n * pB
        weighted_den += n
        if r["verdict"] == "SHIP":
            ship_count += 1
        elif r["verdict"] == "MARGINAL_STABLE":
            marginal_stable_count += 1

    if weighted_den > 0:
        agg_A = weighted_num_A / weighted_den
        agg_B = weighted_num_B / weighted_den
    else:
        agg_A = agg_B = None

    emit("")
    if agg_A is not None:
        both_agg_ship = agg_A <= -SHIP_BRIER_PCT and agg_B <= -SHIP_BRIER_PCT
        both_agg_improve = agg_A < 0 and agg_B < 0
        if ship_count >= MIN_SHIP_REGIMES and both_agg_ship:
            overall = "SHIP"
            rationale = (f"{ship_count} regime(s) individually SHIP AND weighted-by-n "
                         f"agg Brier lifts {agg_A:+.2f}% / {agg_B:+.2f}% both clear "
                         f"{SHIP_BRIER_PCT}% ship gate.")
        elif ship_count >= 1 and both_agg_improve:
            overall = "MARGINAL"
            rationale = (f"{ship_count} regime(s) SHIP + {marginal_stable_count} "
                         f"MARGINAL_STABLE; weighted-by-n agg {agg_A:+.2f}% / {agg_B:+.2f}% "
                         f"below ship gate but positive-direction signal.")
        elif both_agg_improve:
            overall = "MARGINAL"
            rationale = (f"no per-regime SHIP, but weighted-by-n agg improves "
                         f"({agg_A:+.2f}% / {agg_B:+.2f}%). Recalibration hurts less "
                         f"per-regime than pooled.")
        else:
            overall = "HOLD"
            rationale = (f"weighted-by-n agg {agg_A:+.2f}% / {agg_B:+.2f}% "
                         f"does not improve; regime-conditioning didn't rescue Platt.")
    else:
        overall = "HOLD"
        rationale = "no regime cleared the min-n gate; not enough data."

    emit("=" * 100)
    emit(f"→ {overall}: {rationale}")
    emit(f"VERDICT: {overall} pp_platt_by_regime "
         f"ship={ship_count} marginal_stable={marginal_stable_count} "
         f"agg[A→B={agg_B:+.2f}% B→A={agg_A:+.2f}%]"
         if agg_A is not None
         else f"VERDICT: {overall} pp_platt_by_regime insufficient_data")
    emit("=" * 100)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"forecast_error_log.jsonl (field={FIELD}, state_fc.regime_synoptic bucketed)",
        "n_rows": len(rows),
        "n_skipped_no_regime": skipped_no_regime,
        "per_regime": per_regime,
        "aggregate": {"pct_A": agg_A, "pct_B": agg_B, "n": weighted_den,
                      "ship_count": ship_count,
                      "marginal_stable_count": marginal_stable_count},
        "gates": {
            "ship_brier_pct": SHIP_BRIER_PCT,
            "stable_da": STABLE_DA,
            "stable_db": STABLE_DB,
            "min_regime_rows": MIN_REGIME_ROWS,
            "min_ship_regimes": MIN_SHIP_REGIMES,
            "ridge": RIDGE,
        },
        "verdict": {
            "state": overall,
            "candidate": "pp_platt_by_regime",
            "rationale": rationale,
        },
    }

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)

    return 0


if __name__ == "__main__":
    sys.exit(main())

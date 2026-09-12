"""sr sea_breeze Lsr refit — Stage 1 preview.

Follow-on to v0.6.309 confound diagnostic (`sr_shortwave_cc_confound.py`,
first read 2026-07-11). That read found sea_breeze has Cause B evidence:
in the matched-cc bin (|Δcc|<10) mean signed shortwave error is +83.6 W/m²,
meaning HRRR/GFS over-predicts total shortwave in sea_breeze even when the
cloud forecast is correct. Current Lsr operates on direct_radiation with
regime × hour biases fit against direct_beam observations; the shortwave
overshoot isn't in its cost function.

Stage 1 hypothesis: for sea_breeze rows, replace `Lsr on direct_radiation`
with a per-hour bias-corrected `forecast_shortwave`, and see if that beats
current Production on held-out sea_breeze rows.

Method:
  1. Pull sr pair rows in sea_breeze regime with both direct-radiation
     forecast (via `error_l4` → current Prod) and `forecast_shortwave`.
  2. Split by obs date: earliest 60% = train, latest 40% = test.
  3. On train: fit a per-hour signed-bias table for
     (forecast_shortwave − observed) in sea_breeze at each local hour.
  4. On test: compute two MAEs —
       (a) BASELINE: current Production sr (post-Lsr) MAE
       (b) INTERVENTION: (forecast_shortwave − bias_by_hour) MAE
     If (b) beats (a) by ≥5% AND both halves of train show the effect,
     PROMOTE. Else HOLD.

Note: total-shortwave and direct-beam are DIFFERENT signals (shortwave
includes diffuse). This is not a small-tweak refit of Lsr — it swaps the
source signal for sea_breeze specifically. If Stage 1 promotes, Stage 2
adds the (regime × hour) cross-cut and per-cell verification the ship
gate requires.

Run:
    python3 analysis/sr_sea_breeze_lsr_refit_stage1.py

Output:
    analysis/output/sr_sea_breeze_lsr_refit_stage1.txt
    analysis/output/sr_sea_breeze_lsr_refit_stage1.json
"""
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "sr_sea_breeze_lsr_refit_stage1.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "sr_sea_breeze_lsr_refit_stage1.json")

REGIME = "sea_breeze"
TRAIN_FRAC = 0.6
MIN_N_PER_HOUR = 15   # skip hour cells with too few train pairs → fall back to overall mean
MIN_N_TEST = 200      # ship-gate floor for the held-out comparison
MIN_HALVES_HITS = 2   # both training halves must show improvement
PROMOTE_PCT = 5.0     # held-out ≥5% MAE improvement to promote


def load_rows():
    """Yield dicts with obs_date, hour, obs, fc_prod, fc_shortwave for sea_breeze sr rows."""
    rows = []
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != "sr":
                continue
            state_obs = r.get("state_obs") or {}
            if state_obs.get("regime_synoptic") != REGIME:
                continue
            obs = r.get("observed")
            fc_prod = r.get("forecast_l4")  # current production sr (post-Lsr)
            fc_sw = r.get("forecast_shortwave")  # shadow-logged since v0.6.309
            vt = r.get("valid_time")
            if obs is None or fc_prod is None or fc_sw is None or not vt:
                continue
            try:
                dt = datetime.fromisoformat(vt)
            except ValueError:
                continue
            rows.append({
                "obs_date": dt.date().isoformat(),
                "hour": dt.hour,
                "obs": float(obs),
                "fc_prod": float(fc_prod),
                "fc_sw": float(fc_sw),
            })
    rows.sort(key=lambda r: r["obs_date"])
    return rows


def fit_hourly_bias(train_rows):
    """Return {hour: mean(fc_sw - obs)} for hours with ≥MIN_N_PER_HOUR pairs.
    Also return overall_mean as the fallback for thin hours."""
    per_hour = defaultdict(list)
    all_biases = []
    for r in train_rows:
        b = r["fc_sw"] - r["obs"]
        per_hour[r["hour"]].append(b)
        all_biases.append(b)
    hourly = {h: statistics.mean(xs) for h, xs in per_hour.items() if len(xs) >= MIN_N_PER_HOUR}
    overall = statistics.mean(all_biases) if all_biases else 0.0
    return hourly, overall, {h: len(xs) for h, xs in per_hour.items()}


def corrected_sw(row, hourly_bias, overall_bias):
    b = hourly_bias.get(row["hour"], overall_bias)
    return row["fc_sw"] - b


def mae(errs):
    return sum(abs(x) for x in errs) / len(errs) if errs else float("nan")


def main():
    lines = []

    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 96)
    emit(f"sr {REGIME} Lsr refit — Stage 1 preview (v0.6.309 shortwave shadow log)")
    emit("=" * 96)
    emit("Baseline = current Production sr (post-Lsr on direct_radiation).")
    emit("Intervention = forecast_shortwave minus per-hour signed bias (fit on train).")
    emit(f"Split: earliest {int(TRAIN_FRAC*100)}% of {REGIME} rows = train, latest {int((1-TRAIN_FRAC)*100)}% = test.")
    emit(f"Ship-gate: test MAE improvement ≥ {PROMOTE_PCT}% AND both training halves confirm.")
    emit("")

    rows = load_rows()
    n = len(rows)
    if n < MIN_N_TEST + 100:
        emit(f"INSUFFICIENT DATA — only {n} {REGIME} sr rows with shortwave forecast.")
        emit(f"Need at least {MIN_N_TEST + 100}. v0.6.309 shortwave shadow log started 2026-07-06;")
        emit(f"sea_breeze regime firing is intermittent so accumulation is slow. Re-run in a week.")
        _write(lines, verdict="INSUFFICIENT", n=n, extra={})
        return 0

    split = int(n * TRAIN_FRAC)
    train = rows[:split]
    test = rows[split:]
    train_date_range = (train[0]["obs_date"], train[-1]["obs_date"])
    test_date_range = (test[0]["obs_date"], test[-1]["obs_date"])
    emit(f"n total: {n:,}   train: {len(train):,} ({train_date_range[0]} → {train_date_range[1]})   "
         f"test: {len(test):,} ({test_date_range[0]} → {test_date_range[1]})")
    emit("")

    # Fit on full train
    hourly_bias, overall_bias, hour_counts = fit_hourly_bias(train)
    emit("Fitted per-hour bias (fc_shortwave − obs) on train:")
    emit(f"  {'hour':>4}  {'n_train':>8}  {'bias W/m²':>12}  {'fitted?':>10}")
    for h in sorted(hour_counts):
        used = "hourly" if h in hourly_bias else f"fallback ({overall_bias:+.1f})"
        b = hourly_bias.get(h, overall_bias)
        emit(f"  {h:>4d}  {hour_counts[h]:>8,}  {b:>+12.2f}  {used:>10}")
    emit(f"  overall bias fallback: {overall_bias:+.2f} W/m²  (used for hours with <{MIN_N_PER_HOUR} train pairs)")
    emit("")

    # Evaluate on test
    baseline_errs = [r["fc_prod"] - r["obs"] for r in test]
    intervention_errs = [corrected_sw(r, hourly_bias, overall_bias) - r["obs"] for r in test]
    baseline_mae = mae(baseline_errs)
    intervention_mae = mae(intervention_errs)
    delta_pct = 100.0 * (baseline_mae - intervention_mae) / baseline_mae if baseline_mae else 0.0

    emit("HELD-OUT COMPARISON")
    emit(f"  {'baseline (current Prod)':<32} MAE = {baseline_mae:>8.2f} W/m²")
    emit(f"  {'intervention (fc_sw + bias)':<32} MAE = {intervention_mae:>8.2f} W/m²")
    emit(f"  {'improvement':<32}       {delta_pct:>+7.2f}%")
    emit("")

    # Halves check on train — fit on train_A, evaluate on train_B and vice versa,
    # both must beat baseline for stability.
    half = len(train) // 2
    train_a, train_b = train[:half], train[half:]
    halves_hits = 0
    halves_lines = []
    for label, fit_set, eval_set in (("A→B", train_a, train_b), ("B→A", train_b, train_a)):
        h_bias, o_bias, _ = fit_hourly_bias(fit_set)
        b_errs = [r["fc_prod"] - r["obs"] for r in eval_set]
        i_errs = [corrected_sw(r, h_bias, o_bias) - r["obs"] for r in eval_set]
        b_m = mae(b_errs)
        i_m = mae(i_errs)
        d = 100.0 * (b_m - i_m) / b_m if b_m else 0.0
        halves_lines.append(f"  half {label}:  baseline MAE {b_m:.2f}   intervention MAE {i_m:.2f}   Δ {d:+.2f}%")
        if d > 0:
            halves_hits += 1
    emit("HALVES CHECK (stability)")
    for hl in halves_lines:
        emit(hl)
    emit(f"  hits: {halves_hits}/2   (need {MIN_HALVES_HITS})")
    emit("")

    # Verdict
    if len(test) < MIN_N_TEST:
        verdict = "THIN"
        note = f"test n={len(test)} < {MIN_N_TEST}"
    elif delta_pct >= PROMOTE_PCT and halves_hits >= MIN_HALVES_HITS:
        verdict = "PROMOTE"
        note = f"test Δ +{delta_pct:.2f}% + both halves confirm → Stage 2"
    elif delta_pct >= PROMOTE_PCT and halves_hits < MIN_HALVES_HITS:
        verdict = "MARGINAL"
        note = f"test Δ +{delta_pct:.2f}% but only {halves_hits}/2 halves confirm — re-run after window rolls"
    elif delta_pct > 0:
        verdict = "HOLD"
        note = f"test Δ +{delta_pct:.2f}% below {PROMOTE_PCT}% floor"
    else:
        verdict = "KILL"
        note = f"test Δ {delta_pct:+.2f}% — intervention loses; direct_radiation + Lsr already better on sea_breeze"

    emit("=" * 96)
    emit(f"VERDICT: {verdict}")
    emit(f"  {note}")
    emit("=" * 96)

    _write(lines, verdict=verdict, n=n, extra={
        "delta_pct": round(delta_pct, 2),
        "baseline_mae": round(baseline_mae, 2),
        "intervention_mae": round(intervention_mae, 2),
        "halves_hits": halves_hits,
        "train_n": len(train),
        "test_n": len(test),
        "train_dates": list(train_date_range),
        "test_dates": list(test_date_range),
        "hourly_bias": {str(h): round(b, 2) for h, b in hourly_bias.items()},
        "overall_bias": round(overall_bias, 2),
    })
    return 0


def _write(lines, verdict, n, extra):
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    payload = {
        "regime": REGIME,
        "verdict": verdict,
        "n_total": n,
        **extra,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {OUT_TXT}")
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    sys.exit(main())

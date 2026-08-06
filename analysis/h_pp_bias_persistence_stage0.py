"""
pp bias-persistence Stage 0 — feasibility check for an antecedent-error
specialist on precipitation probability.

Same template as the dpbp/wsbp Stage 0 arc that produced dp_bias_persistence
(LIVE 2026-08-04). Question: does last-24h pp forecast bias, per regime,
predict next-24h pp bias? If yes in some regime, ppbp is a viable
correction candidate — the same antecedent-error mechanism that succeeded
where fixed-effect Platt / bin-lift / per-regime Platt kept HOLDing.

pp obs is BINARY (0 = dry hour, 1 = wet hour), so:
  bias per hour = fc_prob − obs_binary
  daily bias = mean of hourly bias over a calendar day, per regime
  persistence = lag-1 autocorrelation of daily bias per regime

Kill / promote decision:
  KILL     — no regime shows lag-1 r ≥ 0.35 AND |mean_daily_bias| ≥ 0.10
  PROMOTE  — at least one regime meets both thresholds. Advance to Stage 1
             halves-verify with that regime as focus candidate.

Zero production risk — read-only against pair log.

Run:
    python3 -m analysis.h_pp_bias_persistence_stage0

Output:
    analysis/output/h_pp_bias_persistence_stage0.txt
    analysis/output/h_pp_bias_persistence_stage0.json
"""
import json
import math
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_pp_bias_persistence_stage0.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_pp_bias_persistence_stage0.json")

FIELD = "pp"

# Gates — mirror dpbp Stage 0 magnitudes.
MIN_DAYS_PER_REGIME = 5
MIN_ROWS_PER_DAY = 8           # min pair-log rows/day to trust a daily mean
LAG1_R_PROMOTE = 0.35          # lag-1 daily bias autocorrelation threshold
MEAN_BIAS_PROMOTE = 0.10       # 10 percentage points

# Lead scope — skip nowcasts (specialist would fire at lead ≥ 6h to match dpbp/wsbp).
MIN_LEAD = 6


def _pearson(xs, ys):
    if len(xs) < 3:
        return None
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx2 = sum((x - mx) ** 2 for x in xs)
    dy2 = sum((y - my) ** 2 for y in ys)
    denom = math.sqrt(dx2 * dy2)
    if denom == 0:
        return None
    return num / denom


def load_rows():
    """Return list of dicts with: date, regime, bias (fc - obs)."""
    rows = []
    n_pp = 0
    n_kept = 0
    n_skipped_no_regime = 0
    n_skipped_short_lead = 0
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            n_pp += 1
            fc = r.get("forecast_l1")
            if fc is None:
                fc = r.get("forecast")
            obs = r.get("observed")
            vt = r.get("valid_time")
            lead = r.get("lead_h")
            if fc is None or obs is None or vt is None or lead is None:
                continue
            if lead < MIN_LEAD:
                n_skipped_short_lead += 1
                continue
            state_fc = r.get("state_fc") or {}
            regime = state_fc.get("regime_synoptic")
            if not regime:
                n_skipped_no_regime += 1
                continue
            fc_p = max(0.0, min(1.0, float(fc) / 100.0))
            obs_p = 1.0 if float(obs) > 0 else 0.0
            date = vt[:10] if len(vt) >= 10 else None
            if date is None:
                continue
            rows.append({"date": date, "regime": regime, "bias": fc_p - obs_p})
            n_kept += 1
    stats = {
        "pp_rows_total": n_pp,
        "kept_after_filters": n_kept,
        "skipped_no_regime": n_skipped_no_regime,
        "skipped_short_lead": n_skipped_short_lead,
    }
    return rows, stats


def compute_daily_by_regime(rows):
    """Return {regime: [(date, mean_bias, n), ...]} sorted by date, filtered to MIN_ROWS_PER_DAY."""
    by_rd = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_rd[r["regime"]][r["date"]].append(r["bias"])
    out = {}
    for regime, day_map in by_rd.items():
        daily = []
        for date in sorted(day_map.keys()):
            biases = day_map[date]
            if len(biases) < MIN_ROWS_PER_DAY:
                continue
            daily.append((date, sum(biases) / len(biases), len(biases)))
        if len(daily) >= MIN_DAYS_PER_REGIME:
            out[regime] = daily
    return out


def analyze_regime(daily):
    """Return dict with n_days, mean_bias, abs_mean_bias, lag1_r, n_pairs, verdict."""
    biases = [b for _, b, _ in daily]
    n_days = len(daily)
    mean_bias = sum(biases) / n_days
    abs_mean = abs(mean_bias)
    # Lag-1 autocorrelation only on consecutive-date pairs (skip if any date-gap in sequence).
    lag_xs, lag_ys = [], []
    from datetime import datetime as _dt, timedelta as _td
    for i in range(1, n_days):
        d_prev = _dt.strptime(daily[i - 1][0], "%Y-%m-%d")
        d_curr = _dt.strptime(daily[i][0], "%Y-%m-%d")
        if d_curr - d_prev == _td(days=1):
            lag_xs.append(daily[i - 1][1])
            lag_ys.append(daily[i][1])
    lag1 = _pearson(lag_xs, lag_ys)
    verdict = "SKIP"
    if lag1 is not None and lag1 >= LAG1_R_PROMOTE and abs_mean >= MEAN_BIAS_PROMOTE:
        verdict = "PROMOTE"
    elif lag1 is not None and lag1 >= LAG1_R_PROMOTE:
        verdict = "PERSISTENT-BUT-SMALL"
    elif abs_mean >= MEAN_BIAS_PROMOTE:
        verdict = "BIASED-BUT-NON-PERSISTENT"
    return {
        "n_days": n_days,
        "mean_bias": round(mean_bias, 4),
        "abs_mean_bias": round(abs_mean, 4),
        "lag1_r": round(lag1, 3) if lag1 is not None else None,
        "n_lag_pairs": len(lag_xs),
        "verdict": verdict,
    }


def main():
    rows, stats = load_rows()
    daily_by_regime = compute_daily_by_regime(rows)

    per_regime = {}
    for regime, daily in daily_by_regime.items():
        per_regime[regime] = analyze_regime(daily)

    promote = [r for r, a in per_regime.items() if a["verdict"] == "PROMOTE"]
    overall_verdict = "PROMOTE" if promote else "KILL"

    # ── Text output ─────────────────────────────────────────────────────
    lines = []
    lines.append("=" * 100)
    lines.append("pp BIAS-PERSISTENCE STAGE 0 — feasibility of an antecedent-error specialist for pp")
    lines.append("=" * 100)
    lines.append(f"Field: {FIELD}   Lead scope: ≥ {MIN_LEAD}h   Bias = fc_prob − obs_binary")
    lines.append(f"Promote gate: any regime with lag-1 r ≥ {LAG1_R_PROMOTE:+.2f} AND |mean_daily_bias| ≥ {MEAN_BIAS_PROMOTE:.2f}")
    lines.append("")
    lines.append(f"Rows scanned      : {stats['pp_rows_total']:,}")
    lines.append(f"Kept after filters: {stats['kept_after_filters']:,}")
    lines.append(f"Skipped short-lead: {stats['skipped_short_lead']:,}")
    lines.append(f"Skipped no-regime : {stats['skipped_no_regime']:,}")
    lines.append(f"Regimes with ≥ {MIN_DAYS_PER_REGIME} days: {len(per_regime)}")
    lines.append("")
    hdr = f"{'regime':<14}{'n_days':>7}{'mean_bias':>12}{'|mean|':>10}{'lag1_r':>10}{'n_pairs':>9}  verdict"
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for regime in sorted(per_regime.keys()):
        a = per_regime[regime]
        lag1_s = f"{a['lag1_r']:+.3f}" if a["lag1_r"] is not None else "  --"
        mark = " ★" if a["verdict"] == "PROMOTE" else ""
        lines.append(
            f"{regime:<14}{a['n_days']:>7}{a['mean_bias']:>+12.4f}{a['abs_mean_bias']:>10.4f}"
            f"{lag1_s:>10}{a['n_lag_pairs']:>9}  {a['verdict']}{mark}"
        )
    lines.append("")
    lines.append("=" * 100)
    if overall_verdict == "PROMOTE":
        promote_str = ", ".join(sorted(promote))
        lines.append(f"VERDICT: PROMOTE — {len(promote)} regime(s) meet feasibility gates: {promote_str}")
        lines.append("Next: h_pp_bias_persistence_stage1.py (halves-verify Brier lift on these regimes)")
    else:
        lines.append("VERDICT: KILL — no regime shows persistent-and-material pp bias.")
        lines.append(f"Gates: lag-1 r ≥ {LAG1_R_PROMOTE:+.2f} AND |mean_daily_bias| ≥ {MEAN_BIAS_PROMOTE:.2f}")
        lines.append("Interpretation: antecedent-error mechanism doesn't apply to pp — bias is either")
        lines.append("small or non-persistent day-to-day. Fixed-effect Platt/bin-lift already HOLDs,")
        lines.append("so this closes the calibration correction workstream for pp.")
    lines.append("=" * 100)

    txt = "\n".join(lines)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(txt + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump({
            "stats": stats,
            "per_regime": per_regime,
            "promote_regimes": promote,
            "overall_verdict": overall_verdict,
            "gates": {
                "lag1_r_promote": LAG1_R_PROMOTE,
                "mean_bias_promote": MEAN_BIAS_PROMOTE,
                "min_lead": MIN_LEAD,
                "min_rows_per_day": MIN_ROWS_PER_DAY,
                "min_days_per_regime": MIN_DAYS_PER_REGIME,
            },
        }, fh, indent=2)
    print(txt)
    print(f"\nwrote {OUT_TXT}")
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()

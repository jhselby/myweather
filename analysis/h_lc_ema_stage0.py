"""Stage 0 — EMA/Kalman shift tracker as Lc fallback, per field.

Motivated by 2026-07-30 cl kill + 2026-08-14 un-skip investigation. Current
Lc uses a 30d rolling shift table refit once per day per (field, bin). When
HRRR's bias distribution shifts materially (07-30 cl overcast episode),
the table lags — the fixed-window rolling-window sweep (`h_lc_rolling_window`)
shows no window length recovers cl on last-14d hold-out.

Hypothesis: replace the fixed table with a per-(field, bin) exponentially-
weighted-moving-average of (forecast_l4 - obs). Update online after every
new obs; apply the current EMA as the shift on future forecasts. Warm-up
before applying. α controls responsiveness vs stability.

Stage 0 question: does ANY α make EMA-Lc beat raw on 14d held-out for cl
without wrecking cc/cm/ch (fields currently in a good place)?

Method:
  - Walk pair log chronologically by obs_time.
  - Per (field, bin): maintain EMA of (fc_l4 - obs). Warm-up MIN_WARMUP obs
    before applying (avoids first-shift noise).
  - Corrected forecast for scoring: fc_l4 - EMA[(field, bin)]  (subtract
    because EMA is the bias; corrected = fc - bias).
  - Score |corrected - obs| across the last HELD_OUT_DAYS days.
  - Compare to raw L2 |error_l2| across the same rows.
  - Sweep α ∈ ALPHAS.

Verdict:
  STAGE 0 HIT  — some α wins for cl (≥+2% vs raw on 14d) AND doesn't hurt
                 cc/cm/ch by more than 3% vs their current pooled Lc.
  MIXED        — cl improves but at cost to another field.
  MISS         — no α clears the cl bar.

Run:
    python3 -m analysis.h_lc_ema_stage0
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402
from _prod import prod_error  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_lc_ema_stage0.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_lc_ema_stage0.json")

FIELDS = ("cc", "cl", "cm", "ch")

BINS = [(0, 5, "0-5"), (5, 20, "5-20"), (20, 50, "20-50"),
        (50, 80, "50-80"), (80, 95, "80-95"), (95, 100.01, "95-100")]

ALPHAS = (0.01, 0.02, 0.05, 0.10, 0.20)
HELD_OUT_DAYS = 14
MIN_WARMUP = 20  # obs per (field, bin) before EMA is trusted
CL_WIN_FLOOR_PCT = 2.0
OTHER_HURT_CAP_PCT = 3.0


def _bin_of(v):
    for lo, hi, lab in BINS:
        if lo <= v < hi:
            return lab
    return None


def _load_rows():
    """Return chronologically-sorted list of (obs_time, field, bin, fc_l4, obs, err_l2).
    Only rows with forecast_l4 + observed + a bin match."""
    rows = []
    with open(cached_path(PAIR_LOG_URL)) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            fld = r.get("field")
            if fld not in FIELDS:
                continue
            ot = r.get("obs_time")
            fc_l4 = r.get("forecast_l4")
            obs = r.get("observed")
            if not (ot and fc_l4 is not None and obs is not None):
                continue
            b = _bin_of(fc_l4)
            if b is None:
                continue
            err_l2 = r.get("error_l2")
            err_prod = prod_error(r)
            rows.append((ot, fld, b, float(fc_l4), float(obs), err_l2, err_prod))
    rows.sort(key=lambda x: x[0])
    return rows


def _simulate(rows, alpha, cutoff_ot):
    """Walk rows chronologically. Maintain EMA per (field, bin) of (fc_l4 - obs).

    Two-phase per obs_time to avoid leakage from repeated-obs updates:
      1. SCORE — apply the pre-obs-time EMA snapshot to every row of this
         obs_time. Score |corrected - obs|.
      2. UPDATE — after all rows for this obs_time are scored, update the
         EMA once per (field, bin) with the mean residual across the rows
         that fell in that (field, bin).

    Without the two-phase split, the second-through-Nth rows for a given
    (field, bin, obs_time) would each see the EMA update with the same obs,
    and by the 20th row the EMA has effectively memorized obs — the "gain"
    over raw is persistence leakage, not forecast skill.

    Warm up MIN_WARMUP obs-count per (field, bin) before applying. Score
    rows on/after cutoff_ot as held-out.

    Returns per-field {n, mae_ema, mae_raw_l2, mae_prod_live}. mae_raw_l2 =
    average |error_l2| on held-out rows (what cl would see if we removed
    the field-skip and Lc did nothing). mae_prod_live = average of the row's
    actual production error (what live production shipped)."""
    ema = defaultdict(float)   # (field, bin) -> current EMA
    n_updates = defaultdict(int)  # (field, bin) -> update count (for warm-up)
    out = {f: {"n": 0, "sum_ema": 0.0, "sum_raw_l2": 0.0, "sum_prod_live": 0.0,
               "n_warmed": 0} for f in FIELDS}

    # Group rows by obs_time (already sorted, so walk contiguously)
    i = 0
    N = len(rows)
    while i < N:
        j = i
        cur_ot = rows[i][0]
        while j < N and rows[j][0] == cur_ot:
            j += 1
        batch = rows[i:j]
        i = j

        # Phase 1: score using pre-batch EMA snapshot
        # Also accumulate per-(field, bin) residuals for phase 2 update
        residual_bucket = defaultdict(list)  # (field, bin) -> [residuals]
        for ot, fld, b, fc_l4, obs, err_l2, err_prod in batch:
            key = (fld, b)
            warm = n_updates[key] >= MIN_WARMUP
            if ot >= cutoff_ot:
                out[fld]["n"] += 1
                if warm:
                    corrected = fc_l4 - ema[key]
                    out[fld]["sum_ema"] += abs(corrected - obs)
                    out[fld]["n_warmed"] += 1
                else:
                    out[fld]["sum_ema"] += abs(fc_l4 - obs)
                if err_l2 is not None:
                    out[fld]["sum_raw_l2"] += abs(float(err_l2))
                if err_prod is not None:
                    out[fld]["sum_prod_live"] += abs(float(err_prod))
            residual_bucket[key].append(fc_l4 - obs)

        # Phase 2: single EMA update per (field, bin), using batch mean residual
        for key, residuals in residual_bucket.items():
            r_bar = sum(residuals) / len(residuals)
            if n_updates[key] == 0:
                ema[key] = r_bar
            else:
                ema[key] = (1 - alpha) * ema[key] + alpha * r_bar
            n_updates[key] += 1

    result = {}
    for f in FIELDS:
        n = out[f]["n"]
        if n == 0:
            result[f] = None
            continue
        result[f] = {
            "n": n,
            "n_warmed": out[f]["n_warmed"],
            "mae_ema": out[f]["sum_ema"] / n,
            "mae_raw_l2": out[f]["sum_raw_l2"] / n,
            "mae_prod_live": out[f]["sum_prod_live"] / n,
        }
    return result


def main():
    rows = _load_rows()
    if not rows:
        print("no rows")
        return

    max_ot = rows[-1][0]
    max_dt = datetime.fromisoformat(max_ot[:19])
    cutoff_dt = max_dt - timedelta(days=HELD_OUT_DAYS)
    cutoff_ot = cutoff_dt.isoformat(timespec="minutes")

    lines = []
    def p(s): lines.append(s); print(s)

    p(f"h_lc_ema_stage0 — EMA/Kalman shift tracker on Lc-eligible fields")
    p(f"Pair log rows loaded: {len(rows):,}   ({rows[0][0]} → {rows[-1][0]})")
    p(f"Held-out window: {cutoff_ot} → {max_ot}  ({HELD_OUT_DAYS}d)")
    p(f"Alpha sweep: {ALPHAS}")
    p(f"Warm-up per (field, bin): {MIN_WARMUP} obs")
    p("")

    all_results = {}
    for alpha in ALPHAS:
        r = _simulate(rows, alpha, cutoff_ot)
        all_results[alpha] = r

    # Halves-stability: split held-out into A (first 7d) / B (last 7d)
    mid_dt = cutoff_dt + timedelta(days=HELD_OUT_DAYS / 2)
    mid_ot = mid_dt.isoformat(timespec="minutes")
    halves = {}  # alpha -> {"A": per_field, "B": per_field}
    for alpha in ALPHAS:
        half_a = _simulate([r for r in rows if r[0] < mid_ot], alpha, cutoff_ot)
        half_b = _simulate(rows, alpha, mid_ot)
        halves[alpha] = {"A": half_a, "B": half_b}

    # Header
    p(f"{'field':<6}{'n':>7}{'raw L2':>10}{'prod live':>11}" +
      "".join(f"{'α='+str(a):>10}" for a in ALPHAS))
    p("-" * (6 + 7 + 10 + 11 + 10 * len(ALPHAS)))
    for f in FIELDS:
        base = all_results[ALPHAS[0]][f]
        if base is None:
            p(f"{f:<6}  (no held-out rows)")
            continue
        raw = base["mae_raw_l2"]
        prod = base["mae_prod_live"]
        row = f"{f:<6}{base['n']:>7}{raw:>10.3f}{prod:>11.3f}"
        for a in ALPHAS:
            ema = all_results[a][f]["mae_ema"]
            row += f"{ema:>10.3f}"
        p(row)
    p("")

    # Improvement vs raw L2 (positive = EMA better than raw)
    p(f"{'field':<6}   Δ vs raw L2 (positive = EMA improves)  |  Δ vs live prod")
    p("-" * 80)
    for f in FIELDS:
        base = all_results[ALPHAS[0]][f]
        if base is None:
            continue
        raw = base["mae_raw_l2"]
        prod = base["mae_prod_live"]
        deltas_raw = []
        deltas_prod = []
        for a in ALPHAS:
            ema = all_results[a][f]["mae_ema"]
            d_raw = (raw - ema) / raw * 100 if raw > 0 else 0
            d_prod = (prod - ema) / prod * 100 if prod > 0 else 0
            deltas_raw.append((a, d_raw))
            deltas_prod.append((a, d_prod))
        row_r = "  ".join(f"α{a}:{d:+5.1f}%" for a, d in deltas_raw)
        row_p = "  ".join(f"α{a}:{d:+5.1f}%" for a, d in deltas_prod)
        p(f"{f:<6} vs raw:  {row_r}")
        p(f"       vs prod: {row_p}")
    p("")

    # Halves stability (best-α per field)
    p(f"Halves stability at α=0.2 (Δ vs raw L2, positive = EMA improves):")
    p(f"  {'field':<6}{'half A n':>10}{'A Δ%':>10}{'half B n':>10}{'B Δ%':>10}   stable?")
    p("-" * 70)
    for f in FIELDS:
        a_res = halves[0.20]["A"][f]
        b_res = halves[0.20]["B"][f]
        if a_res is None or b_res is None or a_res["mae_raw_l2"] == 0 or b_res["mae_raw_l2"] == 0:
            continue
        a_d = (a_res["mae_raw_l2"] - a_res["mae_ema"]) / a_res["mae_raw_l2"] * 100
        b_d = (b_res["mae_raw_l2"] - b_res["mae_ema"]) / b_res["mae_raw_l2"] * 100
        stable = "STABLE ★" if (a_d > 0 and b_d > 0) else "UNSTABLE"
        p(f"  {f:<6}{a_res['n']:>10}{a_d:>+10.1f}{b_res['n']:>10}{b_d:>+10.1f}   {stable}")
    p("")

    # Verdict on cl
    cl = all_results[ALPHAS[0]]["cl"]
    if cl is None:
        p("VERDICT: NO DATA — cl has no held-out rows.")
    else:
        raw = cl["mae_raw_l2"]
        cl_wins = []
        for a in ALPHAS:
            ema = all_results[a]["cl"]["mae_ema"]
            d = (raw - ema) / raw * 100 if raw > 0 else 0
            if d >= CL_WIN_FLOOR_PCT:
                cl_wins.append((a, d))
        cl_wins.sort(key=lambda x: -x[1])

        # Check other fields don't regress vs their live prod under best cl α
        harm = []
        if cl_wins:
            best_a = cl_wins[0][0]
            for f in ("cc", "cm", "ch"):
                r = all_results[best_a][f]
                if r is None: continue
                prod = r["mae_prod_live"]
                ema = r["mae_ema"]
                d = (prod - ema) / prod * 100 if prod > 0 else 0
                # Negative d = EMA worse than live prod
                if d < -OTHER_HURT_CAP_PCT:
                    harm.append((f, d))

        if not cl_wins:
            p(f"VERDICT: MISS — no α beats raw for cl by {CL_WIN_FLOOR_PCT}%+ on {HELD_OUT_DAYS}d held-out. "
              f"EMA/Kalman fallback does NOT rescue cl at this level; either wider hyperparameter "
              f"sweep needed or the shift-table architecture itself is wrong for cl. Consider "
              f"regime-conditional EMA (per-regime per-bin) as Stage 0 followup.")
        elif harm:
            best_a, best_d = cl_wins[0]
            harm_s = ", ".join(f"{f}={d:+.1f}%" for f, d in harm)
            p(f"VERDICT: MIXED — best cl α={best_a} improves +{best_d:.1f}% vs raw, but hurts other "
              f"fields vs live prod: {harm_s}. Per-field α tuning may be needed.")
        else:
            best_a, best_d = cl_wins[0]
            other = ", ".join(
                f"{f}:{(all_results[best_a][f]['mae_prod_live']-all_results[best_a][f]['mae_ema'])/all_results[best_a][f]['mae_prod_live']*100:+.1f}%"
                for f in ("cc","cm","ch") if all_results[best_a][f] is not None and all_results[best_a][f]['mae_prod_live'] > 0
            )
            p(f"VERDICT: STAGE 0 HIT — α={best_a} improves cl by +{best_d:.1f}% vs raw on {HELD_OUT_DAYS}d "
              f"held-out; other fields vs live prod ({other}). "
              f"Advance to Stage 1: chronological halves-stability check, regime-slice halves, and "
              f"walk-forward validator vs current pooled Lc.")

    # Write outputs
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump({"held_out_days": HELD_OUT_DAYS, "min_warmup": MIN_WARMUP,
                   "alphas": list(ALPHAS), "results": {str(k): v for k, v in all_results.items()}},
                  fh, indent=2)
    p(f"\nwrote {OUT_TXT}\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()

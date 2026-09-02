"""Stage 1a — baseline sanity check on Lc EMA/Kalman.

Question: is the EMA's +33% cl gain doing something a naive "mean residual
over last N obs" can't do? If a for-loop over the last 6-48 obs matches
the EMA within 1-2pp, the EMA machinery isn't buying anything — just ship
the simpler lookback. If EMA meaningfully beats lookback, the exponential
weighting has legs and Stage 1 walkforward is warranted.

Same held-out window (14d), same warm-up (20 obs per (field, bin)), same
two-phase per-obs_time processing as h_lc_ema_stage0.py. Compares:
  - EMA α=0.2 (Stage 0 winner)
  - Lookback N ∈ {6, 12, 24, 48} — mean residual over last N obs updates

Verdict:
  EMA WINS   — EMA beats all lookbacks by ≥2pp on cl.
  LOOKBACK   — some N matches or beats EMA within 1pp on cl. Ship lookback
               (simpler, same skill).
  MIXED      — EMA wins on some fields, lookback wins on others.

Run:
    python3 -m analysis.h_lc_ema_stage1_baseline
"""
import json
import os
import sys
from collections import defaultdict, deque
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402
from _prod import prod_error  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_lc_ema_stage1_baseline.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_lc_ema_stage1_baseline.json")

FIELDS = ("cc", "cl", "cm", "ch")
BINS = [(0, 5, "0-5"), (5, 20, "5-20"), (20, 50, "20-50"),
        (50, 80, "50-80"), (80, 95, "80-95"), (95, 100.01, "95-100")]
LOOKBACKS = (6, 12, 24, 48)
EMA_ALPHA = 0.20
HELD_OUT_DAYS = 14
MIN_WARMUP = 20
EMA_MARGIN_PP = 2.0  # EMA must beat best lookback by this much to "win"


def _bin_of(v):
    for lo, hi, lab in BINS:
        if lo <= v < hi:
            return lab
    return None


def _load_rows():
    rows = []
    with open(cached_path(PAIR_LOG_URL)) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            fld = r.get("field")
            if fld not in FIELDS: continue
            ot = r.get("obs_time")
            fc_l4 = r.get("forecast_l4")
            obs = r.get("observed")
            if not (ot and fc_l4 is not None and obs is not None): continue
            b = _bin_of(fc_l4)
            if b is None: continue
            err_l2 = r.get("error_l2")
            err_prod = prod_error(r)
            rows.append((ot, fld, b, float(fc_l4), float(obs), err_l2, err_prod))
    rows.sort(key=lambda x: x[0])
    return rows


def _simulate_ema(rows, alpha, cutoff_ot):
    """Same two-phase EMA simulator as Stage 0."""
    ema = defaultdict(float)
    n_updates = defaultdict(int)
    out = {f: {"n": 0, "sum": 0.0} for f in FIELDS}
    i, N = 0, len(rows)
    while i < N:
        j = i
        cur_ot = rows[i][0]
        while j < N and rows[j][0] == cur_ot:
            j += 1
        batch = rows[i:j]
        i = j
        residual_bucket = defaultdict(list)
        for ot, fld, b, fc_l4, obs, err_l2, err_prod in batch:
            key = (fld, b)
            warm = n_updates[key] >= MIN_WARMUP
            if ot >= cutoff_ot:
                out[fld]["n"] += 1
                if warm:
                    out[fld]["sum"] += abs(fc_l4 - ema[key] - obs)
                else:
                    out[fld]["sum"] += abs(fc_l4 - obs)
            residual_bucket[key].append(fc_l4 - obs)
        for key, residuals in residual_bucket.items():
            r_bar = sum(residuals) / len(residuals)
            if n_updates[key] == 0:
                ema[key] = r_bar
            else:
                ema[key] = (1 - alpha) * ema[key] + alpha * r_bar
            n_updates[key] += 1
    return {f: (out[f]["sum"] / out[f]["n"] if out[f]["n"] else None) for f in FIELDS}


def _simulate_lookback(rows, n_window, cutoff_ot):
    """Same two-phase structure, but shift = mean of last n_window batch-mean
    residuals (a rolling window instead of exponential weighting)."""
    history = defaultdict(lambda: deque(maxlen=n_window))
    out = {f: {"n": 0, "sum": 0.0} for f in FIELDS}
    i, N = 0, len(rows)
    while i < N:
        j = i
        cur_ot = rows[i][0]
        while j < N and rows[j][0] == cur_ot:
            j += 1
        batch = rows[i:j]
        i = j
        residual_bucket = defaultdict(list)
        for ot, fld, b, fc_l4, obs, err_l2, err_prod in batch:
            key = (fld, b)
            warm = len(history[key]) >= MIN_WARMUP or (
                # Also allow warm once the deque is full (deque cap == n_window;
                # once full it means at least n_window batches have contributed).
                len(history[key]) == n_window
            )
            if ot >= cutoff_ot:
                out[fld]["n"] += 1
                if warm and history[key]:
                    shift = sum(history[key]) / len(history[key])
                    out[fld]["sum"] += abs(fc_l4 - shift - obs)
                else:
                    out[fld]["sum"] += abs(fc_l4 - obs)
            residual_bucket[key].append(fc_l4 - obs)
        for key, residuals in residual_bucket.items():
            history[key].append(sum(residuals) / len(residuals))
    return {f: (out[f]["sum"] / out[f]["n"] if out[f]["n"] else None) for f in FIELDS}


def _mae_raw_l2(rows, cutoff_ot):
    """Simple raw L2 MAE on held-out for the baseline column."""
    out = {f: {"n": 0, "sum": 0.0} for f in FIELDS}
    for ot, fld, b, fc_l4, obs, err_l2, err_prod in rows:
        if ot < cutoff_ot: continue
        out[fld]["n"] += 1
        if err_l2 is not None:
            out[fld]["sum"] += abs(float(err_l2))
    return {f: (out[f]["sum"] / out[f]["n"] if out[f]["n"] else None) for f in FIELDS}


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

    p(f"h_lc_ema_stage1_baseline — EMA vs simple lookback")
    p(f"Pair log: {len(rows):,} rows  ({rows[0][0]} → {rows[-1][0]})")
    p(f"Held-out: {cutoff_ot} → {max_ot}  ({HELD_OUT_DAYS}d)")
    p(f"EMA α={EMA_ALPHA}   lookback N ∈ {LOOKBACKS}   warm-up={MIN_WARMUP}")
    p("")

    raw = _mae_raw_l2(rows, cutoff_ot)
    ema_mae = _simulate_ema(rows, EMA_ALPHA, cutoff_ot)
    lb_mae = {n: _simulate_lookback(rows, n, cutoff_ot) for n in LOOKBACKS}

    p(f"MAE table (lower = better):")
    header = f"  {'field':<6}{'raw L2':>10}{'EMA α=0.2':>12}" + "".join(f"{'N='+str(n):>10}" for n in LOOKBACKS)
    p(header)
    p("  " + "-" * (len(header) - 2))
    for f in FIELDS:
        if raw[f] is None: continue
        row = f"  {f:<6}{raw[f]:>10.3f}{ema_mae[f]:>12.3f}"
        for n in LOOKBACKS:
            row += f"{lb_mae[n][f]:>10.3f}"
        p(row)
    p("")

    p(f"Δ% vs raw L2 (positive = correction improves):")
    p(f"  {'field':<6}{'EMA α=0.2':>12}" + "".join(f"{'N='+str(n):>10}" for n in LOOKBACKS))
    p("  " + "-" * (6 + 12 + 10 * len(LOOKBACKS)))
    for f in FIELDS:
        if raw[f] is None or raw[f] == 0: continue
        row = f"  {f:<6}"
        d_ema = (raw[f] - ema_mae[f]) / raw[f] * 100
        row += f"{d_ema:>+11.1f}%"
        for n in LOOKBACKS:
            d = (raw[f] - lb_mae[n][f]) / raw[f] * 100
            row += f"{d:>+9.1f}%"
        p(row)
    p("")

    # Verdict on cl (the field that motivates the whole workstream)
    p(f"cl-focused verdict:")
    if raw["cl"] is None:
        p(f"  NO DATA — cl has no held-out rows.")
    else:
        ema_gain = (raw["cl"] - ema_mae["cl"]) / raw["cl"] * 100
        lb_gains = {n: (raw["cl"] - lb_mae[n]["cl"]) / raw["cl"] * 100 for n in LOOKBACKS}
        best_n = max(lb_gains, key=lb_gains.get)
        best_lb_gain = lb_gains[best_n]
        margin = ema_gain - best_lb_gain
        p(f"  EMA α=0.2 gain vs raw:      {ema_gain:+.1f}%")
        p(f"  Best lookback N={best_n} gain:   {best_lb_gain:+.1f}%")
        p(f"  EMA margin over lookback:   {margin:+.1f}pp")
        p("")
        if margin >= EMA_MARGIN_PP:
            p(f"VERDICT: EMA WINS — exponential weighting beats best lookback (N={best_n}) "
              f"by {margin:.1f}pp on cl. Stage 1 walkforward vs pooled Lc warranted; the "
              f"EMA machinery is doing more than a simple rolling mean.")
        elif margin >= -1.0:
            p(f"VERDICT: LOOKBACK — simple rolling mean over last {best_n} obs matches EMA "
              f"within {abs(margin):.1f}pp on cl. Ship lookback instead of EMA — simpler, "
              f"same skill. Update project_lc_ema_kalman_fallback to reflect the pivot.")
        else:
            p(f"VERDICT: LOOKBACK WINS — lookback N={best_n} beats EMA by {-margin:.1f}pp "
              f"on cl. Ship lookback; EMA machinery is actively worse than the naive "
              f"baseline. Update project_lc_ema_kalman_fallback and pivot Stage 2 to "
              f"lookback-N sweep.")

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump({
            "held_out_days": HELD_OUT_DAYS, "min_warmup": MIN_WARMUP,
            "ema_alpha": EMA_ALPHA, "lookbacks": list(LOOKBACKS),
            "raw_l2": raw, "ema": ema_mae,
            "lookback": {str(n): lb_mae[n] for n in LOOKBACKS},
        }, fh, indent=2)
    p(f"\nwrote {OUT_TXT}\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()

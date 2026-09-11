#!/usr/bin/env python3
"""L3_NBM per (regime, band) diagnostic fit — analysis-only, no runtime change.

Purpose: distinguish two hypotheses about the NBM error surface —
  (A) NBM's error is genuinely smoother than HRRR's; pooled per-lead
      correction captures ~all of the fixable bias.
  (B) NBM has different-structured biases than HRRR (different regime
      interactions, different diurnal shapes); direct-clone gates fail
      because they're wrong-axis, but a native regime-aware fit would earn.

The current runtime `l3_nbm_fit.py` fits pooled per-lead (48 scalars per
field). HRRR's L3 fits per (regime, band, fc-quartile) with SKIP_TABLE.
This diagnostic fits per (regime, band) — one step in the direction of the
HRRR shape without the fc-quartile complexity — and compares held-out
MAE against pooled.

Sign convention (mirrors l3_nbm_fit.py): `error = forecast - observed`, so
the correction applied at forecast time is `l3_nbm = l2_nbm - bias`.

Output: text + JSON to `analysis/output/l3_nbm_fit_by_regime.*`. Does NOT
overwrite `weather_collector/data/l3_nbm_curated.json` — the runtime table
stays pooled until we decide to wire regime-aware.

Runtime:
    python3 -m analysis.l3_nbm_fit_by_regime
    MYWEATHER_REFRESH=1 python3 -m analysis.l3_nbm_fit_by_regime
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import pair_log_paths

OUT_TXT = Path(__file__).resolve().parent / "output" / "l3_nbm_fit_by_regime.txt"
OUT_JSON = Path(__file__).resolve().parent / "output" / "l3_nbm_fit_by_regime.json"

FIELDS = ("t", "ws", "wg", "h", "ch", "sr", "dp", "cc")
LEAD_BINS = 48
TAU_DAYS = 14
RETENTION_DAYS = 30
TEST_WINDOW_DAYS = 7
MIN_PAIRS_PER_LEAD_POOLED = 20
MIN_PAIRS_PER_CELL_REGIME = 50   # regime × band cells pool 6–24 leads,
                                  # but need more n than per-lead since
                                  # regime × band is 4× narrower than pool.

# Same 4 lead-bands the HRRR L3 uses.
_LEAD_BANDS = [
    ("0-5",   0,  5),
    ("6-11",  6, 11),
    ("12-23", 12, 23),
    ("24-47", 24, 47),
]


def _lead_band(lead_h):
    for name, lo, hi in _LEAD_BANDS:
        if lo <= lead_h <= hi:
            return name
    return None


def _load_rows(now):
    """Yield (field, lead_h, band, regime, obs_time, err_l2, fc_l2, obs, age_days) tuples
    for rows in the retention window that carry error_l2_nbm + regime + obs.
    obs is reconstructed as `forecast_l2_nbm - error_l2_nbm` (both fields
    stamped by the joiner). Skips wd (circular)."""
    cutoff = (now - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")
    n_in = 0
    n_no_regime = 0
    n_no_fc = 0
    for path in pair_log_paths():
        try:
            fh = open(path)
        except FileNotFoundError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                n_in += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                field = row.get("field")
                if field not in FIELDS:
                    continue
                lead_h = row.get("lead_h")
                if lead_h is None or not (0 <= lead_h < LEAD_BINS):
                    continue
                band = _lead_band(lead_h)
                if band is None:
                    continue
                obs_time = row.get("obs_time", "")
                if obs_time < cutoff:
                    continue
                err = row.get("error_l2_nbm")
                fc = row.get("forecast_l2_nbm")
                if err is None or fc is None:
                    n_no_fc += 1
                    continue
                regime = ((row.get("state_fc") or {}).get("regime_synoptic")) or None
                if not regime:
                    n_no_regime += 1
                    continue
                try:
                    obs_dt = datetime.strptime(obs_time, "%Y-%m-%dT%H:%M")
                except ValueError:
                    continue
                age_days = max(0.0, (now - obs_dt).total_seconds() / 86400.0)
                obs = float(fc) - float(err)
                yield (field, lead_h, band, regime, obs_time, obs_dt,
                       float(err), float(fc), obs, age_days)
    print(f"  scanned {n_in:,} rows; skipped {n_no_regime:,} no-regime, {n_no_fc:,} no-fc")


def _fit_pooled(train_rows_by_field):
    """Fit pooled per-lead bias with exponential recency weighting.
    Returns {field: {lead_h: bias or None}}."""
    sums = defaultdict(float)
    weights = defaultdict(float)
    counts = defaultdict(int)
    for field, rows in train_rows_by_field.items():
        for r in rows:
            _, lead_h, _band, _regime, _obs_time, _obs_dt, err, _fc, _obs, age = r
            w = math.exp(-age / TAU_DAYS)
            sums[(field, lead_h)] += err * w
            weights[(field, lead_h)] += w
            counts[(field, lead_h)] += 1
    tbl = {}
    for f in FIELDS:
        arr = [None] * LEAD_BINS
        for h in range(LEAD_BINS):
            n = counts.get((f, h), 0)
            w = weights.get((f, h), 0.0)
            if n >= MIN_PAIRS_PER_LEAD_POOLED and w > 0:
                arr[h] = sums[(f, h)] / w
        tbl[f] = arr
    return tbl


def _fit_by_regime(train_rows_by_field):
    """Fit per (regime, band) bias with exponential recency weighting.
    Returns {field: {regime: {band: bias}}} and per-cell n dict."""
    sums = defaultdict(float)
    weights = defaultdict(float)
    counts = defaultdict(int)
    for field, rows in train_rows_by_field.items():
        for r in rows:
            _, _lead_h, band, regime, _obs_time, _obs_dt, err, _fc, _obs, age = r
            w = math.exp(-age / TAU_DAYS)
            key = (field, regime, band)
            sums[key] += err * w
            weights[key] += w
            counts[key] += 1
    tbl = {}
    n_tbl = {}
    for (field, regime, band), n in counts.items():
        w = weights[(field, regime, band)]
        if n >= MIN_PAIRS_PER_CELL_REGIME and w > 0:
            tbl.setdefault(field, {}).setdefault(regime, {})[band] = sums[(field, regime, band)] / w
        n_tbl.setdefault(field, {}).setdefault(regime, {})[band] = n
    return tbl, n_tbl


def _score(test_rows, pooled_tbl, regime_tbl):
    """Score three baselines on the test window:
      raw:     MAE(|err_l2_nbm|)                              — no L3 correction
      pooled:  MAE(|err_l2_nbm - pooled_bias[lead]|)          — current runtime shape
      regime:  MAE(|err_l2_nbm - regime_bias[regime][band]|)  — proposed shape
                                                                (falls back to pooled
                                                                when regime cell empty)
    Returns per-field summary + per-cell regime-vs-pooled comparison."""
    per_field = {}
    per_cell_vs = defaultdict(lambda: {"n": 0, "sum_pool_abs": 0.0, "sum_reg_abs": 0.0})
    for field, rows in test_rows.items():
        n = 0
        sum_raw = 0.0
        sum_pool = 0.0
        sum_reg = 0.0
        pooled_arr = pooled_tbl.get(field, [None] * LEAD_BINS)
        r_field = regime_tbl.get(field, {})
        for r in rows:
            _, lead_h, band, regime, _obs_time, _obs_dt, err, _fc, _obs, _age = r
            pooled_bias = pooled_arr[lead_h] if lead_h < len(pooled_arr) else None
            pooled_bias = pooled_bias if pooled_bias is not None else 0.0
            reg_bias = ((r_field.get(regime) or {}).get(band))
            reg_bias_effective = reg_bias if reg_bias is not None else pooled_bias
            sum_raw += abs(err)
            sum_pool += abs(err - pooled_bias)
            sum_reg += abs(err - reg_bias_effective)
            n += 1
            key = (regime, band)
            cell = per_cell_vs[(field, regime, band)]
            cell["n"] += 1
            cell["sum_pool_abs"] += abs(err - pooled_bias)
            cell["sum_reg_abs"] += abs(err - reg_bias_effective)
        if n > 0:
            per_field[field] = {
                "n_test": n,
                "raw_mae": sum_raw / n,
                "pooled_mae": sum_pool / n,
                "regime_mae": sum_reg / n,
                "pooled_lift_vs_raw_pct": 100.0 * (sum_raw - sum_pool) / sum_raw if sum_raw > 0 else 0.0,
                "regime_lift_vs_raw_pct": 100.0 * (sum_raw - sum_reg) / sum_raw if sum_raw > 0 else 0.0,
                "regime_lift_vs_pooled_pct": 100.0 * (sum_pool - sum_reg) / sum_pool if sum_pool > 0 else 0.0,
            }
    return per_field, per_cell_vs


def _halves(test_rows_by_field, pooled_tbl, regime_tbl, mid_dt):
    """Split test window at mid_dt and score each half."""
    first = defaultdict(list)
    second = defaultdict(list)
    for field, rows in test_rows_by_field.items():
        for r in rows:
            _, _lead_h, _band, _regime, _obs_time, obs_dt, _err, _fc, _obs, _age = r
            (first if obs_dt < mid_dt else second)[field].append(r)
    return _score(first, pooled_tbl, regime_tbl)[0], _score(second, pooled_tbl, regime_tbl)[0]


def run():
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    test_cutoff = now - timedelta(days=TEST_WINDOW_DAYS)
    print(f"l3_nbm_fit_by_regime — retention {RETENTION_DAYS}d, test {TEST_WINDOW_DAYS}d "
          f"(train ≤ {test_cutoff.strftime('%Y-%m-%dT%H:%M')}, test > that)")

    train_rows = defaultdict(list)
    test_rows = defaultdict(list)
    for tup in _load_rows(now):
        field, _lead_h, _band, _regime, _obs_time, obs_dt, _err, _fc, _obs, _age = tup
        if obs_dt < test_cutoff:
            train_rows[field].append(tup)
        else:
            test_rows[field].append(tup)

    print(f"  train rows/field: {dict((f, len(v)) for f, v in train_rows.items())}")
    print(f"  test rows/field:  {dict((f, len(v)) for f, v in test_rows.items())}")

    pooled_tbl = _fit_pooled(train_rows)
    regime_tbl, regime_n = _fit_by_regime(train_rows)

    per_field, per_cell = _score(test_rows, pooled_tbl, regime_tbl)

    mid = test_cutoff + timedelta(days=TEST_WINDOW_DAYS / 2.0)
    halves_first, halves_second = _halves(test_rows, pooled_tbl, regime_tbl, mid)

    # Per-cell wins: cell "wins" for regime iff regime MAE < pooled MAE with
    # n≥30 test rows and gap ≥ 2% relative.
    cell_wins = []
    cell_losses = []
    for (field, regime, band), s in per_cell.items():
        if s["n"] < 30:
            continue
        pool_mae = s["sum_pool_abs"] / s["n"]
        reg_mae = s["sum_reg_abs"] / s["n"]
        if pool_mae <= 0:
            continue
        gap_pct = 100.0 * (pool_mae - reg_mae) / pool_mae
        rec = {"field": field, "regime": regime, "band": band,
               "n": s["n"], "pool_mae": round(pool_mae, 4),
               "reg_mae": round(reg_mae, 4), "gap_pct": round(gap_pct, 2)}
        if gap_pct >= 2.0:
            cell_wins.append(rec)
        elif gap_pct <= -2.0:
            cell_losses.append(rec)
    cell_wins.sort(key=lambda x: -x["gap_pct"])
    cell_losses.sort(key=lambda x: x["gap_pct"])

    # Verdict per-field: PROMOTE iff regime_lift_vs_pooled ≥ 3% AND halves
    # both positive AND ≥ 2 winning cells.
    verdicts = {}
    for f, pf in per_field.items():
        h1 = (halves_first.get(f) or {}).get("regime_lift_vs_pooled_pct", 0.0)
        h2 = (halves_second.get(f) or {}).get("regime_lift_vs_pooled_pct", 0.0)
        winning_cells = sum(1 for c in cell_wins if c["field"] == f)
        overall = pf["regime_lift_vs_pooled_pct"]
        if overall >= 3.0 and h1 > 0 and h2 > 0 and winning_cells >= 2:
            verdicts[f] = "PROMOTE"
        elif overall >= 1.0 and (h1 > 0 or h2 > 0):
            verdicts[f] = "MARGINAL"
        elif abs(overall) < 1.0:
            verdicts[f] = "FLAT"
        else:
            verdicts[f] = "HOLD"

    # Text report.
    lines = []
    lines.append(f"L3_NBM per (regime × band) diagnostic — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"  Retention {RETENTION_DAYS}d, test window last {TEST_WINDOW_DAYS}d, TAU={TAU_DAYS}d")
    lines.append(f"  Train n/field: " + ", ".join(f"{f}={len(train_rows.get(f, []))}" for f in FIELDS))
    lines.append(f"  Test  n/field: " + ", ".join(f"{f}={len(test_rows.get(f, []))}" for f in FIELDS))
    lines.append("")
    lines.append(f"{'field':<6}{'n_test':>8}{'raw_MAE':>10}{'pool_MAE':>10}{'reg_MAE':>10}"
                 f"{'pool_v_raw':>12}{'reg_v_raw':>12}{'reg_v_pool':>12}"
                 f"{'halves1':>10}{'halves2':>10}   verdict")
    for f in FIELDS:
        pf = per_field.get(f)
        if not pf:
            lines.append(f"{f:<6}   —  no test data")
            continue
        h1 = (halves_first.get(f) or {}).get("regime_lift_vs_pooled_pct", 0.0)
        h2 = (halves_second.get(f) or {}).get("regime_lift_vs_pooled_pct", 0.0)
        lines.append(
            f"{f:<6}{pf['n_test']:>8}{pf['raw_mae']:>10.3f}{pf['pooled_mae']:>10.3f}"
            f"{pf['regime_mae']:>10.3f}{pf['pooled_lift_vs_raw_pct']:>+11.2f}%"
            f"{pf['regime_lift_vs_raw_pct']:>+11.2f}%{pf['regime_lift_vs_pooled_pct']:>+11.2f}%"
            f"{h1:>+9.2f}%{h2:>+9.2f}%   {verdicts[f]}"
        )
    lines.append("")
    lines.append(f"Cell-level wins (regime beats pooled by ≥ 2%, n_test ≥ 30):")
    if not cell_wins:
        lines.append("  (none)")
    else:
        for c in cell_wins[:30]:
            lines.append(f"  {c['field']:<4} {c['regime']:<12} {c['band']:<7} "
                         f"n={c['n']:>4}  pool={c['pool_mae']:>7.3f}  reg={c['reg_mae']:>7.3f}"
                         f"  gap={c['gap_pct']:>+6.2f}%")
        if len(cell_wins) > 30:
            lines.append(f"  ... and {len(cell_wins) - 30} more")
    lines.append("")
    lines.append(f"Cell-level losses (regime loses to pooled by ≥ 2%, n_test ≥ 30):")
    if not cell_losses:
        lines.append("  (none)")
    else:
        for c in cell_losses[:20]:
            lines.append(f"  {c['field']:<4} {c['regime']:<12} {c['band']:<7} "
                         f"n={c['n']:>4}  pool={c['pool_mae']:>7.3f}  reg={c['reg_mae']:>7.3f}"
                         f"  gap={c['gap_pct']:>+6.2f}%")
        if len(cell_losses) > 20:
            lines.append(f"  ... and {len(cell_losses) - 20} more")
    lines.append("")
    lines.append("Verdict summary:")
    for f in FIELDS:
        v = verdicts.get(f, "—")
        lines.append(f"  {f}: {v}")
    lines.append("")
    total_promote = sum(1 for v in verdicts.values() if v == "PROMOTE")
    total_marginal = sum(1 for v in verdicts.values() if v == "MARGINAL")
    total_flat = sum(1 for v in verdicts.values() if v == "FLAT")
    total_hold = sum(1 for v in verdicts.values() if v == "HOLD")
    lines.append(f"Overall: {total_promote} PROMOTE / {total_marginal} MARGINAL "
                 f"/ {total_flat} FLAT / {total_hold} HOLD")
    if total_promote == 0 and total_marginal <= 1:
        lines.append("→ Reads as hypothesis A: NBM error surface is smooth "
                     "enough that regime × band fit doesn't beat pooled. "
                     "Close the port-more-HRRR-gates thread; focus elsewhere.")
    elif total_promote >= 2:
        lines.append("→ Reads as hypothesis B: NBM has real regime × band structure "
                     "worth fitting. Scope regime-aware L3_NBM as a wire-in workstream.")
    else:
        lines.append("→ Mixed read. Some fields have structure, most don't. "
                     "Consider a narrow ship on the PROMOTE fields only.")

    text = "\n".join(lines) + "\n"
    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text(text)

    out_json = {
        "fitted_at": now.strftime("%Y-%m-%dT%H:%M"),
        "retention_days": RETENTION_DAYS,
        "test_window_days": TEST_WINDOW_DAYS,
        "tau_days": TAU_DAYS,
        "min_pairs_per_lead_pooled": MIN_PAIRS_PER_LEAD_POOLED,
        "min_pairs_per_cell_regime": MIN_PAIRS_PER_CELL_REGIME,
        "per_field": per_field,
        "halves": {
            "first": halves_first,
            "second": halves_second,
        },
        "cell_wins": cell_wins,
        "cell_losses": cell_losses,
        "verdicts": verdicts,
        "regime_bias_table": regime_tbl,
        "regime_n_table": regime_n,
    }
    OUT_JSON.write_text(json.dumps(out_json, indent=2, default=str))

    print(text)
    print(f"  wrote {OUT_TXT}")
    print(f"  wrote {OUT_JSON}")


if __name__ == "__main__":
    run()

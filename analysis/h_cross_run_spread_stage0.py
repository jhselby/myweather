"""Stage 0 — cross-run ensemble spread as a confidence signal, per field.

Motivated by round-2 smoke (08-10). For any valid_time V, group all pair-log
rows by (field, V) and enumerate the distinct run_times that produced a
forecast for V. Spread across those forecasts is same-model disagreement —
a novel confidence axis (existing disagreement analyses cover inter-source
sigma, not intra-model cross-run).

Question: does bucket-conditional |err| structure survive held-out?

Design:
  * Bucket valid_times into spread quintiles per field (fit on train).
  * Held-out test: does mean|err| in top quintile / bottom quintile exceed
    STAGE0_GATE_RATIO?  And is monotonicity preserved across quintiles?
  * Reports each field's held-out ratio + monotonicity check.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402
from _prod import prod_error  # noqa: E402
from _windows import rolling_windows  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_cross_run_spread_stage0.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_cross_run_spread_stage0.json")

WINDOW_DAYS = 45
HELD_OUT_DAYS = 7
MIN_RUNS_PER_VT = 3
MIN_VT_TRAIN = 200
MIN_VT_TEST = 40
STAGE0_GATE_RATIO = 1.60  # top-quintile mean|err| must be >= 1.6x bottom-quintile

TARGET_FIELDS = ["cc", "ch", "cl", "cm", "dp", "h", "pr", "t", "wd", "wg", "ws"]


def _load_groups(window_days):
    WIN = rolling_windows(recent_days=window_days, prior_days=0)
    lo, hi = WIN.A_LO, WIN.A_HI
    groups = defaultdict(list)  # (field, valid_time) -> [(run_time, fc, err)]
    n_scanned = 0
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            n_scanned += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            vt = r.get("valid_time") or ""
            if vt < lo or vt >= hi:
                continue
            f = r.get("field")
            if f not in TARGET_FIELDS:
                continue
            rt = r.get("run_time")
            fc = r.get("forecast")
            err = prod_error(r)
            if not (rt and fc is not None and err is not None):
                continue
            groups[(f, vt)].append((rt, float(fc), float(err)))
    return groups, lo, hi, n_scanned


def _quintile_edges(sorted_vals):
    """Return [q20, q40, q60, q80] on a sorted list."""
    n = len(sorted_vals)
    return [sorted_vals[int(n * p)] for p in (0.20, 0.40, 0.60, 0.80)]


def _bin(x, edges):
    for i, e in enumerate(edges):
        if x < e:
            return i
    return len(edges)


def _fmt_pct_from_zero(v):
    return f"{v:+.2f}"


def analyze_field(field, groups, test_start):
    """Return dict with per-quintile stats on train and test, monotonicity flag,
    and the top/bottom ratio on test."""
    # Collect per-VT (spread, mean|err|)
    train_pts = []
    test_pts = []
    for (f, vt), items in groups.items():
        if f != field:
            continue
        if len(items) < MIN_RUNS_PER_VT:
            continue
        fcs = [fc for _, fc, _ in items]
        errs = [err for _, _, err in items]
        spread = max(fcs) - min(fcs)
        mabs = mean(abs(e) for e in errs)
        if vt[:10] < test_start:
            train_pts.append((spread, mabs))
        else:
            test_pts.append((spread, mabs))

    result = {
        "field": field,
        "n_train_vt": len(train_pts),
        "n_test_vt": len(test_pts),
    }
    if len(train_pts) < MIN_VT_TRAIN:
        result["status"] = "THIN_TRAIN"
        return result
    if len(test_pts) < MIN_VT_TEST:
        result["status"] = "THIN_TEST"
        return result

    edges = _quintile_edges(sorted(s for s, _ in train_pts))

    # bin test set by TRAIN-derived edges
    bins_test = defaultdict(list)
    for s, m in test_pts:
        bins_test[_bin(s, edges)].append(m)
    bins_train = defaultdict(list)
    for s, m in train_pts:
        bins_train[_bin(s, edges)].append(m)

    # For each of 5 bins, compute mean|err| and n
    per_bin = []
    for i in range(5):
        tr = bins_train.get(i, [])
        te = bins_test.get(i, [])
        per_bin.append({
            "bin": i,
            "n_train": len(tr),
            "train_mean_abs_err": round(mean(tr), 4) if tr else None,
            "n_test": len(te),
            "test_mean_abs_err": round(mean(te), 4) if te else None,
        })

    test_means = [b["test_mean_abs_err"] for b in per_bin]
    valid_test = [m for m in test_means if m is not None]
    if len(valid_test) < 4:
        result["status"] = "THIN_TEST_BINS"
        result["per_bin"] = per_bin
        return result

    lo_m = per_bin[0]["test_mean_abs_err"]
    hi_m = per_bin[4]["test_mean_abs_err"]
    ratio = hi_m / lo_m if lo_m and lo_m > 0 else None

    # Monotone-ish check: allow one small dip; require net rise
    rises = sum(1 for i in range(4)
                if per_bin[i]["test_mean_abs_err"] is not None
                and per_bin[i + 1]["test_mean_abs_err"] is not None
                and per_bin[i + 1]["test_mean_abs_err"] > per_bin[i]["test_mean_abs_err"])

    result.update({
        "status": "SCORED",
        "quintile_edges": [round(e, 4) for e in edges],
        "per_bin": per_bin,
        "test_ratio_top_over_bottom": round(ratio, 3) if ratio else None,
        "monotone_rises": rises,  # out of 4
    })
    return result


def emit(results, meta):
    lines = []
    lines.append("=" * 96)
    lines.append("STAGE 0 — cross-run ensemble spread as a per-field confidence signal")
    lines.append("=" * 96)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Held-out: last {HELD_OUT_DAYS}d.")
    lines.append(f"Min runs per valid_time: {MIN_RUNS_PER_VT}.  "
                 f"Min train VTs: {MIN_VT_TRAIN}.  Min test VTs: {MIN_VT_TEST}.")
    lines.append(f"Gate: held-out top-quintile mean|err| / bottom-quintile >= "
                 f"{STAGE0_GATE_RATIO:.2f}, AND monotone_rises >= 3 (of 4).")
    lines.append(f"Test window starts: {meta.get('test_start', '?')}   "
                 f"(scanned {meta.get('n_scanned', 0):,} pair-log rows)")
    lines.append("")
    lines.append(f"{'field':>6}  {'n_tr':>5}  {'n_te':>5}  "
                 f"{'test |err| by quintile (Q1 .. Q5)':<50}  {'ratio':>7}  {'monotone':>9}  {'verdict':<14}")
    lines.append("-" * 118)
    hits = []
    for r in results:
        f = r["field"]
        st = r["status"]
        if st in ("THIN_TRAIN", "THIN_TEST", "THIN_TEST_BINS"):
            lines.append(f"{f:>6}  {r.get('n_train_vt', 0):>5}  {r.get('n_test_vt', 0):>5}  "
                         f"{st:<50}  {'-':>7}  {'-':>9}  {'-':<14}")
            continue
        per_bin_str = "  ".join(
            f"{(b['test_mean_abs_err'] if b['test_mean_abs_err'] is not None else 0):>7.3f}"
            for b in r["per_bin"]
        )
        ratio = r["test_ratio_top_over_bottom"] or 0
        mono = r["monotone_rises"]
        hit = ratio >= STAGE0_GATE_RATIO and mono >= 3
        verdict = "STAGE0 HIT" if hit else "no"
        if hit:
            hits.append((f, ratio, mono))
        lines.append(f"{f:>6}  {r['n_train_vt']:>5}  {r['n_test_vt']:>5}  "
                     f"{per_bin_str:<50}  {ratio:>7.2f}  {mono:>9}  {verdict:<14}")
    lines.append("")
    if hits:
        hit_str = ", ".join(f"{f}(ratio={r:.2f},mono={m}/4)" for f, r, m in hits)
        lines.append(f"VERDICT: STAGE 0 HIT — {len(hits)} field(s) qualify: {hit_str}.")
        lines.append("Warrants Stage 1: build a spread-conditional confidence weight and "
                     "test it as an input to c1 confidence calibration.")
    else:
        lines.append("VERDICT: NO STAGE 0 HIT — no field clears both gates on held-out. "
                     "Do not proceed to Stage 1.")
    return "\n".join(lines)


def main():
    groups, lo, hi, n_scanned = _load_groups(WINDOW_DAYS)
    if not groups:
        print("VERDICT: INSUFFICIENT DATA — no rows in window.")
        return 0
    # Test start = max_vt.date() - HELD_OUT_DAYS
    max_vt = max(vt for _, vt in groups.keys())
    max_date = datetime.strptime(max_vt[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    results = [analyze_field(f, groups, test_start) for f in TARGET_FIELDS]
    meta = {
        "window_lo": lo,
        "window_hi": hi,
        "test_start": test_start,
        "n_scanned": n_scanned,
    }
    text = emit(results, meta)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump({
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "meta": meta,
            "results": results,
        }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())

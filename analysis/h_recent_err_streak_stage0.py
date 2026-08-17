"""Stage 0 — recent |err| streak as a live per-field confidence signal.

Round-4 smoke (08-10) showed that for a fixed (field, lead-band), if the
past-3h hourly mean |err| is in its top quintile, the next hour's |err|
is 2-24x larger than when past-3h was in the bottom quintile.

Distinct from bias-sign persistence: this is |err|-magnitude persistence.
When forecast quality has been poor for the past few hours (any sign),
the next hour's forecast is also more likely to be poor.

Live signal — computable from the last 3 hours of freshly-obs'd forecasts.
Per-lead-band because different lead bands have different pair-log arrival
timing.

Bounded fields (cc, ch, cl, cm, sr, pa, pp, pr) show inflated ratios
driven by near-zero bottom quintile |err|. Restrict to unbounded fields
where the ratio isn't a divide-by-tiny.

Gate on TEST: top(Q5)/bottom(Q1) |err| ratio >= 2.0 AND monotone rising
across 5 bins.
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
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_recent_err_streak_stage0.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_recent_err_streak_stage0.json")

WINDOW_DAYS = 45
HELD_OUT_DAYS = 7
LEAD_BANDS = [("4-12", 4, 12), ("13-36", 13, 36)]
MIN_N_TRAIN_HR = 300
MIN_N_TEST_BIN = 20
GATE_RATIO = 2.0
TARGET_FIELDS = ["t", "dp", "h", "wd", "wg", "ws"]  # unbounded only


def _band_of(lh):
    for name, lo, hi in LEAD_BANDS:
        if lo <= lh <= hi:
            return name
    return None


def _q_edges(sorted_vals):
    n = len(sorted_vals)
    return [sorted_vals[int(n * p)] for p in (0.20, 0.40, 0.60, 0.80)]


def _bin(x, edges):
    for i, e in enumerate(edges):
        if x < e:
            return i
    return len(edges)


def h_step(k, n):
    dt = datetime.strptime(k, "%Y-%m-%dT%H")
    return (dt + timedelta(hours=n)).strftime("%Y-%m-%dT%H")


def main():
    WIN = rolling_windows(recent_days=WINDOW_DAYS, prior_days=0)
    lo_win, hi_win = WIN.A_LO, WIN.A_HI

    # Build per-(field, band) hourly mean |err|
    accum = defaultdict(dict)  # (f, band) -> {hour_key: [sum_abs, n]}
    n_scanned = 0
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            n_scanned += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            vt = r.get("valid_time") or ""
            if vt < lo_win or vt >= hi_win:
                continue
            f = r.get("field")
            if f not in TARGET_FIELDS:
                continue
            lh = r.get("lead_h")
            band = _band_of(lh) if lh is not None else None
            if band is None:
                continue
            err = prod_error(r)
            if err is None:
                continue
            k = vt[:13]
            bucket = accum[(f, band)]
            if k not in bucket:
                bucket[k] = [0.0, 0]
            bucket[k][0] += abs(float(err))
            bucket[k][1] += 1

    if not accum:
        print("VERDICT: INSUFFICIENT DATA — no rows in window.")
        return 0

    # For each (f, band), build (past3_mean, current) pairs, split train/test.
    results = []
    max_key = ""
    for (f, band), bucket in accum.items():
        for k in bucket:
            if k > max_key:
                max_key = k
    max_date = datetime.strptime(max_key[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    for (f, band), bucket in accum.items():
        hourly = {k: v[0] / v[1] for k, v in bucket.items() if v[1] > 0}
        train_pairs, test_pairs = [], []
        for k, cur in hourly.items():
            p1 = hourly.get(h_step(k, -1))
            p2 = hourly.get(h_step(k, -2))
            p3 = hourly.get(h_step(k, -3))
            if p1 is None or p2 is None or p3 is None:
                continue
            pt3 = (p1 + p2 + p3) / 3.0
            if k[:10] < test_start:
                train_pairs.append((pt3, cur))
            else:
                test_pairs.append((pt3, cur))
        if len(train_pairs) < MIN_N_TRAIN_HR or len(test_pairs) < 5 * MIN_N_TEST_BIN:
            results.append({
                "field": f, "band": band, "status": "THIN",
                "n_train": len(train_pairs), "n_test": len(test_pairs),
            })
            continue
        edges = _q_edges(sorted(p for p, _ in train_pairs))
        te_bins = defaultdict(list)
        for p, cur in test_pairs:
            te_bins[_bin(p, edges)].append(cur)
        per_bin = []
        for i in range(5):
            xs = te_bins.get(i, [])
            per_bin.append({
                "bin": i,
                "n_test": len(xs),
                "test_mean_abs_err": round(mean(xs), 4) if xs else None,
            })
        te_means = [b["test_mean_abs_err"] for b in per_bin]
        n_ok = all(b["n_test"] >= MIN_N_TEST_BIN for b in per_bin)
        if not (n_ok and all(m is not None for m in te_means)):
            results.append({"field": f, "band": band, "status": "THIN_TEST_BIN",
                            "per_bin": per_bin})
            continue
        ratio = te_means[4] / te_means[0] if te_means[0] > 0 else 0
        rises = sum(1 for i in range(4) if te_means[i + 1] > te_means[i])
        hit = ratio >= GATE_RATIO and rises >= 3
        results.append({
            "field": f, "band": band, "status": "SCORED",
            "per_bin": per_bin,
            "test_ratio_top_over_bottom": round(ratio, 3),
            "monotone_rises": rises,
            "verdict": "STAGE0 HIT" if hit else "no",
        })

    lines = []
    lines.append("=" * 100)
    lines.append("STAGE 0 — past-3h |err| streak -> current |err|  (unbounded fields only)")
    lines.append("=" * 100)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Held-out: last {HELD_OUT_DAYS}d.")
    lines.append(f"Lead bands: {', '.join(b for b, _, _ in LEAD_BANDS)}.  "
                 f"Fields: {', '.join(TARGET_FIELDS)} (unbounded).")
    lines.append(f"Gate: test Q5/Q1 ratio >= {GATE_RATIO:.1f} AND monotone rises >= 3/4.")
    lines.append(f"Test starts: {test_start}.  Scanned {n_scanned:,} pair-log rows.")
    lines.append("")
    lines.append(f"{'field':>6}  {'band':>7}  {'test |err| by past-3h quintile (Q1..Q5)':<48}  "
                 f"{'ratio':>6}  {'mono':>5}  verdict")
    lines.append("-" * 100)
    hits = []
    for r in sorted(results, key=lambda x: (x["field"], x["band"])):
        if r["status"] != "SCORED":
            lines.append(f"{r['field']:>6}  {r['band']:>7}  {r['status']:<48}  "
                         f"{'-':>6}  {'-':>5}  -")
            continue
        pb = "  ".join(f"{(b['test_mean_abs_err'] or 0):>7.3f}" for b in r["per_bin"])
        lines.append(f"{r['field']:>6}  {r['band']:>7}  {pb:<48}  "
                     f"{r['test_ratio_top_over_bottom']:>6.2f}  {r['monotone_rises']:>3}/4  "
                     f"{r['verdict']}")
        if r["verdict"] == "STAGE0 HIT":
            hits.append((r["field"], r["band"], r["test_ratio_top_over_bottom"]))
    lines.append("")
    if hits:
        hit_str = ", ".join(f"{f}/{b}({r:.2f}x)" for f, b, r in hits)
        lines.append(f"VERDICT: STAGE 0 HIT — {len(hits)} (field,band) cell(s): {hit_str}.")
        lines.append("Warrants Stage 1: orthogonality vs [[project_cross_run_spread_c1_axis]] "
                     "(both are difficulty proxies) and vs c1 transition+pt.")
    else:
        lines.append("VERDICT: NO STAGE 0 HIT.  Do not proceed to Stage 1.")

    text = "\n".join(lines)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump({
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_lo": lo_win,
            "window_hi": hi_win,
            "test_start": test_start,
            "results": results,
        }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())

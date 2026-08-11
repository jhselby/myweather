"""Stage 0 — forecast-magnitude quintile as a per-field confidence axis.

Round-3 smoke (08-10) found monotone |err| structure across forecast quintiles
for three unbounded fields:
  * t   Q5 |err| 3.41 vs Q1 1.16   ratio 2.94x  (hot afternoons harder)
  * wg  Q5 |err| 8.28 vs Q1 3.04   ratio 2.72x  (high wind harder)
  * dp  Q1 |err| 4.12 vs Q5 1.49   ratio 2.77x  (low-dp / dry air harder)

Bounded fields (cc, cl, cm, ch, sr, pa, pp, pr) showed 12x-13x ratios that
are artefacts of the field being zero-heavy — Q1 forecasts are ~0 and obs are
often ~0 too, driving |err|~0. Excluded here.

Design mirrors h_cross_run_spread_stage0.py:
  * Fit quintile edges on train (first 38d).
  * Held-out check on last 7d: top-vs-bottom |err| ratio and monotonicity.
  * Direction of ratio depends on field (t/wg high-side; dp low-side).

Gate: |ratio| >= 2.0 AND monotone across 5 bins on TEST.
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
from _windows import rolling_windows  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_forecast_magnitude_confidence_stage0.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_forecast_magnitude_confidence_stage0.json")

WINDOW_DAYS = 45
HELD_OUT_DAYS = 7
LEAD_LO = 4
LEAD_HI = 12
MIN_N_TRAIN = 1500
MIN_N_TEST_BIN = 30
GATE_RATIO = 2.0
# Field: expected direction of harder-forecast bin ("hi" = top quintile harder,
# "lo" = bottom quintile harder).
FIELDS = {
    "t":  "hi",
    "wg": "hi",
    "dp": "lo",
}


def _quintile_edges(sorted_vals):
    n = len(sorted_vals)
    return [sorted_vals[int(n * p)] for p in (0.20, 0.40, 0.60, 0.80)]


def _bin(x, edges):
    for i, e in enumerate(edges):
        if x < e:
            return i
    return len(edges)


def analyze_field(field, direction, rows_by_field, test_start):
    pts_train = []
    pts_test = []
    for fc, err, day in rows_by_field.get(field, []):
        if day < test_start:
            pts_train.append((fc, err))
        else:
            pts_test.append((fc, err))
    if len(pts_train) < MIN_N_TRAIN:
        return {"field": field, "status": "THIN_TRAIN",
                "n_train": len(pts_train), "n_test": len(pts_test)}
    if len(pts_test) < 5 * MIN_N_TEST_BIN:
        return {"field": field, "status": "THIN_TEST",
                "n_train": len(pts_train), "n_test": len(pts_test)}

    edges = _quintile_edges(sorted(fc for fc, _ in pts_train))

    train_bins = defaultdict(list)
    test_bins = defaultdict(list)
    for fc, err in pts_train:
        train_bins[_bin(fc, edges)].append(err)
    for fc, err in pts_test:
        test_bins[_bin(fc, edges)].append(err)

    per_bin = []
    for i in range(5):
        tr = train_bins.get(i, [])
        te = test_bins.get(i, [])
        per_bin.append({
            "bin": i,
            "n_train": len(tr),
            "train_mean_abs_err": round(mean(tr), 4) if tr else None,
            "n_test": len(te),
            "test_mean_abs_err": round(mean(te), 4) if te else None,
        })

    n_ok = all(b["n_test"] >= MIN_N_TEST_BIN for b in per_bin)
    te_means = [b["test_mean_abs_err"] for b in per_bin]
    if not (n_ok and all(m is not None for m in te_means)):
        return {"field": field, "status": "THIN_TEST_BIN", "per_bin": per_bin,
                "edges": [round(e, 4) for e in edges]}

    lo_m, hi_m = te_means[0], te_means[4]
    if direction == "hi":
        ratio = hi_m / lo_m if lo_m > 0 else 0
        rises = sum(1 for i in range(4) if te_means[i + 1] > te_means[i])
        gate_ok = ratio >= GATE_RATIO and rises >= 3
    else:  # "lo"
        ratio = lo_m / hi_m if hi_m > 0 else 0
        falls = sum(1 for i in range(4) if te_means[i + 1] < te_means[i])
        rises = falls  # reuse field for reporting
        gate_ok = ratio >= GATE_RATIO and falls >= 3
    verdict = "STAGE0 HIT" if gate_ok else "no"

    return {
        "field": field,
        "direction": direction,
        "status": "SCORED",
        "per_bin": per_bin,
        "edges": [round(e, 4) for e in edges],
        "test_ratio_hard_over_easy": round(ratio, 3),
        "monotone_correct_dir": rises,
        "verdict": verdict,
    }


def main():
    WIN = rolling_windows(recent_days=WINDOW_DAYS, prior_days=0)
    lo_win, hi_win = WIN.A_LO, WIN.A_HI

    rows_by_field = defaultdict(list)
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
            if f not in FIELDS:
                continue
            lh = r.get("lead_h")
            if lh is None or not (LEAD_LO <= lh <= LEAD_HI):
                continue
            fc = r.get("forecast")
            err = r.get("error")
            if fc is None or err is None:
                continue
            rows_by_field[f].append((float(fc), abs(float(err)), vt[:10]))

    if not rows_by_field:
        print("VERDICT: INSUFFICIENT DATA — no rows in window.")
        return 0

    max_day = max(day for pts in rows_by_field.values() for _, _, day in pts)
    max_date = datetime.strptime(max_day, "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    results = [analyze_field(f, d, rows_by_field, test_start) for f, d in FIELDS.items()]

    lines = []
    lines.append("=" * 96)
    lines.append("STAGE 0 — forecast-magnitude quintile as a per-field confidence axis")
    lines.append("=" * 96)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Held-out: last {HELD_OUT_DAYS}d.  "
                 f"Lead band: {LEAD_LO}-{LEAD_HI}h.")
    lines.append(f"Fields: t (high-side harder), wg (high-side), dp (low-side).")
    lines.append(f"Gate: |ratio| >= {GATE_RATIO:.1f} AND monotone_correct_dir >= 3/4 on TEST.")
    lines.append(f"Test starts: {test_start}.  Scanned {n_scanned:,} pair-log rows.")
    lines.append("")
    lines.append(f"{'field':>6}  {'dir':>4}  {'test |err| by quintile (Q1..Q5)':<45}  {'ratio':>6}  {'mono':>5}  verdict")
    lines.append("-" * 96)
    hits = []
    for r in results:
        f = r["field"]
        if r["status"] != "SCORED":
            lines.append(f"{f:>6}  {'-':>4}  {r['status']:<45}  {'-':>6}  {'-':>5}  -")
            continue
        pb = "  ".join(f"{(b['test_mean_abs_err'] or 0):>7.3f}" for b in r["per_bin"])
        lines.append(f"{f:>6}  {r['direction']:>4}  {pb:<45}  {r['test_ratio_hard_over_easy']:>6.2f}  "
                     f"{r['monotone_correct_dir']:>3}/4  {r['verdict']}")
        if r["verdict"] == "STAGE0 HIT":
            hits.append((f, r["direction"], r["test_ratio_hard_over_easy"]))
    lines.append("")
    if hits:
        hit_str = ", ".join(f"{f}({d}: {r:.2f}x)" for f, d, r in hits)
        lines.append(f"VERDICT: STAGE 0 HIT — {len(hits)} field(s): {hit_str}.")
        lines.append("Warrants Stage 1: orthogonality check vs c1 axes AND vs "
                     "[[project_cross_run_spread_c1_axis]] (both are hard-forecast proxies).")
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

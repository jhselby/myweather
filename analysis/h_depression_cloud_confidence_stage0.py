"""Stage 0 — observed T-Td depression as a confidence axis for cloud fields.

Round-4 smoke (08-10). Distinct from [[h_dewpoint_depression]] which asks
whether the forecast's DEPRESSION BIAS should be corrected. This script asks
a different question: does the OBSERVED depression at valid_time V predict
the |err| of the cloud forecast at V?

Mechanism: high depression = dry air = clouds sparse and easy to forecast.
Low depression = moist air near saturation = cloud fields near-saturation,
harder to forecast.

Smoke found: cl/cm |err| at Q5 depression is 0.34x / 0.49x of Q1 depression.
Big effect, novel axis. Live signal — we already have T and dp obs.

Design: observed_dep = obs_t - obs_dp joined at valid_time.  Quintile edges
fit on train (first 38d), held-out on last 7d.

Gate: bottom(Q1)/top(Q5) ratio >= 1.8 AND monotone falling on TEST.
Direction: high depression -> lower |err|.
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
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_depression_cloud_confidence_stage0.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_depression_cloud_confidence_stage0.json")

WINDOW_DAYS = 45
HELD_OUT_DAYS = 7
LEAD_LO = 4
LEAD_HI = 24
MIN_N_TRAIN = 1000
MIN_N_TEST_BIN = 30
GATE_RATIO = 1.8   # bottom / top on TEST (harder for moist)
TARGET_FIELDS = ["cc", "cl", "cm", "ch"]


def _quintile_edges(sorted_vals):
    n = len(sorted_vals)
    return [sorted_vals[int(n * p)] for p in (0.20, 0.40, 0.60, 0.80)]


def _bin(x, edges):
    for i, e in enumerate(edges):
        if x < e:
            return i
    return len(edges)


def main():
    WIN = rolling_windows(recent_days=WINDOW_DAYS, prior_days=0)
    lo_win, hi_win = WIN.A_LO, WIN.A_HI

    # Pass 1: build obs_t and obs_dp lookup per valid_time
    obs_t = {}
    obs_dp = {}
    cloud_rows = []  # (field, vt, err)
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
            if f == "t":
                ob = r.get("observed")
                if ob is not None and vt not in obs_t:
                    obs_t[vt] = float(ob)
            elif f == "dp":
                ob = r.get("observed")
                if ob is not None and vt not in obs_dp:
                    obs_dp[vt] = float(ob)
            elif f in TARGET_FIELDS:
                lh = r.get("lead_h")
                err = prod_error(r)
                if lh is None or not (LEAD_LO <= lh <= LEAD_HI) or err is None:
                    continue
                cloud_rows.append((f, vt, abs(float(err))))

    if not cloud_rows:
        print("VERDICT: INSUFFICIENT DATA — no cloud rows in window.")
        return 0

    # Compute depression per vt
    dep = {vt: obs_t[vt] - obs_dp[vt] for vt in obs_t.keys() & obs_dp.keys()}
    max_vt = max(vt for _, vt, _ in cloud_rows)
    max_date = datetime.strptime(max_vt[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    per_field_train = defaultdict(list)  # field -> [(dep, |err|)]
    per_field_test = defaultdict(list)
    n_dropped_no_dep = 0
    for f, vt, err in cloud_rows:
        d = dep.get(vt)
        if d is None:
            n_dropped_no_dep += 1
            continue
        (per_field_test if vt[:10] >= test_start else per_field_train)[f].append((d, err))

    results = []
    for f in TARGET_FIELDS:
        tr = per_field_train.get(f, [])
        te = per_field_test.get(f, [])
        if len(tr) < MIN_N_TRAIN:
            results.append({"field": f, "status": "THIN_TRAIN",
                            "n_train": len(tr), "n_test": len(te)})
            continue
        if len(te) < 5 * MIN_N_TEST_BIN:
            results.append({"field": f, "status": "THIN_TEST",
                            "n_train": len(tr), "n_test": len(te)})
            continue
        edges = _quintile_edges(sorted(d for d, _ in tr))
        train_bins = defaultdict(list)
        test_bins = defaultdict(list)
        for d, e in tr:
            train_bins[_bin(d, edges)].append(e)
        for d, e in te:
            test_bins[_bin(d, edges)].append(e)

        per_bin = []
        for i in range(5):
            tri = train_bins.get(i, [])
            tei = test_bins.get(i, [])
            per_bin.append({
                "bin": i,
                "n_train": len(tri),
                "train_mean_abs_err": round(mean(tri), 4) if tri else None,
                "n_test": len(tei),
                "test_mean_abs_err": round(mean(tei), 4) if tei else None,
            })
        te_means = [b["test_mean_abs_err"] for b in per_bin]
        n_ok = all(b["n_test"] >= MIN_N_TEST_BIN for b in per_bin)
        if not (n_ok and all(m is not None for m in te_means)):
            results.append({"field": f, "status": "THIN_TEST_BIN", "per_bin": per_bin,
                            "edges": [round(e, 3) for e in edges]})
            continue

        # Direction: expect Q1 (low dep, moist) > Q5 (high dep, dry). Ratio Q1/Q5.
        ratio = te_means[0] / te_means[4] if te_means[4] > 0 else 0
        falls = sum(1 for i in range(4) if te_means[i + 1] < te_means[i])
        hit = ratio >= GATE_RATIO and falls >= 3

        results.append({
            "field": f,
            "status": "SCORED",
            "edges": [round(e, 3) for e in edges],
            "per_bin": per_bin,
            "test_ratio_moist_over_dry": round(ratio, 3),
            "monotone_falls": falls,
            "verdict": "STAGE0 HIT" if hit else "no",
        })

    lines = []
    lines.append("=" * 96)
    lines.append("STAGE 0 — observed T-Td depression as a confidence axis for cloud fields")
    lines.append("=" * 96)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Held-out: last {HELD_OUT_DAYS}d.  "
                 f"Lead band: {LEAD_LO}-{LEAD_HI}h.")
    lines.append(f"Fields: cc, cl, cm, ch.  Gate: Q1(moist)/Q5(dry) |err| ratio >= "
                 f"{GATE_RATIO:.1f} AND monotone falling >=3/4 on TEST.")
    lines.append(f"Test starts: {test_start}.  Scanned {n_scanned:,} pair-log rows.")
    lines.append(f"Dropped {n_dropped_no_dep:,} cloud rows lacking t or dp obs at same vt.")
    lines.append("")
    lines.append(f"{'field':>6}  {'test |err| by dep quintile (moist Q1 .. dry Q5)':<50}  "
                 f"{'ratio':>6}  {'falls':>5}  verdict")
    lines.append("-" * 100)
    hits = []
    for r in results:
        f = r["field"]
        if r["status"] != "SCORED":
            lines.append(f"{f:>6}  {r['status']:<50}  {'-':>6}  {'-':>5}  -")
            continue
        pb = "  ".join(f"{(b['test_mean_abs_err'] or 0):>7.3f}" for b in r["per_bin"])
        lines.append(f"{f:>6}  {pb:<50}  {r['test_ratio_moist_over_dry']:>6.2f}  "
                     f"{r['monotone_falls']:>3}/4  {r['verdict']}")
        if r["verdict"] == "STAGE0 HIT":
            hits.append((f, r["test_ratio_moist_over_dry"]))
    lines.append("")
    if hits:
        hit_str = ", ".join(f"{f}({r:.2f}x)" for f, r in hits)
        lines.append(f"VERDICT: STAGE 0 HIT — {len(hits)} field(s): {hit_str}.")
        lines.append("Warrants Stage 1: orthogonality vs cluster_spread_q AND vs "
                     "[[project_cross_run_spread_c1_axis]].")
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

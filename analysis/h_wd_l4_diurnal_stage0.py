"""Stage 0 — wd L4 diurnal residual per hour-of-day (0-23 local).

Circular analogue of L4-style diurnal-bias correction, narrowed to hour-of-day
bucketing of (obs − L2_wd) residuals.

Question: does a per-hour circular-mean residual (obs − L2_wd), applied on top
of L2 held-out, reduce wd MAE by ≥ 1% for any hour bucket?

Baseline: forecast_l2 (per [[measure-against-live-stack-baseline]]).
Buckets:  valid_time local hour 0-23.
Signal:   circular mean of angular residual in the bucket over training window.
Apply:    corrected_fc = (fc_l2 + mean_residual) mod 360, held-out.
MAE:      mean |circular_diff(corrected, obs)|.

Gates:
  MIN_N_BUCKET = 30          — need at least this many training pairs per hour
  MIN_TEST_PER_BUCKET = 20   — held-out sample per hour
  STAGE0_HIT_PCT = 1.0       — ≥ 1% MAE improvement on any hour

Because wd L2 shipped 07-20 v0.6.368/368a, `forecast_l2` for wd only exists in
post-ship pairs. Until ~07-27 most buckets will report INSUFFICIENT DATA.
Script lands now so the verdict is one command away once the pair log deepens.

Run:
    python3 analysis/h_wd_l4_diurnal_stage0.py

Output:
    analysis/output/h_wd_l4_diurnal_stage0.txt
    analysis/output/h_wd_l4_diurnal_stage0.json
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_wd_l4_diurnal_stage0.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_wd_l4_diurnal_stage0.json")

MIN_N_BUCKET = 30
MIN_TEST_PER_BUCKET = 20
STAGE0_HIT_PCT = 1.0
HELD_OUT_DAYS = 7


def parse_local_hour(vt):
    if not vt or len(vt) < 13:
        return None
    try:
        return int(vt[11:13])
    except ValueError:
        return None


def signed_circ_diff(a, b):
    return ((float(a) - float(b) + 180.0) % 360.0) - 180.0


def abs_circ_diff(a, b):
    d = abs(float(a) - float(b)) % 360.0
    return d if d <= 180.0 else 360.0 - d


def circular_mean_deg(residuals_deg):
    if not residuals_deg:
        return 0.0
    sx = sum(math.sin(math.radians(r)) for r in residuals_deg) / len(residuals_deg)
    cx = sum(math.cos(math.radians(r)) for r in residuals_deg) / len(residuals_deg)
    if sx == 0.0 and cx == 0.0:
        return 0.0
    return math.degrees(math.atan2(sx, cx))


def compute():
    rows = []  # (obs_time, hour, fc_l2, obs)
    n_scanned = n_wd = n_kept = 0
    max_obs_time = ""
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            n_scanned += 1
            if r.get("field") != "wd":
                continue
            n_wd += 1
            fc_l2 = r.get("forecast_l2")
            obs = r.get("observed")
            vt = r.get("valid_time")
            if fc_l2 is None or obs is None or vt is None:
                continue
            hour = parse_local_hour(vt)
            if hour is None:
                continue
            obs_time = r.get("obs_time") or ""
            rows.append((obs_time, hour, float(fc_l2), float(obs)))
            if obs_time > max_obs_time:
                max_obs_time = obs_time
            n_kept += 1

    if not rows or len(max_obs_time) < 10:
        return {}, n_scanned, n_wd, n_kept, None, None

    max_date = datetime.strptime(max_obs_time[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    train = defaultdict(list)  # hour -> [signed residual]
    test = defaultdict(list)   # hour -> [(fc_l2, obs)]
    for obs_time, hour, fc_l2, obs in rows:
        if obs_time[:10] < test_start:
            train[hour].append(signed_circ_diff(obs, fc_l2))
        else:
            test[hour].append((fc_l2, obs))

    buckets = {}
    for hour in range(24):
        residuals = train.get(hour, [])
        test_rows = test.get(hour, [])
        if len(residuals) < MIN_N_BUCKET:
            buckets[hour] = {"status": "THIN_TRAIN", "n_train": len(residuals),
                             "n_test": len(test_rows)}
            continue
        mu = circular_mean_deg(residuals)
        if len(test_rows) < MIN_TEST_PER_BUCKET:
            buckets[hour] = {"status": "THIN_TEST", "n_train": len(residuals),
                             "n_test": len(test_rows),
                             "mean_residual_deg": round(mu, 2)}
            continue
        mae_l2 = sum(abs_circ_diff(fc, ob) for fc, ob in test_rows) / len(test_rows)
        corrected = [((fc + mu) % 360.0, ob) for fc, ob in test_rows]
        mae_corr = sum(abs_circ_diff(fc, ob) for fc, ob in corrected) / len(corrected)
        pct = (mae_l2 - mae_corr) / mae_l2 * 100.0 if mae_l2 > 0 else 0.0
        buckets[hour] = {
            "status": "SCORED",
            "n_train": len(residuals),
            "n_test": len(test_rows),
            "mean_residual_deg": round(mu, 2),
            "mae_l2": round(mae_l2, 2),
            "mae_corr": round(mae_corr, 2),
            "mae_improve_pct": round(pct, 2),
        }

    return buckets, n_scanned, n_wd, n_kept, test_start, max_obs_time


def emit(buckets, n_scanned, n_wd, n_kept, test_start, max_obs_time):
    lines = []
    lines.append("=" * 88)
    lines.append("STAGE 0 — wd L4 diurnal residual per hour-of-day (local)   [circular]")
    lines.append("=" * 88)
    lines.append(f"Scanned {n_scanned:,} rows; {n_wd:,} were wd; {n_kept:,} had forecast_l2 + obs + valid_time.")
    lines.append(f"Baseline: forecast_l2 (wd L2 shipped 07-20 v0.6.368/368a).")
    if test_start:
        lines.append(f"Train: obs_date <  {test_start}    Test: obs_date >= {test_start} (max {max_obs_time[:10]}).")
    lines.append(f"Gates: MIN_N_BUCKET={MIN_N_BUCKET} (train), MIN_TEST_PER_BUCKET={MIN_TEST_PER_BUCKET}, "
                 f"STAGE0_HIT ≥ +{STAGE0_HIT_PCT:.1f}% MAE.")
    lines.append("")
    if n_kept == 0:
        lines.append("Verdict: INSUFFICIENT DATA — no wd pairs carry forecast_l2 yet.")
        lines.append("Re-run after wd L2 has been shipping for ≥ 7 days (~07-27).")
        return "\n".join(lines)

    scored = {h: v for h, v in buckets.items() if v.get("status") == "SCORED"}
    thin_train = sum(1 for v in buckets.values() if v.get("status") == "THIN_TRAIN")
    thin_test = sum(1 for v in buckets.values() if v.get("status") == "THIN_TEST")
    lines.append(f"Buckets: {len(scored)}/24 SCORED, {thin_train} THIN_TRAIN, {thin_test} THIN_TEST.")
    lines.append("")
    if not scored:
        lines.append("Verdict: INSUFFICIENT DATA — no hour had ≥ {} train AND ≥ {} test pairs."
                     .format(MIN_N_BUCKET, MIN_TEST_PER_BUCKET))
        lines.append("Re-run once the post-L2 pair log deepens.")
        return "\n".join(lines)

    lines.append(f"{'hour':<6}{'n_train':>10}{'n_test':>8}{'μ_res°':>10}"
                 f"{'MAE_L2':>10}{'MAE_corr':>12}{'Δ MAE %':>10}")
    lines.append("-" * 68)
    hits = 0
    for h in range(24):
        d = buckets.get(h)
        if not d or d.get("status") != "SCORED":
            continue
        mark = " ★" if d["mae_improve_pct"] >= STAGE0_HIT_PCT else ""
        if d["mae_improve_pct"] >= STAGE0_HIT_PCT:
            hits += 1
        lines.append(f"{h:02d}:00 {d['n_train']:>10}{d['n_test']:>8}"
                     f"{d['mean_residual_deg']:>+10.1f}{d['mae_l2']:>10.1f}"
                     f"{d['mae_corr']:>12.1f}{d['mae_improve_pct']:>+10.2f}{mark}")
    lines.append("")
    if hits:
        lines.append(f"Verdict: STAGE 0 HIT — {hits} hour(s) show ≥ {STAGE0_HIT_PCT:.1f}% MAE improvement.")
        lines.append("Warrants circular-primitive build + Stage 1 wd L4 per [[project_wd_l3_l4_circular]].")
    else:
        lines.append(f"Verdict: NO STAGE 0 HIT — no hour crosses +{STAGE0_HIT_PCT:.1f}% MAE improvement.")
        lines.append("wd L4 diurnal signal absent above L2's circular blend; do not proceed to Stage 1.")
    return "\n".join(lines)


def main():
    buckets, n_scanned, n_wd, n_kept, test_start, max_obs_time = compute()
    text = emit(buckets, n_scanned, n_wd, n_kept, test_start, max_obs_time)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "forecast_error_log.jsonl",
        "min_n_bucket": MIN_N_BUCKET,
        "min_test_per_bucket": MIN_TEST_PER_BUCKET,
        "stage0_hit_pct": STAGE0_HIT_PCT,
        "held_out_days": HELD_OUT_DAYS,
        "n_scanned": n_scanned,
        "n_wd_rows": n_wd,
        "n_kept": n_kept,
        "test_start": test_start,
        "max_obs_time": max_obs_time,
        "buckets": {f"{h:02d}": v for h, v in buckets.items()},
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())

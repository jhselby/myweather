"""Marine-layer / low-cloud (cl) Stage 1 signal scan.

Hypothesis: cloud-low (`cl`) forecasts are systematically biased in NW-flow
night/evening conditions — a different atmospheric mechanism than the
existing ne-flow-morning cc bias (marine_layer_stage1.py / _stage2.py /
marine_layer_correction.py, still sandboxed).

Origin: 2026-07-09 investigation of the Stage 4 c1_stage4_mixture_check
DEGRADED verdict on cl/12-23h stable. Per-bin stratification showed the
degradation is dominated by the low-forecast bin (b1, ~90% of cell rows).
Signed error in b1 shifted calib −2.85 → recent −7.18: mean forecast held
at ~1 pp, mean observed doubled (4.0 → 8.25). The pattern concentrated in
nw_flow regime (calib MAE 0.88 → recent 8.52 with n growing 272 → 506) and
in nighttime + early morning + evening hours (0, 6, 17-20). Classic
coastal-stratus vs inland-METAR disconnect.

This script tests two candidate triggers for the same mechanism:
  A. state_obs.regime_synoptic == "nw_flow"  (classifier-based)
  B. state_obs.wind_dir in [270, 360)         (wd-only, cheaper)

For each, stratify cl residuals by trigger × hour-window and report MAE +
signed bias. If B tracks A closely we can adopt the cheaper trigger for
Stage 2 (mirrors the wd-based gate the cc marine-layer module uses).
"""

import json
import statistics
from collections import defaultdict
from datetime import datetime

from _cache import cached_path


ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"

# Trigger A: regime classification
TARGET_REGIME = "nw_flow"

# Trigger B: raw wind-direction range
NW_WD_MIN, NW_WD_MAX = 270.0, 360.0

# Hour windows to compare — night/evening triggered per today's finding,
# morning + midday as controls.
HOUR_BUCKETS = [
    ("night+eve (17-6)", lambda h: h >= 17 or h <= 6),
    ("morning (7-11)",   lambda h: 7 <= h <= 11),
    ("midday (12-16)",   lambda h: 12 <= h <= 16),
]


def hour_of(obs_time):
    try:
        return datetime.fromisoformat(obs_time[:19]).hour
    except (TypeError, ValueError):
        return None


def bucket_for(hour):
    for name, pred in HOUR_BUCKETS:
        if pred(hour):
            return name
    return "other"


def main():
    path = cached_path(ERROR_LOG_URL)
    # (trigger_kind, active, hour_bucket) -> list of signed errors
    signed = defaultdict(list)
    abs_err = defaultdict(list)
    # weekly signed bias in the trigger cell, to check stationarity
    weekly_A = defaultdict(list)
    n_total = 0
    n_cl = 0
    n_cl_stateobs = 0
    with open(path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_total += 1
            if r.get("field") != "cl":
                continue
            n_cl += 1
            st = r.get("state_obs") or {}
            regime = st.get("regime_synoptic")
            wd = st.get("wind_dir")
            if not regime and wd is None:
                continue
            n_cl_stateobs += 1
            err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
            if err is None:
                err = r.get("error")
            if err is None:
                continue
            ot = r.get("obs_time")
            h = hour_of(ot) if ot else None
            if h is None:
                continue
            hb = bucket_for(h)
            active_A = (regime == TARGET_REGIME)
            active_B = (wd is not None and NW_WD_MIN <= wd < NW_WD_MAX)
            key_A = ("A/regime", active_A, hb)
            key_B = ("B/wd270-360", active_B, hb)
            signed[key_A].append(err)
            signed[key_B].append(err)
            abs_err[key_A].append(abs(err))
            abs_err[key_B].append(abs(err))
            if active_A and hb == "night+eve (17-6)":
                # bucket by ISO week for stationarity view
                try:
                    dt = datetime.fromisoformat(ot[:19])
                    iso = dt.isocalendar()
                    week_key = f"{iso.year}-W{iso.week:02d}"
                    weekly_A[week_key].append(err)
                except (TypeError, ValueError):
                    pass

    print(f"Rows: total={n_total:,}  cl={n_cl:,}  cl w/ state_obs={n_cl_stateobs:,}")
    print()
    print(f"{'trigger':<14} {'active':<7} {'hour bucket':<20} "
          f"{'n':>8} {'MAE':>8} {'signed_bias':>13}")
    print("-" * 80)
    for kind in ("A/regime", "B/wd270-360"):
        for active in (True, False):
            for hb, _ in HOUR_BUCKETS:
                k = (kind, active, hb)
                sxs = signed.get(k, [])
                axs = abs_err.get(k, [])
                if not sxs:
                    continue
                mae = statistics.mean(axs)
                sb = statistics.mean(sxs)
                marker = " ★" if active and abs(sb) >= 3.0 and len(sxs) >= 200 else ""
                print(f"{kind:<14} {str(active):<7} {hb:<20} "
                      f"{len(sxs):>8} {mae:>8.2f} {sb:>+13.2f}{marker}")
        print()

    print("Trigger A (regime=nw_flow) × night+eve — weekly signed bias:")
    print(f"  {'ISO week':<12} {'n':>7} {'mean':>8} {'median':>8}")
    for w in sorted(weekly_A):
        xs = weekly_A[w]
        m = statistics.mean(xs)
        md = statistics.median(xs)
        marker = " ★" if abs(m) >= 3.0 and len(xs) >= 100 else ""
        print(f"  {w:<12} {len(xs):>7} {m:>+8.2f} {md:>+8.2f}{marker}")

    print()
    print("Reading:")
    print("  signed_bias = forecast - observed. Negative = model UNDER-forecasts.")
    print("  Origin finding was signed_bias ≈ -7 in the low-forecast b1 bin of")
    print("  cl/12-23h stable. Here we test the full-cell trigger, not just b1.")


if __name__ == "__main__":
    main()

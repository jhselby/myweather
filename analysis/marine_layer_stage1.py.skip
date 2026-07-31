"""Marine-layer / coastal-cloud Stage 1 signal scan.

Hypothesis: cloud-cover forecasts are systematically biased in onshore-flow
(NE) morning conditions. Stratify pair-log residuals by wind-direction band
and hour-of-day, look for a bias not visible at the global level.

Stage 1 finding (2026-06-21): NE-flow morning (wd 45-105, hour 4-9 EDT)
shows a consistent +25pp over-call of cloud cover (mean +28.1, median +25.0,
n=3,119). Other strata sit near zero bias. This bias is invisible to the L3
lead-decay and L4 hour-of-day walk-forward validators because it lives in
~3% of all conditions and averages out at the global level.

If signal holds on a held-out cutoff, this becomes a Stage-2 candidate for a
regime-conditional bias correction (sibling to L5 solar — see hypothesis
backlog Group B "marine-layer / harbor inversion").
"""

import json
import statistics
from collections import defaultdict
from datetime import datetime

from _cache import cached_path

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"

NE_WD_MIN, NE_WD_MAX = 45, 105
MORN_HOUR_MIN, MORN_HOUR_MAX = 4, 9
FIELDS = ["t", "h", "dp", "cc", "cl"]


def is_ne_flow(wd):
    return wd is not None and NE_WD_MIN <= wd <= NE_WD_MAX


def is_morning(obs_time):
    return MORN_HOUR_MIN <= datetime.fromisoformat(obs_time).hour <= MORN_HOUR_MAX


def main():
    path = cached_path(ERROR_LOG_URL)
    bins = defaultdict(lambda: defaultdict(list))
    overall = defaultdict(list)
    signed_cc = {"ne_morn": [], "other": []}
    n_with_state = 0
    n_total = 0
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            n_total += 1
            st = r.get("state_obs")
            if not st:
                continue
            n_with_state += 1
            fld = r["field"]
            if fld not in FIELDS:
                continue
            err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error")
            if err is None:
                continue
            ne = is_ne_flow(st.get("wind_dir"))
            morn = is_morning(r["obs_time"])
            bins[(ne, morn)][fld].append(abs(err))
            overall[fld].append(abs(err))
            if fld == "cc":
                (signed_cc["ne_morn"] if (ne and morn) else signed_cc["other"]).append(err)

    print(f"Rows total: {n_total:,}  with state_obs: {n_with_state:,}  ({100*n_with_state/n_total:.1f}%)\n")
    print(f"{'field':<5} {'baseline':>10} {'NE+morn':>14} {'NE+other':>14} {'other+morn':>14} {'other+other':>14}")
    print("-" * 78)

    def cell(ne, mo, fld):
        xs = bins[(ne, mo)][fld]
        return f"{statistics.mean(xs):.2f} (n={len(xs)})" if xs else "n/a"

    for fld in FIELDS:
        bl = statistics.mean(overall[fld]) if overall[fld] else 0
        print(f"{fld:<5} {bl:>10.2f} "
              f"{cell(True, True, fld):>14} {cell(True, False, fld):>14} "
              f"{cell(False, True, fld):>14} {cell(False, False, fld):>14}")

    print("\nSigned cc bias (error = forecast - observed; +ve = over-call):")
    for k, xs in signed_cc.items():
        print(f"  {k:<10}  n={len(xs):>7,}  mean={statistics.mean(xs):+.2f}  median={statistics.median(xs):+.2f}")


if __name__ == "__main__":
    main()

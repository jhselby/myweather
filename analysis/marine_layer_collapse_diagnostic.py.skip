"""Marine-layer MLC in-bin bias — collapse discriminator.

marine_layer_anomaly.py reads decay_fit's own per-tick watch series, which
aggregates over a growing pair set. That series went +37 → +4 between
06-22 and 07-16 (COLLAPSE verdict). Two hypotheses:

  (a) HRRR-anomaly-coincident: something in HRRR shifted on/around 07-04
      for the NE-flow-morning cc stratum specifically. If true, MLC re-arms
      once the anomaly clears.
  (b) Seasonal shift: July marine layer weakens, obs cloud in NE+morn
      drops, closing the gap with forecasts. If true, MLC needs redesign
      — the trained bias doesn't apply to July.

This script recomputes the in-bin signed cc bias FRESH per OBS DAY (not
cumulative), so a step-change on 07-07 is visible in the daily series
directly instead of diluted by the growing fitter window. Also computes
pre/post-07-04 means (HRRR anomaly split) for both in-bin and out-of-bin
(control).

Bin definition matches marine_layer_stage1.py / marine_layer_correction.py:
  state_obs.wind_dir ∈ [45, 105], obs hour ∈ [4, 9] EDT, field = cc.

Run:
    python3 analysis/marine_layer_collapse_diagnostic.py

Output:
    analysis/output/marine_layer_collapse_diagnostic.txt
"""
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "marine_layer_collapse_diagnostic.txt")

NE_WD_MIN, NE_WD_MAX = 45, 105
MORN_HOUR_MIN, MORN_HOUR_MAX = 4, 9
SPLIT_DATE = "2026-07-04"  # HRRR anomaly onset per anomaly_detector notes


def is_in_bin(wd, hour):
    return (
        wd is not None
        and NE_WD_MIN <= wd <= NE_WD_MAX
        and MORN_HOUR_MIN <= hour <= MORN_HOUR_MAX
    )


def main():
    path = cached_path(ERROR_LOG_URL)
    # per obs day → list of signed cc errors, split by in-bin / out-bin
    in_by_day = defaultdict(list)
    out_by_day = defaultdict(list)

    n_total = n_cc = 0
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            n_total += 1
            if r.get("field") != "cc":
                continue
            n_cc += 1
            err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error")
            if err is None:
                continue
            st = r.get("state_obs") or {}
            obs_time = r.get("obs_time")
            if not obs_time:
                continue
            try:
                ot = datetime.fromisoformat(obs_time)
            except ValueError:
                continue
            in_bin = is_in_bin(st.get("wind_dir"), ot.hour)
            day = ot.date().isoformat()
            (in_by_day if in_bin else out_by_day)[day].append(err)

    all_days = sorted(set(in_by_day) | set(out_by_day))
    lines = []

    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 92)
    emit("MLC COLLAPSE DIAGNOSTIC — fresh per-day in-bin cc bias (independent of fitter aggregation)")
    emit("=" * 92)
    emit(f"Pair log rows: {n_total:,}   cc rows: {n_cc:,}")
    emit(f"Bin: state_obs.wind_dir ∈ [{NE_WD_MIN},{NE_WD_MAX}], obs hour ∈ [{MORN_HOUR_MIN},{MORN_HOUR_MAX}]")
    emit(f"Split date (HRRR anomaly onset): {SPLIT_DATE}")
    emit("")

    # Daily trajectory (only days with ≥5 in-bin pairs, to avoid noise)
    emit(f"{'obs_day':<12} {'in_n':>6} {'in_bias':>9} {'in_mae':>8}  |  {'out_n':>6} {'out_bias':>10}")
    emit("-" * 92)
    for day in all_days:
        i = in_by_day.get(day, [])
        o = out_by_day.get(day, [])
        if len(i) < 5:
            continue
        in_bias = statistics.mean(i)
        in_mae = statistics.mean(abs(x) for x in i)
        out_bias = statistics.mean(o) if o else 0.0
        emit(f"{day:<12} {len(i):>6d} {in_bias:>+9.2f} {in_mae:>8.2f}  |  {len(o):>6d} {out_bias:>+10.2f}")

    emit("")
    emit("=" * 92)
    emit(f"WINDOW SPLIT — pre-{SPLIT_DATE} vs {SPLIT_DATE}-onward")
    emit("=" * 92)

    def bucket(day_map, cutoff):
        pre, post = [], []
        for day, errs in day_map.items():
            (pre if day < cutoff else post).append(errs)
        pre_flat = [e for xs in pre for e in xs]
        post_flat = [e for xs in post for e in xs]
        return pre_flat, post_flat

    in_pre, in_post = bucket(in_by_day, SPLIT_DATE)
    out_pre, out_post = bucket(out_by_day, SPLIT_DATE)

    def line(label, pre, post):
        if not pre or not post:
            emit(f"  {label:<24} insufficient data (pre={len(pre)}, post={len(post)})")
            return None
        pm = statistics.mean(pre)
        qm = statistics.mean(post)
        emit(f"  {label:<24} pre  n={len(pre):>6,}  mean={pm:+7.2f}   "
             f"post n={len(post):>6,}  mean={qm:+7.2f}   Δ={qm-pm:+7.2f}")
        return qm - pm

    emit("In-bin signed cc bias (NE+morn — the MLC target stratum):")
    d_in = line("cc / NE+morn", in_pre, in_post)
    emit("")
    emit("Out-of-bin signed cc bias (rest of cc — control):")
    d_out = line("cc / other", out_pre, out_post)

    emit("")
    emit("=" * 92)
    emit("VERDICT")
    emit("=" * 92)

    if d_in is None or d_out is None:
        emit("  THIN — not enough data on one side of the split.")
    else:
        shift_in = abs(d_in)
        shift_out = abs(d_out)
        ratio = shift_in / shift_out if shift_out > 0.01 else float("inf")

        # Find biggest day-over-day step-down in the daily in-bin series
        daily = [(d, statistics.mean(in_by_day[d])) for d in sorted(in_by_day)
                 if len(in_by_day[d]) >= 5]
        break_day = None
        break_step = 0.0
        for i in range(1, len(daily)):
            step = daily[i][1] - daily[i-1][1]
            if step < break_step:
                break_step = step
                break_day = daily[i][0]

        emit(f"  in-bin Δ={d_in:+.2f}   out-of-bin Δ={d_out:+.2f}   ratio in/out={ratio:.1f}x")
        if break_day:
            emit(f"  biggest daily step-down: {break_day} ({break_step:+.2f}pp vs prior sampled day)")
        emit("")

        localized = ratio >= 3 and shift_in >= 15
        pre_hrrr = break_day is not None and break_day < SPLIT_DATE

        if localized and pre_hrrr:
            emit("  LOCALIZED + PRE-HRRR-ANOMALY")
            emit(f"    → The shift is stratum-specific ({ratio:.1f}× larger in-bin than out-of-bin)")
            emit(f"      AND the biggest daily step ({break_day}) predates the HRRR anomaly ({SPLIT_DATE}).")
            emit(f"    → Rules OUT hypothesis (a) 'HRRR-anomaly-coincident'.")
            emit(f"    → Consistent with hypothesis (b) 'seasonal marine-layer weakening'")
            emit(f"      or another stratum-local cause active before 07-04.")
            emit(f"    → Recommendation: keep MLC.ENABLED=False. Do not expect re-arming when")
            emit(f"      the cm HRRR anomaly clears — this is a different event.")
        elif localized and not pre_hrrr:
            emit("  LOCALIZED + HRRR-COINCIDENT")
            emit(f"    → Stratum-specific ({ratio:.1f}×) AND biggest step ({break_day}) is on/after {SPLIT_DATE}.")
            emit(f"    → Consistent with hypothesis (a) HRRR-anomaly-coincident.")
            emit(f"    → Recommendation: MLC may re-arm once the cm HRRR anomaly clears; re-check then.")
        elif shift_in >= 15 and ratio < 3:
            emit("  GLOBAL CC SHIFT")
            emit(f"    → In-bin and out-of-bin both shifted materially (ratio {ratio:.1f}×).")
            emit(f"    → Not stratum-specific — this is a cc-wide change. MLC calibration was")
            emit(f"      trained on a different cc distribution.")
        elif shift_in < 5:
            emit("  NO REAL SHIFT")
            emit(f"    → Fitter watch series 'collapse' is aggregation artifact only.")
        else:
            emit(f"  MIXED — manual read required.")

    text = "\n".join(lines)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
